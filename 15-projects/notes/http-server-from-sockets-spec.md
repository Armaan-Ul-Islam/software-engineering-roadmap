# Project spec: an HTTP/1.1 server from raw sockets

> **In one sentence:** Build an HTTP/1.1 server in plain Java on `ServerSocket`, with a byte-exact request parser, keep-alive connections, a bounded thread pool and static files, and prove with `curl` and a load generator that it neither leaks threads nor sockets.

**Why it matters:** Every framework you will ever use hides the same four problems: where a request ends, when a connection may be reused, which thread does the work, and what happens when clients are slow. Building the server once makes Tomcat's thread settings, nginx timeouts and "connection reset" tickets concrete, and it is the classic interview question for systems-minded backend roles.

## The idea

You will write one program, `tinyhttp`, that listens on a port, parses HTTP/1.1 requests from the raw byte stream, serves files from a directory, and keeps connections open between requests. No library beyond the JDK. The deliverable is not the feature list. It is the proof that the server behaves under 100 concurrent keep-alive connections and 10,000 requests the way RFC 9112 says it should, with the measurements to show it.

Scope, deliberately small:

- 1.1 `GET` and `HEAD` for files under a document root; `404` for missing files, `400` for malformed requests, `405` for other methods.
- 1.2 Persistent connections by default (HTTP/1.1), closed on `Connection: close`, on HTTP/1.0 without `Connection: keep-alive`, and after an idle timeout.
- 1.3 A fixed pool of worker threads with a bounded queue; `503` when the queue is full rather than unbounded growth.
- 1.4 Request bodies read exactly to `Content-Length` and discarded, so a `POST` to a static path gets a clean `405` instead of a connection reset.
- 1.5 Limits on request-line length (`414`) and total header size (`431`), and a `Host` header requirement.

Concepts exercised: Foundations 3.3, 3.4, 3.7; Web & HTTP 3.1, 3.4, 4.1, 4.3, 4.6, 11.1; Memory & Concurrency 4.1, 5.1, 5.4, 5.5; Java 3.2, 5.1, 7.6.

## Example: the connection loop and the milestones

The core is one method per connection that reads requests until the client goes away. This version (Java 21, compiled and tested with `curl`) serves milestone 2; later milestones replace `BufferedReader` with a byte parser, because `readLine` buffers ahead and would swallow the bytes of a request body.

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class SocketHttpServer {

    record Request(String method, String target, String version, Map<String, String> headers) {

        boolean wantsClose() {
            String connection = headers.getOrDefault("connection", "");
            return connection.equalsIgnoreCase("close")
                || (version.equals("HTTP/1.0") && !connection.equalsIgnoreCase("keep-alive"));
        }
    }

    static Request readRequest(BufferedReader reader) throws IOException {
        String requestLine = reader.readLine();
        if (requestLine == null) {
            return null;
        }
        String[] parts = requestLine.split(" ", 3);
        if (parts.length != 3) {
            throw new IOException("malformed request line: " + requestLine);
        }
        Map<String, String> headers = new HashMap<>();
        String line;
        while ((line = reader.readLine()) != null && !line.isEmpty()) {
            int colon = line.indexOf(':');
            if (colon <= 0) {
                throw new IOException("malformed header: " + line);
            }
            headers.put(line.substring(0, colon).trim().toLowerCase(Locale.ROOT), line.substring(colon + 1).trim());
        }
        return new Request(parts[0], parts[1], parts[2], headers);
    }

    static void serveConnection(Socket socket) {
        try (socket;
             BufferedReader reader = new BufferedReader(
                 new InputStreamReader(socket.getInputStream(), StandardCharsets.ISO_8859_1));
             OutputStream output = socket.getOutputStream()) {
            socket.setSoTimeout(5_000);
            while (true) {
                Request request = readRequest(reader);
                if (request == null) {
                    return;
                }
                byte[] body = ("You asked for " + request.target() + "\n").getBytes(StandardCharsets.UTF_8);
                boolean close = request.wantsClose();
                String head = "HTTP/1.1 200 OK\r\n"
                    + "Content-Type: text/plain; charset=utf-8\r\n"
                    + "Content-Length: " + body.length + "\r\n"
                    + (close ? "Connection: close\r\n" : "")
                    + "\r\n";
                output.write(head.getBytes(StandardCharsets.ISO_8859_1));
                output.write(body);
                output.flush();
                if (close) {
                    return;
                }
            }
        } catch (IOException exception) {
            // an idle timeout or a client hanging up mid-request is the normal way a keep-alive connection ends
        }
    }

    public static void main(String[] arguments) throws IOException {
        ExecutorService workers = Executors.newFixedThreadPool(64);
        try (ServerSocket serverSocket = new ServerSocket(8080)) {
            while (true) {
                Socket socket = serverSocket.accept();
                workers.execute(() -> serveConnection(socket));
            }
        }
    }
}
```

`curl -v http://localhost:8080/a http://localhost:8080/b` prints `Re-using existing connection` before the second request; `curl --http1.0` gets `Connection: close` and the socket is closed after the response.

Milestones, each ending in a committed test:

1. **Accept and parse.** Thread per connection, request line and headers parsed, a fixed `200` response with `Content-Length`. Test: open a `java.net.Socket`, write the request bytes by hand, read the response and assert the status line and headers. Do not use `HttpClient` yet; it hides the bytes you are learning.
2. **Keep-alive.** The loop above: several requests on one socket, `Connection: close` honoured, HTTP/1.0 defaults to close, idle connections closed after `setSoTimeout`. Test: two requests on one socket produce two responses; an idle socket is closed by the server within the timeout.
3. **Bytes, bodies and limits.** Replace the reader with a parser over `InputStream` that finds `\r\n\r\n`, then reads exactly `Content-Length` bytes. Return `400` for a bad request line or a missing `Host`, `414` and `431` for oversized lines and headers, `405` for unsupported methods, and read the body before answering so the client never sees a reset. Test: a table of malformed inputs and their expected status codes.
4. **Thread pool and static files.** `ThreadPoolExecutor` with a bounded `ArrayBlockingQueue` and a rejection handler that writes `503` and closes; files served from a document root with `Content-Type` by extension, `HEAD` support, and path traversal (`/../`) rejected after normalising the path. Test: `GET /../../etc/passwd` is `404` or `400`; a served file's SHA-256 matches the file on disk.
5. **Load without leaks.** Run k6 or `wrk` with 100 keep-alive connections for 10,000 requests. Before and after, record the thread count (`jcmd <pid> Thread.print | grep -c tid`) and open sockets (`lsof -p <pid> | grep -c TCP`). Test: an integration test that drives 100 connections through `java.net.http.HttpClient`, then asserts both counts returned to the pre-load baseline.

Definition of done:

- 2.1 Passes a conformance smoke test with `curl -v`, serves 10k requests over 100 keep-alive connections without leaking threads or sockets.
- 2.2 The README lists every parsing decision (line endings accepted, header limits, which methods, what closes a connection) with the RFC 9112 section it follows.
- 2.3 The README has a table of requests per second and p99 latency at 1, 10 and 100 connections, with the pool size and queue length used.

Stretch goals:

- 3.1 Chunked transfer encoding, gzip, HTTP/1.1 pipelining, a virtual-thread variant compared under load.

## Pitfalls

- Using `BufferedReader.readLine` past milestone 2. It reads ahead into its buffer, so the first bytes of the request body are gone when you switch to the raw stream. Parse bytes, not lines.
- Writing responses through a `PrintWriter` or `println`. You get the platform line separator and the default charset instead of `\r\n` and ISO-8859-1 headers; `curl` may still cope, which hides the bug.
- No socket timeout. A keep-alive client that goes quiet holds a pool thread forever; with 64 threads and 64 idle browsers, the server accepts new connections and never answers them.
- A fixed pool with `Executors.newFixedThreadPool`. Its queue is unbounded, so overload turns into memory growth and seconds of latency instead of a fast `503`.
- Answering `4xx` without reading the request body. The server closes with unread bytes, the kernel sends `RST`, and the client reports "connection reset" instead of your status code.
- Treating header names as case-sensitive, or trusting `Content-Length` without a limit. Both are conformance failures a load generator will not catch; the malformed-input test table will.

## Check yourself

1. Why can a thread-per-connection server with 64 threads serve 1,000 requests per second from one client but hang with 65 idle browsers connected, and what does that tell you about keep-alive and pool sizing?
2. Which of `Connection: close`, HTTP/1.0 without `keep-alive`, and an idle timeout should close the connection before the response, after it, or without a response at all?
3. A client sends `POST /index.html` with a 2 MiB body. Describe the two different things the client observes depending on whether you read the body before answering `405`.
4. Your load test shows the thread count stable but `lsof` growing by one socket per connection. Where in the code can a socket escape the `try-with-resources`?

## Go deeper

- [RFC 9112: HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112.html) · message framing, persistent connections and what a server must reject.
- [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html) · methods, status codes and header semantics for milestones 3 and 4.
- [Beej's Guide to Network Programming](https://beej.us/guide/bgnet/) · what the kernel does under `accept`, `read` and `close`.
- [Java Concurrency in Practice](https://jcip.net/) · bounded queues, rejection and shutdown for milestone 4.
- [Grafana k6](https://grafana.com/docs/k6/latest/) · the load generator for milestone 5.

---

Part of [Projects](../README.md) · item 1.1
