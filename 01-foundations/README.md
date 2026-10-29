# Foundations

> How computers actually run your code: hardware, operating systems, networks, data structures, the shell, and Git. Everything else in this roadmap stands on this.

**Prerequisites:** none

**Done when you can:**

- Explain what happens, from CPU cache to page fault, when a program touches memory it has not used before.
- Pick a data structure for a problem and state its time and space complexity without looking it up.
- Trace a TCP connection from socket to packet and read the output of `ss`, `dig`, and `tcpdump` well enough to debug "it works on my machine".
- Work comfortably in a Unix shell: pipes, processes, permissions, and the ten commands you reach for daily.
- Explain Git's object model well enough to rescue a botched rebase with the reflog.

## Roadmap

### 1. How a computer runs code

- [ ] 1.1 CPU basics: instructions, registers, the fetch-decode-execute cycle, pipelining and branch prediction at a glance · [notes](notes/how-a-program-runs.md) · [Crash Course Computer Science](https://www.youtube.com/playlist?list=PL8dPuuaLjXtNlUrzyH5r6jN9ulIgZBpdo) · [CS:APP](https://csapp.cs.cmu.edu/)
- [ ] 1.2 Memory hierarchy: registers, L1/L2/L3 caches, RAM, SSD; cache lines and why locality dominates performance · [notes](notes/how-a-program-runs.md) · [Interactive latency numbers](https://colin-scott.github.io/personal_website/research/interactive_latency.html) · [What Every Programmer Should Know About Memory](https://people.freebsd.org/~lstewart/articles/cpumemory.pdf)
- [ ] 1.3 From source to running process: compilers, interpreters, JIT compilation, linking and loading · [notes](notes/how-a-program-runs.md) · [CS:APP ch. 7](https://csapp.cs.cmu.edu/)
- [ ] 1.4 Numbers in a machine: binary, hex, two's complement, integer overflow, IEEE 754 floating point and why 0.1 + 0.2 != 0.3 · [notes](notes/floating-point-and-money.md) · [Float Toy](https://evanw.github.io/float-toy/) · [What Every Computer Scientist Should Know About Floating-Point](https://docs.oracle.com/cd/E19957-01/806-3568/ncg_goldberg.html)
- [ ] 1.5 Text in a machine: ASCII, Unicode code points, UTF-8 and UTF-16, bytes vs characters vs grapheme clusters · [notes](notes/unicode-and-text-encodings.md) · [Joel Spolsky on Unicode](https://www.joelonsoftware.com/2003/10/08/the-absolute-minimum-every-software-developer-absolutely-positively-must-know-about-unicode-and-character-sets-no-excuses/) · [UTF-8 Everywhere](https://utf8everywhere.org/)
- [ ] 1.6 Build a computer from logic gates up, once, to remove the magic · [Nand to Tetris](https://www.nand2tetris.org/) · [Code by Charles Petzold](https://www.codehiddenlanguage.com/)

### 2. Operating systems

- [ ] 2.1 Processes vs threads: address spaces, the process control block, context switches and their cost · [notes](notes/processes-threads-and-virtual-memory.md) · [OSTEP: Processes](https://pages.cs.wisc.edu/~remzi/OSTEP/cpu-intro.pdf) · [OSTEP: Threads](https://pages.cs.wisc.edu/~remzi/OSTEP/threads-intro.pdf)
- [ ] 2.2 Scheduling: time slices, priorities, CPU-bound vs I/O-bound work, why too many threads hurt · [notes](notes/cpu-scheduling-and-why-too-many-threads-hurt.md) · [OSTEP: Scheduling](https://pages.cs.wisc.edu/~remzi/OSTEP/cpu-sched.pdf)
- [ ] 2.3 Virtual memory: pages, page tables, the TLB, page faults, swap; RSS vs virtual size in `top` · [notes](notes/processes-threads-and-virtual-memory.md) · [OSTEP: Address Translation](https://pages.cs.wisc.edu/~remzi/OSTEP/vm-mechanism.pdf) · [OSTEP: Paging](https://pages.cs.wisc.edu/~remzi/OSTEP/vm-paging.pdf)
- [ ] 2.4 System calls, user vs kernel mode, and what a blocking call really costs · [notes](notes/syscalls-blocking-and-the-page-cache.md) · [OSTEP: Limited Direct Execution](https://pages.cs.wisc.edu/~remzi/OSTEP/cpu-mechanisms.pdf) · [strace zine](https://jvns.ca/blog/2015/04/14/strace-zine/)
- [ ] 2.5 Files and I/O: file descriptors, the page cache, buffering, `fsync` and what "durable" means · [notes](notes/syscalls-blocking-and-the-page-cache.md) · [OSTEP: Files and Directories](https://pages.cs.wisc.edu/~remzi/OSTEP/file-intro.pdf) · [OSTEP: Crash Consistency](https://pages.cs.wisc.edu/~remzi/OSTEP/file-journaling.pdf)
- [ ] 2.6 OS-level concurrency primitives: mutexes, condition variables, semaphores (deep dive in Memory & Concurrency) · [OSTEP: Locks](https://pages.cs.wisc.edu/~remzi/OSTEP/threads-locks.pdf)
- [ ] 2.7 Signals, exit codes, environment variables, stdin/stdout/stderr, and how a shell starts your program · [The Missing Semester: Shell Tools](https://missing.csail.mit.edu/2020/shell-tools/)

### 3. Networking fundamentals

- [ ] 3.1 The layered model in practice: Ethernet, IP, TCP/UDP, application protocols; what each layer adds · [notes](notes/tcp-ip-essentials.md) · [Kurose & Ross](https://gaia.cs.umass.edu/kurose_ross/) · [Practical Networking](https://www.youtube.com/@PracticalNetworking)
- [ ] 3.2 IP addressing: IPv4/IPv6, subnets and CIDR, private ranges, NAT, routing basics · [notes](notes/ip-addressing-subnets-and-nat.md) · [Cloudflare: What is an IP address?](https://www.cloudflare.com/learning/dns/glossary/what-is-my-ip-address/)
- [ ] 3.3 TCP: three-way handshake, sequence numbers, retransmission, flow and congestion control, head-of-line blocking; UDP and when to prefer it · [notes](notes/tcp-ip-essentials.md) · [HPBN: Building Blocks of TCP](https://hpbn.co/building-blocks-of-tcp/) · [HPBN: Building Blocks of UDP](https://hpbn.co/building-blocks-of-udp/)
- [ ] 3.4 Sockets and ports: what "listening" means, accept queues, ephemeral ports, `TIME_WAIT`, connection limits · [notes](notes/tcp-ip-essentials.md) · [Beej's Guide to Network Programming](https://beej.us/guide/bgnet/)
- [ ] 3.5 DNS resolution path, record types, TTLs and caching (deep dive in Web & HTTP) · [How DNS works](https://howdns.works/)
- [ ] 3.6 TLS at a glance: what it protects, what it does not (deep dive in Web & HTTP and Security) · [How HTTPS works](https://howhttps.works/)
- [ ] 3.7 Tools: `curl`, `dig`, `ss`, `traceroute`, `tcpdump`, Wireshark · [Everything curl](https://everything.curl.dev/) · [tcpdump is amazing](https://jvns.ca/blog/2016/03/16/tcpdump-is-amazing/)

### 4. Data structures and algorithms essentials

- [ ] 4.1 Big-O: time and space, best/average/worst case, amortised cost, and the constants Big-O hides · [notes](notes/big-o-in-practice.md) · [Big-O Cheat Sheet](https://www.bigocheatsheet.com/) · [MIT 6.006 lecture 1](https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/)
- [ ] 4.2 Arrays and dynamic arrays; strings and their cost model (immutability, builders, encoding) · [VisuAlgo](https://visualgo.net/en)
- [ ] 4.3 Hash tables: hash functions, collisions, load factor, resizing; why `equals`/`hashCode` contracts exist · [notes](notes/choosing-a-data-structure.md) · [Algorithms, 4th ed.: Hash Tables](https://algs4.cs.princeton.edu/34hash/)
- [ ] 4.4 Linked lists, stacks, queues, deques; when a linked list is actually the right choice (rarely) · [notes](notes/choosing-a-data-structure.md) · [Algorithms, 4th ed.: Bags, Queues, Stacks](https://algs4.cs.princeton.edu/13stacks/)
- [ ] 4.5 Trees: binary search trees, balanced trees (red-black, B-trees), heaps and priority queues · [notes](notes/choosing-a-data-structure.md) · [Algorithms, 4th ed.: Balanced Search Trees](https://algs4.cs.princeton.edu/33balanced/) · [Algorithms, 4th ed.: Priority Queues](https://algs4.cs.princeton.edu/24pq/)
- [ ] 4.6 Graphs: representations, BFS, DFS, shortest paths, topological sort, union-find · [William Fiset: Graph Theory](https://www.youtube.com/playlist?list=PLDV1Zeh2NRsDGO4--qE8yH72HFL1Km93P)
- [ ] 4.7 Sorting and searching: comparison sorts, stability, binary search, and when the library sort is all you need · [Algorithms, 4th ed.: Sorting](https://algs4.cs.princeton.edu/20sorting/)
- [ ] 4.8 Recognising recursion, divide and conquer, dynamic programming and greedy problems (practice lives in DSA & Interviews) · [Grokking Algorithms](https://www.manning.com/books/grokking-algorithms-second-edition)
- [ ] 4.9 Choosing a data structure for everyday backend code: a decision table you can apply in a code review · [notes](notes/choosing-a-data-structure.md) · [Java Collections overview](https://dev.java/learn/api/collections-framework/)

### 5. Linux and the shell

- [ ] 5.1 Filesystem layout, paths, permissions, users and groups, `sudo` · [notes](notes/linux-essentials-for-developers.md) · [Linux Journey](https://linuxjourney.com/) · [The Missing Semester](https://missing.csail.mit.edu/)
- [ ] 5.2 Processes and jobs: `ps`, `top`/`htop`, `kill` and signals, background jobs, `nohup`, exit codes · [notes](notes/linux-essentials-for-developers.md) · [The Missing Semester: Command-line Environment](https://missing.csail.mit.edu/2020/command-line/)
- [ ] 5.3 Pipes, redirection and text tools: `grep`, `sed`, `awk`, `cut`, `sort`, `uniq`, `xargs`, `jq` · [notes](notes/linux-essentials-for-developers.md) · [The Art of Command Line](https://github.com/jlevy/the-art-of-command-line) · [explainshell](https://explainshell.com/)
- [ ] 5.4 Shell scripting basics, quoting, exit codes, `set -euo pipefail`, and when to stop scripting and write a program · [notes](notes/shell-scripting-with-safety-rails.md) · [BashGuide](https://mywiki.wooledge.org/BashGuide) · [ShellCheck](https://www.shellcheck.net/)
- [ ] 5.5 SSH: keys, agents, config, port forwarding, `scp`/`rsync` · [notes](notes/ssh-keys-agents-and-tunnels.md) · [SSH Academy: SSH command](https://www.ssh.com/academy/ssh/command)
- [ ] 5.6 Package managers, `PATH`, environment variables, dotfiles, and reproducible developer machines · [Missing Semester: Shell](https://missing.csail.mit.edu/2020/course-shell/)
- [ ] 5.7 Finding what is eating CPU, memory, disk or sockets (deep dive in DevOps & Delivery) · [Linux Performance Analysis in 60 seconds](https://netflixtechblog.com/linux-performance-analysis-in-60-000-milliseconds-accc10403c55) · [Brendan Gregg: Linux Performance](https://www.brendangregg.com/linuxperf.html)
- [ ] 5.8 Reading `man` pages and `--help` faster than searching the web · [man7.org](https://man7.org/linux/man-pages/) · [tldr pages](https://tldr.sh/)

### 6. Git

- [ ] 6.1 The object model: blobs, trees, commits, refs; a branch is a pointer, a commit is a snapshot · [notes](notes/git-mental-model.md) · [Pro Git: Git Internals](https://git-scm.com/book/en/v2/Git-Internals-Plumbing-and-Porcelain) · [Learn Git Branching](https://learngitbranching.js.org/)
- [ ] 6.2 Everyday workflow: staging, atomic commits, good messages, `log`, `diff`, `blame` · [How to Write a Git Commit Message](https://cbea.ms/git-commit/)
- [ ] 6.3 Branching, merging, rebasing, cherry-picking, and resolving conflicts calmly · [notes](notes/git-mental-model.md) · [Pro Git: Branching](https://git-scm.com/book/en/v2/Git-Branching-Branches-in-a-Nutshell) · [Pro Git: Rebasing](https://git-scm.com/book/en/v2/Git-Branching-Rebasing)
- [ ] 6.4 Undoing things: `restore` vs `reset` vs `revert`, the reflog, `stash` · [notes](notes/git-mental-model.md) · [Oh Shit, Git!?!](https://ohshitgit.com/)
- [ ] 6.5 Remotes, fetch vs pull, pull requests, protected branches, force-push etiquette · [Pro Git: Working with Remotes](https://git-scm.com/book/en/v2/Git-Basics-Working-with-Remotes)
- [ ] 6.6 `bisect`, hooks, `.gitignore`, `.gitattributes`, `worktree`, submodules at a glance · [Pro Git: Debugging with Git](https://git-scm.com/book/en/v2/Git-Tools-Debugging-with-Git)

### 7. Building, configuring and debugging software

- [ ] 7.1 Build and dependency management concepts: artifacts, transitive dependencies, version conflicts, lockfiles, reproducible builds (Maven and npm live in their domains) · [Semantic Versioning](https://semver.org/)
- [ ] 7.2 Configuration and environments: dev/test/prod parity, config via environment, secrets never in code · [The Twelve-Factor App](https://12factor.net/)
- [ ] 7.3 Debugging as a method: reproduce, form hypotheses, bisect, read the stack trace from the top, instrument · [notes](notes/debugging-as-a-method.md) · [Debugging: The 9 Indispensable Rules](https://debuggingrules.com/)
- [ ] 7.4 Regular expressions you will actually use, and when a regex is the wrong tool · [notes](notes/regular-expressions-you-actually-use.md) · [RegexOne](https://regexone.com/) · [regex101](https://regex101.com/)
- [ ] 7.5 Time and dates: UTC, offsets vs zones, DST, monotonic vs wall clocks, ISO 8601 · [notes](notes/time-dates-and-time-zones.md) · [Falsehoods programmers believe about time](https://gist.github.com/timvisee/fcda9bbdff88d45cc9061606b4b923ca)

## Resources

### Start here

- [Computer Systems: A Programmer's Perspective (CS:APP)](https://csapp.cs.cmu.edu/) · the one book that connects code to hardware, OS, and network. Read chapters 1-3, 6, 7, 9, 11, 12.
- [Operating Systems: Three Easy Pieces (OSTEP)](https://pages.cs.wisc.edu/~remzi/OSTEP/) · free, readable, and complete. Virtualisation and concurrency parts are mandatory for backend work.
- [The Missing Semester of Your CS Education](https://missing.csail.mit.edu/) · MIT's free course on the shell, editors, Git, debugging and profiling.
- [High Performance Browser Networking](https://hpbn.co/) · free online; the networking chapters double as the best TCP/TLS primer for web developers.
- [Crash Course Computer Science](https://www.youtube.com/playlist?list=PL8dPuuaLjXtNlUrzyH5r6jN9ulIgZBpdo) · 40 short videos from transistors to operating systems; a fast, enjoyable refresher.

### Books

- [Code: The Hidden Language of Computer Hardware and Software](https://www.codehiddenlanguage.com/) · Charles Petzold. The gentlest path to understanding what a CPU is.
- [The Elements of Computing Systems (Nand to Tetris)](https://www.nand2tetris.org/) · build a working computer, assembler, VM and compiler. Also free on Coursera.
- [Algorithms, 4th Edition](https://algs4.cs.princeton.edu/home/) · Sedgewick and Wayne, with a free companion site and Java code. Pairs with the free Coursera course.
- [Pro Git](https://git-scm.com/book/en/v2) · free; chapters 2, 3, 7 and 10 are enough.
- [Computer Networking: A Top-Down Approach](https://gaia.cs.umass.edu/kurose_ross/) · Kurose and Ross, with free lecture videos and interactive exercises.

### Courses and videos

- [Nand to Tetris on Coursera](https://www.coursera.org/learn/build-a-computer) · free to audit.
- [MIT 6.006 Introduction to Algorithms](https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/) · full lectures and problem sets.
- [Algorithms, Part I (Coursera)](https://www.coursera.org/learn/algorithms-part1) · Sedgewick's course, in Java.
- [Practical Networking](https://www.youtube.com/@PracticalNetworking) · the clearest explanations of packet flow, subnets and TLS on YouTube.
- [Computerphile](https://www.youtube.com/@Computerphile) · short, accurate explainers on CS topics.

### References

- [roadmap.sh: Computer Science](https://roadmap.sh/computer-science) · a visual version of this section.
- [Big-O Cheat Sheet](https://www.bigocheatsheet.com/) and [VisuAlgo](https://visualgo.net/en) · complexity tables and animated data structures.
- [GeeksforGeeks DSA Tutorial](https://www.geeksforgeeks.org/dsa/dsa-tutorial-learn-data-structures-and-algorithms/) · broad coverage with many worked examples; verify details against a primary source.
- [explainshell](https://explainshell.com/), [regex101](https://regex101.com/), [man7.org](https://man7.org/linux/man-pages/) · the three tabs you keep open.
- [Julia Evans' blog](https://jvns.ca/) · the best writing on debugging, networking and Linux tools for working developers.
