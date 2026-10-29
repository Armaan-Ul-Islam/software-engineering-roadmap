# Patterns: intervals and greedy

> **In one sentence:** Interval problems become a single left-to-right sweep once the intervals are sorted by start, and greedy problems are the ones where a locally best choice can be proven never to hurt the final answer, which is exactly what you must be able to argue out loud before you trust the greedy.

**Why it matters:** Calendars, booking systems, rate limiters, log compaction and garbage collection all merge or schedule ranges of time. Merge Intervals and Jump Game are among the most frequently asked interview problems, and the greedy family is where candidates most often produce a confident, wrong answer because they skipped the proof.

## The idea

### Intervals

**Recognising the pattern.** The input is a list of `[start, end]` pairs: meetings, bookings, ranges, segments. The question asks whether they overlap, how to merge them, how many resources run at once, or where to insert a new one.

**The template.** Sort by start. Sweep once, carrying the interval you are currently building. For each next interval, either it overlaps the current one (`next.start <= current.end`, the equality depending on whether touching counts as overlapping) and you extend `current.end`, or it does not and you emit `current` and start again from `next`. Sorting makes the sweep correct: after sorting by start, any interval that overlaps `current` is adjacent to it, so one comparison per interval is enough.

```java
Arrays.sort(intervals, Comparator.comparingInt(interval -> interval[0]));
int[] current = intervals[0];
for (int index = 1; index < intervals.length; index++) {
    int[] next = intervals[index];
    if (next[0] <= current[1]) {
        current[1] = Math.max(current[1], next[1]);
    } else {
        emit(current);
        current = next;
    }
}
emit(current);
```

**Variants.** Insert Interval: the intervals are already sorted and disjoint, so walk past the ones that end before the new one starts, merge every one that overlaps into the new interval, append the rest. Meeting Rooms: sort, then check that no interval starts before the previous one ends. Meeting Rooms II (how many rooms?): sort by start and keep a min-heap of end times; before placing a meeting, free the room with the earliest end if it has ended. The heap size after the sweep is the answer. Non-overlapping Intervals (minimum removals): sort by *end* and keep each interval whose start is at or after the last kept end, a greedy choice.

**Complexity.** O(n log n) for the sort, O(n) for the sweep, O(n) extra space for the output or the heap.

### Greedy

**Recognising the pattern.** "Minimum number of", "can you reach", "maximum you can collect", on a sequence where a decision at each step does not need to be revisited. The signal that greedy might apply is that the problem has an obvious locally best move (extend the reach as far as possible, take the earliest finishing interval, do the most frequent task first) and no "either/or" that depends on later input. If you find yourself wanting to try both branches, it is dynamic programming (items 5.3 and 5.4), not greedy.

**The exchange argument.** Greedy is correct when you can show: take any optimal solution, and if it does not start with the greedy choice, swap the greedy choice in; the result is still feasible and no worse. Repeating the swap turns the optimal solution into the greedy one without losing anything. For Jump Game the argument is immediate: if some position is reachable, every position before it is reachable too, so tracking only the farthest reachable index loses nothing. In an interview, say the exchange argument in one or two sentences before you code. If you cannot say it, do not trust the greedy.

**Three greedy shapes.**

1. **Farthest reach.** Jump Game: sweep left to right, maintain `farthestReachable`; if the current index is beyond it, you are stuck. Jump Game II counts the number of times the reach boundary is crossed.
2. **Reset on negative prefix.** Gas Station: if the total surplus is non-negative, a start exists; sweep once, and whenever the running surplus since the candidate start goes negative, the candidate start moves to the next station, because no station inside the failed stretch can do better.
3. **Most frequent first.** Task Scheduler: the task with the highest count `maximumCount` forces at least `(maximumCount - 1) * (cooldown + 1) + numberOfTasksWithMaximumCount` slots; the answer is the larger of that and the total task count. Scheduling the most frequent tasks first fills the forced gaps.

**Complexity.** All three are O(n) time and O(1) extra space, which is often the hint that the interviewer expects greedy rather than DP.

## Example: Merge Intervals (56)

Return the intervals with every overlapping group merged.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public final class MergeIntervals {

    public int[][] merge(int[][] intervals) {
        Arrays.sort(intervals, Comparator.comparingInt(interval -> interval[0]));
        List<int[]> merged = new ArrayList<>();
        int[] current = intervals[0];
        for (int index = 1; index < intervals.length; index++) {
            int[] next = intervals[index];
            if (next[0] <= current[1]) {
                current[1] = Math.max(current[1], next[1]);
            } else {
                merged.add(current);
                current = next;
            }
        }
        merged.add(current);
        return merged.toArray(new int[0][]);
    }

    public static void main(String[] arguments) {
        MergeIntervals solver = new MergeIntervals();
        System.out.println(Arrays.deepToString(solver.merge(new int[][] {{1, 3}, {2, 6}, {8, 10}, {15, 18}})));
        System.out.println(Arrays.deepToString(solver.merge(new int[][] {{1, 4}, {4, 5}})));
        System.out.println(Arrays.deepToString(solver.merge(new int[][] {{1, 4}, {2, 3}})));
    }
}
```

```text
$ java MergeIntervals.java
[[1, 6], [8, 10], [15, 18]]
[[1, 5]]
[[1, 4]]
```

The third case is the one people get wrong: `[2, 3]` lies entirely inside `[1, 4]`, so `current[1]` must be `max(4, 3)`, not simply `next[1]`. O(n log n) time, O(n) space for the result.

## Example: Meeting Rooms II, intervals with a heap

How many rooms are needed so that no two overlapping meetings share one?

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.PriorityQueue;

public final class MeetingRoomsTwo {

    public int minMeetingRooms(int[][] intervals) {
        Arrays.sort(intervals, Comparator.comparingInt(interval -> interval[0]));
        PriorityQueue<Integer> endTimesOfOccupiedRooms = new PriorityQueue<>();
        for (int[] meeting : intervals) {
            if (!endTimesOfOccupiedRooms.isEmpty() && endTimesOfOccupiedRooms.peek() <= meeting[0]) {
                endTimesOfOccupiedRooms.poll();
            }
            endTimesOfOccupiedRooms.offer(meeting[1]);
        }
        return endTimesOfOccupiedRooms.size();
    }

    public static void main(String[] arguments) {
        MeetingRoomsTwo solver = new MeetingRoomsTwo();
        System.out.println(solver.minMeetingRooms(new int[][] {{0, 30}, {5, 10}, {15, 20}}));
        System.out.println(solver.minMeetingRooms(new int[][] {{7, 10}, {2, 4}}));
        System.out.println(solver.minMeetingRooms(new int[][] {{1, 5}, {5, 10}, {2, 7}, {3, 4}}));
    }
}
```

```text
$ java MeetingRoomsTwo.java
2
1
3
```

Each meeting is pushed once and polled at most once, so O(n log n) time and O(n) space. Polling at most one room per meeting is enough because one meeting can reuse only one room; the heap never needs to shrink by more than one per step for the size to be correct.

## Example: Jump Game (55) and Gas Station (134), greedy

```java
public final class JumpGame {

    public boolean canJump(int[] maximumJumps) {
        int farthestReachable = 0;
        for (int position = 0; position < maximumJumps.length; position++) {
            if (position > farthestReachable) {
                return false;
            }
            farthestReachable = Math.max(farthestReachable, position + maximumJumps[position]);
        }
        return true;
    }

    public int canCompleteCircuit(int[] gas, int[] cost) {
        int totalSurplus = 0;
        int surplusSinceCandidate = 0;
        int candidateStart = 0;
        for (int station = 0; station < gas.length; station++) {
            int surplus = gas[station] - cost[station];
            totalSurplus += surplus;
            surplusSinceCandidate += surplus;
            if (surplusSinceCandidate < 0) {
                candidateStart = station + 1;
                surplusSinceCandidate = 0;
            }
        }
        return totalSurplus >= 0 ? candidateStart : -1;
    }

    public static void main(String[] arguments) {
        JumpGame solver = new JumpGame();
        System.out.println(solver.canJump(new int[] {2, 3, 1, 1, 4}));
        System.out.println(solver.canJump(new int[] {3, 2, 1, 0, 4}));
        System.out.println(solver.canCompleteCircuit(new int[] {1, 2, 3, 4, 5}, new int[] {3, 4, 5, 1, 2}));
        System.out.println(solver.canCompleteCircuit(new int[] {2, 3, 4}, new int[] {3, 4, 3}));
    }
}
```

```text
$ java JumpGame.java
true
false
3
-1
```

In the second Jump Game input, position 3 has a jump of 0 and nothing before it reaches past it, so `farthestReachable` stays at 3 and position 4 is never reached. In Gas Station the exchange argument is: if starting at station `s` fails at station `f`, then every station strictly between `s` and `f` also fails at `f` (it starts with less fuel than the run from `s` had at that point), so the next candidate is `f + 1`. Both run in O(n) time and O(1) space.

## Pitfalls

- Not sorting, or sorting by end when the sweep assumes start order. The symptom is a merge that works on the example and fails on `{{2, 6}, {1, 3}}`.
- Using `<` instead of `<=` for the overlap test (or the reverse). Decide whether `[1, 4]` and `[4, 5]` overlap from the problem statement and say it aloud; Merge Intervals treats them as overlapping, Meeting Rooms treats a meeting ending at 10 and one starting at 10 as compatible.
- Setting `current[1] = next[1]` instead of the maximum. Fully contained intervals then shrink the merged range.
- Sorting a `List<int[]>` or `int[][]` with a comparator on boxed subtraction (`a[0] - b[0]`). It overflows for large values; use `Integer.compare` or `Comparator.comparingInt`.
- Applying greedy to a problem that needs DP. Coin Change with coins `{1, 3, 4}` and amount 6 is the standard counter-example: greedy takes 4 + 1 + 1, the optimum is 3 + 3. If no exchange argument comes to mind in a minute, switch to DP.
- Jump Game as a BFS or DP. It is correct but O(n²) or O(n · maxJump); the interviewer is waiting for the O(n) sweep.
- Gas Station by trying every start. O(n²) and the time limit. The single-pass reset only works because the total surplus check is done separately.
- Task Scheduler by simulation with a heap. It works and is acceptable, but the closed formula is O(n) and shows you understood why the most frequent task dictates the answer.

## Check yourself

1. Why does sorting by start make a single sweep sufficient for Merge Intervals? Give an input where sorting by end instead breaks the sweep.
2. In Meeting Rooms II, why is polling at most one end time per meeting enough, and what would go wrong if you polled every ended meeting but then forgot to push the new one?
3. State the exchange argument for Non-overlapping Intervals (keep the interval that ends earliest). Why does "keep the one that starts earliest" fail?
4. Gas Station: a colleague claims the answer can be found by starting at the station with the largest `gas - cost`. Construct an input where that is wrong and explain which invariant the single-pass reset relies on instead.

## Go deeper

- [Tech Interview Handbook: Interval cheatsheet](https://www.techinterviewhandbook.org/algorithms/interval/) · the sort-and-sweep template, the touching-endpoint question and the problems to practise.
- [Tech Interview Handbook: Coding interview techniques](https://www.techinterviewhandbook.org/coding-interview-techniques/) · how to recognise greedy and when to distrust it.
- [NeetCode roadmap](https://neetcode.io/roadmap) · the Intervals and Greedy nodes, each with a video solution per problem.

---

Part of [DSA & Interviews](../README.md) · items 2.6, 5.5
