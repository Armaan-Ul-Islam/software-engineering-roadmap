# SQL injection and prepared statements

> **In one sentence:** SQL injection happens when user input is spliced into the text of a query so the database parses it as SQL; prepared statements send the query text and the values separately, so a value can never change what the query does.

**Why it matters:** Injection has been on every OWASP Top 10 and still ships in new code, usually in the one dynamic query (search, sort, report) that the ORM did not cover. A single injectable query against a database user with broad rights is a complete data breach. The fix is mechanical, which is why interviewers expect more than "use prepared statements": they want the cases where binding does not apply and what you do then.

## The idea

A query built by concatenation hands the database a single string:

```java
String sql = "SELECT id, email FROM account WHERE username = '" + username + "'";
```

For `alice` the database sees `WHERE username = 'alice'`. For the textbook input `' OR '1'='1` it sees `WHERE username = '' OR '1'='1'`, which is true for every row. The parser cannot tell where your SQL ended and the data began, because by the time it runs there is no difference: it is all one string. From there an attacker appends `UNION SELECT` to read other tables, or uses boolean and timing differences to extract data one bit at a time when nothing is displayed. The details of exploitation do not matter for the defence; the root cause does: **data was parsed as code**.

Escaping quotes treats the symptom. It fails for numeric contexts (`WHERE id = ` + input has no quotes to escape), for character-set edge cases, and for the next developer who forgets. The fix is to keep data out of the parser entirely. A **prepared statement** sends the SQL text with placeholders, and the values separately. With PostgreSQL the JDBC driver uses the extended query protocol: the text is parsed once, then the values are bound to the placeholders as typed parameters. A bound value is only ever a value; `' OR '1'='1` becomes a 13-character username that nobody has.

Every data-access API in a Spring application has a bound form:

| API | Bound (safe) | Concatenated (injectable) |
|---|---|---|
| JDBC | `prepareStatement("... = ?")` then `setString(1, value)` | `createStatement().executeQuery("... = '" + value + "'")` |
| `JdbcTemplate` | `query(sql, rowMapper, value)` with `?` in the SQL | `query("..." + value, rowMapper)` |
| `NamedParameterJdbcTemplate` | `:name` with a `MapSqlParameterSource` | string building |
| JPA and Hibernate | `createQuery("... = :name").setParameter("name", value)` | `createQuery("... = '" + value + "'")` |
| Spring Data | derived queries, `@Query` with `:name` or `?1`, including `nativeQuery = true` | custom repository code that concatenates |

Binding covers values. It cannot cover **identifiers and structure**: a column in `ORDER BY`, a table name, `ASC` or `DESC`, or whether a `WHERE` clause exists at all. For those the only defence is an allow-list: the user's input selects an entry in a map you own, and only the map's values reach the SQL.

Two more things complete the picture. **Second-order injection**: a value stored safely through a prepared statement is read back later and concatenated into another query. A display name of `admin'--` is harmless on insert and fatal in the nightly job that builds `DELETE FROM session WHERE username = '...'` by hand. Data from your own database is still data; every query binds. **Least privilege**: the connection's database role bounds the damage of the injection you did not find. A role that can only `SELECT`, `INSERT`, `UPDATE` and `DELETE` on the application's tables cannot drop them, alter them or read files from the server.

## Example: the vulnerable call, the fix, and a safe dynamic sort

The vulnerable version. A legitimate user named `O'Brien` breaks it with a syntax error: correctness and security fail together, which is often how injection is found.

```java
public Optional<Account> findByUsername(Connection connection, String username) throws SQLException {
    String sql = "SELECT id, email FROM account WHERE username = '" + username + "'";
    try (Statement statement = connection.createStatement();
         ResultSet resultSet = statement.executeQuery(sql)) {
        if (!resultSet.next()) {
            return Optional.empty();
        }
        return Optional.of(new Account(resultSet.getLong("id"), resultSet.getString("email")));
    }
}
```

The fixed version. The SQL text is a constant; the value travels separately.

```java
public Optional<Account> findByUsername(Connection connection, String username) throws SQLException {
    String sql = "SELECT id, email FROM account WHERE username = ?";
    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setString(1, username);
        try (ResultSet resultSet = statement.executeQuery()) {
            if (!resultSet.next()) {
                return Optional.empty();
            }
            return Optional.of(new Account(resultSet.getLong("id"), resultSet.getString("email")));
        }
    }
}
```

A dynamic sort cannot be bound, so the request parameter picks a key and the code supplies the column:

```java
private static final Map<String, String> SORT_COLUMNS = Map.of(
        "created", "created_at",
        "total", "total_cents",
        "customer", "customer_name");

public List<Order> findOrders(long customerId, String sortKey, boolean descending) {
    String column = SORT_COLUMNS.get(sortKey);
    if (column == null) {
        throw new IllegalArgumentException("unknown sort key: " + sortKey);
    }
    String sql = "SELECT id, created_at, total_cents, customer_name FROM orders WHERE customer_id = ? ORDER BY "
            + column + (descending ? " DESC" : " ASC");
    return jdbcTemplate.query(sql, ORDER_ROW_MAPPER, customerId);
}
```

The concatenated text comes from the map's values, which the code owns; the user only chooses among them. In Spring Data the same map feeds `Sort.by(direction, property)`. Spring Data JPA rejects sort properties that contain punctuation or spaces (unless you use `JpaSort.unsafe`), but it will sort by any attribute name you pass, including ones you never meant to expose, so keep the allow-list.

`IN` lists are values and can be bound; the template expands the collection into one placeholder per element:

```java
MapSqlParameterSource parameters = new MapSqlParameterSource("ids", orderIds);
List<Order> orders = namedParameterJdbcTemplate.query(
        "SELECT id, total_cents FROM orders WHERE id IN (:ids)", parameters, ORDER_ROW_MAPPER);
```

In JPQL, `where o.id in :ids` with `setParameter("ids", orderIds)` does the same, and Spring Data derives it from `findByIdIn(Collection<Long> ids)`.

`LIKE` patterns are bound too, but binding does not stop `%` and `_` in the input from acting as wildcards, so escape them and declare the escape character:

```java
static String escapeLikePattern(String term) {
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_");
}

List<Customer> search(String term) {
    return jdbcTemplate.query("SELECT id, name FROM customer WHERE name ILIKE ? ESCAPE '\\'", CUSTOMER_ROW_MAPPER,
            "%" + escapeLikePattern(term) + "%");
}
```

Native queries follow the same rule as everything else: `@Query(value = "... WHERE status = :status", nativeQuery = true)` is bound and safe; `entityManager.createNativeQuery("... " + input)` is not. The danger is concatenation, not SQL versus JPQL.

Finally, the role the application connects as (PostgreSQL):

```sql
CREATE ROLE orders_app LOGIN PASSWORD 'from-the-secret-store';
GRANT CONNECT ON DATABASE orders TO orders_app;
GRANT USAGE ON SCHEMA public TO orders_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO orders_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO orders_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO orders_app;
```

Run migrations as a separate role that owns the schema; the application role never needs `CREATE`, `DROP` or `ALTER`. Executed by the migration role, the `ALTER DEFAULT PRIVILEGES` line covers the tables it creates later, so new tables need no extra grant.

## Pitfalls

- "We use JPA, so we are safe." `createQuery("... '" + value + "'")` and `createNativeQuery` with concatenation are JPA too. The ORM binds what you let it bind.
- Binding the value but concatenating the sort column, the table name or the page size. Anything that is not a value needs an allow-list.
- Input validation as the defence. A regex that rejects quotes misses numeric contexts, misses second-order data and breaks `O'Brien`. Validate for business rules; bind for safety.
- Dynamic SQL inside the database. A PL/pgSQL function that runs `EXECUTE 'SELECT ... ' || input` is injection with extra steps; use `EXECUTE ... USING` for values and `format('%I', ...)` for identifiers.
- One database role for everything. If Flyway and the application share a superuser, every injection is a schema drop.
- Returning database errors to the client. `ERROR: syntax error at or near` in a JSON response is a free oracle for an attacker. Spring Boot's `server.error.include-message=never` has been the default since 2.3; keep it.

## Check yourself

1. Why does `statement.setString(1, "' OR '1'='1")` return no rows while concatenating the same string returns every row? What does the database receive in each case?
2. A colleague proposes a global filter that rejects any input containing a quote or a semicolon. Name two queries that remain injectable.
3. The API accepts `?sort=total&direction=desc`. Explain why `ORDER BY ?` does not work and what you do instead.
4. Your application connects as the database owner. What can an attacker with one injectable `SELECT` do that they could not do against the `orders_app` role above?

## Go deeper

- [PortSwigger: SQL injection](https://portswigger.net/web-security/sql-injection) · how the attacks work, with free labs; understanding UNION and blind techniques makes the defence obvious.
- [OWASP: SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html) · the defences, including the allow-list treatment of identifiers.
- [OWASP: Query Parameterization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Query_Parameterization_Cheat_Sheet.html) · bound queries in every language and framework, including JPA and Spring.
- [PostgreSQL: GRANT](https://www.postgresql.org/docs/current/sql-grant.html) · the privileges available for a least-privilege application role.
- [PostgreSQL: Message Flow](https://www.postgresql.org/docs/current/protocol-flow.html) · the extended query protocol, which is what "the values travel separately" means on the wire.

---

Part of [Security](../README.md) · item 2.3
