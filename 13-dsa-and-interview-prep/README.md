# DSA & Interviews

> Deliberate practice for coding and system design interviews, and for the day job: the problem-solving method, every algorithmic pattern that shows up, a practice plan built on NeetCode and Grind 75, Java idioms for interviews, behavioural interviews, and how to prepare without burning out.

**Related domains:** [Foundations](../01-foundations/README.md), [System Design](../07-system-design/README.md), [Java](../05-java/README.md)

**Done when you can:**

- Solve a medium LeetCode problem in Java in 25 minutes while explaining your reasoning, with correct complexity analysis.
- Recognise the pattern behind an unseen problem (two pointers, sliding window, BFS, DP, ...) within a few minutes.
- Explain the approach, trade-offs and edge cases before writing code, and test your code by hand.
- Lead a 45-minute system design interview using the framework from System Design.
- Tell six concrete stories covering conflict, failure, leadership, ambiguity, impact and learning, in STAR form.
- Run a sustainable 8-12 week preparation plan and track it.

## Roadmap

### 1. Method

- [ ] 1.1 A problem-solving protocol: understand, match a pattern, plan, implement, review, evaluate · [notes](notes/problem-solving-protocol.md) · [Tech Interview Handbook: Coding interview cheatsheet](https://www.techinterviewhandbook.org/coding-interview-cheatsheet/)
- [ ] 1.2 Complexity analysis, fast: counting loops, recursion trees, the master theorem at a glance, amortised cost · [notes](notes/complexity-analysis-fast.md) · [Big-O Cheat Sheet](https://www.bigocheatsheet.com/) · [MIT 6.006](https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/)
- [ ] 1.3 Communicating while coding: thinking aloud, clarifying questions, stating assumptions, using hints · [notes](notes/problem-solving-protocol.md) · [Tech Interview Handbook: Coding interview techniques](https://www.techinterviewhandbook.org/coding-interview-techniques/)
- [ ] 1.4 Testing by hand: edge cases (empty, single element, duplicates, negatives, overflow), tracing a small example · [notes](notes/problem-solving-protocol.md) · [Tech Interview Handbook: Coding interview cheatsheet](https://www.techinterviewhandbook.org/coding-interview-cheatsheet/)
- [ ] 1.5 Deliberate practice: spaced repetition of patterns, timeboxing, studying solutions, keeping a mistakes log · [notes](notes/mock-interviews-and-deliberate-practice.md) · [NeetCode roadmap](https://neetcode.io/roadmap)

### 2. Patterns: arrays, strings and hashing

- [ ] 2.1 Arrays and hashing: frequency maps, prefix sums, the two-sum family, grouping · [notes](notes/patterns-hashing-and-prefix-sums.md) · [Tech Interview Handbook: Array cheatsheet](https://www.techinterviewhandbook.org/algorithms/array/) · [Tech Interview Handbook: Hash table cheatsheet](https://www.techinterviewhandbook.org/algorithms/hash-table/)
- [ ] 2.2 Two pointers: sorted arrays, palindromes, partitioning, container with most water · [notes](notes/patterns-two-pointers-and-sliding-window.md) · [LeetCode Patterns (Sean Prashad)](https://seanprashad.com/leetcode-patterns/)
- [ ] 2.3 Sliding window: fixed and variable windows, longest substring without repeats, minimum window substring · [notes](notes/patterns-two-pointers-and-sliding-window.md) · [NeetCode roadmap](https://neetcode.io/roadmap)
- [ ] 2.4 Stack and monotonic stack: valid parentheses, next greater element, daily temperatures, largest rectangle in a histogram · [notes](notes/patterns-stack-and-monotonic-stack.md) · [Tech Interview Handbook: Stack cheatsheet](https://www.techinterviewhandbook.org/algorithms/stack/)
- [ ] 2.5 Binary search: on indices, on the answer space, rotated arrays, first and last occurrence · [notes](notes/patterns-binary-search.md) · [Tech Interview Handbook: Sorting and searching cheatsheet](https://www.techinterviewhandbook.org/algorithms/sorting-searching/)
- [ ] 2.6 Intervals: merge, insert, meeting rooms; sort by start · [notes](notes/patterns-intervals-and-greedy.md) · [Tech Interview Handbook: Interval cheatsheet](https://www.techinterviewhandbook.org/algorithms/interval/)
- [ ] 2.7 Strings: parsing, anagrams, building strings efficiently, encodings · [notes](notes/patterns-strings-and-matrices.md) · [Tech Interview Handbook: String cheatsheet](https://www.techinterviewhandbook.org/algorithms/string/)
- [ ] 2.8 Matrices and grids: traversal, rotation, spiral order, grids as graphs · [notes](notes/patterns-strings-and-matrices.md) · [Tech Interview Handbook: Matrix cheatsheet](https://www.techinterviewhandbook.org/algorithms/matrix/)

### 3. Patterns: linked lists, trees, heaps and tries

- [ ] 3.1 Linked lists: dummy heads, fast and slow pointers, reversal, merging, cycle detection · [notes](notes/patterns-linked-lists.md) · [Tech Interview Handbook: Linked list cheatsheet](https://www.techinterviewhandbook.org/algorithms/linked-list/)
- [ ] 3.2 Trees: DFS orders, BFS by level, recursion that returns values, BST invariants, lowest common ancestor, serialisation · [notes](notes/patterns-trees-and-bst.md) · [Tech Interview Handbook: Tree cheatsheet](https://www.techinterviewhandbook.org/algorithms/tree/) · [VisuAlgo: Binary Search Tree](https://visualgo.net/en/bst)
- [ ] 3.3 Heaps and priority queues: top-k, k-way merge, median of a stream, scheduling · [notes](notes/patterns-heaps-and-top-k.md) · [Tech Interview Handbook: Heap cheatsheet](https://www.techinterviewhandbook.org/algorithms/heap/)
- [ ] 3.4 Tries: prefix search, word search, autocomplete · [notes](notes/patterns-tries-and-union-find.md) · [Tech Interview Handbook: Trie cheatsheet](https://www.techinterviewhandbook.org/algorithms/trie/)
- [ ] 3.5 Union-find: connected components, cycle detection, Kruskal's algorithm · [notes](notes/patterns-tries-and-union-find.md) · [William Fiset: Union Find](https://www.youtube.com/playlist?list=PLDV1Zeh2NRsBI1C-mR6ZhHTyfoEJWlxvq)

### 4. Patterns: graphs

- [ ] 4.1 Representations, BFS and DFS, grids as graphs (islands, flood fill, rotting oranges) · [notes](notes/patterns-graphs-bfs-dfs-and-topological-sort.md) · [Tech Interview Handbook: Graph cheatsheet](https://www.techinterviewhandbook.org/algorithms/graph/) · [William Fiset: Graph Theory](https://www.youtube.com/playlist?list=PLDV1Zeh2NRsDGO4--qE8yH72HFL1Km93P)
- [ ] 4.2 Topological sort (Kahn's algorithm and DFS): course schedule, dependency resolution · [notes](notes/patterns-graphs-bfs-dfs-and-topological-sort.md) · [William Fiset: Graph Theory](https://www.youtube.com/playlist?list=PLDV1Zeh2NRsDGO4--qE8yH72HFL1Km93P)
- [ ] 4.3 Shortest paths (Dijkstra, Bellman-Ford, 0-1 BFS) and minimum spanning trees (Prim, Kruskal) · [notes](notes/patterns-shortest-paths-and-minimum-spanning-trees.md) · [William Fiset: Graph Theory](https://www.youtube.com/playlist?list=PLDV1Zeh2NRsDGO4--qE8yH72HFL1Km93P)
- [ ] 4.4 Advanced, at a glance: bipartite check, bridges and articulation points, strongly connected components, A* · [William Fiset: Graph Theory](https://www.youtube.com/playlist?list=PLDV1Zeh2NRsDGO4--qE8yH72HFL1Km93P)

### 5. Patterns: recursion, backtracking, dynamic programming and greedy

- [ ] 5.1 Recursion and divide and conquer: recursion trees, memoisation, merge sort, quickselect · [Tech Interview Handbook: Recursion cheatsheet](https://www.techinterviewhandbook.org/algorithms/recursion/)
- [ ] 5.2 Backtracking: subsets, permutations, combinations, N-queens, word search; pruning · [notes](notes/patterns-backtracking.md) · [NeetCode roadmap](https://neetcode.io/roadmap)
- [ ] 5.3 Dynamic programming in one dimension: climbing stairs, house robber, coin change, longest increasing subsequence, decode ways · [notes](notes/patterns-dynamic-programming.md) · [Tech Interview Handbook: Dynamic programming cheatsheet](https://www.techinterviewhandbook.org/algorithms/dynamic-programming/) · [Aditya Verma: Dynamic Programming playlist](https://www.youtube.com/playlist?list=PL_z_8CaSLPWekqhdCPmFohncHwz8TY2Go)
- [ ] 5.4 Dynamic programming in two dimensions: grids, longest common subsequence, edit distance, the knapsack family, interval DP · [notes](notes/patterns-dynamic-programming.md) · [NeetCode roadmap](https://neetcode.io/roadmap)
- [ ] 5.5 Greedy algorithms and the exchange argument: jump game, gas station, task scheduler · [notes](notes/patterns-intervals-and-greedy.md) · [Tech Interview Handbook: Coding interview techniques](https://www.techinterviewhandbook.org/coding-interview-techniques/)
- [ ] 5.6 Bit manipulation and math: XOR tricks, counting bits, modular arithmetic, gcd, fast exponentiation · [notes](notes/patterns-bit-manipulation-and-math.md) · [Tech Interview Handbook: Binary cheatsheet](https://www.techinterviewhandbook.org/algorithms/binary/) · [Tech Interview Handbook: Math cheatsheet](https://www.techinterviewhandbook.org/algorithms/math/)

### 6. Java for coding interviews

- [ ] 6.1 Idioms: `ArrayDeque` over `Stack`, `PriorityQueue` with comparators, `Map.merge` and `computeIfAbsent`, records for pairs, `Arrays.fill`, `Collections.nCopies` · [notes](notes/java-idioms-for-interviews.md) · [Baeldung: Guide to the Java ArrayDeque](https://www.baeldung.com/java-array-deque)
- [ ] 6.2 Pitfalls: `Integer` equality and the cache, overflow (use `long`), `char` arithmetic, sort stability, mutable keys in a `HashMap`, `substring` cost · [notes](notes/java-idioms-for-interviews.md) · [JLS 5.1.7: Boxing Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.7)
- [ ] 6.3 Fast input and output, a reusable template, and when to avoid streams in interview code · [Baeldung: Fast I/O? BufferedReader](https://www.baeldung.com/java-buffered-reader)
- [ ] 6.4 Complexity of Java collection operations at a glance · [Big-O Cheat Sheet](https://www.bigocheatsheet.com/)

### 7. Practice plans and tools

- [ ] 7.1 Pick one curated list and finish it: NeetCode 150 (by pattern) or Grind 75 (by time budget); track solved problems and revisit failures · [notes](notes/a-12-week-study-plan.md) · [NeetCode roadmap](https://neetcode.io/roadmap) · [Grind 75](https://www.techinterviewhandbook.org/grind75/) · [LeetCode](https://leetcode.com/)
- [ ] 7.2 Weekly structure: patterns on weekdays, a timed set or mock at the weekend, review notes · [notes](notes/a-12-week-study-plan.md) · [Tech Interview Handbook](https://www.techinterviewhandbook.org/)
- [ ] 7.3 Mock interviews with peers or platforms; record yourself and watch it back · [notes](notes/mock-interviews-and-deliberate-practice.md) · [Pramp](https://www.pramp.com/) · [interviewing.io](https://interviewing.io/)
- [ ] 7.4 Visualise algorithms and trace code: VisuAlgo, Python Tutor (supports Java) · [VisuAlgo](https://visualgo.net/en) · [Python Tutor](https://pythontutor.com/)

### 8. System design, Java and low-level design interviews

- [ ] 8.1 System design interviews: the framework and practice list live in the System Design roadmap, section 6 · [System Design roadmap](../07-system-design/README.md)
- [ ] 8.2 Java and Spring questions as a self-check: JVM, collections, concurrency, the container, transactions, JPA, security · [notes](notes/java-and-spring-interview-questions-self-check.md) · [Baeldung: Java interview questions](https://www.baeldung.com/java-interview-questions) · [Baeldung: Spring interview questions](https://www.baeldung.com/spring-interview-questions)
- [ ] 8.3 Database and SQL questions: joins, indexes, isolation levels, reading a plan · [notes](notes/java-and-spring-interview-questions-self-check.md) · [PostgreSQL Exercises](https://pgexercises.com/) · [roadmap.sh: Backend interview questions](https://roadmap.sh/questions/backend)
- [ ] 8.4 Low-level design: classes and interfaces for a parking lot, an elevator, a cache, a rate limiter; SOLID in action · [notes](notes/low-level-design-interviews.md) · [awesome-low-level-design](https://github.com/ashishps1/awesome-low-level-design)

### 9. Behavioural interviews and the process

- [ ] 9.1 The STAR method and a bank of six to eight stories: conflict, failure, leadership, ambiguity, impact, learning · [notes](notes/behavioural-interviews-with-star.md) · [Tech Interview Handbook: Behavioral interview](https://www.techinterviewhandbook.org/behavioral-interview/)
- [ ] 9.2 Questions to ask interviewers; evaluating a team and a role · [Tech Interview Handbook: Questions to ask](https://www.techinterviewhandbook.org/questions-to-ask/)
- [ ] 9.3 Resume and online presence: impact-oriented bullets, a focused GitHub · [Tech Interview Handbook: Resume](https://www.techinterviewhandbook.org/resume/)
- [ ] 9.4 Negotiation basics and offer evaluation · [Tech Interview Handbook: Negotiation](https://www.techinterviewhandbook.org/negotiation/) · [Haseeb Qureshi: Ten Rules for Negotiating a Job Offer](https://haseebq.com/my-ten-rules-for-negotiating-a-job-offer/)
- [ ] 9.5 Sustainable preparation: an 8-12 week plan, rest days, and knowing when you are ready · [notes](notes/a-12-week-study-plan.md) · [Tech Interview Handbook: Study and practice? Coding interview study plan](https://www.techinterviewhandbook.org/coding-interview-study-plan/)

## Resources

### Start here

- [NeetCode](https://neetcode.io/) · the pattern-ordered roadmap plus a video solution for every problem; free.
- [Tech Interview Handbook](https://www.techinterviewhandbook.org/) · Yangshun Tay's free, complete guide: algorithms cheatsheets, Grind 75, behavioural prep, negotiation.
- [Grind 75](https://www.techinterviewhandbook.org/grind75/) · a study list that adapts to the weeks and hours you have.
- [LeetCode](https://leetcode.com/) · the practice platform; the free tier is enough.
- [William Fiset: Graph Theory](https://www.youtube.com/playlist?list=PLDV1Zeh2NRsDGO4--qE8yH72HFL1Km93P) · the clearest graph algorithms course available.

### Books

- [Cracking the Coding Interview](https://www.crackingthecodinginterview.com/) · Gayle Laakmann McDowell (paid). Still the standard orientation to the process.
- [Elements of Programming Interviews in Java](https://elementsofprogramminginterviews.com/) · Aziz, Lee and Prakash (paid). Harder problems with rigorous solutions.
- [Grokking Algorithms, 2nd edition](https://www.manning.com/books/grokking-algorithms-second-edition) · Aditya Bhargava (paid). The gentlest introduction.
- [The Algorithm Design Manual](https://www.algorist.com/) · Steven Skiena (paid). The "war stories" teach how to think about problems.
- [Algorithms, 4th edition](https://algs4.cs.princeton.edu/home/) · Sedgewick and Wayne; Java implementations and a free booksite.

### Courses and videos

- [NeetCode on YouTube](https://www.youtube.com/@NeetCode) · solution walkthroughs for the roadmap.
- [Abdul Bari: Algorithms](https://www.youtube.com/@abdul_bari) · classic lectures on algorithm design.
- [Back To Back SWE](https://www.youtube.com/@BackToBackSWE) · careful explanations of the hard problems.
- [MIT 6.006 Introduction to Algorithms](https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/) · the theory behind the patterns.
- [Algorithms, Part I and II (Coursera)](https://www.coursera.org/learn/algorithms-part1) · Sedgewick's courses in Java; free to audit.

### References

- [LeetCode Patterns](https://seanprashad.com/leetcode-patterns/) · Sean Prashad's problem list grouped by pattern.
- [Big-O Cheat Sheet](https://www.bigocheatsheet.com/) · complexity of every structure and algorithm.
- [VisuAlgo](https://visualgo.net/en) and [Python Tutor](https://pythontutor.com/) · animate structures and trace your code.
- [Hello Interview](https://www.hellointerview.com/) · system design interview preparation.
- [GeeksforGeeks: DSA](https://www.geeksforgeeks.org/dsa/dsa-tutorial-learn-data-structures-and-algorithms/) · broad coverage with worked examples; verify details against a primary source.
- [roadmap.sh: Data Structures and Algorithms](https://roadmap.sh/datastructures-and-algorithms) · visual overview.
