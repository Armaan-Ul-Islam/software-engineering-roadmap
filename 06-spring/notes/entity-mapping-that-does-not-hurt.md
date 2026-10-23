# Entity mapping that does not hurt

> **In one sentence:** Use `SEQUENCE` identifiers so inserts can batch, make every `@ManyToOne` lazy, let the child own the foreign key with sync methods keeping both sides consistent, implement `equals` so it survives the transient-to-managed transition, and cascade only from the aggregate root to the parts it owns.

**Why it matters:** Mapping mistakes are invisible until load: an `IDENTITY` id that silently turns a batch of a thousand inserts into a thousand round trips, an eager `@ManyToOne` that drags the customer and its address into every order query, an `equals` that makes a `Set` lose entities after `persist`. Fixing them later means a migration and a code change in every place that touched the entity, so the defaults below are worth memorising.

## The idea

**Identifier generation.** `@GeneratedValue(strategy = GenerationType.IDENTITY)` relies on an auto-increment column, so Hibernate must execute each `INSERT` immediately to learn the id, and it disables JDBC batching for that entity. `SEQUENCE` lets Hibernate ask the database for a block of ids up front: with `allocationSize = 50` one `select nextval(...)` serves fifty inserts, and the inserts themselves can be batched (`spring.jpa.properties.hibernate.jdbc.batch_size=50`). The database sequence must advance by the same step (`CREATE SEQUENCE orders_seq INCREMENT BY 50`); Hibernate reads the sequence's increment at startup and fails by default when it differs. Name the sequence explicitly so the migration and the mapping agree.

**`@Version`** adds optimistic locking to any entity that can be updated concurrently (item 5.8). Put it on aggregate roots.

**`equals` and `hashCode`.** The default identity-based methods break as soon as an entity is detached and reloaded (two instances, one row). Using the generated id alone breaks the other way: before `persist` the id is null, so a transient entity added to a `HashSet` changes its hash after it is saved and can no longer be found. Two approaches survive all states. If the entity has a natural key that is set in the constructor and never changes (an ISBN, an IBAN), compare on that. Otherwise compare on the id when both are non-null and return a constant `hashCode`: equal entities keep equal hashes across every state, and the constant only costs performance in huge sets, which entity collections never are. Compare with `instanceof` and read the other side's id through its getter, because the other object may be a Hibernate proxy subclass whose fields are empty until initialised.

**Associations.** `@ManyToOne` and `@OneToOne` default to `EAGER` in JPA; write `fetch = FetchType.LAZY` on every one of them, and fetch what a use case needs explicitly (item 5.4). A `@ManyToOne` is also the right default for modelling a relationship at all: it maps to a plain foreign key, and "lines of this order" is one indexed query. Add the `@OneToMany` side only when the parent manages the children's lifecycle, mark it `mappedBy`, and keep both sides in sync with `addLine` and `removeLine` methods so the in-memory graph matches what will be written. A unidirectional `@OneToMany` without `@JoinColumn` creates a join table; with `@JoinColumn` it issues extra `UPDATE` statements to set the foreign key. `@ManyToMany` is where `List` hurts most: removing one element from a bag deletes every join row and re-inserts the rest. Use `Set`, never cascade `REMOVE` across it (you would delete the other side's rows that other parents share), and the moment the relationship needs a column of its own (quantity, since-when), map the join table as an entity with two `@ManyToOne` fields.

**Cascade and `orphanRemoval`.** `cascade = CascadeType.ALL` means "persist, merge, remove and the rest follow the parent", which is correct from an aggregate root to the parts nobody else references, and wrong on any `@ManyToOne` (removing an order line must not remove the product). `orphanRemoval = true` additionally deletes a child that is removed from the collection; `CascadeType.REMOVE` alone only acts when the parent itself is removed.

## Example: Order and OrderLine

```java
@Entity
@Table(name = "orders")
public class Order {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "orders_seq")
    @SequenceGenerator(name = "orders_seq", sequenceName = "orders_seq", allocationSize = 50)
    private Long id;

    @Version
    private long version;

    @Column(nullable = false)
    private String customerEmail;

    @OneToMany(mappedBy = "order", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<OrderLine> lines = new ArrayList<>();

    protected Order() {
    }

    public Order(String customerEmail) {
        this.customerEmail = customerEmail;
    }

    public OrderLine addLine(Product product, int quantity) {
        OrderLine line = new OrderLine(this, product, quantity);
        lines.add(line);
        return line;
    }

    public void removeLine(OrderLine line) {
        lines.remove(line);
        line.detachFromOrder();
    }

    public Long getId() {
        return id;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof Order otherOrder)) {
            return false;
        }
        return id != null && id.equals(otherOrder.getId());
    }

    @Override
    public int hashCode() {
        return Order.class.hashCode();
    }
}
```

```java
@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "order_line_seq")
    @SequenceGenerator(name = "order_line_seq", sequenceName = "order_line_seq", allocationSize = 50)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private Order order;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id", nullable = false)
    private Product product;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {
    }

    OrderLine(Order order, Product product, int quantity) {
        this.order = order;
        this.product = product;
        this.quantity = quantity;
    }

    void detachFromOrder() {
        this.order = null;
    }

    public Long getId() {
        return id;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof OrderLine otherLine)) {
            return false;
        }
        return id != null && id.equals(otherLine.getId());
    }

    @Override
    public int hashCode() {
        return OrderLine.class.hashCode();
    }
}
```

The matching migration (PostgreSQL):

```sql
CREATE SEQUENCE orders_seq START WITH 1 INCREMENT BY 50;
CREATE SEQUENCE order_line_seq START WITH 1 INCREMENT BY 50;

CREATE TABLE orders (
    id              bigint PRIMARY KEY,
    version         bigint NOT NULL,
    customer_email  text   NOT NULL
);

CREATE TABLE order_line (
    id          bigint PRIMARY KEY,
    order_id    bigint NOT NULL REFERENCES orders (id),
    product_id  bigint NOT NULL REFERENCES product (id),
    quantity    integer NOT NULL
);

CREATE INDEX order_line_order_id_idx ON order_line (order_id);
```

What this buys you: `orderRepository.save(order)` with three lines and batching enabled produces one `nextval` per sequence and two batched `INSERT` statements. Removing a line through `removeLine` deletes exactly that row at flush. Nothing loads the product or the order unless asked. The index on `order_id` is the one most people forget: PostgreSQL does not create indexes for foreign keys.

## Pitfalls

- `IDENTITY` because "that is what the database does". It works, and it throws away batching forever. If you inherit such a schema, the gain from switching is large enough to justify the migration.
- `@ManyToOne` without `fetch = LAZY`. One eager association per entity is enough to make every query a join or an extra select; three nested ones fetch half the schema.
- Lombok's `@Data`, `@EqualsAndHashCode` or `@ToString` on entities. They touch every field including lazy collections, which initialises them (or throws outside a session, often from a log statement), and the hash changes on every update.
- Exposing the mutable `List` from `getLines()`. Callers add to it directly and skip the sync method, so the child's `order` field stays null and the insert fails on `order_id NOT NULL`.
- `CascadeType.ALL` on `@ManyToOne` or `@ManyToMany`. Deleting one order deletes the product; deleting one student deletes the courses.
- Mapping a join table with extra columns as `@ManyToMany`. The columns have nowhere to live; make the join table an entity.

## Check yourself

1. Why does an `IDENTITY` identifier prevent Hibernate from batching inserts, while `SEQUENCE` with `allocationSize = 50` does not?
2. An `Order` is added to a `HashSet` before `persist` and looked up after. With id-based `equals` and an id-based `hashCode`, what happens? With the constant `hashCode`?
3. A colleague removes a line with `order.getLines().remove(line)` on a mutable list and no sync method. What is written at flush, and what does the `NOT NULL` constraint on `order_id` have to do with it?
4. When would you replace a `@ManyToMany` with an entity for the join table, and what changes in the two owning classes?

## Go deeper

- [Vlad Mihalcea: Identity, sequence and table generators](https://vladmihalcea.com/hibernate-identity-sequence-and-table-sequence-generator/) · the batching argument with measurements.
- [Vlad Mihalcea: equals, hashCode and toString for entities](https://vladmihalcea.com/the-best-way-to-implement-equals-hashcode-and-tostring-with-jpa-and-hibernate/) · the state-transition test every `equals` implementation should pass.
- [Vlad Mihalcea: The best way to map a @OneToMany](https://vladmihalcea.com/the-best-way-to-map-a-onetomany-association-with-jpa-and-hibernate/) · unidirectional versus bidirectional with the SQL each generates.
- [Vlad Mihalcea: The best way to use @ManyToMany](https://vladmihalcea.com/the-best-way-to-use-the-manytomany-annotation-with-jpa-and-hibernate/) · why `Set`, and when to promote the join table to an entity.

---

Part of [Spring](../README.md) · items 5.2, 5.3
