# I/O and NIO essentials: `Path`, `Files`, streams, readers, charsets, buffering and memory-mapped files

> **In one sentence:** Use `java.nio.file.Path` and `Files` for everything on disk, read bytes through an `InputStream` and text through a `Reader` with an explicit charset, always buffer or read in chunks, close with try-with-resources (including the `Stream<String>` from `Files.lines`), and reach for `FileChannel.map` only when you need random access to a large file.

**Why it matters:** File handling is where "works on my laptop" meets "fills the disk, leaks file descriptors and corrupts the export halfway". The API has three generations (`java.io.File`, `java.nio` channels and buffers, `java.nio.file`), and most production code mixes them badly: unbuffered byte-at-a-time loops that are a thousand times slower than necessary, `new FileReader(path)` that uses the platform charset, and `Files.lines` streams that are never closed and exhaust the process's file descriptor limit under load.

## The idea

**Paths and files.** `Path` (Java 7, `java.nio.file`) is an immutable, typed path: `Path.of("exports", "orders.csv")`, `resolve`, `getParent`, `getFileName`, `normalize`, `relativize`. `Files` is the static toolbox: `exists`, `size`, `createDirectories`, `copy`, `move`, `delete`, `walk`, `list`, `readString`, `writeString`, `readAllLines`, `lines`, `newBufferedReader`, `newBufferedWriter`, `newInputStream`, `newOutputStream`. Errors are real exceptions with the path in them (`NoSuchFileException`, `AccessDeniedException`, `FileAlreadyExistsException`), unlike `java.io.File` methods that return `false`. Treat `File` as legacy; `file.toPath()` and `path.toFile()` convert when a library insists.

**Bytes versus characters.** `InputStream`/`OutputStream` move bytes. `Reader`/`Writer` move `char`s and need a charset to convert: `InputStreamReader(input, StandardCharsets.UTF_8)`. `Files.newBufferedReader(path, charset)` and `Files.readString(path, charset)` do this for you; the overloads without a charset default to UTF-8. `FileReader` and `FileWriter` without a charset argument use the platform default, which has been UTF-8 since Java 18 but is still implicit. Name the charset (see item 1.2 for what goes wrong otherwise).

**Buffering.** A file system call has a fixed cost per call, so `read()` one byte at a time is catastrophically slow. Either wrap in `BufferedInputStream`/`BufferedReader` (which read 8 KiB at a time behind a byte-sized API) or read into your own array with `read(byte[])`. `Files.newBufferedReader` is already buffered; `Files.newInputStream` is not. The same applies to writes: unbuffered single-byte `write` calls each hit the kernel.

**Streams of lines.** `Files.lines(path)` returns a lazy `Stream<String>` that holds the file open until the stream is closed. It must be in a try-with-resources; the same is true of `Files.list`, `Files.walk` and `Files.find`. `Files.readAllLines` and `Files.readString` load everything into memory and close the file themselves, which is right for small files only.

**Atomic replacement.** Writing directly to the final path means a reader (or a crash) can see a half-written file. Write to a temporary file in the same directory, then `Files.move(temporary, target, ATOMIC_MOVE, REPLACE_EXISTING)`. On POSIX file systems the rename is atomic; across file systems `ATOMIC_MOVE` throws `AtomicMoveNotSupportedException` instead of silently copying.

**Channels, buffers and memory-mapped files.** `FileChannel` is the lower-level API: positional reads and writes (`read(buffer, position)`), `transferTo` for zero-copy file-to-socket copies, file locks, and `map`, which asks the operating system to map a region of the file into memory as a `MappedByteBuffer`. Reads and writes on the buffer become page faults served by the kernel's page cache, so random access to a multi-gigabyte file costs no system call per access and no heap. It is how databases, Lucene and Kafka's index files work. The costs: the mapping is only released when the buffer is garbage collected (Java has no `unmap`, except through the `Arena`-scoped foreign memory API in Java 22 and later), `MappedByteBuffer` is limited to 2 GiB per mapping, and a write to a mapped buffer is not durable until `force()` or the OS flushes.

## Example

```java
import java.io.BufferedInputStream;
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.stream.Stream;

public class FilesDemo {

    public static void main(String[] arguments) throws IOException {
        Path directory = Files.createTempDirectory("files-demo");
        Path csv = directory.resolve("orders.csv");

        Files.writeString(csv, "id,sku,quantity\n1,apple,3\n2,pear,5\n", StandardCharsets.UTF_8);
        System.out.println("size : " + Files.size(csv) + " bytes");

        try (Stream<String> lines = Files.lines(csv, StandardCharsets.UTF_8)) {
            int total = lines.skip(1)
                .mapToInt(line -> Integer.parseInt(line.split(",")[2]))
                .sum();
            System.out.println("total quantity : " + total);
        }

        try (BufferedWriter writer = Files.newBufferedWriter(csv, StandardCharsets.UTF_8, StandardOpenOption.APPEND)) {
            writer.write("3,plum,7");
            writer.newLine();
        }
        try (BufferedReader reader = Files.newBufferedReader(csv, StandardCharsets.UTF_8)) {
            System.out.println("lines after append : " + reader.lines().count());
        }

        Path temporary = directory.resolve("orders.csv.tmp");
        Files.writeString(temporary, "id,sku,quantity\n", StandardCharsets.UTF_8);
        Files.move(temporary, csv, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        System.out.println("after atomic replace : " + Files.readAllLines(csv));

        Path big = directory.resolve("big.bin");
        try (OutputStream output = Files.newOutputStream(big)) {
            byte[] chunk = new byte[1 << 20];
            for (int index = 0; index < 64; index++) {
                output.write(chunk);
            }
        }
        long started = System.nanoTime();
        try (InputStream input = Files.newInputStream(big)) {
            while (input.read() != -1) {
            }
        }
        System.out.println("64 MiB byte-by-byte unbuffered : " + (System.nanoTime() - started) / 1_000_000 + " ms");
        started = System.nanoTime();
        try (InputStream input = new BufferedInputStream(Files.newInputStream(big))) {
            while (input.read() != -1) {
            }
        }
        System.out.println("64 MiB byte-by-byte buffered : " + (System.nanoTime() - started) / 1_000_000 + " ms");
        started = System.nanoTime();
        try (InputStream input = Files.newInputStream(big)) {
            byte[] buffer = new byte[64 * 1024];
            while (input.read(buffer) != -1) {
            }
        }
        System.out.println("64 MiB in 64 KiB chunks : " + (System.nanoTime() - started) / 1_000_000 + " ms");

        try (FileChannel channel = FileChannel.open(big, StandardOpenOption.READ, StandardOpenOption.WRITE)) {
            MappedByteBuffer mapped = channel.map(FileChannel.MapMode.READ_WRITE, 0, channel.size());
            mapped.putLong(0, 42L);
            System.out.println("mapped capacity : " + mapped.capacity() + ", first long : " + mapped.getLong(0));
        }

        try {
            Files.readString(directory.resolve("missing.txt"));
        } catch (NoSuchFileException exception) {
            System.out.println("NoSuchFileException : " + exception.getFile());
        }
    }
}
```

One run of `java FilesDemo.java` on a laptop with an SSD (timings are a single unscientific run, but the ratios are the point):

```text
size : 35 bytes
total quantity : 8
lines after append : 4
after atomic replace : [id,sku,quantity]
64 MiB byte-by-byte unbuffered : 21253 ms
64 MiB byte-by-byte buffered : 205 ms
64 MiB in 64 KiB chunks : 5 ms
mapped capacity : 67108864, first long : 42
NoSuchFileException : /var/folders/.../files-demo.../missing.txt
```

Twenty-one seconds versus five milliseconds for the same 64 MiB: the unbuffered loop made sixty-seven million system calls. The buffered version makes eight thousand; the chunked version one thousand and skips the per-byte method call as well.

## Pitfalls

- Unbuffered reads and writes. The symptom is an import or export that is "CPU bound" while doing almost nothing; the profiler shows `FileInputStream.read` at the top. Wrap it or read into an array.
- `Files.lines`, `Files.list` and `Files.walk` outside try-with-resources. Each leaks one file descriptor; under load the process hits `Too many open files` and every socket accept fails too. The compiler cannot warn you because `Stream` does not look like a resource.
- Implicit charsets. `new FileReader(file)`, `new String(bytes)`, `getBytes()`, `new InputStreamReader(input)` and `new PrintWriter(file)` all use the default charset. Pass `StandardCharsets.UTF_8`.
- `Files.readAllBytes` or `readString` on a file you did not size. A 4 GiB upload read into a `byte[]` is an `OutOfMemoryError`; stream it, or bound it with `Files.size` first.
- Writing the final file in place. A crash or a concurrent reader sees a truncated file. Temporary file plus atomic move, in the same directory.
- `File.delete()` and friends returning `false`. No exception, no reason. `Files.delete` throws `NoSuchFileException`, `DirectoryNotEmptyException` or `AccessDeniedException` and tells you which.
- Path traversal. `Path.of(uploadDirectory, userSuppliedName)` with a name like `../../etc/passwd` escapes the directory. `resolve`, then `normalize`, then check `startsWith(uploadDirectory)`.
- Memory-mapped files as a default. They are excellent for random access to large read-mostly files and a trap for everything else: the 2 GiB limit per mapping, unmapping only on GC, and durability only after `force()`. For a sequential read, a buffered stream is as fast and far simpler.
- `Files.walk` on a tree with unreadable directories. It throws `UncheckedIOException` on the first one and the whole stream is gone; `Files.walkFileTree` with a `SimpleFileVisitor` lets you override `visitFileFailed`, skip and continue.

## Check yourself

1. A service reads a 200 MB log file with `Files.lines(path).filter(...).count()` on every request and crashes after a few hundred requests with `Too many open files`. What is leaking, and what is the one-line fix?
2. Why does `input.read()` on a bare `Files.newInputStream` take seconds per megabyte, and which two different changes each fix it?
3. Your exporter writes `report.csv` directly and a downstream job occasionally reads a truncated file. Describe the write sequence that makes this impossible on a POSIX file system.
4. When is a `MappedByteBuffer` the right choice over a `BufferedInputStream`, and what are two costs you accept by using it?

## Go deeper

- [dev.java: Java I/O](https://dev.java/learn/java-io/) · the official tutorial, covering streams, readers, `Path`, `Files` and the file system API in order.
- [java.nio.file.Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html) · read the method list once; most hand-written file code already exists here.
- [FileChannel.map](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html#map(java.nio.channels.FileChannel.MapMode,long,long)) · the exact semantics and caveats of memory mapping.
- [JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400) · what the default charset means for each `java.io` constructor since Java 18.

---

Part of [Java](../README.md) · item 3.2
