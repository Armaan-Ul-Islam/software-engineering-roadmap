# Time, dates and time zones

> **In one sentence:** An instant is a point on the global timeline and is unambiguous; a local date-time is a wall-clock reading that means nothing until you attach a zone; an offset is a fixed number of hours from UTC while a zone is a set of rules that changes the offset over the year and over history; and the clock you measure durations with must be a different clock from the one that tells the time.

**Why it matters:** Every backend stores, compares and schedules times. The bugs are seasonal: a nightly job runs twice or not at all on the last Sunday of March, a "30 days ago" query is off by an hour, a timeout fires early when NTP steps the clock, and a meeting booked for 09:00 Oslo shows at 08:00 after the summer-time change because somebody stored `+01:00` instead of `Europe/Oslo`.

## The idea

**Three different things people call "a time".**

1. An **instant**: a point on the timeline, the same for everyone. `2026-10-29T10:15:30Z`. Java: `Instant`. PostgreSQL: `timestamptz` (which, despite the name, stores a UTC instant and no zone). This is what "the order was placed at" and "the token expires at" are.
2. A **local date-time**: a wall-clock reading with no zone. `2026-10-29T11:15:30`. Java: `LocalDateTime`. It is ambiguous: it names a different instant in every zone, and in some zones it names zero or two instants (see the gap and overlap below). It is correct only for things that are genuinely local, like "the shop opens at 09:00".
3. A **zoned date-time**: a local reading plus the rules to interpret it. Java: `ZonedDateTime` with a `ZoneId` such as `Europe/Oslo`. Use it for future events agreed in human terms ("the meeting is at 09:00 Oslo time next March"), because the offset at that time is not known until the rules say.

**Offset versus zone.** `+01:00` is an offset: a fixed number. `Europe/Oslo` is a zone: a named entry in the IANA time zone database that says "`+01:00` in winter, `+02:00` in summer, with these transition dates, and here is what it was in 1940". Storing an offset with a future local time silently freezes the wrong rule; storing the zone lets the library apply whichever rule is in force. The database is updated several times a year because governments change the rules; the JDK ships a copy and gets updates with releases (`java.time` reads it from `tzdata` inside the JDK).

**DST gaps and overlaps.** When clocks go forward (Oslo, 29 March 2026 at 02:00) the local times 02:00 to 02:59 do not exist; when they go back (25 October 2026 at 03:00) the local times 02:00 to 02:59 happen twice. Any code that builds a local time and converts it must decide what to do; `java.time` shifts a time in the gap forward by the gap length and picks the earlier offset in an overlap unless told otherwise. A day is not always 24 hours: `plusDays(1)` keeps the wall-clock time, `plusHours(24)` keeps the elapsed time, and they disagree twice a year.

**UTC.** Store and transmit instants in UTC, convert at the edges (the user's screen, the report's header) using the user's zone. Servers run in UTC so logs and cron are unambiguous. The one exception is future human-scheduled events, which need the zone *and* the local time, because the instant can change if the rules do.

**ISO 8601.** The one format to use everywhere: `2026-10-29T10:15:30Z` or `2026-10-29T11:15:30+01:00`; dates as `2026-10-29`; durations as `PT30M`. It sorts lexically, has no month/day ambiguity, and every library parses it. `java.time`'s `toString` and `parse` use it by default. `10/11/2026` means two different days in two countries.

**Monotonic versus wall clock.** `System.currentTimeMillis()` and `Instant.now()` read the wall clock, which can jump backwards or forwards when NTP corrects it, when a VM is migrated, or when an administrator sets it. `System.nanoTime()` reads a monotonic clock that only moves forward and has no meaning except as a difference between two readings. Measure elapsed time, timeouts and rate limits with the monotonic clock; stamp events with the wall clock. (The example below shows them agreeing over 250 ms; the point is what happens when they do not.)

## Example: the gap, the overlap, and two kinds of plus

```java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;

public final class Clocks {

    public static void main(String[] arguments) {
        ZoneId oslo = ZoneId.of("Europe/Oslo");

        LocalDateTime inTheGap = LocalDateTime.of(2026, 3, 29, 2, 30);
        System.out.println("gap:      " + inTheGap + " in Oslo becomes " + inTheGap.atZone(oslo));

        LocalDateTime inTheOverlap = LocalDateTime.of(2026, 10, 25, 2, 30);
        ZonedDateTime earlier = inTheOverlap.atZone(oslo).withEarlierOffsetAtOverlap();
        ZonedDateTime later = inTheOverlap.atZone(oslo).withLaterOffsetAtOverlap();
        System.out.println("overlap:  " + earlier + " and " + later + " are "
                + Duration.between(earlier, later).toMinutes() + " minutes apart");

        ZonedDateTime beforeChange = ZonedDateTime.of(2026, 3, 28, 12, 0, 0, 0, oslo);
        System.out.println("plusDays: " + beforeChange.plusDays(1) + "  (offset changed)");
        System.out.println("plusHours:" + beforeChange.plusHours(24) + "  (24 real hours)");

        ZonedDateTime fixedOffset = ZonedDateTime.of(2026, 1, 15, 12, 0, 0, 0, ZoneOffset.ofHours(1));
        System.out.println("offset:   " + fixedOffset.plusMonths(6) + "  vs zone: "
                + beforeChange.withMonth(7).withDayOfMonth(15));

        Instant instant = Instant.parse("2026-10-29T10:15:30Z");
        System.out.println("same instant, three spellings:");
        System.out.println("  " + instant);
        System.out.println("  " + instant.atZone(oslo));
        System.out.println("  " + instant.atZone(ZoneId.of("America/New_York"))
                .format(DateTimeFormatter.ISO_OFFSET_DATE_TIME));
    }
}
```

```text
$ java Clocks.java
gap:      2026-03-29T02:30 in Oslo becomes 2026-03-29T03:30+02:00[Europe/Oslo]
overlap:  2026-10-25T02:30+02:00[Europe/Oslo] and 2026-10-25T02:30+01:00[Europe/Oslo] are 60 minutes apart
plusDays: 2026-03-29T12:00+02:00[Europe/Oslo]  (offset changed)
plusHours:2026-03-29T13:00+02:00[Europe/Oslo]  (24 real hours)
offset:   2026-07-15T12:00+01:00  vs zone: 2026-07-15T12:00+02:00[Europe/Oslo]
same instant, three spellings:
  2026-10-29T10:15:30Z
  2026-10-29T11:15:30+01:00[Europe/Oslo]
  2026-10-29T06:15:30-04:00
```

Line by line. `02:30` on the spring-forward night does not exist, so the library moved it to `03:30` without complaint; a scheduler that stores "run at 02:30 local" runs at a different wall-clock time that night, and one that computes "next run = today's run + 1 day" drifts. The overlap has two valid answers an hour apart and the library picked the first unless asked; a log line timestamped `02:30` without an offset that night is ambiguous forever. `plusDays(1)` and `plusHours(24)` land an hour apart across the change, so "same time tomorrow" and "in 24 hours" are different questions. The fixed-offset value stays at `+01:00` in July, when Oslo is at `+02:00`: a meeting stored with an offset shows up an hour wrong for half the year. And one instant has as many spellings as there are zones, all equal under `Instant.equals` and all different under `ZonedDateTime.equals`, which compares the zone too; compare instants with `isBefore`, `isAfter` or by converting to `Instant`.

```java
public final class Monotonic {

    public static void main(String[] arguments) throws InterruptedException {
        long wallStart = System.currentTimeMillis();
        long monotonicStart = System.nanoTime();
        Thread.sleep(250);
        System.out.println("wall clock elapsed:  " + (System.currentTimeMillis() - wallStart) + " ms");
        System.out.println("monotonic elapsed:   " + (System.nanoTime() - monotonicStart) / 1_000_000 + " ms");
        System.out.println("nanoTime raw value:  " + System.nanoTime() + " (meaningless on its own)");
    }
}
```

```text
$ java Monotonic.java
wall clock elapsed:  261 ms
monotonic elapsed:   263 ms
nanoTime raw value:  695268420583 (meaningless on its own)
```

Both agree today. The day NTP steps the clock back 2 seconds, the first line goes negative and a cache entry with a wall-clock expiry lives 2 seconds longer, or a `while (System.currentTimeMillis() < deadline)` loop spins 2 seconds more. The second line is unaffected. The raw `nanoTime` value is time since some arbitrary origin (often boot) and must never be stored or compared across JVMs.

## Pitfalls

- `timestamp without time zone` in PostgreSQL for instants. It stores a local reading with no zone; two servers in different zones write different values for the same moment. Use `timestamptz` and keep the session zone at UTC.
- Storing an offset for a future event. `2027-03-15T09:00+01:00` is correct until the rules change, or until summer. Store the local time plus the zone name, and compute the instant when it is needed.
- `java.util.Date` and `Calendar`. Mutable, zone-confused, with months starting at 0. Convert at the boundary and use `java.time` everywhere else.
- `LocalDateTime` in an API. The receiver cannot know which instant you meant. Send ISO 8601 with `Z` or an offset.
- Cron at 02:30 local. Runs twice or never on the DST nights. Schedule in UTC, or at a local time outside the 02:00 to 03:00 window if the job must be local.
- Timeouts from the wall clock. A clock step turns a 30-second timeout into zero or into a minute. `System.nanoTime` for anything measured, `Instant` for anything recorded.
- Day arithmetic in hours. "Thirty days ago" is `minusDays(30)` on a zoned date, not `minusHours(720)`; the two differ by an hour across a change and reports disagree by a day at the edge.
- Trusting the JDK's time zone data forever. Rules change every year somewhere. Keep the JDK patched; a stale `tzdata` is a bug that only shows on the transition date.

## Check yourself

1. A meeting is booked for 09:00 Oslo time on 15 July 2027. What do you store, why not an instant or an offset, and when do you compute the instant?
2. A nightly job is scheduled with cron at `30 2 * * *` on a server in `Europe/Oslo`. What happens on 29 March and 25 October 2026, and what are two fixes?
3. A cache uses `System.currentTimeMillis() + ttlMillis` as the expiry. Describe a failure, and the one-line change.
4. Two `ZonedDateTime` values represent the same instant in different zones. What do `equals`, `isEqual` and `compareTo` each say, and which would you use in a query?

## Go deeper

- [Falsehoods programmers believe about time](https://gist.github.com/timvisee/fcda9bbdff88d45cc9061606b4b923ca) · the list of assumptions this note is built to break; read it once a year.
- [java.time package summary](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/package-summary.html) · which class to use for which concept, and the design rationale.
- [PostgreSQL: Date/Time Types](https://www.postgresql.org/docs/current/datatype-datetime.html) · what `timestamptz` really stores and how the session time zone affects input and output.
- [IANA Time Zone Database](https://www.iana.org/time-zones) · the source of every zone rule your JDK, database and operating system use.

---

Part of [Foundations](../README.md) · item 7.5
