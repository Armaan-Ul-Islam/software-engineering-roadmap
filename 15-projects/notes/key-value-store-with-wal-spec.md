# Project spec: a key-value store with a write-ahead log and crash recovery

> **In one sentence:** Build a persistent key-value store in Java whose only on-disk structure is an append-only, checksummed log, then add an in-memory index over that log and compaction, and prove with `kill -9` that an acknowledged write is never lost.

**Why it matters:** "Committed" is a physical claim: bytes that survive a crash. Every database you will operate (PostgreSQL's WAL, Kafka's segments, RocksDB's memtable and SSTables) is a variation of what you build here, and reasoning about `fsync`, torn writes and recovery is what separates engineers who can explain a durability incident from those who can only restart the service.

## The idea

You will write one library, `logkv`, with a `put`, `get` and `delete` API and one file on disk. Every mutation is appended to the log and flushed before the call returns. On start, the log is replayed to rebuild an in-memory hash index from key to file offset (the Bitcask design: values stay on disk, the index holds only offsets). A compaction step rewrites the live records into a fresh file when the log grows too large.

Scope:

- 1.1 Records are self-describing: a CRC32, a key length, a value length (`-1` marks a tombstone), the key bytes, the value bytes.
- 1.2 `put` and `delete` append and `force` the channel before acknowledging; `get` does one positional read.
- 1.3 Recovery stops at the first record that is short or fails its checksum, truncates the file there, and continues appending from that point.
- 1.4 Compaction writes live records into a new file, flushes it, and swaps it in with an atomic rename.
- 1.5 One writer at a time (a lock), any number of concurrent readers (positional reads on `FileChannel` are thread-safe).

Concepts exercised: Foundations 2.5, 2.7; Databases 2.1, 2.2, 2.3; Memory & Concurrency 4.3; Java 3.2, 5.3, 7.6.

## Example: the record format and the milestones

```text
offset 0        4          8            12            12+k
       +--------+----------+------------+-------------+-------------+
       | crc32  | key len  | value len  | key bytes   | value bytes |
       +--------+----------+------------+-------------+-------------+
       crc32 covers everything after itself; value len = -1 is a tombstone
```

The two methods that carry the correctness argument, from a class compiled and tested on Java 21 (the full class also holds `get`, `put`, `delete` and a `main` that appends garbage bytes and reopens the file):

```java
private void append(String key, byte[] value) throws IOException {
    byte[] keyBytes = key.getBytes(StandardCharsets.UTF_8);
    int valueLength = value == null ? TOMBSTONE : value.length;
    ByteBuffer record = ByteBuffer.allocate(HEADER_BYTES + keyBytes.length + Math.max(valueLength, 0));
    record.putInt(0).putInt(keyBytes.length).putInt(valueLength).put(keyBytes);
    if (value != null) {
        record.put(value);
    }
    record.putInt(0, checksumOf(record.array(), Integer.BYTES, record.position() - Integer.BYTES));
    record.flip();
    long offset = channel.position();
    while (record.hasRemaining()) {
        channel.write(record);
    }
    channel.force(false);
    if (value == null) {
        offsetByKey.remove(key);
    } else {
        offsetByKey.put(key, offset);
    }
}

private long replay() throws IOException {
    long offset = 0;
    ByteBuffer header = ByteBuffer.allocate(HEADER_BYTES);
    while (true) {
        header.clear();
        if (channel.read(header, offset) < HEADER_BYTES) {
            return offset;
        }
        header.flip();
        int storedChecksum = header.getInt();
        int keyLength = header.getInt();
        int valueLength = header.getInt();
        if (keyLength < 0 || valueLength < TOMBSTONE) {
            return offset;
        }
        ByteBuffer payload = ByteBuffer.allocate(keyLength + Math.max(valueLength, 0));
        if (channel.read(payload, offset + HEADER_BYTES) < payload.capacity()) {
            return offset;
        }
        CRC32 checksum = new CRC32();
        checksum.update(header.array(), Integer.BYTES, 2 * Integer.BYTES);
        checksum.update(payload.array(), 0, payload.capacity());
        if ((int) checksum.getValue() != storedChecksum) {
            return offset;
        }
        String key = new String(payload.array(), 0, keyLength, StandardCharsets.UTF_8);
        if (valueLength == TOMBSTONE) {
            offsetByKey.remove(key);
        } else {
            offsetByKey.put(key, offset);
        }
        offset += HEADER_BYTES + payload.capacity();
    }
}
```

The constructor calls `replay()`, then `channel.truncate(validLength)` and `channel.position(validLength)`. Writing `alpha`, `beta`, `alpha` again, deleting `beta`, appending five garbage bytes and reopening prints `alpha=uno beta=null` and `size before 80, after truncating torn tail 75`.

Milestones, each ending in a committed test:

1. **Append-only log.** `put`, `get`, `delete` where `get` scans the whole file and the last record wins. Test: a put, overwrite, delete sequence survives close and reopen.
2. **Crash recovery.** Checksums, torn-tail detection and truncation, then the real test: start a child JVM that writes keys in a loop and prints each key to stdout only after `force` returns; kill it with `ProcessHandle.destroyForcibly()` after a random delay; reopen the log in the test and assert every printed key is present. Run it 50 times in a loop. Record recovery time per megabyte of log.
3. **In-memory index.** The hash map from key to offset shown above; `get` becomes one positional read. Test: a JMH benchmark comparing `get` at 10 and 100,000 keys against milestone 1 (scan) shows the index is flat, the scan linear.
4. **Compaction.** Rewrite live records to `data.log.compacting`, `force` it, rename it over `data.log` with `StandardCopyOption.ATOMIC_MOVE`, rebuild the index. Test: after 100,000 overwrites of 10 keys, the compacted file holds 10 records and every read is unchanged; a crash injected between the write and the rename leaves either the old or the new file complete, never a mix.
5. **Concurrent readers.** Writers take a lock; readers use `channel.read(buffer, position)` without one. Test: 8 reader threads and 2 writer threads for 10 seconds never observe a value whose checksum fails or a key that was never written.

Definition of done:

- 2.1 `kill -9` during writes never loses an acknowledged write, and recovery time is measured.
- 2.2 The README documents the record format, the write path with and without `force` (puts per second for each, measured), and the recovery time per megabyte.
- 2.3 The README states which crash the tests prove safety against (process death) and which they do not (power loss), with the reason.

Stretch goals:

- 3.1 An LSM-tree with SSTables and bloom filters; a B-tree variant; compare read and write amplification.
- 3.2 Hint files written during compaction so that recovery reads only keys and offsets instead of the whole log.

## Pitfalls

- Believing `kill -9` tests `fsync`. The page cache belongs to the kernel and survives process death, so a store that never calls `force` passes milestone 2. Only a VM power-off, a fault-injecting file system or a disk pull tests durability; say so in the README instead of claiming more.
- Acknowledging before `force` returns. Batching writes and flushing once per group is fine and fast (that is group commit); returning to the caller before the flush is a lost write waiting to happen.
- Recovering without truncating. If a torn record stays at the tail and you append after it, the next replay stops at the garbage and every later record is invisible.
- Appending with a channel opened in `APPEND` mode while also reading. `FileChannel.open` rejects `READ` with `APPEND`; open with `READ` and `WRITE`, position explicitly, and keep one writer.
- Renaming the compacted file without flushing it first. The rename can become durable before the data does; `force` the new file, then rename, then (on Linux) `force` the directory channel too.
- Letting the index assume a record exists at an offset after compaction. Rebuild or swap the index together with the file under the same lock.
- Measuring recovery on a tiny log. Fill a few hundred megabytes before timing it; the per-megabyte figure is what the README should quote.

## Check yourself

1. A write returns successfully, the process is killed one millisecond later, and the key is missing after restart. List every place in the write path where this could happen and which one `force` closes.
2. Why does recovery stop at the first bad checksum instead of skipping it and continuing to scan?
3. The in-memory index holds offsets, not values. What does that cost on `get`, what does it save, and how big can the data set get before the index itself becomes the problem?
4. Compaction renames a new file over the old one. What state can the directory be in after a crash at each step, and which step makes the swap atomic?

## Go deeper

- [Database Internals](https://www.databass.dev/) · chapters on storage engines, log-structured storage and B-trees (paid book).
- [PostgreSQL: Write-Ahead Logging](https://www.postgresql.org/docs/current/wal-intro.html) · how a production database frames the same guarantee.
- [Build your own X](https://github.com/codecrafters-io/build-your-own-x) · other from-scratch databases to compare designs against.
- [JMH](https://github.com/openjdk/jmh) · the benchmark harness for milestone 3.

---

Part of [Projects](../README.md) · item 1.3
