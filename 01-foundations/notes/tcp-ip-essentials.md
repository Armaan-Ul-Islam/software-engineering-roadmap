# TCP/IP essentials: handshakes, ports, queues and TIME_WAIT

> **In one sentence:** IP moves packets between hosts with no promises, TCP turns that into an ordered, reliable byte stream between two address-and-port pairs after a three-way handshake, and most production "connection" problems live at the edges of that stream: the accept queue, the ephemeral port range and `TIME_WAIT`.

**Why it matters:** "Connection refused", "connection timed out" and "connection reset" each name a different failure in a different place, and reading them correctly saves hours. Connection pools, load balancers and batch jobs fail on accept-queue overflow and ephemeral-port exhaustion, not on the happy path. And the handshake is the first thing an interviewer draws on the whiteboard.

## The idea

**Layers in practice (item 3.1).** An Ethernet frame carries an IP packet across one link; IP routes the packet hop by hop to a destination address and may lose, duplicate or reorder it; TCP or UDP inside the packet adds ports, which select a process on the host; the application protocol (HTTP, TLS, PostgreSQL's wire protocol) rides inside that. Each layer wraps the one above and knows nothing about it. A TCP connection is identified by the four-tuple of source address, source port, destination address and destination port, which is why one host can hold thousands of connections to the same server port.

**Ports.** 16 bits, so 0 to 65535. Ports below 1024 need root or `CAP_NET_BIND_SERVICE`. A server binds a fixed port; a client lets the kernel pick an *ephemeral* port from a range: 32768 to 60999 on Linux by default (`/proc/sys/net/ipv4/ip_local_port_range`), 49152 to 65535 on macOS.

**TCP (item 3.3).** A connection starts with a three-way handshake: the client sends `SYN` with its initial sequence number, the server answers `SYN-ACK`, the client answers `ACK`; one round trip before the first byte of data, and TLS adds more. Every byte is numbered; the receiver acknowledges, the sender retransmits what is not acknowledged in time, the receive window stops a fast sender from drowning a slow receiver (flow control), and the congestion window stops it from drowning the network. The price is head-of-line blocking: one lost segment holds back every byte behind it until the retransmission arrives. UDP offers ports and a checksum on top of IP and nothing else: no connection, no ordering, no retransmission, and message boundaries preserved. DNS, real-time media and QUIC (HTTP/3) use it, QUIC precisely so that it can rebuild reliability per stream and escape TCP's head-of-line blocking.

**Listening and the accept queue (item 3.4).** `socket()`, `bind()`, `listen(backlog)` create a listening socket. The kernel completes handshakes on its own and parks finished connections in the *accept queue*; `accept()` takes one out and returns a new socket for it, and the listening socket stays. If the application is slow to accept (thread pool full, a long GC pause), the queue fills to `backlog` (capped by `net.core.somaxconn`, 4096 by default on current kernels) and further handshakes are dropped or reset; clients see slow connects or resets while the server looks idle.

**Closing and TIME_WAIT.** Each side sends `FIN` and acknowledges the other's. The side that closes first enters `TIME_WAIT` for twice the maximum segment lifetime, 60 seconds on Linux, so that late packets cannot be mistaken for a new connection on the same four-tuple. A client that opens a fresh connection per request to the same server therefore ties up one of its roughly 28,000 ephemeral ports for a minute each time; above about 470 connections per second it runs out and `connect` fails with `EADDRNOTAVAIL` ("Cannot assign requested address"). Connection pooling and keep-alive exist to prevent exactly this.

## Example: reading `ss` and `curl -v`

A Java `HttpServer` listening on port 8081 in a Linux container, then one request with `curl`:

```text
$ ss -tlnp
State  Recv-Q Send-Q Local Address:Port Peer Address:Port Process
LISTEN 0      50                 *:8081            *:*    users:(("java",pid=333,fd=5))
```

For a `LISTEN` socket the queue columns have a special meaning: `Recv-Q` is how many completed connections are waiting in the accept queue right now, `Send-Q` is the backlog limit (50, Java's default). A `Recv-Q` that stays close to `Send-Q` means the application is not accepting fast enough.

```text
$ curl -sv http://127.0.0.1:8081/health
*   Trying 127.0.0.1:8081...
* Established connection to 127.0.0.1 (127.0.0.1 port 8081) from 127.0.0.1 port 37048
* using HTTP/1.x
> GET /health HTTP/1.1
> Host: 127.0.0.1:8081
> User-Agent: curl/8.18.0
> Accept: */*
>
* Request completely sent off
< HTTP/1.1 200 OK
< Date: Fri, 23 Oct 2026 18:43:21 GMT
< Content-length: 3
<
{ [3 bytes data]
* Connection #0 to host 127.0.0.1:8081 left intact
ok
```

`Trying` is the `SYN` going out. `Established connection` is the handshake done, and recent curl versions print the full four-tuple, including the kernel-chosen ephemeral port 37048 (older versions say `Connected to` without the source port). Only then does HTTP start. `left intact` means curl kept the connection open while it ran; it closed it on exit, which makes the client the side that closed first:

```text
$ ss -tan
State     Recv-Q Send-Q Local Address:Port  Peer Address:Port
TIME-WAIT 0      0          127.0.0.1:37048    127.0.0.1:8081
LISTEN    0      50                 *:8081             *:*
```

For an `ESTAB` socket, `Recv-Q` is bytes received that the application has not read yet (the application is slow) and `Send-Q` is bytes sent but not yet acknowledged (the peer or the network is slow). The three failures you will meet: *connection refused* is a `RST` in answer to the `SYN`, immediate, meaning the host is reachable and nothing listens on that port; *connection timed out* means the `SYN` got no answer at all (a firewall dropped it, the address is wrong, or the accept queue overflowed); *connection reset* is a `RST` in the middle of a stream (the process died, or a NAT or load balancer dropped an idle connection and no longer recognises the next packet).

## Pitfalls

- Treating "refused" and "timed out" alike. Refused is fast and points at the port; timed out is slow and points at the path or the queue.
- A new connection per request to a database or an API. `TIME_WAIT` piles up on the client and ephemeral ports run out. Pool connections and use keep-alive.
- A backlog sized for average load. Bursts and GC pauses overflow a small accept queue; Tomcat's `acceptCount` defaults to 100. Watch `Recv-Q` on the listening socket during peaks.
- Believing a successful `write` means the peer received the data. It is in the local send buffer. Only an application-level acknowledgement proves delivery.
- No timeouts. Without traffic, TCP takes a long time to notice a dead peer. Set connect and read timeouts on every client, and TCP keepalive on long-idle connections.
- A pool idle time longer than the load balancer's idle timeout. The balancer silently drops the connection; the next request gets a reset. Keep the pool's maximum idle time below the balancer's.
- `Address already in use` on restart. Usually an old process still holds the port; `lsof -i :8081` or `ss -tlnp` names it.
- Binding to `127.0.0.1` inside a container. Nothing outside the container can reach it; bind to `0.0.0.0`.

## Check yourself

1. `ss -tln` shows `LISTEN 101 100 0.0.0.0:8080` during a traffic spike. What is happening, and what do new clients experience?
2. A batch job opens a new connection to PostgreSQL per row and fails after about 28,000 rows with "Cannot assign requested address". Explain, and give two fixes.
3. Your client gets "connection refused" from one host and "connection timed out" from another. What does each tell you about the network path and about the server process?
4. Why does QUIC run over UDP when it needs reliability anyway?

## Go deeper

- [HPBN: Building Blocks of TCP](https://hpbn.co/building-blocks-of-tcp/) and [Building Blocks of UDP](https://hpbn.co/building-blocks-of-udp/) · handshake, slow start, head-of-line blocking and when UDP wins, written for application developers.
- [Beej's Guide to Network Programming](https://beej.us/guide/bgnet/) · `socket`, `bind`, `listen`, `accept` with code; the socket API every language wraps.
- [Cloudflare: SYN packet handling in the wild](https://blog.cloudflare.com/syn-packet-handling-in-the-wild/) · the SYN queue and the accept queue explained by people who run them at scale.
- [ss(8)](https://man7.org/linux/man-pages/man8/ss.8.html) · every column and filter of `ss`.
- [RFC 9293: Transmission Control Protocol](https://www.rfc-editor.org/rfc/rfc9293) · the current TCP specification, with the state diagram that `TIME_WAIT` lives in.

---

Part of [Foundations](../README.md) · items 3.1, 3.3, 3.4
