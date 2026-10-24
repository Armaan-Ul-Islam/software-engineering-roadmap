# Reference types and caches: soft, weak and phantom references, `WeakHashMap` and `Cleaner`

> **In one sentence:** Java's four reference strengths tell the collector how hard to keep an object: a strong reference pins it, a soft reference is cleared when memory runs short, a weak reference is cleared at the next collection that finds nothing stronger, and a phantom reference only reports that the object is gone; `WeakHashMap` and `Cleaner` are the two tools built on them that earn their place, and neither soft nor weak references make a good cache, which is a job for a bounded cache with a policy you chose.

**Why it matters:** `WeakHashMap` gets used as a cache with `String` keys that either never disappear or disappear while callers still hold equal keys; soft-reference caches turn the garbage collector into an eviction policy that inflates every pause and then empties the cache all at once under load; and `finalize()` has been deprecated for removal since Java 18 (JEP 421) while code still depends on it to close things. Interviewers ask which reference to pick because the answer shows whether you know the names or the collector's actual behaviour (item 2.1).

## The idea

**Reachability strengths.** An object's reachability is the strongest path to it from a GC root (item 2.1). Weaker paths let the collector reclaim the object despite the reference:

| Reference | Cleared when | `get()` afterwards | Honest use |
|---|---|---|---|
| strong (`Object field = ...`) | never, while reachable | the object | everything |
| `SoftReference<T>` | at the collector's discretion under memory demand; guaranteed before `OutOfMemoryError`; biased towards keeping recently used objects | `null` | almost nothing; see below |
| `WeakReference<T>` | at the next collection that finds the object only weakly reachable | `null` | metadata keyed by objects you do not own; canonicalising maps |
| `PhantomReference<T>` | cleared and enqueued once the object is phantom reachable (after any finalisation) | always `null` | post-mortem cleanup, which `Cleaner` packages for you |

A `ReferenceQueue` passed to a reference's constructor receives the reference once it has been cleared, so code can react without polling `get()`. HotSpot's soft-reference policy keeps a softly reachable object for about one second per megabyte of free heap since it was last used (`-XX:SoftRefLRUPolicyMSPerMB`, default 1000), so in practice soft references survive until the heap is nearly full and are then cleared in bulk.

**What `WeakHashMap` is actually for.** Weak *keys*, strong values: an entry disappears once its key object is no longer strongly referenced anywhere else, and the map expunges such entries on its next operation. That is the right tool for attaching data to objects you neither own nor can modify: parsed metadata per `Class`, per-connection state keyed by the connection object, listener registrations keyed by the component. It is the wrong tool for a cache keyed by values. A `String` literal is interned and lives as long as its class, so the entry never goes; a computed `String` key can be collected while callers still hold equal but different instances, so the entry goes while "the key" is still in use. The Javadoc's own warning is the other trap: values are strong, so a value that refers to its key, directly or through another entry, makes the key strongly reachable through the map itself and the entry immortal. It is also not thread-safe; wrap it or use a concurrent cache with weak keys.

**Why soft references make poor caches.** They delegate eviction to the collector: there is no size you control, no admission policy, no ordering across the cache beyond the per-reference timestamp. Until the heap is tight the "cache" simply inflates the live set, so every young collection has more to scan and promote and the old generation fills with entries nobody asked to keep (item 2.3). When the heap finally is tight, the collector clears soft references wholesale, and the hit rate collapses at the moment of highest load. Memory dashboards show a heap that is always full. Caffeine and Guava both attach a warning to `softValues()` telling you to set a maximum size instead.

**`Cleaner` instead of finalizers.** `finalize()` runs at an unknown time on a single finalizer thread, resurrects the object, delays reclamation by a whole extra collection cycle and is deprecated for removal. `java.lang.ref.Cleaner` (Java 9) is the replacement: `cleaner.register(object, action)` registers a `Runnable` that the cleaner's daemon thread runs once the object becomes phantom reachable, and returns a `Cleanable` whose `clean()` runs the action at most once and unregisters it. Two rules from its Javadoc. The action must not refer to the object being cleaned (a lambda capturing `this`, or a non-static inner class, keeps the object reachable, so it never becomes phantom reachable and the action never runs); keep the resource in a separate static nested state object. And the cleaner is a safety net: implement `AutoCloseable`, make `close()` call `cleanable.clean()`, and rely on try-with-resources for the normal path. Direct `ByteBuffer`s release their native memory this way, which is why that memory is only reclaimed after the buffer object itself has been collected (item 2.7).

**What to use for a cache instead.** A cache has a bound and a policy that you chose. The smallest version is a `LinkedHashMap` constructed with `accessOrder = true` and `removeEldestEntry` overridden to return `size() > maximum`: LRU in ten lines, for one thread or behind a lock. For anything shared and hot, use Caffeine: `Caffeine.newBuilder().maximumSize(10_000).expireAfterWrite(Duration.ofMinutes(10)).recordStats().build()` gives size or weight bounds, time-based expiry, a near-optimal admission policy (W-TinyLFU), asynchronous loading and refresh, and hit and miss statistics you can graph. When the data must outlive the process or be shared between instances, the cache is a separate system such as Redis. Weak and soft references appear in those libraries as options (`weakKeys()`, `softValues()`), to be chosen for the identity semantics above, not for eviction.

## Example: a `WeakHashMap` entry disappearing after `System.gc()`

```java
import java.lang.ref.SoftReference;
import java.lang.ref.WeakReference;
import java.util.Map;
import java.util.WeakHashMap;

public class WeakKeysDemo {

    public static void main(String[] arguments) throws InterruptedException {
        Map<Object, String> metadata = new WeakHashMap<>();
        Object sessionKey = new Object();
        metadata.put(sessionKey, "attached to an object nobody else references");
        metadata.put("config", "attached to an interned string literal");
        System.out.println("before: " + metadata.size() + " entries");

        sessionKey = null;
        SoftReference<byte[]> soft = new SoftReference<>(new byte[1_000_000]);
        WeakReference<byte[]> weak = new WeakReference<>(new byte[1_000_000]);
        System.gc();
        Thread.sleep(100);

        System.out.println("after System.gc(): " + metadata.size() + " entry, keys " + metadata.keySet());
        System.out.println("soft reference cleared: " + (soft.get() == null));
        System.out.println("weak reference cleared: " + (weak.get() == null));
    }
}
```

On OpenJDK 25 with default settings:

```text
before: 2 entries
after System.gc(): 1 entry, keys [config]
soft reference cleared: false
weak reference cleared: true
```

The entry keyed by the anonymous object vanished because nothing else referenced its key; the entry keyed by the literal `"config"` stayed, because the class's constant pool holds that string for as long as the class is loaded. The weak reference was cleared by the same collection; the soft reference survived, since a 1 MB array in a heap with gigabytes free is nowhere near the policy's threshold. `System.gc()` is a request that HotSpot honours by default (and ignores under `-XX:+DisableExplicitGC`); nothing guarantees that a collection runs, or that it clears anything, so a test written this way is a demonstration, not a specification.

## Example: a `Cleaner`-backed resource

```java
import java.lang.ref.Cleaner;
import java.nio.ByteBuffer;

public final class TemporaryBuffer implements AutoCloseable {

    private static final Cleaner CLEANER = Cleaner.create();

    private final State state;
    private final Cleaner.Cleanable cleanable;

    TemporaryBuffer(String name, int bytes) {
        this.state = new State(name, ByteBuffer.allocateDirect(bytes));
        this.cleanable = CLEANER.register(this, state);
    }

    ByteBuffer buffer() {
        return state.buffer;
    }

    @Override
    public void close() {
        cleanable.clean();
    }

    // Static on purpose: an inner class would capture the TemporaryBuffer and keep it reachable forever.
    private static final class State implements Runnable {

        private final String name;
        private final ByteBuffer buffer;

        State(String name, ByteBuffer buffer) {
            this.name = name;
            this.buffer = buffer;
        }

        @Override
        public void run() {
            System.out.println("released " + name + " on thread " + Thread.currentThread().getName());
        }
    }

    public static void main(String[] arguments) throws InterruptedException {
        try (TemporaryBuffer closedProperly = new TemporaryBuffer("closed-properly", 1024)) {
            closedProperly.buffer().putInt(42);
        }
        new TemporaryBuffer("forgotten", 1024).buffer().putInt(43);
        System.gc();
        Thread.sleep(200);
        System.out.println("main done");
    }
}
```

```text
released closed-properly on thread main
released forgotten on thread Cleaner-0
main done
```

The properly closed buffer is released immediately, on the calling thread, by `close()`; the forgotten one is released later, on the cleaner's thread, after a collection noticed that nothing referenced it. In a real resource the `run` method frees the native memory, closes the handle or returns the connection, and never touches the owning object. One shared `static` cleaner per class or per application is the norm; each `Cleaner.create()` starts a thread.

## Pitfalls

- `WeakHashMap<String, V>` as a cache. Literal keys are never collected; computed keys are collected while callers still hold equal strings. Neither is the lifetime you wanted.
- Values that reference their keys. A `WeakHashMap<Session, SessionData>` where `SessionData` has a `session` field never drops an entry (item 2.5).
- Soft-reference caches "because the GC will size them". The heap reads as full, pauses grow, and the cache empties exactly under load. Bound the cache yourself.
- A cleaning action that captures the object. `() -> this.buffer.free()` or a non-static inner class keeps the object strongly reachable from its own registration, so the action never runs and the native memory leaks.
- Relying on the cleaner at all. Collections may be minutes apart on a quiet heap, and file handles or connections run out long before. `close()` is the mechanism; the cleaner is the apology.
- A `Cleaner` per instance. Each one owns a thread.
- `System.gc()` in production code to "flush" weak or soft references. It requests a full collection, the most expensive kind, and promises nothing (item 2.3).

## Check yourself

1. A `WeakHashMap<String, Profile>` keyed by user name "never evicts anything" in production but "randomly loses entries" in a test that builds keys with `new String(...)`. Explain both observations.
2. Why does a cache of `SoftReference` values make young-generation pauses longer even when the cache is rarely hit, and what will the GC log show in the minutes before the references are cleared?
3. A cleaning action is written as the lambda `() -> buffer.free()`, where `buffer` is a field of the resource being registered. Why does it never run, and what does the fixed version look like?
4. You must cache 50,000 parsed templates with ten-minute freshness, shared by 200 request threads. Which option from this note do you choose, and which two numbers do you watch after deploying it?

## Go deeper

- [Baeldung: Soft, Weak and Phantom References](https://www.baeldung.com/java-weak-reference) · the four strengths with code for each.
- [java.lang.ref package summary](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ref/package-summary.html) · the precise definitions of reachability and of when each reference type is cleared and enqueued.
- [Cleaner Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ref/Cleaner.html) · the class comment contains the canonical static-state example and the rules for the cleaning action.
- [WeakHashMap Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/WeakHashMap.html) · the semantics of weak keys and the warning about values that refer to their keys.
- [JEP 421: Deprecate Finalization for Removal](https://openjdk.org/jeps/421) · why finalizers are going and what to use instead.
- [Caffeine](https://github.com/ben-manes/caffeine) · the cache library to use; its wiki explains the eviction policy and the cost of reference-based caching.

---

Part of [Memory & Concurrency](../README.md) · item 2.6
