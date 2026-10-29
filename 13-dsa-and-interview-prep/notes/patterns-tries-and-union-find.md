# Patterns: tries and union-find

> **In one sentence:** A trie turns "does any stored word start with this prefix?" into a walk of `prefix.length()` steps, and union-find turns "are these two things in the same group?" into a near-constant lookup that stays fast while groups keep merging, which is why both show up whenever a problem is about prefixes or about dynamic connectivity.

**Why it matters:** Autocomplete, routing tables, IP prefix matching and spell checkers are tries. Detecting whether a new edge creates a cycle, counting clusters in a stream of "these two are the same" facts, and Kruskal's minimum spanning tree are union-find. In interviews, Implement Trie, Word Search II and Redundant Connection are the usual vehicles, and both structures are expected to be written from memory in under ten minutes.

## The idea

### Tries

**Recognising the pattern.** Many strings, and questions about prefixes: "starts with", "autocomplete", "shortest unique prefix", "is any word in the dictionary a prefix of this one", "search many words in a grid at once". A `HashSet<String>` answers exact membership; the moment a prefix question appears, you want a trie.

**The template.** A node holds a fixed array of 26 child references (for lowercase letters) or a `HashMap<Character, TrieNode>` for arbitrary alphabets, plus a boolean `endOfWord`. Insert walks the word, creating missing children, and marks the last node. Search walks the word and checks the mark; `startsWith` walks the prefix and only checks that the walk did not fall off.

```java
private static final class TrieNode {
    private final TrieNode[] children = new TrieNode[26];
    private boolean endOfWord;
}
```

**Variants.** Store a count per node to answer "how many words have this prefix". Store the whole word at the terminal node so that a grid search (Word Search II) can emit matches without rebuilding them. Delete by walking down, unmarking, and pruning nodes that have no children and no mark on the way back up.

**Complexity.** Insert, search and `startsWith` are O(length of the word), independent of how many words are stored. Space is O(total characters) in the worst case, with each node costing 26 references, so a trie of a million English words is large but still practical.

### Union-find (disjoint set union)

**Recognising the pattern.** A set of elements that start separate, a stream of "merge these two" operations, and queries of "same group?" or "how many groups?". Also: an undirected graph where you only need components or cycle detection and the edges arrive one by one, so that rebuilding an adjacency list and re-running DFS after every edge would be too slow.

**The template.** An array `parent` where each element starts as its own parent. `find` follows parents to the root; `union` links one root under the other. Two optimisations make it fast: **path compression** (while finding, point nodes closer to the root) and **union by rank** or by size (hang the shorter tree under the taller one). With both, a sequence of operations costs amortised O(α(n)) each, where α is the inverse Ackermann function, which is at most 4 for any input that fits in memory. In an interview, say "effectively constant".

```java
private int find(int node) {
    while (parent[node] != node) {
        parent[node] = parent[parent[node]];
        node = parent[node];
    }
    return node;
}
```

`union` returns `false` when the two roots are already the same. In a graph, that means the edge closes a cycle. Count the number of successful unions and subtract from the element count to get the number of components.

**Where it is the right tool and where it is not.** Union-find only merges; it cannot split. Edge removal ("what if this link fails?") is solved offline by reversing time, or with DFS instead. It also does not give paths, only membership.

## Example: Implement Trie (208)

```java
public final class Trie {

    private static final class TrieNode {
        private final TrieNode[] children = new TrieNode[26];
        private boolean endOfWord;
    }

    private final TrieNode root = new TrieNode();

    public void insert(String word) {
        TrieNode node = root;
        for (char letter : word.toCharArray()) {
            int slot = letter - 'a';
            if (node.children[slot] == null) {
                node.children[slot] = new TrieNode();
            }
            node = node.children[slot];
        }
        node.endOfWord = true;
    }

    public boolean search(String word) {
        TrieNode node = walk(word);
        return node != null && node.endOfWord;
    }

    public boolean startsWith(String prefix) {
        return walk(prefix) != null;
    }

    private TrieNode walk(String text) {
        TrieNode node = root;
        for (char letter : text.toCharArray()) {
            node = node.children[letter - 'a'];
            if (node == null) {
                return null;
            }
        }
        return node;
    }

    public static void main(String[] arguments) {
        Trie trie = new Trie();
        trie.insert("apple");
        System.out.println(trie.search("apple"));
        System.out.println(trie.search("app"));
        System.out.println(trie.startsWith("app"));
        trie.insert("app");
        System.out.println(trie.search("app"));
    }
}
```

```text
$ java Trie.java
true
false
true
true
```

The second line is the whole point of `endOfWord`: `app` is a path in the trie after inserting `apple`, but not a stored word until it is inserted itself. Every operation is O(length).

**Word Search II (212)** is the trie's signature problem: insert all dictionary words, then run one backtracking DFS from every grid cell (item 5.2) while walking the trie in step with the path; prune as soon as the current node has no child for the next letter. Without the trie, each word would need its own grid search.

## Example: Redundant Connection (684), union-find

A tree with one extra edge. Return the edge that, if removed, leaves a tree (the last such edge in input order). Process edges in order; the first edge whose two endpoints are already connected is the answer.

```java
import java.util.Arrays;

public final class RedundantConnection {

    private int[] parent;
    private int[] rank;

    public int[] findRedundantConnection(int[][] edges) {
        int nodeCount = edges.length;
        parent = new int[nodeCount + 1];
        rank = new int[nodeCount + 1];
        for (int node = 0; node <= nodeCount; node++) {
            parent[node] = node;
        }
        for (int[] edge : edges) {
            if (!union(edge[0], edge[1])) {
                return edge;
            }
        }
        return new int[0];
    }

    private int find(int node) {
        while (parent[node] != node) {
            parent[node] = parent[parent[node]];
            node = parent[node];
        }
        return node;
    }

    private boolean union(int first, int second) {
        int firstRoot = find(first);
        int secondRoot = find(second);
        if (firstRoot == secondRoot) {
            return false;
        }
        if (rank[firstRoot] < rank[secondRoot]) {
            parent[firstRoot] = secondRoot;
        } else if (rank[firstRoot] > rank[secondRoot]) {
            parent[secondRoot] = firstRoot;
        } else {
            parent[secondRoot] = firstRoot;
            rank[firstRoot]++;
        }
        return true;
    }

    public static void main(String[] arguments) {
        RedundantConnection solver = new RedundantConnection();
        System.out.println(Arrays.toString(solver.findRedundantConnection(new int[][] {{1, 2}, {1, 3}, {2, 3}})));
        System.out.println(Arrays.toString(solver.findRedundantConnection(new int[][] {{1, 2}, {2, 3}, {3, 4}, {1, 4}, {1, 5}})));
    }
}
```

```text
$ java RedundantConnection.java
[2, 3]
[1, 4]
```

Nodes are numbered from 1, so the arrays have `nodeCount + 1` slots. The `find` loop uses path halving (`parent[node] = parent[parent[node]]`), which is the one-line form of path compression and avoids recursion. O(n · α(n)) time for n edges, O(n) space.

The same `union` that returns `false` is the heart of **Kruskal's algorithm** (item 4.3): sort edges by weight, union each one, and keep the edges whose union succeeds. **Number of Connected Components in an Undirected Graph (323)** is `nodeCount` minus the number of successful unions. **Accounts Merge (721)** unions account indices that share an email, then groups by root.

## Pitfalls

- Trie `search` without checking `endOfWord`. The symptom is `search("app")` returning `true` after inserting only `"apple"`.
- A `HashMap<Character, TrieNode>` per node when the alphabet is 26 lowercase letters. It works, but it is slower and the interviewer expects the array; use the map only for Unicode or when most nodes have one or two children and memory matters.
- `letter - 'a'` on input that is not lowercase ASCII. An uppercase letter or a digit produces a negative or out-of-range index and an `ArrayIndexOutOfBoundsException`; state the alphabet assumption aloud.
- Union-find without path compression or union by rank. Correct, but a chain of unions degrades `find` to O(n) and the solution times out on large inputs. Either optimisation alone gives O(log n); both give near-constant.
- Comparing `parent[first] == parent[second]` instead of `find(first) == find(second)`. Parents are not roots; the check is wrong as soon as a tree is two levels deep.
- Off-by-one on 1-indexed nodes. Allocate `nodeCount + 1` or subtract 1 on input, and be consistent.
- Recursive `find` on a long chain before compression has happened. The first call on a degenerate chain can overflow the stack; the iterative form above cannot.
- Reaching for union-find when the problem needs paths or shortest distances. It answers "connected?", not "how". Use BFS or DFS for the path (item 4.1).

## Check yourself

1. After inserting `"car"`, `"card"` and `"care"`, draw the trie. How many nodes does it have, and which nodes carry `endOfWord`? What does `startsWith("ca")` walk, and why is its cost independent of the number of stored words?
2. Explain in two sentences why union by rank alone bounds tree height by O(log n), and why path compression on top makes repeated finds cheap even though the first find on a chain may be slow.
3. In Redundant Connection, why does processing edges in input order and returning the first failed union give the *last* redundant edge the problem asks for, rather than an arbitrary cycle edge?
4. You must answer "are x and y connected?" after each of a million edge insertions, then after each of a million edge deletions. Which half can union-find do directly, and how would you handle the other half?

## Go deeper

- [Tech Interview Handbook: Trie cheatsheet](https://www.techinterviewhandbook.org/algorithms/trie/) · the node layout, the three operations and the common follow-up questions.
- [William Fiset: Union Find](https://www.youtube.com/playlist?list=PLDV1Zeh2NRsBI1C-mR6ZhHTyfoEJWlxvq) · path compression and union by size explained with animations, then Kruskal built on top.
- [NeetCode roadmap](https://neetcode.io/roadmap) · the Tries node (208, 211, 212) and the union-find problems inside Advanced Graphs.

---

Part of [DSA & Interviews](../README.md) · items 3.4, 3.5
