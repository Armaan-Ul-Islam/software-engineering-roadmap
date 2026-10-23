# java.time essentials

> **In one sentence:** Store and compare points in time as `Instant` (UTC), use `ZonedDateTime` only when a human calendar in a named zone matters, treat `LocalDateTime` as a wall-clock reading that is not a point in time, measure elapsed time with `Duration` and calendar distances with `Period`, and inject a `Clock` so time can be tested.

**Why it matters:** Time bugs ship twice a year, at the daylight saving transitions, and once a year at the week-year boundary. A service that stores `LocalDateTime` in a `timestamp without time zone` column works perfectly until the server, the database or a user is in a different zone. "What is the difference between `Instant` and `LocalDateTime`?" is a standard interview question because the answer shows whether you understand that a time without a zone is not a moment.

## The idea

| Type | What it is | Use it for |
|---|---|---|
| `Instant` | a point on the UTC timeline, nanosecond precision, prints as `2026-10-24T07:00:00Z` | timestamps (`created_at`), logs, ordering and comparing events, anything stored in a database |
| `LocalDate`, `LocalTime`, `LocalDateTime` | a date, a time, or both, with no zone or offset | birthdays, opening hours, "the meeting is at 09:00" before you know where |
| `ZonedDateTime` | `LocalDateTime` + `ZoneId` (`Europe/Oslo`) + the offset that applies at that moment, with the zone's rules | user-facing scheduling, recurring events, calendar arithmetic that must respect daylight saving |
| `OffsetDateTime` | `LocalDateTime` + a fixed offset (`+02:00`), no rules | what ISO 8601 strings with an offset parse to; the JDBC mapping of `timestamptz`; API payloads |
| `ZoneId` vs `ZoneOffset` | a region with rules from the tz database, versus a fixed offset | always prefer the region id for anything in the future |
| `Duration` | seconds and nanoseconds, machine time, prints `PT25H` | timeouts, elapsed time, SLAs |
| `Period` | years, months and days, calendar time, prints `P1M3D` | "due in 30 days", subscription lengths, ages |

Two kinds of arithmetic follow from this. `plusDays(1)` on a `ZonedDateTime` is calendar arithmetic: the local time stays 09:00 even if the day has 23 or 25 hours. `plusHours(24)` or `Instant.plus(Duration.ofDays(1))` is timeline arithmetic: exactly 86,400 seconds later, whatever the clock then says.

**Formatting and parsing.** `DateTimeFormatter` is immutable and thread-safe (unlike the old `SimpleDateFormat`). Use the ISO constants (`ISO_INSTANT`, `ISO_OFFSET_DATE_TIME`) for machine formats and `ofPattern(pattern, locale)` for people, always with an explicit `Locale`. Pattern letters are case-sensitive and the wrong case is a silent bug: `yyyy` is the year, `YYYY` is the week-based year; `MM` is month, `mm` is minute; `HH` is 0 to 23, `hh` is 1 to 12. An `Instant` has no date fields, so formatting it with `yyyy-MM-dd` throws `UnsupportedTemporalTypeException`; convert with `instant.atZone(zone)` first. `LocalDateTime.parse` expects the ISO form with a `T`: `"2026-10-24 09:00"` fails with `DateTimeParseException ... could not be parsed at index 10`.

**Storing timestamps.** Store instants, in UTC. In PostgreSQL that is `timestamptz`, which despite its name stores no zone: it normalises the input to UTC and converts on output to the session's zone. The JDBC 4.2 mapping is `timestamptz` to `OffsetDateTime` and `timestamp` to `LocalDateTime`; call `toInstant()` on the former. Run the JVM with `-Duser.timezone=UTC` (or set `hibernate.jdbc.time_zone=UTC`) so a server's zone never leaks into stored values. When you need to show or re-schedule in the user's zone, store the zone id (`Europe/Oslo`) as a separate column.

**Daylight saving.** Three things go wrong. A **gap**: on 29 March 2026 the Oslo clock jumps from 02:00 to 03:00, so 02:30 does not exist and `ZonedDateTime.of(...)` shifts it to 03:30. An **overlap**: on 25 October 2026 the clock goes from 03:00 back to 02:00, so 02:30 happens twice; the default picks the earlier offset (`+02:00`), and `withLaterOffsetAtOverlap()` picks the other. And **23- or 25-hour days**, which is what breaks "same time tomorrow" and any "add 24 hours" shortcut.

**Testing.** Never call `Instant.now()` or `LocalDate.now()` directly in domain code. Take a `Clock` in the constructor and call `Instant.now(clock)`; in tests pass `Clock.fixed(Instant.parse("2026-10-25T01:30:00Z"), ZoneId.of("Europe/Oslo"))`. Java 17 added the `InstantSource` interface for code that only needs instants.

## Example: same time tomorrow across the autumn transition

Oslo leaves summer time on 25 October 2026. Start on the Saturday morning before it:

```java
ZoneId oslo = ZoneId.of("Europe/Oslo");
ZonedDateTime saturdayNine = ZonedDateTime.of(LocalDateTime.of(2026, 10, 24, 9, 0), oslo);

ZonedDateTime sameTimeTomorrow = saturdayNine.plusDays(1);
ZonedDateTime twentyFourHoursLater = saturdayNine.plusHours(24);
Instant viaInstant = saturdayNine.toInstant().plus(Duration.ofDays(1));

System.out.println(saturdayNine);
System.out.println(sameTimeTomorrow + "  elapsed " + Duration.between(saturdayNine, sameTimeTomorrow));
System.out.println(twentyFourHoursLater + "  elapsed " + Duration.between(saturdayNine, twentyFourHoursLater));
System.out.println(viaInstant.atZone(oslo));
System.out.println(saturdayNine.toOffsetDateTime().plusDays(1));
```

```text
2026-10-24T09:00+02:00[Europe/Oslo]
2026-10-25T09:00+01:00[Europe/Oslo]  elapsed PT25H
2026-10-25T08:00+01:00[Europe/Oslo]  elapsed PT24H
2026-10-25T08:00+01:00[Europe/Oslo]
2026-10-25T09:00+02:00
```

`plusDays(1)` keeps 09:00 and the offset changes, so 25 hours pass: that is what a user who booked "09:00 tomorrow" expects. Both timeline versions land at 08:00 local. The `OffsetDateTime` version keeps `+02:00` because a fixed offset has no rules, and now points at 08:00 Oslo time while claiming to be 09:00: this is the bug you get from storing a zoned event as an offset.

The two edge cases, directly:

```java
ZonedDateTime.of(LocalDateTime.of(2026, 10, 25, 2, 30), oslo);                              // 2026-10-25T02:30+02:00[Europe/Oslo]
ZonedDateTime.of(LocalDateTime.of(2026, 10, 25, 2, 30), oslo).withLaterOffsetAtOverlap();    // 2026-10-25T02:30+01:00[Europe/Oslo]
ZonedDateTime.of(LocalDateTime.of(2026, 3, 29, 2, 30), oslo);                               // 2026-03-29T03:30+02:00[Europe/Oslo]
```

And the week-year trap:

```java
DateTimeFormatter.ofPattern("YYYY-MM-dd").format(LocalDate.of(2024, 12, 30));   // 2025-12-30
```

## Pitfalls

- `LocalDateTime` for events. It cannot be compared with anything from another zone and cannot be converted to an instant without guessing. Use it only for values that are genuinely zone-free.
- `LocalDateTime.now()` on a server. The result depends on the host's zone; containers default to UTC, developer laptops do not, and the difference shows up as "all timestamps are two hours off in production".
- `ZoneOffset` where `ZoneId` was meant. `+02:00` is right for half the year.
- Scheduling future events as instants only. If the zone's rules change (governments do this), "09:00 local" stored as an instant becomes 08:00 or 10:00. Store local time plus zone id for future events; store instants for things that happened.
- `Date`, `Calendar`, `SimpleDateFormat`. Mutable, not thread-safe, zone handling by accident. Convert at the boundary with `Date.from(instant)` and `date.toInstant()` and never let them inside.
- Formatting without a `Locale`. Month and day names follow the default locale of the machine; your test machine and the server disagree.
- `Duration.between` on `LocalDate`s throws `UnsupportedTemporalTypeException`; use `Period.between` or `ChronoUnit.DAYS.between`.
- Precision mismatch in equality tests. `Instant.now()` has microsecond or nanosecond precision depending on the platform, PostgreSQL stores microseconds, so a value round-tripped through the database may not `equals` the original. Truncate with `truncatedTo(ChronoUnit.MICROS)` or compare with a tolerance.

## Check yourself

1. A nightly job is scheduled for 02:30 Oslo time. What happens on 29 March 2026 and on 25 October 2026 if the schedule is kept as a `LocalDateTime`, as a `ZonedDateTime`, and as an `Instant` computed once in advance?
2. Why does `Duration.between(start, start.plusDays(1))` give `PT25H` for a `ZonedDateTime` on 24 October but always `PT24H` for an `OffsetDateTime`?
3. Your orders table has `created_at timestamp` (without time zone) filled from `LocalDateTime.now()`. What information is missing from each row, and why does the bug appear only after the service is redeployed to a container?
4. Formatting an `Instant` with `yyyy-MM-dd HH:mm` throws. What exactly is the formatter missing, and what is the one-line fix?

## Go deeper

- [Baeldung: Introduction to the Java Date/Time API](https://www.baeldung.com/java-8-date-time-intro) · a tour of the main types with examples.
- [java.time package documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/package-summary.html) · the package comment explains the design (human time versus machine time) better than most articles.
- [DateTimeFormatter API documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html) · the full pattern-letter table; check it every time you write a pattern.
- [PostgreSQL: Date/Time Types](https://www.postgresql.org/docs/current/datatype-datetime.html) · what `timestamptz` really stores and how input is interpreted.

---

Part of [Java](../README.md) · item 3.1
