# VPC and VNet networking basics: subnets, routes, gateways and firewall rules

> **In one sentence:** A VPC or VNet is a private IP range you carve into subnets, where a subnet is "public" only because its route table points the default route at an internet gateway, and everything else is kept reachable through NAT gateways, stateful security groups and load balancers.

**Why it matters:** Networking is where cloud designs fail quietly: a database with a public IP "for debugging", an application tier that cannot reach the package registry because nobody added a NAT route, a NAT gateway that processes terabytes and becomes the biggest line on the bill. Being able to draw the layout and justify every rule is the first thing a reviewer or interviewer will ask of a backend developer who claims to deploy their own service.

## The idea

### Address space and subnets

A **VPC** (AWS) or **virtual network** (Azure) is an isolated network with a private CIDR range, for example `10.20.0.0/16`, inside one region. You divide it into **subnets**, each tied to one availability zone on AWS (Azure subnets span zones; the resources in them are zonal). Pick a range that does not overlap with your office network or anything you may peer with later; renumbering is painful. Both providers reserve five addresses per subnet, so a `/24` gives 251 usable addresses. Container platforms hand an IP to every task or pod, so give their subnets room (`/20` rather than `/24`).

### Public, private and isolated subnets

A subnet has no "public" flag. On AWS it is public when its **route table** has `0.0.0.0/0 -> internet gateway` and the instance has a public IP. It is private when `0.0.0.0/0` points at a **NAT gateway** that lives in a public subnet: outbound connections work, inbound ones from the internet cannot be initiated. It is isolated when there is no default route at all, which is what a database subnet should be.

Azure has no internet gateway object. Inbound reachability comes from a public IP on a NIC or on a load balancer; outbound comes from an explicit method, preferably an **Azure NAT Gateway** on the subnet (new subnets are private by default for API versions released after 31 March 2026, so plan the NAT gateway in from day one). **Route tables (user-defined routes)** override Azure's system routes when you need to send traffic through a firewall appliance.

NAT gateways are charged per hour *and* per gigabyte processed, on both clouds. A service that pulls large files from S3 or Blob Storage through the NAT gateway pays for every byte twice over; a gateway endpoint (AWS) or private endpoint (Azure) keeps that traffic off the NAT path (see items 3.4 and 3.6).

### Stateful versus stateless filtering

| | AWS security group | Azure network security group (NSG) | AWS network ACL |
|---|---|---|---|
| Attached to | Instance, ENI, task, RDS instance | Subnet and/or NIC | Subnet |
| Stateful? | Yes: a reply to an allowed connection is allowed automatically | Yes | No: return traffic needs its own rule, including ephemeral ports 1024-65535 |
| Rule types | Allow only | Allow and deny, evaluated by priority (100 to 4096, lowest first) | Allow and deny, evaluated by rule number |
| Can reference a group? | Yes: "allow 8080 from sg-app" | Yes, via application security groups and service tags | No, CIDR only |
| Default | Deny all inbound, allow all outbound | Default rules allow traffic inside the VNet and from the Azure load balancer, deny other inbound, allow outbound | Allow everything |

Stateful rules are what you write day to day. Referencing a group instead of an IP range is the feature that makes rules survive autoscaling: "the database accepts 5432 from whatever currently carries the application group" needs no updating when instances come and go. Network ACLs are a coarse, subnet-level backstop; most teams leave them at the default and put their effort into security groups. Azure has no stateless equivalent; an NSG on the subnet plays the subnet-level role.

### Load balancer tiers

| Layer | AWS | Azure | Use it for |
|---|---|---|---|
| Layer 7 (HTTP) | Application Load Balancer | Application Gateway (regional), Front Door (global, with CDN) | Path and host routing, TLS termination, HTTP health checks, WAF |
| Layer 4 (TCP/UDP) | Network Load Balancer | Azure Load Balancer | Static IPs, non-HTTP protocols, very high throughput, TLS passthrough |
| DNS-based | Route 53 routing policies | Traffic Manager | Steering users between regions |

For a Spring Boot API the layer 7 option is the default: it terminates TLS, routes by path, and polls a health endpoint (`/actuator/health` or the readiness group, see item 8.4) to decide which targets receive traffic. An ALB must be given subnets in at least two availability zones; it places a node in each and the DNS name resolves to all of them.

## Example: a two-tier layout with every rule

```text
VPC 10.20.0.0/16, region eu-north-1 (Azure: VNet 10.20.0.0/16, swedencentral)

           internet
              |
     internet gateway (AWS)            route table "public":  0.0.0.0/0 -> igw
              |
  +-----------+-----------+-----------+
  | public-a  | public-b  | public-c  |   10.20.0.0/24, 10.20.1.0/24, 10.20.2.0/24
  | ALB node  | ALB node  | ALB node  |   one NAT gateway per zone lives here too
  | NAT gw a  | NAT gw b  | NAT gw c  |
  +-----------+-----------+-----------+
              | port 8080 (only from the ALB's security group)
  +-----------+-----------+-----------+
  | app-a     | app-b     | app-c     |   10.20.10.0/24, 10.20.11.0/24, 10.20.12.0/24
  | Spring    | Spring    | Spring    |   route table "private-<zone>":  0.0.0.0/0 -> NAT gw <zone>
  | tasks     | tasks     | tasks     |
  +-----------+-----------+-----------+
              | port 5432 (only from the app security group)
  +-----------+-----------+-----------+
  | db-a      | db-b      | db-c      |   10.20.20.0/24, 10.20.21.0/24, 10.20.22.0/24
  | primary   | standby   | (spare)   |   route table "isolated":  local routes only, no default route
  +-----------+-----------+-----------+
```

Security groups (AWS) with their NSG equivalents (Azure, as priority-ordered rules on the matching subnets):

| Group | Inbound | Outbound | Why |
|---|---|---|---|
| `sg-alb` | 443 from `0.0.0.0/0`; 80 from `0.0.0.0/0` only if you redirect it to 443 | 8080 to `sg-app` | The only thing the internet may reach is the load balancer, on TLS |
| `sg-app` | 8080 from `sg-alb` | 5432 to `sg-db`; 443 to `0.0.0.0/0` (cloud APIs, package feeds) via the NAT gateway | Nobody but the balancer talks to the application; the application talks to the database and to HTTPS endpoints only |
| `sg-db` | 5432 from `sg-app` | None needed; remove the default allow-all | The database answers the application and nothing else; replies are allowed because the group is stateful |

On Azure the same table becomes three NSGs: `nsg-alb` allowing inbound TCP 443 from `Internet`; `nsg-app` allowing inbound TCP 8080 from the gateway subnet and outbound 5432 to the database subnet plus 443 to `Internet`; `nsg-db` allowing inbound TCP 5432 from the app subnet and then, at a lower priority, denying all other inbound so the default VNet-wide allow does not quietly open the database to the whole network. Application security groups let you reference "the app NICs" instead of a subnet range, the closer equivalent to `sg-app`.

Three deliberate choices in the diagram: one NAT gateway per zone, because a single one is both a single point of failure and a source of cross-zone data charges; three database subnets even though only two are used, because the managed database service picks the standby's zone and a subnet group with spare zones makes failover and resizing easier; and an isolated route table for the database tier, so that a misconfigured security group still cannot expose it to the internet.

## Pitfalls

- Public IPs on application or database instances "temporarily". Temporary becomes permanent; put a bastion or a VPN in front and keep the tiers private.
- One NAT gateway for three zones. When its zone fails, every private subnet loses outbound access, and in normal operation two thirds of outbound traffic crosses zones and is billed for it.
- Routing S3 or Blob traffic through the NAT gateway. Backups, file uploads and log shipping are large; use a gateway endpoint or a private endpoint.
- Writing security group rules with CIDRs for internal tiers. They break on the first autoscaling event; reference the group.
- Forgetting ephemeral ports in a network ACL. Inbound 443 is allowed, the reply on port 51234 is dropped, and the symptom is a TLS handshake that hangs.

## Check yourself

1. A subnet has an instance with a public IP, but connections to it time out. Which two things decide whether the subnet is actually public, and which security group behaviour could still block it?
2. Why can the database security group have no outbound rules at all and still return query results to the application?
3. Your service downloads 2 TB a month from S3 through the NAT gateway. What changes in the diagram removes that cost, and does the same fix apply to Azure Blob Storage?
4. Explain the difference between a network ACL rule and a security group rule for the same port, and why only one of them needs a rule for ports 1024-65535.

## Go deeper

- [AWS: How Amazon VPC works](https://docs.aws.amazon.com/vpc/latest/userguide/how-it-works.html) · subnets, route tables, gateways and the reserved addresses, with diagrams.
- [Azure: Virtual Network overview](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-overview) · the Azure vocabulary for the same concepts, and what is different (no internet gateway object, system routes).
- [AWS: Security groups](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html) · stateful semantics, group references and the default rules.
- [Azure: Network security groups](https://learn.microsoft.com/en-us/azure/virtual-network/network-security-groups-overview) · the default rules, priorities, service tags and application security groups.
- [AWS Elastic Load Balancing](https://docs.aws.amazon.com/elasticloadbalancing/latest/userguide/what-is-load-balancing.html) and [Azure: Load-balancing options](https://learn.microsoft.com/en-us/azure/architecture/guide/technology-choices/load-balancing-overview) · how to choose between the tiers on each cloud.

---

Part of [Cloud](../README.md) · items 3.1, 3.2, 3.3
