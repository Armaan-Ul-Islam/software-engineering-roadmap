# Patterns: hashing and prefix sums

> **In one sentence:** A hash map turns "have I already seen the thing that completes this one?" into an O(1) question, a prefix sum turns "sum of any range" into one subtraction, and combining the two makes "count the subarrays with sum k" a single pass.

**Why it matters:** Hashing is the most common way to remove a factor of `n` from a brute force, in interviews and in production code alike (de-duplication, grouping, in-memory joins). Prefix sums are the standard answer to range queries over data that does not change, and the counting trick behind Subarray Sum Equals K generalises to a whole family of "subarrays with a property" problems that defeat the sliding window.

## The idea

**Recognising the pattern.** "Two elements that ...", "pair", "duplicate", "anagram", "group by", "most frequent", "range sum", "contiguous subarray with sum", "count the subarrays". Also any brute force whose inner loop asks "is there an earlier element equal to X?".

**Four moves.**

1. **Frequency map.** `Map<T, Integer>` filled with `counts.merge(key, 1, Integer::sum)`; an `int[26]` when the keys are lowercase letters. Answers "how many of each", "most frequent", "do these two strings have the same letters".
2. **Complement lookup.** Scan once. For each element, compute what would complete it (`target - value`, or `prefixSum - k`) and look that up among the elements already seen; then insert the current element. Checking before inserting guarantees an element never pairs with itself, and it also means every pair is counted once, with its later element.
3. **Canonical key.** To group things that "belong together", define a function that maps all members of a group to the same key and nothing else to it. For anagrams, the sorted string (O(L log L) per word) or a 26-slot count signature (O(L)). Then `groups.computeIfAbsent(key, ignored -> new ArrayList<>()).add(word)`.
4. **Prefix sums.** `prefix[index + 1] = prefix[index] + values[index]`, with `prefix[0] = 0`. The sum of `values[left..right]` is `prefix[right + 1] - prefix[left]`, so after O(n) preparation every range sum is O(1). The counting trick: a subarray ending at `right` has sum `k` exactly when some earlier prefix equals `prefix[right + 1] - k`, so keep a map from prefix value to how often it has occurred and add that count as you go.

**Complexity.** All four are O(n) time and O(n) space for `n` elements (grouping is O(n · L) with the count key). The space is the price of the lookups; when the problem forbids extra memory, look at sorting plus two pointers instead (item 2.2).

## Example: Two Sum (1)

The complement lookup in its purest form, returning indices:

```java
Map<Integer, Integer> indexByValue = new HashMap<>();
for (int index = 0; index < numbers.length; index++) {
    Integer complementIndex = indexByValue.get(target - numbers[index]);
    if (complementIndex != null) {
        return new int[] {complementIndex, index};
    }
    indexByValue.put(numbers[index], index);
}
```

With `[3, 3]` and target 6, the check at index 1 finds the 3 stored at index 0; had the `put` come first, index 0 would have found itself.

## Example: Group Anagrams (49)

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class GroupAnagrams {

    public List<List<String>> groupAnagrams(String[] words) {
        Map<String, List<String>> groupsByKey = new HashMap<>();
        for (String word : words) {
            groupsByKey.computeIfAbsent(canonicalKey(word), ignored -> new ArrayList<>()).add(word);
        }
        return new ArrayList<>(groupsByKey.values());
    }

    private static String canonicalKey(String word) {
        int[] letterCounts = new int[26];
        for (char letter : word.toCharArray()) {
            letterCounts[letter - 'a']++;
        }
        StringBuilder key = new StringBuilder();
        for (int count : letterCounts) {
            key.append(count).append('#');
        }
        return key.toString();
    }
}
```

For `["eat", "tea", "tan", "ate", "nat", "bat"]` the keys put `eat`, `tea`, `ate` in one group, `tan`, `nat` in another and `bat` alone. The `'#'` separator matters: without it the counts `1, 11` and `11, 1` would both produce `"111"`. The alternative key, `Arrays.sort` on the `char[]` and `new String(sortedLetters)`, is shorter to write and costs O(L log L) per word; either is acceptable in an interview if you say the trade-off.

## Example: Subarray Sum Equals K (560)

```java
import java.util.HashMap;
import java.util.Map;

public final class SubarraySumEqualsK {

    public int subarraySum(int[] numbers, int targetSum) {
        Map<Integer, Integer> countByPrefixSum = new HashMap<>();
        countByPrefixSum.put(0, 1);
        int prefixSum = 0;
        int subarrayCount = 0;
        for (int number : numbers) {
            prefixSum += number;
            subarrayCount += countByPrefixSum.getOrDefault(prefixSum - targetSum, 0);
            countByPrefixSum.merge(prefixSum, 1, Integer::sum);
        }
        return subarrayCount;
    }
}
```

Trace for `numbers = [1, 2, 3, -3, 3]` and `targetSum = 3`:

| number | prefixSum | look up prefixSum - 3 | found | subarrayCount | map after |
|---|---|---|---|---|---|
| start | 0 | | | 0 | {0: 1} |
| 1 | 1 | -2 | 0 | 0 | {0: 1, 1: 1} |
| 2 | 3 | 0 | 1 | 1 | {0: 1, 1: 1, 3: 1} |
| 3 | 6 | 3 | 1 | 2 | {0: 1, 1: 1, 3: 1, 6: 1} |
| -3 | 3 | 0 | 1 | 3 | {0: 1, 1: 1, 3: 2, 6: 1} |
| 3 | 6 | 3 | 2 | 5 | {0: 1, 1: 1, 3: 2, 6: 2} |

The five subarrays are `[1, 2]`, `[3]`, `[1, 2, 3, -3]`, `[3, -3, 3]` and the final `[3]`. The seed `{0: 1}` represents the empty prefix and is what lets a subarray that starts at index 0 be counted. A sliding window cannot solve this input: after `[1, 2, 3]` the sum is 6, but extending the window to include `-3` brings it back to 3, so "sum too big, shrink" is not a valid rule.

The same shape solves "count subarrays with sum divisible by k" (store `prefixSum % k`, normalised to be non-negative), "longest subarray with sum k" (store the first index of each prefix instead of a count) and "contiguous array with equal 0s and 1s" (treat 0 as -1 and look for sum 0).

## Pitfalls

- Forgetting the seed `{0: 1}`. The symptom is an answer that is too small by exactly the number of valid subarrays starting at index 0.
- Inserting the current element before looking up its complement. Two Sum then pairs an element with itself when `target` is twice its value; Subarray Sum counts empty subarrays when `targetSum` is 0.
- Comparing map values with `==`. `countByPrefixSum.get(a) == countByPrefixSum.get(b)` compares `Integer` references and is only reliable between -128 and 127 (item 6.2). Unbox to `int` or use `equals`.
- Arrays as keys. `int[]` uses identity `hashCode` and `equals`, so `Map<int[], ...>` never finds an equal array. Convert to a `String`, a `List<Integer>` or a record.
- A canonical key without separators, or one that depends on insertion order when it should not.
- Expecting `HashMap` to iterate in insertion order. It does not; use `LinkedHashMap` when the output order must follow the input, or sort the result.
- Prefix sums that overflow `int`. With 10^5 values of up to 10^9 each, prefixes reach 10^14; use `long` and say so.
- Mutable keys. If an object's `hashCode` changes after it is put in the map, it is lost in the wrong bucket. Keys should be immutable, which is one more reason records make good keys.
- Hashing when the alphabet is tiny. For lowercase letters, an `int[26]` is simpler and faster than a `HashMap<Character, Integer>`; reaching for the map anyway signals you did not read the constraints.

## Check yourself

1. In Subarray Sum Equals K, what does the value stored in the map mean, and why is it incremented after the lookup rather than before?
2. How would you change the solution to return the length of the longest subarray with sum `k` instead of the count? What do you store in the map, and when do you overwrite it?
3. Two valid anagram keys are the sorted string and the count signature. Give one input where the sorted-string key is the better choice and one where the signature is.
4. Why can a sliding window not solve "subarray with sum exactly k" when the array contains negative numbers, while prefix sums can?

## Go deeper

- [Tech Interview Handbook: Hash table cheatsheet](https://www.techinterviewhandbook.org/algorithms/hash-table/) · when a hash table applies and the corner cases to mention.
- [Tech Interview Handbook: Array cheatsheet](https://www.techinterviewhandbook.org/algorithms/array/) · covers prefix sums and the array techniques around them.
- [NeetCode roadmap](https://neetcode.io/roadmap) · the Arrays & Hashing node is the first in the roadmap and includes Two Sum and Group Anagrams with video solutions.

---

Part of [DSA & Interviews](../README.md) · item 2.1
