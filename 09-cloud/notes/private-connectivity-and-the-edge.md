# Private connectivity and the edge: private endpoints, peering, DNS, CDN, WAF and DDoS protection

> **In one sentence:** Traffic to managed services and to other networks should stay on the provider's backbone (private endpoints, peering, VPN or dedicated circuits) and traffic from the internet should arrive through a DNS name that points at a CDN or global front door with a web application firewall in front of the only public entry point you have.

**Why it matters:** The two failure modes are mirror images: a service that reaches its database or its secret store over the public internet because nobody created a private endpoint, and a load balancer that answers directly to the internet because nobody put a firewall in front of it. Both pass every functional test. Both show up in a security review, and the first one also shows up on the NAT gateway line of the bill.

## The idea

### Reaching managed services privately

| Need | AWS | Azure | What it does |
|---|---|---|---|
| Reach S3 or DynamoDB from private subnets without NAT | Gateway VPC endpoint (free, a route table entry) | Not applicable; use a private endpoint | Adds a route so traffic to the service's prefix list stays inside the VPC |
| Reach any other AWS service, or a partner's service, privately | Interface VPC endpoint (AWS PrivateLink): an elastic network interface with a private IP in your subnet | Private endpoint (Azure Private Link): a NIC with a private IP in your VNet | The service's DNS name resolves to that private IP; billed per hour per zone plus per GB |
| Older Azure option | | Virtual network service endpoints | Keeps the public IP of the service but routes over the backbone and lets the firewall allow your subnet; cheaper, less private |

The piece people miss is **DNS**. A private endpoint only works if the name your code uses resolves to the private IP. On AWS, enabling *private DNS* on the interface endpoint overrides the public name inside the VPC. On Azure, the private endpoint is linked to a **private DNS zone** such as `privatelink.postgres.database.azure.com` or `privatelink.blob.core.windows.net`, and the zone is linked to the VNet; without that link the public name still resolves to the public IP and the connection either goes out through NAT or is refused by the service's firewall.

### Reaching other networks

- **Peering** connects two VPCs or VNets so their private ranges route to each other. It is not transitive: A peered with B and B peered with C does not connect A to C. Address ranges must not overlap. AWS Transit Gateway and Azure Virtual WAN (or a hub VNet with a firewall) are the hub-and-spoke answers once there are more than a handful of networks.
- **VPN** (AWS Site-to-Site VPN, Azure VPN Gateway) is an IPsec tunnel over the internet to an office or data centre: quick to set up, bandwidth and latency vary with the internet.
- **Dedicated circuits** (AWS Direct Connect, Azure ExpressRoute) are private links from a colocation facility into the provider: predictable latency, high bandwidth, weeks to provision, and the right answer when a data centre and the cloud exchange serious volumes.

### The edge: DNS, CDN, WAF and DDoS

| Layer | AWS | Azure | Role |
|---|---|---|---|
| DNS | Route 53 (hosted zones, alias records to balancers and distributions, routing policies with health checks) | Azure DNS (zones), Traffic Manager (DNS-based routing between regions) | The name users type; also the switch for regional failover |
| CDN and global entry point | Amazon CloudFront (distributions with origins and cache behaviours, edge TLS, origin access control for S3) | Azure Front Door (global layer 7 with caching, TLS, routing rules, Standard and Premium tiers) | Cache static content near users, terminate TLS at the edge, hide origins |
| Web application firewall | AWS WAF web ACLs with managed rule groups, attached to CloudFront, ALB or API Gateway | Azure Web Application Firewall policies on Front Door or Application Gateway | Block SQL injection and cross-site scripting patterns, rate-limit abusive clients, geo-block |
| DDoS | AWS Shield Standard (always on, free) and Shield Advanced (paid, with response team and cost protection) | Azure DDoS infrastructure protection (always on) and DDoS Network Protection or IP Protection (paid) | Absorb volumetric floods before they reach your balancer |

The pattern is a single public path: `users -> DNS -> CDN or Front Door (TLS, WAF, caching) -> load balancer -> service`. The balancer should accept traffic only from the edge: on AWS by referencing the CloudFront origin-facing managed prefix list in the balancer's security group, on Azure by validating the `X-Azure-FDID` header or by attaching the origin through Private Link (Premium tier). Otherwise an attacker who finds the balancer's address walks around the firewall.

## Example: a database behind a private endpoint and an API behind the edge

```text
internet --> Route 53 / Azure DNS --> CloudFront / Front Door (TLS, WAF) --> ALB / App Gateway
                                                                                 |
                                               private subnets:  Spring tasks ---+
                                                                   |         |
                                    private endpoint 10.20.30.5 ---+         +--- gateway endpoint (S3)
                                                                   |              or private endpoint (Blob)
                                                   managed PostgreSQL (no public access)
```

Creating the AWS endpoints: a free gateway endpoint for S3 attached to the private route tables, and an interface endpoint for Secrets Manager with private DNS so the SDK's default endpoint resolves privately:

```bash
aws ec2 create-vpc-endpoint --vpc-id vpc-0a1b2c --vpc-endpoint-type Gateway \
  --service-name com.amazonaws.eu-north-1.s3 --route-table-ids rtb-private-a rtb-private-b rtb-private-c

aws ec2 create-vpc-endpoint --vpc-id vpc-0a1b2c --vpc-endpoint-type Interface \
  --service-name com.amazonaws.eu-north-1.secretsmanager --subnet-ids subnet-app-a subnet-app-b subnet-app-c \
  --security-group-ids sg-endpoints --private-dns-enabled
```

On Azure, the private endpoint for a Flexible Server plus the DNS zone link. The proof that it worked is the lookup from inside the VNet:

```bash
az network private-endpoint create --name pe-orders-db --resource-group orders-prod \
  --vnet-name vnet-orders --subnet snet-private-endpoints \
  --private-connection-resource-id "$POSTGRES_SERVER_ID" --group-id postgresqlServer \
  --connection-name orders-db

dig +short orders-db.postgres.database.azure.com
```

```text
orders-db.privatelink.postgres.database.azure.com.
10.20.30.5
```

The public name is a CNAME to the `privatelink` name, which the linked private DNS zone resolves to the endpoint's IP. The same `dig` from a laptop outside the VNet returns a public IP, which is fine as long as the server's public network access is disabled.

For the edge, the one rule that must exist on the balancer's security group:

```text
sg-alb inbound:  443 from the managed prefix list "com.amazonaws.global.cloudfront.origin-facing"
```

Nothing else. The AWS WAF web ACL is attached to the CloudFront distribution with the managed rule groups for common threats and known bad inputs, plus a rate-based rule per client IP, and it starts in count mode for a week before rules are switched to block.

## Pitfalls

- A private endpoint with no DNS. The resource exists, the bill rises, and traffic still leaves through NAT because the name resolves publicly. Always test with `dig` or `nslookup` from inside the network.
- Interface endpoints in one zone only. Cross-zone traffic to the endpoint is billed and the zone is a single point of failure; one per zone your tasks run in.
- Peering as a mesh. Six networks need fifteen peerings and route entries; use a transit gateway or hub.
- Overlapping CIDRs chosen years apart. Peering and VPN both fail; renumbering a production VNet is a project (see item 3.1).
- Caching responses that vary by user. A CDN that caches `Set-Cookie` or an authorised JSON response serves one customer's data to another. Cache only what the cache key fully describes; set `Cache-Control: private` on the rest.
- The balancer reachable directly. The WAF protects the path through the edge, not the origin's own address.
- WAF left in count mode forever, or switched to block on day one. The first gives no protection; the second blocks legitimate traffic that matched a rule nobody tuned.
- Assuming DDoS protection means the paid tier. Shield Standard and Azure's infrastructure protection are already on; the paid tiers add tuning, visibility, response support and cost protection.

## Check yourself

1. Your service in private subnets talks to Secrets Manager. Describe the packet path before and after an interface endpoint with private DNS, and what changes on the NAT gateway line of the bill.
2. A colleague creates an Azure private endpoint for Blob Storage and the service still connects over the public IP. What is missing, and how do you prove it from a container in the VNet?
3. Why is VPC peering unsuitable for connecting ten networks, and which service replaces it on each cloud?
4. List the three things that have to be true for the WAF on CloudFront or Front Door to actually protect the API behind it.

## Go deeper

- [AWS PrivateLink](https://docs.aws.amazon.com/vpc/latest/privatelink/what-is-privatelink.html) · gateway versus interface endpoints, private DNS and endpoint policies.
- [Azure Private Link](https://learn.microsoft.com/en-us/azure/private-link/private-link-overview) · private endpoints, the private DNS zone names per service and the comparison with service endpoints.
- [Amazon CloudFront](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Introduction.html) · distributions, origins, cache behaviours and origin access control.
- [Azure Front Door](https://learn.microsoft.com/en-us/azure/frontdoor/front-door-overview) · tiers, routing rules, WAF integration and origin security.
- [AWS: How Amazon VPC works](https://docs.aws.amazon.com/vpc/latest/userguide/how-it-works.html) · route tables and prefix lists, which the endpoint and balancer rules above depend on.

---

Part of [Cloud](../README.md) · items 3.4, 3.5
