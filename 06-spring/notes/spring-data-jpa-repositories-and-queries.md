# Spring Data JPA repositories and queries

> **In one sentence:** A Spring Data repository is an interface Spring implements at startup from the method names, `@Query` strings and projection types you declare, which removes boilerplate for the common eighty percent of queries and should be bypassed with a custom fragment or `JdbcClient` for the rest rather than bent.

**Why it matters:** The derived-query mechanism is so convenient that teams end up with `findByStatusAndCustomerEmailIgnoreCaseAndCreatedAtBetweenOrderByCreatedAtDesc` and a `Page` query that counts a hundred-million-row table on every request. Knowing the five or six tools and the limits of each keeps the repository layer readable and the SQL predictable.

## The idea

`JpaRepository<Order, Long>` gives you `SimpleJpaRepository` behind a proxy: `findById`, `findAll`, `save`, `saveAll`, `delete`, paging and sorting, all transactional (reads with `readOnly = true`). On top of that you add methods, and each kind is implemented differently.

**Derived queries** are parsed from the method name: `findByCustomerEmailAndStatus` becomes `where o.customerEmail = ?1 and o.status = ?2`. Supported subjects include `find`, `exists`, `count`, `delete`, `findFirst3`, `findDistinct`; supported keywords include `Between`, `LessThan`, `In`, `IsNull`, `Like`, `IgnoreCase`, `OrderBy`. The name is validated at startup, so a typo fails fast. The limit is readability: when a name needs more than two conditions, or needs a join fetch, a group by or a projection with an expression, write the query.

**`@Query`** takes JPQL by default and SQL with `nativeQuery = true`. Named parameters (`:status`) bind to `@Param("status")` or to the parameter name when compiled with `-parameters`, which the Boot plugins do. A native query with `Pageable` needs a `countQuery`, since Spring Data cannot derive a count from arbitrary SQL. Text blocks make multi-line queries readable.

**`@Modifying`** marks a JPQL `update` or `delete`. These run straight against the database and bypass the persistence context, so managed entities keep their stale state: `clearAutomatically = true` clears the context afterwards and `flushAutomatically = true` flushes pending changes before. A declared query method is not transactional by itself; a modifying query without `@Transactional` fails with `TransactionRequiredException: Executing an update/delete query`.

**Projections** return less than an entity. An interface with getters (`Long getId(); String getCustomerEmail();`) is a closed projection: Spring Data selects only those columns. A record or class with a matching constructor is a class-based projection, written as `select new com.example.OrderSummary(o.id, c.email) ...` or returned directly from a derived query. Projections are the right return type for lists and screens; entities are for use cases that modify state.

**`Page` versus `Slice` versus `Window`.** `Page<T>` runs the query and a `count` query, so it can report total elements and pages; the count is the expensive half on large tables. `Slice<T>` asks for `size + 1` rows and only knows whether a next page exists. Both use offset pagination, which gets slower with each page. `Window<T>` with `ScrollPosition.keyset()` (Spring Data 3.1 and later) implements keyset pagination: the next page is `where (createdAt, id) < (?, ?)`, constant cost at any depth, at the price of no random access.

**`Specification<T>`** builds a Criteria predicate from a lambda and composes with `and`/`or`. It is the tool for search screens with optional filters; the repository extends `JpaSpecificationExecutor<Order>`. The individual specifications stay small and testable.

**Custom fragments** are where you write the implementation yourself. Declare an interface, implement it in a class named with the `Impl` suffix (`OrderSearchRepositoryImpl`), inject the `EntityManager`, and let the repository interface extend both. Spring Data wires the fragment into the same proxy, so callers see one repository.

**`JdbcClient`** (Spring Framework 6.1) is for the queries that are not about entities at all: reports, aggregates, bulk updates, anything where the SQL is the point. It maps rows onto records by column name and needs no mapping metadata.

## Example: one repository, each kind of query

```java
public interface OrderRepository extends JpaRepository<Order, Long>, JpaSpecificationExecutor<Order>, OrderSearchRepository {

    List<Order> findByCustomerEmailAndStatusOrderByCreatedAtDesc(String customerEmail, OrderStatus status);

    boolean existsByCustomerEmailAndStatus(String customerEmail, OrderStatus status);

    @Query("""
            select o from Order o
            join fetch o.customer
            where o.status = :status and o.createdAt >= :since
            """)
    List<Order> findRecentByStatus(OrderStatus status, Instant since);

    @Query(value = "select * from orders where created_at >= :since",
           countQuery = "select count(*) from orders where created_at >= :since",
           nativeQuery = true)
    Page<Order> findCreatedSince(Instant since, Pageable pageable);

    @Transactional
    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("update Order o set o.status = :newStatus where o.status = :currentStatus and o.createdAt < :before")
    int expire(OrderStatus currentStatus, OrderStatus newStatus, Instant before);

    List<OrderDigest> findByStatus(OrderStatus status);

    @Query("select new com.example.orders.OrderSummary(o.id, c.email, o.total) from Order o join o.customer c where o.status = :status")
    List<OrderSummary> summariesByStatus(OrderStatus status);

    Slice<Order> findAllByStatus(OrderStatus status, Pageable pageable);

    Window<Order> findFirst20ByStatusOrderByCreatedAtDescIdDesc(OrderStatus status, ScrollPosition position);
}

public interface OrderDigest {
    Long getId();
    OrderStatus getStatus();
    Instant getCreatedAt();
}

public record OrderSummary(Long id, String customerEmail, BigDecimal total) {
}
```

A specification and its use:

```java
public final class OrderSpecifications {

    private OrderSpecifications() {
    }

    public static Specification<Order> hasStatus(OrderStatus status) {
        return (root, query, builder) -> builder.equal(root.get("status"), status);
    }

    public static Specification<Order> createdAfter(Instant since) {
        return (root, query, builder) -> builder.greaterThanOrEqualTo(root.get("createdAt"), since);
    }
}

Page<Order> page = orderRepository.findAll(hasStatus(OrderStatus.NEW).and(createdAfter(since)), PageRequest.of(0, 50));
```

The custom fragment:

```java
public interface OrderSearchRepository {
    List<Order> search(OrderFilter filter);
}

public class OrderSearchRepositoryImpl implements OrderSearchRepository {

    private final EntityManager entityManager;

    public OrderSearchRepositoryImpl(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Override
    public List<Order> search(OrderFilter filter) {
        CriteriaBuilder builder = entityManager.getCriteriaBuilder();
        CriteriaQuery<Order> criteria = builder.createQuery(Order.class);
        Root<Order> order = criteria.from(Order.class);
        List<Predicate> predicates = new ArrayList<>();
        if (filter.status() != null) {
            predicates.add(builder.equal(order.get("status"), filter.status()));
        }
        if (filter.customerEmail() != null) {
            predicates.add(builder.equal(order.get("customer").get("email"), filter.customerEmail()));
        }
        criteria.where(predicates.toArray(Predicate[]::new));
        return entityManager.createQuery(criteria).setMaxResults(filter.limit()).getResultList();
    }
}
```

And the report that does not want entities at all:

```java
public record OrderCountRow(String customerEmail, long orderCount) {
}

List<OrderCountRow> rows = jdbcClient.sql("""
        select c.email as customer_email, count(o.id) as order_count
        from customer c
        join orders o on o.customer_id = c.id
        where o.created_at >= :since
        group by c.email
        order by order_count desc
        """)
        .param("since", since)
        .query(OrderCountRow.class)
        .list();
```

`customer_email` maps onto `customerEmail` by Spring's underscore-to-camel-case convention; no annotations needed.

## Pitfalls

- A derived method name that needs a comment to understand. Replace it with `@Query` and a short method name that states intent (`findOverdueInvoices`).
- `Page` where `Slice` or `Window` would do. "Load more" buttons and infinite scroll never need the total count; drop it and the count query disappears.
- `@Modifying` without `clearAutomatically`. Entities loaded earlier in the same transaction still show the old values, and a later dirty-check may write them back over your bulk update.
- Interface projections on a `@Query` without aliases. The getters are matched by name, so `select o.id, c.email ...` must be `select o.id as id, c.email as customerEmail ...`.
- `findAll()` followed by filtering in Java. The whole table crosses the wire; move the condition into the query.
- Treating `save` as required after modifying a loaded entity. Within a transaction dirty checking writes the change anyway; the call is noise and, on a detached entity, a blind `merge` (item 5.1).
- Native SQL with entity results plus `join fetch`-style column lists. Native queries return entities only when the columns match the mapping exactly; for anything else return a projection or use `JdbcClient`.

## Check yourself

1. Why does a declared `@Modifying` query need `@Transactional` when `deleteById` from `JpaRepository` does not?
2. A search screen has six optional filters. Compare derived queries, `Specification` and a custom fragment for it, and pick one.
3. Explain the extra query `Page` runs that `Slice` does not, and when that query becomes the bottleneck.
4. A monthly revenue report groups by customer and month. Repository projection or `JdbcClient`, and what decides it?

## Go deeper

- [Spring Data JPA: Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html) · derived query keywords, `@Query`, named parameters, native queries and paging.
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/) · projections, specifications, custom implementations and scrolling (`Window`) are each a short chapter.
- [Vlad Mihalcea: DTO projections](https://vladmihalcea.com/the-best-way-to-map-a-projection-query-to-a-dto-with-jpa-and-hibernate/) · why projections beat entities for read screens, with the generated SQL.
- [Spring: JdbcClient](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html#jdbc-JdbcClient) · the fluent API and its row mapping rules.
- [Baeldung: Spring Data JPA @Query](https://www.baeldung.com/spring-data-jpa-query) · worked examples of JPQL and native queries with parameters and sorting.

---

Part of [Spring](../README.md) · items 5.6, 5.10
