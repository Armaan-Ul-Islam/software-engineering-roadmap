# Java, Spring and SQL interview questions: a self-check

> **In one sentence:** Backend interviews for Java roles include a round of short knowledge questions on the JVM, collections, concurrency, the Spring container, transactions, JPA, security and SQL, and the way to prepare is to answer each one aloud in two to four sentences, then check against the model answer below.

**Why it matters:** These questions are cheap for an interviewer to ask and brutal to bluff: "how does `HashMap` work?" or "what happens when a `@Transactional` method calls another on `this`?" has a right answer, and a vague one ends the round. Every answer below is also something you will need at work; the self-check doubles as a list of the gaps in your understanding of the stack you use daily.

## The idea

Cover the list in three passes: say each answer aloud before reading the model answer and mark the misses; a week later, only the marked ones; the week before the interviews, everything, timed at one minute per question. The model answers are deliberately short; the follow-up questions are where the deeper roadmap items pay off. Where behaviour depends on a version, the answers assume Java 21, Spring Boot 3 and PostgreSQL.

## Example: the questions and model answers

### JVM

1. **What lives on the heap and what on the stack?** Objects and arrays live on the heap, shared by all threads and reclaimed by the garbage collector. Each thread has its own stack of frames holding local variables, primitives and references to heap objects. A `StackOverflowError` is a stack that grew past its limit, usually from unbounded recursion; an `OutOfMemoryError` is a heap that cannot be reclaimed enough to satisfy an allocation.

2. **How does generational garbage collection work, and which collector is the default?** Most objects die young, so the heap is split into a young generation (collected often and cheaply) and an old generation (collected rarely). Objects that survive several young collections are promoted. G1 has been the default since Java 9; it divides the heap into regions and aims for a pause-time goal, and ZGC is the choice when pauses must stay in the low milliseconds on large heaps.

### Collections

3. **How does `HashMap` work?** `hashCode()` selects a bucket in an array; entries in the same bucket form a linked list, which becomes a red-black tree when it grows past eight entries and the table has at least 64 buckets (below that the table is resized instead). When the number of entries exceeds capacity times the load factor (0.75), the array doubles and entries are redistributed. Lookup is O(1) on average and O(log n) in a treeified bucket.

4. **What is the `equals` and `hashCode` contract, and what breaks when it is violated?** Equal objects must have equal hash codes; unequal objects may share one. If `equals` is overridden without `hashCode`, two equal keys can land in different buckets and `map.get` returns `null` for a key you just put. Mutating a key after insertion breaks it the same way, which is why keys should be immutable (records are a good fit).

5. **`ArrayList` or `LinkedList`?** `ArrayList` almost always: contiguous memory, O(1) index access, O(1) amortised append, and cache-friendly iteration. `LinkedList` has O(1) insertion at a known node but O(n) to reach the node, and each element costs an extra object. For a queue or stack use `ArrayDeque`.

6. **Why is `String` immutable, and what does the `Integer` cache do to `==`?** Immutability makes strings safe to share, cache (the string pool) and use as map keys, and lets the hash code be computed once. `Integer.valueOf` caches -128 to 127, so `==` on boxed integers is `true` in that range and `false` outside it; always compare boxed values with `equals`.

### Concurrency

7. **What does `synchronized` guarantee that `volatile` does not?** Both create a happens-before edge, so both give visibility. `synchronized` additionally gives mutual exclusion, so a read-modify-write such as `count++` is atomic inside a `synchronized` block and is not with `volatile`. `volatile` is for a flag or a reference that is written by one thread and read by others; for counters use `AtomicInteger` or `LongAdder`.

8. **What is happens-before, in one breath?** The Java Memory Model only guarantees that a thread sees another thread's write when a happens-before chain connects them: a volatile write to a later read of the same field, a monitor release to a later acquire of the same lock, `Thread.start` to the thread's actions, the thread's actions to `join` returning. Without such an edge, a stale value may be seen forever, and the bug typically only appears after JIT compilation or on ARM hardware.

9. **When would you choose `ReentrantLock` over `synchronized`?** When you need `tryLock` with a timeout, interruptible waiting, fairness, or multiple `Condition` queues on one lock. `synchronized` is simpler, cannot leak an unlock, and performs as well in the uncontended case.

10. **What are the four conditions for deadlock, and which one do you break in practice?** Mutual exclusion, hold and wait, no preemption, and circular wait. The practical fix is to break circular wait by always acquiring locks in the same global order, or to break hold and wait with `tryLock` and a timeout.

11. **What are virtual threads?** Since Java 21, a virtual thread is a thread scheduled by the JVM onto a small pool of platform threads; when it blocks on I/O, it unmounts and the carrier runs another one. They make thread-per-request cheap for I/O-bound services, so a blocking style scales without reactive code. They do not speed up CPU-bound work.

### Spring: the container

12. **What is inversion of control, and why is constructor injection preferred?** The container creates beans and wires their dependencies instead of the beans looking them up. Constructor injection makes dependencies explicit and final, fails fast on cycles, and lets tests construct the object with fakes without Spring. Field injection hides dependencies and needs reflection or a container to test.

13. **What are the bean scopes, and what is the default?** Singleton (one instance per container) is the default; prototype creates a new instance per injection or lookup; request, session and application are web scopes. A prototype injected into a singleton is created once, at the singleton's creation, unless you inject an `ObjectProvider` or a scoped proxy.

14. **How does Spring Boot auto-configuration decide what to create?** Auto-configuration classes listed in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` are evaluated after your own configuration, and each is guarded by conditions such as `@ConditionalOnClass` and `@ConditionalOnMissingBean`. Declaring your own bean of the same type therefore switches the default off.

15. **How do Spring proxies work, and when does a proxy not apply?** AOP features (`@Transactional`, `@Async`, `@Cacheable`, security annotations) wrap the bean in a proxy, a JDK dynamic proxy for interfaces or a CGLIB subclass otherwise. A call from a method of the bean to another method of the same bean goes through `this`, not the proxy, so the annotation on the called method is ignored. Private and final methods cannot be proxied either.

### Spring: transactions and JPA

16. **What are the defaults of `@Transactional`?** Propagation `REQUIRED` (join the current transaction or start one), rollback only for unchecked exceptions and `Error`, the database's default isolation level, no timeout, and read-write. Checked exceptions commit unless `rollbackFor` says otherwise. Catching an exception from an inner `REQUIRED` method does not undo the rollback-only mark, and the commit fails with `UnexpectedRollbackException`.

17. **What is the N+1 problem, and how do you fix it?** Loading a list of entities and then touching a lazy association on each issues one query for the list and one per row. Fix it with a `JOIN FETCH` in the JPQL query, an `@EntityGraph` on the repository method, or Hibernate's batch fetching, and verify by counting statements in a test. Turn off `spring.jpa.open-in-view` so lazy loading in the view layer cannot hide the problem.

18. **What are the JPA entity states?** New (not yet associated with a persistence context), managed (tracked; changes are flushed at commit), detached (the context closed; changes are not tracked), and removed. `LazyInitializationException` is an access to a lazy association on a detached entity. `save` on a detached entity merges a copy; the instance you passed is not the managed one.

19. **How does optimistic locking work in JPA?** A `@Version` column is included in the `WHERE` clause of every update and incremented. If another transaction changed the row in between, the update matches zero rows and Hibernate throws `OptimisticLockException`, which the application turns into a retry or a conflict response. It prevents lost updates without holding database locks.

### Spring Security

20. **How does a request pass through Spring Security?** A servlet filter delegates to a `SecurityFilterChain` bean, an ordered list of filters that authenticate (extract credentials, create an `Authentication` in the `SecurityContext`) and authorise (match the request against the rules declared with `authorizeHttpRequests`). Method security (`@PreAuthorize`) adds a second check at the service layer. Authentication answers "who", authorisation answers "may they".

21. **Session or stateless token, and what about CSRF?** With session cookies the browser attaches credentials automatically, so CSRF protection must stay on for state-changing requests. With a bearer token (a JWT validated by the resource server filter) nothing is attached automatically, so CSRF can be disabled, but the token cannot be revoked before expiry without extra state. Passwords are stored with a slow adaptive hash; `BCryptPasswordEncoder` is the usual choice.

### Databases and SQL

22. **Explain the join types.** An inner join returns rows with a match on both sides; a left join keeps every left row and fills the right side with nulls; a right join is the mirror; a full outer join keeps both. A cross join is every combination. Filtering on the right table in the `WHERE` clause of a left join turns it into an inner join, because the null rows fail the filter; put that condition in the `ON` clause instead.

23. **How does a B-tree index speed up a query, and why does column order in a composite index matter?** The index stores the key values in sorted order with pointers to rows, so an equality or range condition is a tree descent plus a scan of neighbouring leaves instead of a scan of the table. A composite index on `(customer_id, created_at)` serves conditions on `customer_id` alone or on both, but not on `created_at` alone, because the entries are sorted by the first column first. An index that contains every column the query needs is covering and avoids visiting the table.

24. **What are the isolation levels, and which does PostgreSQL use by default?** Read committed (the default) sees only committed data but each statement sees a new snapshot, so two reads in one transaction can differ and a read-then-write can lose an update. Repeatable read fixes the snapshot at the first statement and aborts a writer that conflicts with a concurrent update. Serializable additionally detects write skew. Any load-modify-save in application code needs `SELECT ... FOR UPDATE`, an atomic `UPDATE ... SET x = x + 1`, or optimistic locking.

25. **How do you read an `EXPLAIN ANALYZE` plan?** Read from the innermost node outward; each node shows the estimated and actual rows, and a large gap means stale statistics (`ANALYZE` the table). A sequential scan on a large table filtered by an indexed column means the index was not usable, often because a function or a type cast wraps the column. A nested loop with a large outer side, or a hash join that spills to disk, explains most slow queries.

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, total
FROM orders
WHERE customer_id = 42 AND created_at >= now() - interval '30 days';
```

The desirable plan is an `Index Scan` on an index led by `customer_id`; if it shows `Seq Scan` with `Rows Removed by Filter` in the millions, the index is missing or not applicable.

## Pitfalls

- Reciting definitions without a consequence. "Volatile guarantees visibility" is half an answer; add "and not atomicity, so `count++` still races".
- Answering for the wrong version. The default collector, virtual threads and Boot's auto-configuration mechanics changed across versions; state the version you assume.
- Memorising the ANSI isolation table and applying it to PostgreSQL. Its repeatable read is snapshot isolation and prevents phantoms; its default is read committed.
- Describing the N+1 fix as "use eager fetching". Eager fetching on the mapping makes every query pay; the fix is per query.

## Check yourself

1. Which five questions above did you answer incompletely on the first pass, and which roadmap items (in Java, Spring, Databases and Memory and Concurrency) cover them?
2. For questions 15 and 16, write the three-line code example that demonstrates the bug (a `@Transactional` method called via `this`) and say what you would observe in the logs.
3. Rewrite the answer to question 24 for MySQL InnoDB. Which sentences change?
4. Take the `EXPLAIN` query above and name two changes to the SQL that would stop the index from being used, and one index definition that would make the query index-only.

## Go deeper

- [Baeldung: Java interview questions](https://www.baeldung.com/java-interview-questions) · a longer bank, grouped by topic, with links to full articles.
- [Baeldung: Spring interview questions](https://www.baeldung.com/spring-interview-questions) · the container, Boot, MVC, data and security questions with worked answers.
- [PostgreSQL Exercises](https://pgexercises.com/) · joins, aggregates and window functions as runnable exercises against a real schema.
- [roadmap.sh: Backend interview questions](https://roadmap.sh/questions/backend) · the broader backend set, useful for spotting topics outside this list.

---

Part of [DSA & Interviews](../README.md) · items 8.2, 8.3
