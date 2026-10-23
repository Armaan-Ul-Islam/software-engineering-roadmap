# Lazy loading, N+1 and fetch strategies

> **In one sentence:** Lazy associations are placeholders that run a query the first time you touch them, so touching one inside a loop runs one query per row (N+1) and touching one after the transaction ends throws `LazyInitializationException`; the cure is to fetch what the use case needs in the query itself, and to turn off Open Session in View so the symptom cannot hide.

**Why it matters:** N+1 is the most common performance defect in JPA applications and it passes every test, because with ten rows it is eleven fast queries. In production with ten thousand rows it is a timeout. Open Session in View, which Spring Boot enables by default, makes the problem invisible in development by keeping the session open during JSON serialisation, so the first time anyone notices is in the database's slow-query log.

## The idea

A lazy `@ManyToOne` is a Hibernate proxy: a subclass of the entity holding only the id, which loads the row on the first method call that needs it. A lazy collection is a `PersistentBag` or `PersistentSet` that loads on first access. Both need the persistence context that created them to be open. After the transaction ends they are detached, and the first access fails:

```text
org.hibernate.LazyInitializationException: failed to lazily initialize a collection of role:
com.example.Order.lines: could not initialize proxy - no Session
```

**N+1** is the lazy mechanism working as designed in the wrong place. Load N orders in one query, then read `order.getCustomer().getEmail()` for each: N further queries, one per proxy. Eager fetching does not fix it. `@ManyToOne(fetch = EAGER)` on an entity loaded through a JPQL query still runs one secondary select per row, because the query decides what is joined, not the mapping. Eager only changes the symptom from "N+1 when accessed" to "N+1 always".

The fixes, in the order to try them:

1. **`JOIN FETCH`** in the JPQL for that use case: `select o from Order o join fetch o.customer left join fetch o.lines`. One query, the associations are initialised, and nothing else in the application changes. Hibernate 6 removes the duplicate parent rows that the collection join produces, so `distinct` is no longer needed.
2. **`@EntityGraph`** on a Spring Data method: `@EntityGraph(attributePaths = {"customer", "lines"})`. Same SQL as a fetch join, declared on the repository method instead of in the query string, and usable on derived queries and `findAll`.
3. **`@BatchSize(size = 50)`** on the association (or `spring.jpa.properties.hibernate.default_batch_fetch_size=50` globally). Lazy loading still happens, but Hibernate loads proxies in groups with `where id in (?, ?, ...)`, turning N+1 into N/50+1. This is the right tool when the parent query must stay paginated, because a fetch join on a collection cannot be paginated in SQL (Hibernate warns `firstResult/maxResults specified with collection fetch; applying in memory` and loads the whole table).
4. **DTO projections** when the screen only needs a few columns: `select new com.example.OrderSummary(o.id, c.email, size(o.lines)) from Order o join o.customer c`, or an interface projection in Spring Data (item 5.6). No entities, no proxies, no lazy loading possible.

Two fetch joins on `List` collections in one query fail with `MultipleBagFetchException: cannot simultaneously fetch multiple bags`. Hibernate refuses because the result is a cartesian product with no way to tell which combination of rows is a duplicate. Fetch one collection per query (the second query resolves to the same managed parents, so both collections end up initialised), or change one collection to a `Set`.

**Open Session in View** is an interceptor (`OpenEntityManagerInViewInterceptor`) that opens the `EntityManager` when the request starts and closes it after the response is written, so the transaction ends in the service but the persistence context survives into the controller and the JSON serialiser. Boot enables it by default and logs a warning at startup: `spring.jpa.open-in-view is enabled by default. Therefore, database queries may be performed during view rendering.` It exists so that templates and serialisers can touch lazy associations without failing. The cost: every lazy access in the web layer is a query running outside the service's transaction, without its isolation guarantees, holding a pooled connection while the response is written; N+1 problems become invisible in development; and the data layer's boundary disappears, because any getter anywhere may hit the database. Set `spring.jpa.open-in-view=false`, let each `LazyInitializationException` point at a use case that was not fetching what it needed, and fix the query. Return DTOs from the service so that the controller cannot trigger a load even by accident.

## Example: the N+1 log and the rewrite

```java
@Transactional(readOnly = true)
public List<OrderSummary> summaries() {
    return orderRepository.findAll().stream()
            .map(order -> new OrderSummary(order.getId(), order.getCustomer().getEmail(), order.getLines().size()))
            .toList();
}
```

With `logging.level.org.hibernate.SQL=DEBUG` and three orders:

```text
select o1_0.id,o1_0.customer_id,o1_0.version from orders o1_0
select c1_0.id,c1_0.email from customer c1_0 where c1_0.id=?
select l1_0.order_id,l1_0.id,l1_0.product_id,l1_0.quantity from order_line l1_0 where l1_0.order_id=?
select c1_0.id,c1_0.email from customer c1_0 where c1_0.id=?
select l1_0.order_id,l1_0.id,l1_0.product_id,l1_0.quantity from order_line l1_0 where l1_0.order_id=?
select c1_0.id,c1_0.email from customer c1_0 where c1_0.id=?
select l1_0.order_id,l1_0.id,l1_0.product_id,l1_0.quantity from order_line l1_0 where l1_0.order_id=?
```

Seven queries for three rows: 1 + 2N. The rewrite:

```java
public interface OrderRepository extends JpaRepository<Order, Long> {

    @Query("select o from Order o join fetch o.customer left join fetch o.lines")
    List<Order> findAllWithCustomerAndLines();
}
```

```text
select o1_0.id,c1_0.id,c1_0.email,l1_0.order_id,l1_0.id,l1_0.product_id,l1_0.quantity,o1_0.version
from orders o1_0
join customer c1_0 on c1_0.id=o1_0.customer_id
left join order_line l1_0 on o1_0.id=l1_0.order_id
```

One query regardless of N. The same thing without a query string:

```java
@Override
@EntityGraph(attributePaths = {"customer", "lines"})
List<Order> findAll();
```

To make the regression impossible to miss, enable `spring.jpa.properties.hibernate.generate_statistics=true` during development; Hibernate then logs a `Session Metrics` block at the end of every session with the number of JDBC statements it executed, and a test can assert on the same numbers through `SessionFactory.getStatistics()`.

## Pitfalls

- Fixing `LazyInitializationException` with `EAGER`. It makes every query for that entity load the association, including the ones that did not need it, and still does not stop N+1 for query results.
- Fixing it with `@Transactional` on the controller. Now the transaction spans serialisation and the lazy loads still run one by one; you have reinvented Open Session in View with extra steps.
- Fetch join plus `Pageable`. The page is computed in memory after loading everything. Paginate the parent query and use `@BatchSize` or a second query for the collection.
- Leaving `spring.jpa.open-in-view` at its default because "nothing breaks". Nothing breaks in development. Turn it off before the first real load test, not after.
- Fetch joining two `List` collections. `MultipleBagFetchException` at startup for a named query, or at first execution otherwise; split the fetches.
- Reading `collection.size()` to "check if there are any". It initialises the whole collection. Query the count, or use `isEmpty()` only on a collection you fetched anyway.

## Check yourself

1. Why does `@ManyToOne(fetch = FetchType.EAGER)` not prevent N+1 for entities loaded with a JPQL query? What does it change?
2. You need a paginated list of orders with their lines. Why can a fetch join not do it, and which two combinations work?
3. What does Open Session in View change about where a query can run, and why does that hide N+1 during development?
4. A `select o from Order o join fetch o.lines join fetch o.payments` fails. Name the exception and two fixes, and say which one you would choose when both collections are small.

## Go deeper

- [Vlad Mihalcea: N+1 query problem](https://vladmihalcea.com/n-plus-1-query-problem/) · how to detect it automatically in tests and the fixes with their SQL.
- [Vlad Mihalcea: MultipleBagFetchException](https://vladmihalcea.com/hibernate-multiplebagfetchexception/) · why the exception exists and the multi-query fix.
- [Vlad Mihalcea: The Open Session in View anti-pattern](https://vladmihalcea.com/the-open-session-in-view-anti-pattern/) · the sequence diagram of a request with OSIV and the costs it hides.
- [Baeldung: Eager/Lazy Loading in Hibernate](https://www.baeldung.com/hibernate-lazy-eager-loading) · the proxy mechanics for both association types.
- [Baeldung: Spring Open Session in View](https://www.baeldung.com/spring-open-session-in-view) · what Boot configures and how to turn it off.

---

Part of [Spring](../README.md) · items 5.4, 5.5
