# Patterns: shortest paths and minimum spanning trees

> **In one sentence:** On a weighted graph, Dijkstra finds shortest paths when no edge weight is negative, Bellman-Ford handles negative weights and a bound on the number of edges by relaxing every edge in rounds, 0-1 BFS is Dijkstra with a deque when weights are only 0 and 1, and Prim and Kruskal find the cheapest set of edges that connects everything.

**Why it matters:** Routing, "cheapest flights with at most k stops", network delay, laying cable to connect sites and clustering are all one of these five algorithms. Interviewers use Network Delay Time, Cheapest Flights Within K Stops and Min Cost to Connect All Points because they test whether you can pick the right algorithm, not just code BFS, and because the lazy-deletion heap idiom in Dijkstra is a reliable source of bugs.

## The idea

**Recognising the pattern.** Edges have weights (time, cost, distance), and the question is about the minimum total weight of a path (shortest paths) or of a connecting set of edges (spanning tree). If every edge has the same weight, plain BFS (item 4.1) already gives shortest paths and none of this is needed.

Which algorithm:

| Question | Algorithm | Time | When |
|---|---|---|---|
| Shortest path from one source, weights ≥ 0 | Dijkstra | O((V + E) log V) with a binary heap | the default |
| Shortest path, weights may be negative, or at most k edges | Bellman-Ford | O(V · E), or O(k · E) for k rounds | negative weights, hop limits, negative-cycle detection |
| Shortest path, weights are only 0 or 1 | 0-1 BFS | O(V + E) | grids where some moves are free |
| Cheapest edges that connect every node | Kruskal | O(E log E) | edge list given, sparse graphs |
| Cheapest edges that connect every node | Prim | O(E log V) with a heap | adjacency list given, dense graphs |

**Dijkstra.** Keep `distance[node]`, initially infinity except the source at 0. Keep a min-heap of `(distance, node)` candidates. Poll the smallest; if its distance is already larger than `distance[node]`, it is stale, skip it. Otherwise relax every outgoing edge: if `distance[node] + weight < distance[target]`, update and push a new candidate. Java's `PriorityQueue` has no decrease-key, so pushing duplicates and skipping stale ones is the standard idiom. Correctness needs non-negative weights: once a node is polled, no later path can be shorter.

**Bellman-Ford.** Repeat V - 1 times: for every edge, relax it. After round i, `distance` is correct for every shortest path with at most i edges. A V-th round that still improves something proves a negative cycle. The hop-limited variant copies the distance array at the start of each round and relaxes from the copy, so that one round uses at most one more edge.

**0-1 BFS.** A deque instead of a heap: a 0-weight edge pushes the neighbour to the front, a 1-weight edge pushes to the back. The deque stays sorted by distance, so it behaves like Dijkstra at BFS cost.

**Kruskal.** Sort all edges by weight; walk them, adding each edge whose endpoints are in different components (union-find, item 3.5); stop after V - 1 edges. The exchange argument: the cheapest edge crossing any cut belongs to some minimum spanning tree.

**Prim.** Grow one tree from any node: a heap of edges leaving the tree; poll the cheapest that reaches a node not yet in the tree, add it, push that node's edges. It is Dijkstra with "edge weight" in place of "path length".

## Example: Network Delay Time (743), Dijkstra

Signals travel along directed edges with a delay. How long until every node has received the signal, or -1 if some node is unreachable?

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public final class NetworkDelayTime {

    private record Edge(int target, int weight) {
    }

    private record Candidate(int node, int distance) {
    }

    public int networkDelayTime(int[][] times, int nodeCount, int source) {
        List<List<Edge>> adjacency = new ArrayList<>();
        for (int node = 0; node <= nodeCount; node++) {
            adjacency.add(new ArrayList<>());
        }
        for (int[] time : times) {
            adjacency.get(time[0]).add(new Edge(time[1], time[2]));
        }
        int[] distance = new int[nodeCount + 1];
        Arrays.fill(distance, Integer.MAX_VALUE);
        distance[source] = 0;
        PriorityQueue<Candidate> frontier = new PriorityQueue<>(Comparator.comparingInt(Candidate::distance));
        frontier.offer(new Candidate(source, 0));
        while (!frontier.isEmpty()) {
            Candidate candidate = frontier.poll();
            if (candidate.distance() > distance[candidate.node()]) {
                continue;
            }
            for (Edge edge : adjacency.get(candidate.node())) {
                int relaxed = candidate.distance() + edge.weight();
                if (relaxed < distance[edge.target()]) {
                    distance[edge.target()] = relaxed;
                    frontier.offer(new Candidate(edge.target(), relaxed));
                }
            }
        }
        int slowest = 0;
        for (int node = 1; node <= nodeCount; node++) {
            if (distance[node] == Integer.MAX_VALUE) {
                return -1;
            }
            slowest = Math.max(slowest, distance[node]);
        }
        return slowest;
    }

    public static void main(String[] arguments) {
        NetworkDelayTime solver = new NetworkDelayTime();
        System.out.println(solver.networkDelayTime(new int[][] {{2, 1, 1}, {2, 3, 1}, {3, 4, 1}}, 4, 2));
        System.out.println(solver.networkDelayTime(new int[][] {{1, 2, 1}}, 2, 2));
        System.out.println(solver.networkDelayTime(new int[][] {{1, 2, 5}, {1, 3, 1}, {3, 2, 1}, {2, 4, 2}}, 4, 1));
    }
}
```

```text
$ java NetworkDelayTime.java
2
-1
4
```

In the third case node 2 is first pushed with distance 5 and then with distance 2 via node 3; the stale `(2, 5)` candidate is polled later and skipped by the `candidate.distance() > distance[...]` check. O((V + E) log V) time, O(V + E) space.

## Example: Cheapest Flights Within K Stops (787), Bellman-Ford with a hop limit

At most `k` stops means at most `k + 1` flights, so run `k + 1` rounds of relaxation from a copy of the previous round.

```java
import java.util.Arrays;

public final class CheapestFlights {

    public int findCheapestPrice(int cityCount, int[][] flights, int source, int destination, int maximumStops) {
        int[] cost = new int[cityCount];
        Arrays.fill(cost, Integer.MAX_VALUE);
        cost[source] = 0;
        for (int round = 0; round <= maximumStops; round++) {
            int[] previousRound = cost.clone();
            for (int[] flight : flights) {
                int from = flight[0];
                int to = flight[1];
                int price = flight[2];
                if (previousRound[from] != Integer.MAX_VALUE && previousRound[from] + price < cost[to]) {
                    cost[to] = previousRound[from] + price;
                }
            }
        }
        return cost[destination] == Integer.MAX_VALUE ? -1 : cost[destination];
    }

    public static void main(String[] arguments) {
        CheapestFlights solver = new CheapestFlights();
        int[][] flights = {{0, 1, 100}, {1, 2, 100}, {2, 0, 100}, {1, 3, 600}, {2, 3, 200}};
        System.out.println(solver.findCheapestPrice(4, flights, 0, 3, 1));
        System.out.println(solver.findCheapestPrice(4, flights, 0, 3, 0));
        System.out.println(solver.findCheapestPrice(4, flights, 0, 3, 2));
    }
}
```

```text
$ java CheapestFlights.java
700
-1
400
```

Dijkstra is wrong here: the cheapest route to city 3 (0 → 1 → 2 → 3, cost 400) uses three flights, and with `k = 1` the answer must be the more expensive two-flight route (700). Dijkstra would settle city 3 at 400 and never reconsider. The `previousRound` copy is what enforces the hop limit; relaxing from the live array would let one round chain several flights. O(k · E) time, O(V) space.

## Example: Min Cost to Connect All Points (1584), Kruskal

Connect every point with Manhattan-distance edges at minimum total cost. Build all pairwise edges, sort, and union.

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public final class MinCostToConnectAllPoints {

    private record Edge(int first, int second, int weight) {
    }

    private int[] parent;

    public int minCostConnectPoints(int[][] points) {
        int pointCount = points.length;
        List<Edge> edges = new ArrayList<>();
        for (int first = 0; first < pointCount; first++) {
            for (int second = first + 1; second < pointCount; second++) {
                int manhattan = Math.abs(points[first][0] - points[second][0]) + Math.abs(points[first][1] - points[second][1]);
                edges.add(new Edge(first, second, manhattan));
            }
        }
        edges.sort(Comparator.comparingInt(Edge::weight));
        parent = new int[pointCount];
        for (int point = 0; point < pointCount; point++) {
            parent[point] = point;
        }
        int totalCost = 0;
        int edgesUsed = 0;
        for (Edge edge : edges) {
            int firstRoot = find(edge.first());
            int secondRoot = find(edge.second());
            if (firstRoot != secondRoot) {
                parent[firstRoot] = secondRoot;
                totalCost += edge.weight();
                edgesUsed++;
                if (edgesUsed == pointCount - 1) {
                    break;
                }
            }
        }
        return totalCost;
    }

    private int find(int node) {
        while (parent[node] != node) {
            parent[node] = parent[parent[node]];
            node = parent[node];
        }
        return node;
    }

    public static void main(String[] arguments) {
        MinCostToConnectAllPoints solver = new MinCostToConnectAllPoints();
        System.out.println(solver.minCostConnectPoints(new int[][] {{0, 0}, {2, 2}, {3, 10}, {5, 2}, {7, 0}}));
        System.out.println(solver.minCostConnectPoints(new int[][] {{3, 12}, {-2, 5}, {-4, 1}}));
    }
}
```

```text
$ java MinCostToConnectAllPoints.java
20
18
```

The graph is complete, so there are n(n - 1)/2 edges and the sort dominates: O(n² log n) time, O(n²) space. Prim with a plain array (no heap) runs in O(n²) on a complete graph and is the better answer when n is large; mention it as the follow-up.

## Pitfalls

- Dijkstra with a negative edge. It returns a wrong distance silently; nothing throws. Check the weights before choosing the algorithm.
- Forgetting the stale-candidate skip. Without `if (candidate.distance() > distance[node]) continue;`, every stale entry re-relaxes all its edges, and the solution can time out on dense graphs; with a visited set used instead, the first (possibly non-minimal) entry wins and the result is wrong.
- Marking a node visited when pushed, BFS-style. Dijkstra must settle a node only when polled; a node can be pushed several times with decreasing distances.
- Bellman-Ford without the per-round copy when there is a hop limit. The answer ignores the limit and looks correct on most tests.
- `Integer.MAX_VALUE + weight` overflow. Guard the "unreached" sentinel before adding, as the Bellman-Ford example does, or use `long`.
- Kruskal without stopping after V - 1 edges. Still correct, but on a complete graph it scans all O(n²) edges instead of stopping early.
- Comparing `parent[first] == parent[second]` instead of the roots (item 3.5). Wrong as soon as a component is two levels deep.
- Reaching for Dijkstra on an unweighted graph. BFS is simpler, faster and what the interviewer expects.

## Check yourself

1. Why is Dijkstra correct only for non-negative weights? Give a three-node graph with one negative edge where it returns the wrong distance, and trace which node gets settled too early.
2. In Cheapest Flights, what goes wrong if `previousRound` is removed and relaxation reads from `cost` directly? Trace the `k = 1` case on the example and show which answer you get.
3. Both Prim and Kruskal are greedy. State the cut property in one sentence and explain why it justifies both.
4. Kruskal on the point set uses O(n²) memory for the edge list. Sketch Prim with a `minimumEdgeToTree` array and no heap, and state its time and space.

## Go deeper

- [William Fiset: Graph Theory](https://www.youtube.com/playlist?list=PLDV1Zeh2NRsDGO4--qE8yH72HFL1Km93P) · Dijkstra with lazy deletion, Bellman-Ford, Prim and Kruskal, each animated step by step.
- [Tech Interview Handbook: Graph cheatsheet](https://www.techinterviewhandbook.org/algorithms/graph/) · which graph algorithms interviewers actually ask about and the corner cases they probe.
- [Algorithms, 4th edition: Shortest Paths](https://algs4.cs.princeton.edu/44sp/) and [Minimum Spanning Trees](https://algs4.cs.princeton.edu/43mst/) · Sedgewick's Java implementations and the proofs behind the cut property.

---

Part of [DSA & Interviews](../README.md) · item 4.3
