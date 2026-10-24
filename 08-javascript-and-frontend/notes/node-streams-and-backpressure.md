# Node streams and backpressure

> **In one sentence:** A stream processes data in chunks as they arrive instead of loading everything first, backpressure is the signal that lets a slow consumer pause a fast producer so those chunks do not pile up in memory, and `pipeline` is the way to connect streams because it propagates errors and destroys every stage on failure, which `pipe` does not.

**Why it matters:** A Node service that reads a whole upload into memory before parsing it, or builds a 200 MB JSON string before sending it, works on the developer's laptop and falls over on the first large file in production, and because there is one process and one heap it takes every other request down with it. Streams are also what HTTP requests and responses, file handles and `zlib` already are in Node, so you meet the API whether or not you choose it. Java has `InputStream` and Reactive Streams; Node's version is lower level, and its backpressure rules are easy to ignore by accident.

## The idea

**Four kinds of stream**, all in `node:stream`:

| Class | Role | Examples |
|---|---|---|
| `Readable` | a source you pull chunks from | `fs.createReadStream`, the request body (`http.IncomingMessage`), `process.stdin` |
| `Writable` | a sink you push chunks into | `fs.createWriteStream`, `http.ServerResponse`, `process.stdout` |
| `Duplex` | both, with independent sides | a TCP socket |
| `Transform` | a Duplex whose output is computed from its input | `zlib.createGzip()`, `crypto.createCipheriv()`, your own parsers |

Chunks are `Buffer`s by default, or strings when you set an `encoding`. In **object mode** (`objectMode: true`, or `readableObjectMode`/`writableObjectMode` for one side only) a chunk is any JavaScript value, which is how a parser turns bytes into records.

**Backpressure.** Every stream has an internal buffer and a `highWaterMark`: 64 KiB for byte streams in Node 22 (16 KiB in Node 20), 16 items in object mode. `writable.write(chunk)` returns `false` once the buffer has reached the mark, and the producer is expected to stop and wait for the `'drain'` event. A `Readable` stops pulling from its source while its buffer is full and nobody is reading. `pipe` and `pipeline` connect the two signals: when the writable says stop, the readable pauses. Nothing forces you to honour the return value of `write()`; the chunk is accepted anyway and the buffer simply grows, which is the memory leak that shows up after a week of bulk exports.

**`pipeline`, not `pipe`.** `readable.pipe(writable)` forwards data and backpressure but not errors. If the readable fails, the writable is left open (a leaked file handle, an HTTP response that never finishes) and the error is emitted only on the readable. `pipeline(...stages)` from `node:stream/promises` destroys every stage on the first error and settles once, in one place. It also accepts async generator functions as stages, which is the shortest way to write a transform.

**Async iteration.** Every `Readable` is an async iterable: `for await (const chunk of readable)` pulls chunks with backpressure handled for you and ends when the stream ends. Prefer it to `'data'` listeners, which switch the stream into flowing mode and deliver data as fast as it arrives regardless of whether you can keep up. `Readable.from(iterable)` goes the other way.

**When to stream.** Whenever the data may be larger than you want in memory at once, or the first bytes should leave before the last ones arrive: large files, uploads, CSV and NDJSON exports, proxying, responses of unbounded size. For a 2 KB JSON body, buffering is fine. The test is "would a hundred concurrent requests like this fit in the heap?".

**`EventEmitter`.** Streams are event emitters, which is where `'data'`, `'end'`, `'error'`, `'drain'` and `'finish'` come from. `on(name, listener)` registers a listener, `once` registers one that is removed after its first call, and `emit(name, ...values)` calls every listener synchronously, in registration order, before it returns. `events.once(emitter, name)` returns a promise for the next event, which is what `await once(output, "drain")` below relies on. One rule bites: emitting `'error'` with no `'error'` listener throws, and in a server that uncaught exception ends the process. Attach an error listener to every stream you create by hand, or let `pipeline` do it.

## Example: CSV to JSON as a pipeline

```javascript
// csv-to-json-stream.mjs
import { createReadStream, createWriteStream } from "node:fs";
import { Transform } from "node:stream";
import { pipeline } from "node:stream/promises";

async function* splitLines(source) {
  let remainder = "";
  for await (const chunk of source) {
    const lines = (remainder + chunk).split("\n");
    remainder = lines.pop() ?? "";
    yield* lines.filter((line) => line.length > 0);
  }
  if (remainder.length > 0) {
    yield remainder;
  }
}

class CsvRowToObject extends Transform {
  constructor() {
    super({ objectMode: true });
    this.headers = undefined;
    this.lineNumber = 0;
  }

  _transform(line, encoding, callback) {
    this.lineNumber += 1;
    const fields = line.split(",");
    if (this.headers === undefined) {
      this.headers = fields;
      callback();
      return;
    }
    if (fields.length !== this.headers.length) {
      callback(new Error(`line ${this.lineNumber}: expected ${this.headers.length} fields, got ${fields.length}`));
      return;
    }
    const record = Object.fromEntries(this.headers.map((header, index) => [header, fields[index]]));
    record.quantity = Number(record.quantity);
    record.unitPrice = Number(record.unitPrice);
    callback(null, record);
  }
}

async function* toJsonArray(records) {
  let separator = "[\n";
  for await (const record of records) {
    yield separator + JSON.stringify(record);
    separator = ",\n";
  }
  yield separator === "[\n" ? "[]\n" : "\n]\n";
}

const [, , inputPath, outputPath] = process.argv;
try {
  await pipeline(
    createReadStream(inputPath, { encoding: "utf8" }),
    splitLines,
    new CsvRowToObject(),
    toJsonArray,
    createWriteStream(outputPath),
  );
  console.log(`wrote ${outputPath}`);
} catch (error) {
  console.error(`conversion failed: ${error.message}`);
  process.exitCode = 1;
}
console.log(`peak resident set: ${Math.round(process.resourceUsage().maxRSS / 1024)} MB`);
```

Three kinds of stage in one chain. `splitLines` is an async generator: `pipeline` wraps it as a Duplex, it pulls from the file with `for await` (so it never reads faster than the next stage consumes), and it carries the partial last line across chunk boundaries, because a chunk is not a line. The `encoding: "utf8"` option matters: without it a multi-byte character split across two chunks would decode as garbage. `CsvRowToObject` is a class-based `Transform` in object mode; each `callback(null, record)` pushes one record, and `callback(error)` fails the whole pipeline. `toJsonArray` turns records back into text for the file.

On a 1,000,000-row, 37 MB file, on the laptop used to write this note:

```text
$ node csv-to-json-stream.mjs orders.csv orders.json
wrote orders.json
peak resident set: 86 MB
```

With a malformed third line:

```text
$ node csv-to-json-stream.mjs broken.csv broken.json
conversion failed: line 3: expected 5 fields, got 3
```

The process exits with code 1 and every stage, including the write stream, has been destroyed. What `pipeline` does not do is delete the partially written output; if the file must be all-or-nothing, write to a temporary name and rename on success.

## Example: the memory cost of not streaming

The same conversion with `readFile`, `split`, `map` and `JSON.stringify`:

```javascript
// csv-to-json-buffered.mjs
import { readFile, writeFile } from "node:fs/promises";

const [, , inputPath, outputPath] = process.argv;
const text = await readFile(inputPath, "utf8");
const [headerLine, ...lines] = text.split("\n");
const headers = headerLine.split(",");
const records = lines
  .filter((line) => line.length > 0)
  .map((line) => {
    const fields = line.split(",");
    const record = Object.fromEntries(headers.map((header, index) => [header, fields[index]]));
    record.quantity = Number(record.quantity);
    record.unitPrice = Number(record.unitPrice);
    return record;
  });
await writeFile(outputPath, JSON.stringify(records));
console.log(`peak resident set: ${Math.round(process.resourceUsage().maxRSS / 1024)} MB`);
```

```text
$ node csv-to-json-buffered.mjs orders.csv orders.json
peak resident set: 701 MB
```

Same input, identical output, eight times the memory: the 37 MB text, an array of a million line strings, a million objects and an 86 MB JSON string are all alive at once. To be fair to buffering, this version ran in 1.5 s against 2.2 s for the pipeline, because per-chunk bookkeeping costs CPU. Streaming buys bounded memory, not speed. In a server that trade is the right one: a few concurrent conversions like this one exhaust the heap, and V8 ends the process with a fatal "JavaScript heap out of memory" error that no `try`/`catch` sees.

## Example: what `write()` returning `false` means

```javascript
import { Writable } from "node:stream";

const slowSink = new Writable({
  highWaterMark: 1024,
  write(chunk, encoding, callback) {
    setTimeout(callback, 10);
  },
});
slowSink.on("drain", () => console.log("drain"));

for (let index = 1; index <= 4; index += 1) {
  const accepted = slowSink.write(Buffer.alloc(512));
  console.log(`write ${index}: ${accepted}, buffered ${slowSink.writableLength} bytes`);
}
```

```text
write 1: true, buffered 512 bytes
write 2: false, buffered 1024 bytes
write 3: false, buffered 1536 bytes
write 4: false, buffered 2048 bytes
drain
```

Nothing was dropped and nothing threw; the buffer just passed the mark. The correct producer loop, which is how the test file above was generated, waits when told to:

```javascript
for (let index = 1; index <= rowCount; index += 1) {
  if (!output.write(`${index},SKU-${index % 5000},${(index % 7) + 1},...\n`)) {
    await once(output, "drain");
  }
}
output.end();
await finished(output);
```

## Pitfalls

- `pipe()` with no error handling. The symptom is a slowly growing count of open file descriptors or HTTP responses that hang until the client times out. Use `pipeline`.
- Collecting a request body with `request.on("data", ...)` into an array and `Buffer.concat` with no size limit. A client can send gigabytes; set a body limit (frameworks have one, see item 3.4).
- Ignoring the return value of `write()` in a loop. Memory climbs linearly with the export size and the process dies on the largest customer's data.
- Splitting on `"\n"` per chunk without carrying the remainder. Every chunk boundary silently corrupts one record, and the last line of a file with no trailing newline is lost unless the flush step yields it.
- Doing asynchronous work in `_transform` and calling `callback` before it finishes. Backpressure is broken because the stream believes the chunk was handled. Call `callback` when the work is done, or use an async generator stage.
- Treating streaming as a performance optimisation. It is a memory bound; measure before claiming it is faster.
- Forgetting that `highWaterMark` is a hint about buffering, not a chunk size. Chunks from a file stream are up to the mark; chunks from a socket are whatever arrived.

## Check yourself

1. `write()` returned `false` and your loop kept writing. Where does the data go, what does memory do over time, and why does a `pipeline` never have this problem?
2. A chain built with `pipe()` fails in the read stream. Which streams are destroyed, which resource leaks, and where does the error surface?
3. The buffered converter was faster than the pipeline in the measurement above. Why would you still choose the pipeline in a server, and when is buffering the right call?
4. A line splitter that yields `chunk.split("\n")` directly corrupts data in two different ways. Name both, and say which option on `createReadStream` fixes a third problem with multi-byte characters.

## Go deeper

- [Node.js: Stream](https://nodejs.org/api/stream.html) · the reference; read the "Backpressure" paragraphs under `writable.write()` and the `pipeline` section with its async generator examples.
- [Node.js: Backpressuring in Streams](https://nodejs.org/en/learn/modules/backpressuring-in-streams) · the official guide to what `highWaterMark` and `'drain'` do, with the pipe-versus-pipeline argument.
- [Node.js: Events](https://nodejs.org/api/events.html) · `EventEmitter`, the `'error'` rule and `events.once`.
- [Node.js Design Patterns](https://www.nodejsdesignpatterns.com/) · the streams chapter covers sequential, parallel and ordered-parallel stream processing (paid).

---

Part of [JavaScript & Frontend](../README.md) · item 3.3
