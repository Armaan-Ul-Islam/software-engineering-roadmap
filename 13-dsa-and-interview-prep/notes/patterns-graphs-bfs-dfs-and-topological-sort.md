# Patterns: graphs, BFS, DFS and topological sort

> **In one sentence:** Interview graphs arrive disguised (a grid, a list of prerequisites, a node with a list of neighbours), and once you see the graph, four tools solve nearly everything: BFS for shortest paths in unweighted graphs and for anything that spreads in rounds, DFS for components and reachability, a visited set so cycles do not loop forever, and Kahn's algorithm for ordering under dependencies and detecting cycles.

**Why it matters:** Dependency resolution (build order, bean creation order, migration ordering), reachability and blast-radius analysis are graph problems you will meet at work. In interviews, Number of Islands and Course Schedule are among the most frequently asked problems anywhere, and both are five-minute problems once the representation is right.

## The idea

**Representations.** An adjacency list, `List<List<Integer>>` for nodes numbered `0..n-1` or `Map<Node, List<Node>>` otherwise, is the default. An edge list (`int[][] edges`) is converted to an adjacency list first, O(V + E). A grid is a graph whose nodes are cells and whose edges go to the four neighbours; there is no need to build anything, a `DIRECTIONS` array and a bounds check are the adjacency list. An adjacency matrix is only worth it for small dense graphs.

**BFS.** A queue, and a visited marker set *when a node is enqueued*, not when it is dequeued. Processing the queue one level at a time (capture `queue.size()`) gives the distance in edges, which is the shortest path when all edges have equal weight. Starting with several nodes in the queue (multi-source BFS) gives the distance to the nearest source for every node in one pass.

**DFS.** Recursive or with an explicit stack; mark visited on entry. "How many components?" is a loop over all nodes that starts a DFS from each unvisited one and counts the starts. DFS also gives cycle detection: in an undirected graph, a visited neighbour that is not the parent; in a directed graph, three colours (unvisited, on the current path, finished), where reaching a node that is on the current path is a cycle.

**Kahn's algorithm (topological sort by in-degree).** Count incoming edges per node; enqueue every node with in-degree 0; poll a node, append it to the order, decrement each successor's in-degree and enqueue those that reach 0. If the order is shorter than the node count, the graph has a cycle. O(V + E).

**Complexity.** BFS, DFS and Kahn's algorithm are O(V + E) time and O(V) space; on a grid of `rows × columns` cells that is O(rows · columns).

## Example: Number of Islands (200), DFS on a grid

Count groups of `'1'` cells connected horizontally or vertically. Each unvisited land cell starts a DFS that "sinks" its whole island by overwriting it with `'0'`, which doubles as the visited marker.

```java
public final class NumberOfIslands {

    private static final int[][] DIRECTIONS = {{1, 0}, {-1, 0}, {0, 1}, {0, -1}};

    public int numIslands(char[][] grid) {
        int islandCount = 0;
        for (int row = 0; row < grid.length; row++) {
            for (int column = 0; column < grid[0].length; column++) {
                if (grid[row][column] == '1') {
                    islandCount++;
                    sink(grid, row, column);
                }
            }
        }
        return islandCount;
    }

    private void sink(char[][] grid, int row, int column) {
        if (row < 0 || row >= grid.length || column < 0 || column >= grid[0].length || grid[row][column] != '1') {
            return;
        }
        grid[row][column] = '0';
        for (int[] direction : DIRECTIONS) {
            sink(grid, row + direction[0], column + direction[1]);
        }
    }
}
```

The grid `11000 / 11000 / 00100 / 00011` has 3 islands. Putting the bounds check at the top of `sink` instead of before each call keeps the recursion short. The recursion depth can reach the number of land cells (an all-land 300 × 300 grid is 90,000 frames), which is more than a default-sized thread stack holds on a typical JVM; an explicit `ArrayDeque<int[]>` of cells gives the same traversal without that risk.

## Example: Rotting Oranges (994), multi-source BFS

Every minute, each rotten orange (2) rots its fresh neighbours (1). Return the minutes until no fresh orange remains, or -1. All rotten oranges start in the queue together; the number of BFS levels is the answer.

```java
import java.util.ArrayDeque;
import java.util.Deque;

public final class RottingOranges {

    private static final int[][] DIRECTIONS = {{1, 0}, {-1, 0}, {0, 1}, {0, -1}};

    public int orangesRotting(int[][] grid) {
        Deque<int[]> rottenFrontier = new ArrayDeque<>();
        int freshCount = 0;
        for (int row = 0; row < grid.length; row++) {
            for (int column = 0; column < grid[0].length; column++) {
                if (grid[row][column] == 2) {
                    rottenFrontier.offer(new int[] {row, column});
                } else if (grid[row][column] == 1) {
                    freshCount++;
                }
            }
        }
        int minutes = 0;
        while (!rottenFrontier.isEmpty() && freshCount > 0) {
            int frontierSize = rottenFrontier.size();
            for (int processed = 0; processed < frontierSize; processed++) {
                int[] cell = rottenFrontier.poll();
                for (int[] direction : DIRECTIONS) {
                    int nextRow = cell[0] + direction[0];
                    int nextColumn = cell[1] + direction[1];
                    if (nextRow >= 0 && nextRow < grid.length && nextColumn >= 0 && nextColumn < grid[0].length
                            && grid[nextRow][nextColumn] == 1) {
                        grid[nextRow][nextColumn] = 2;
                        freshCount--;
                        rottenFrontier.offer(new int[] {nextRow, nextColumn});
                    }
                }
            }
            minutes++;
        }
        return freshCount == 0 ? minutes : -1;
    }
}
```

`[[2, 1, 1], [1, 1, 0], [0, 1, 1]]` gives 4; `[[2, 1, 1], [0, 1, 1], [1, 0, 1]]` gives -1 because the bottom-left orange is unreachable; `[[0, 2]]` gives 0. The `freshCount > 0` condition in the `while` stops the clock as soon as the last orange rots, which is what avoids the classic off-by-one of counting a final empty level. Marking a cell rotten when it is *enqueued* is what prevents it being enqueued twice.

## Example: Clone Graph (133), DFS with a map as the visited set

Deep-copy a connected undirected graph. A map from original node to its clone is both the visited set and the way to wire edges to nodes that already exist. The clone must be put in the map *before* recursing into neighbours, otherwise a cycle recurses forever.

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class CloneGraph {

    public static final class GraphNode {
        int value;
        List<GraphNode> neighbours = new ArrayList<>();

        GraphNode(int value) {
            this.value = value;
        }
    }

    private final Map<GraphNode, GraphNode> cloneByOriginal = new HashMap<>();

    public GraphNode cloneGraph(GraphNode original) {
        if (original == null) {
            return null;
        }
        GraphNode existingClone = cloneByOriginal.get(original);
        if (existingClone != null) {
            return existingClone;
        }
        GraphNode clone = new GraphNode(original.value);
        cloneByOriginal.put(original, clone);
        for (GraphNode neighbour : original.neighbours) {
            clone.neighbours.add(cloneGraph(neighbour));
        }
        return clone;
    }
}
```

`GraphNode` does not override `equals` or `hashCode`, so the map compares identities, which is exactly what "the same original node" means here. LeetCode's `Node` class names the fields `val` and `neighbors`.

## Example: Course Schedule (207), Kahn's algorithm

`prerequisites[i] = {course, requiredFirst}` means `requiredFirst` must be taken before `course`, so the edge goes from `requiredFirst` to `course`. Can all courses be finished? Yes exactly when the graph has no cycle.

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;

public final class CourseSchedule {

    public boolean canFinish(int courseCount, int[][] prerequisites) {
        List<List<Integer>> dependentsOf = new ArrayList<>(courseCount);
        int[] prerequisiteCount = new int[courseCount];
        for (int course = 0; course < courseCount; course++) {
            dependentsOf.add(new ArrayList<>());
        }
        for (int[] prerequisite : prerequisites) {
            int course = prerequisite[0];
            int requiredFirst = prerequisite[1];
            dependentsOf.get(requiredFirst).add(course);
            prerequisiteCount[course]++;
        }
        Deque<Integer> ready = new ArrayDeque<>();
        for (int course = 0; course < courseCount; course++) {
            if (prerequisiteCount[course] == 0) {
                ready.offer(course);
            }
        }
        int completed = 0;
        while (!ready.isEmpty()) {
            int course = ready.poll();
            completed++;
            for (int dependent : dependentsOf.get(course)) {
                prerequisiteCount[dependent]--;
                if (prerequisiteCount[dependent] == 0) {
                    ready.offer(dependent);
                }
            }
        }
        return completed == courseCount;
    }
}
```

`canFinish(2, {{1, 0}})` is `true`; `canFinish(2, {{1, 0}, {0, 1}})` is `false` because neither course ever reaches in-degree 0. Course Schedule II (210) is the same loop with the polled courses appended to a result array, returned empty when `completed < courseCount`.

## Pitfalls

- Marking visited on dequeue instead of enqueue. Dense graphs then enqueue the same node many times; the symptom is a time limit exceeded on a correct-looking BFS.
- No visited set at all. Fine on a tree, an infinite loop on the first cycle.
- DFS for a shortest path. DFS finds *a* path; only BFS (on unweighted graphs) finds the shortest.
- Recursion depth. A DFS over a long path or a large all-land grid can overflow the stack; switch to an explicit stack when the node count is large.
- Edge direction in dependency problems. `{a, b}` meaning "b before a" is an edge `b -> a`; reversing it still detects cycles but produces a reversed order in Course Schedule II.
- Forgetting disconnected parts. Components, cycle detection and topological sort must loop over every node, not start from node 0 only.
- `int[]` cells in a `HashSet` as the visited set. Arrays hash by identity, so nothing is ever "already visited". Use a `boolean[][]`, encode the cell as `row * columns + column`, or use a record.
- Mutating the input grid when the statement forbids it, or forgetting to say that you are doing it. Interviewers accept sinking the island if you mention the trade-off.

## Check yourself

1. Why must a cell be marked visited (rotten, sunk) at the moment it is enqueued rather than when it is polled? Describe an input where the difference is large.
2. Convert `sink` in Number of Islands to an iterative version with an `ArrayDeque<int[]>`. Does it matter whether you use it as a stack or as a queue for counting islands? Would it matter for Rotting Oranges?
3. In Course Schedule, how do you detect the cycle with Kahn's algorithm, and how would you detect it with DFS instead? Which nodes does DFS need to track beyond "visited"?
4. In Clone Graph, what happens if `cloneByOriginal.put(original, clone)` is moved after the loop over neighbours? Trace it on a two-node graph where each node is the other's neighbour.

## Go deeper

- [Tech Interview Handbook: Graph cheatsheet](https://www.techinterviewhandbook.org/algorithms/graph/) · representations, the traversal templates and the corner cases interviewers probe.
- [William Fiset: Graph Theory](https://www.youtube.com/playlist?list=PLDV1Zeh2NRsDGO4--qE8yH72HFL1Km93P) · the clearest video course on BFS, DFS, topological sort and what comes after them.
- [VisuAlgo: Graph Traversal](https://visualgo.net/en/dfsbfs) · step through BFS and DFS on your own graph and watch the visited set grow.

---

Part of [DSA & Interviews](../README.md) · items 4.1, 4.2
