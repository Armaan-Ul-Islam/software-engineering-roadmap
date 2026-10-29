# IP addressing, subnets and NAT

> **In one sentence:** An IP address is a number plus a prefix length that splits it into a network part and a host part; a router forwards each packet to the most specific matching prefix in its table; and NAT lets a whole private network hide behind one public address by rewriting addresses and ports on the way out and back.

**Why it matters:** "The service is up but I cannot reach it" is usually a subnet, routing or NAT problem, not an application bug. You will size VPC subnets, read security-group rules written as CIDR blocks, explain why a container can call the internet but the internet cannot call it, and debug a database whose connections drop because a NAT gateway forgot them.

## The idea

**IPv4 addresses are 32-bit numbers.** `10.1.4.37` is the dotted-decimal spelling of one 32-bit integer. The address alone does not say which hosts are neighbours; the *prefix length* does. `10.1.4.37/22` means "the first 22 bits identify the network, the remaining 10 bits identify the host within it". This is CIDR notation, and it replaced the old class A/B/C scheme in 1993. The same information as a *subnet mask* is `255.255.252.0`: 22 one-bits followed by 10 zero-bits.

From a prefix length you can derive everything else with bit arithmetic:

| Quantity | How | For `10.1.4.37/22` |
|---|---|---|
| Mask | `prefixLength` one-bits, then zeros | `255.255.252.0` |
| Network address | `address AND mask` | `10.1.4.0` |
| Broadcast address | `network OR NOT mask` | `10.1.7.255` |
| Addresses in the block | 2 to the power of (32 minus prefix) | 1024 |
| Usable host addresses | block minus network and broadcast | 1022 |

Each step down in prefix length doubles the block: a `/24` is 256 addresses, a `/23` is 512, a `/16` is 65,536. Cloud providers reserve a few more per subnet (AWS takes five from every subnet), so a `/28` in AWS gives you 11 usable addresses, not 14.

**Private ranges and public ranges.** RFC 1918 reserves three blocks that are never routed on the public internet: `10.0.0.0/8`, `172.16.0.0/12` (that is `172.16.0.0` to `172.31.255.255`) and `192.168.0.0/16`. Your office, your home router and every cloud VPC use them. Two more you will meet: `127.0.0.0/8` is loopback (`localhost`), and `169.254.0.0/16` is link-local, which is why a machine that failed to get a DHCP lease shows a `169.254.x.x` address, and why cloud instance metadata lives at `169.254.169.254`. The blocks `192.0.2.0/24`, `198.51.100.0/24` and `203.0.113.0/24` are reserved for documentation; use them in examples instead of someone's real address.

**Routing.** A host or router holds a table of prefixes, each with a next hop. For every packet it picks the entry with the *longest matching prefix* and hands the packet to that next hop; `0.0.0.0/0`, the default route, matches everything and is used when nothing more specific does. A host on `10.1.4.37/22` therefore sends a packet to `10.1.6.9` directly over the link (same `/22`) and a packet to `10.1.8.9` to its default gateway. Packets to a subnet you have no route for are not slow, they are silently dropped or answered with "no route to host".

**NAT.** Private addresses cannot be used on the internet, and there are far fewer public IPv4 addresses than devices. A NAT router sits at the border with one public address. When `192.168.1.20:51000` opens a connection to `203.0.113.9:443`, the router rewrites the source to `198.51.100.1:40321` (its own address and a port it picks), remembers the mapping, and forwards the packet. The reply to `198.51.100.1:40321` is matched against the table and rewritten back to `192.168.1.20:51000`. Consequences: outbound connections work without configuration; inbound connections have no table entry and are dropped unless you add a port-forwarding rule; and the mapping is state in the router, with a timeout. Idle TCP connections that outlive the timeout are dropped silently, which is why long-lived database and message-broker connections across a NAT gateway need TCP keepalives (item 3.4 covers the reset you see when that happens). Cloud "NAT gateways" and Kubernetes nodes do the same thing for pods.

**IPv6.** 128-bit addresses written in hex groups: `2001:db8::1` (the `::` stands for one run of zero groups; `2001:db8::/32` is the documentation block). The address space is large enough that every device gets a public address and NAT is unnecessary; a typical LAN gets a `/64`, which is more addresses than the entire IPv4 internet. The ideas are the same: prefix, longest match, default route. The main practical differences are that there is no broadcast address, link-local addresses start with `fe80::`, and in a URL the address goes in brackets: `http://[2001:db8::1]:8080/`.

## Example: compute a subnet, then read a routing table

A small Java 21 program that does the arithmetic from the table above:

```java
import java.net.InetAddress;
import java.net.UnknownHostException;

public final class Cidr {

    public static void main(String[] arguments) throws UnknownHostException {
        describe("10.1.4.37/22");
        describe("192.168.1.130/26");
        describe("203.0.113.9/32");
    }

    private static void describe(String cidr) throws UnknownHostException {
        String[] parts = cidr.split("/");
        int address = toInt(InetAddress.getByName(parts[0]).getAddress());
        int prefixLength = Integer.parseInt(parts[1]);
        int mask = prefixLength == 0 ? 0 : -1 << (32 - prefixLength);
        int network = address & mask;
        int broadcast = network | ~mask;
        long usableHosts = prefixLength >= 31 ? 0 : (1L << (32 - prefixLength)) - 2;
        System.out.printf("%-20s mask %-16s network %-16s broadcast %-16s usable hosts %d%n",
                cidr, toDotted(mask), toDotted(network), toDotted(broadcast), usableHosts);
    }

    private static int toInt(byte[] octets) {
        return ((octets[0] & 0xff) << 24) | ((octets[1] & 0xff) << 16)
                | ((octets[2] & 0xff) << 8) | (octets[3] & 0xff);
    }

    private static String toDotted(int value) {
        return ((value >>> 24) & 0xff) + "." + ((value >>> 16) & 0xff) + "."
                + ((value >>> 8) & 0xff) + "." + (value & 0xff);
    }
}
```

```text
$ java Cidr.java
10.1.4.37/22         mask 255.255.252.0    network 10.1.4.0         broadcast 10.1.7.255       usable hosts 1022
192.168.1.130/26     mask 255.255.255.192  network 192.168.1.128    broadcast 192.168.1.191    usable hosts 62
203.0.113.9/32       mask 255.255.255.255  network 203.0.113.9      broadcast 203.0.113.9      usable hosts 0
```

The `/26` line shows why "same third octet" does not mean "same subnet": `192.168.1.130` and `192.168.1.20` are in different `/26` blocks (`.128` to `.191` and `.0` to `.63`) and need a router between them. A `/32` is a single address, which is how firewall rules name one host.

The routing table of a laptop on a phone hotspot (`netstat -rn` on macOS; `ip route` on Linux prints the same information in a different layout):

```text
$ netstat -rn -f inet
Routing tables

Internet:
Destination        Gateway            Flags               Netif Expire
default            172.20.10.1        UGScg                 en0
127                127.0.0.1          UCS                   lo0
127.0.0.1          127.0.0.1          UH                    lo0
169.254            link#14            UCS                   en0      !
```

`default` is `0.0.0.0/0` with the hotspot (`172.20.10.1`, inside the `172.16.0.0/12` private block) as the gateway. `127` is the loopback `/8`, delivered locally. `169.254` is link-local and reachable only on `en0` with no gateway. A packet to `8.8.8.8` matches only `default`, so it goes to `172.20.10.1`, which is itself a NAT router onto the mobile carrier's network, which may NAT again (carrier-grade NAT). Two layers of address rewriting between this laptop and the internet is normal.

## Pitfalls

- Overlapping subnets. Two VPCs or an office network and a VPN both using `10.0.0.0/16` cannot be peered or routed between; the router has no way to tell them apart. Plan address space before the first subnet exists, and give each environment a disjoint block.
- Sizing a subnet for today. Kubernetes assigns an address to every pod; a `/24` runs out at a few hundred pods and the fix is a migration. Start with more bits than you think you need.
- Security-group and firewall rules with `0.0.0.0/0` as the source "for now". That is every address on the internet. Use the specific block, or the security group of the caller.
- Expecting inbound connections through NAT. A webhook from a partner, a database replica calling home, a peer-to-peer agent: none of them can reach a private address unless something (a load balancer, a port forward, a tunnel) provides a public endpoint. See item 5.5 for SSH tunnels as the quick fix.
- Idle connections across a NAT gateway or load balancer. The mapping times out, the next packet is answered with a reset or dropped, and the application sees `Connection reset` or a hung read minutes later. Enable TCP keepalive, or let the connection pool validate and recycle connections.
- Trusting the client address in logs behind a NAT or proxy. Every user in an office shares one public address; and behind a load balancer the source address is the balancer's. Read `X-Forwarded-For` only from a proxy you control.
- Assuming the same third octet means the same subnet. It is true for a `/24` and false for everything else; compute the network address.

## Check yourself

1. Your VPC is `10.20.0.0/16` and you need eight subnets of equal size. What prefix length do they get, how many addresses does each hold, and what is the network address of the third one?
2. A host at `10.1.4.37/22` sends packets to `10.1.6.9` and `10.1.8.9`. Which one goes to the default gateway, and why?
3. A background job on a private subnet holds a PostgreSQL connection open for an hour between queries, through a NAT gateway. Describe what the job sees when it runs the next query, and two ways to prevent it.
4. Two companies merge; both use `192.168.0.0/16` internally. Why can they not simply connect their networks, and what is the usual fix?

## Go deeper

- [Cloudflare: What is an IP address?](https://www.cloudflare.com/learning/dns/glossary/what-is-my-ip-address/) · the public/private distinction and what your address reveals, in plain language.
- [Kurose & Ross, chapter 4](https://gaia.cs.umass.edu/kurose_ross/) · the network layer: forwarding, longest-prefix matching, IPv4, NAT and IPv6, with lecture videos.
- [Practical Networking](https://www.youtube.com/@PracticalNetworking) · the subnetting series walks the bit arithmetic until it is automatic.
- [CS:APP chapter 11](https://csapp.cs.cmu.edu/) · how addresses and sockets look from the program's side.

---

Part of [Foundations](../README.md) · item 3.2
