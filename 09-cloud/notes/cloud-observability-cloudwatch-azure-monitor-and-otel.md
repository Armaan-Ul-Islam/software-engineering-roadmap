# Cloud observability: CloudWatch, Azure Monitor and OpenTelemetry, and alerting on symptoms

> **In one sentence:** Logs, metrics and traces are three views of the same requests; emit them from Spring Boot through OpenTelemetry so the backend (CloudWatch and X-Ray, or Azure Monitor and Application Insights) is a configuration choice, alert on what users feel (latency, errors, saturation) rather than on CPU, and set a retention on every log store before the ingestion line becomes the bill.

**Why it matters:** The outage that pages nobody and the dashboard with forty panels that nobody reads are the same failure: data collected without a question in mind. On the other side, log ingestion is routinely one of the larger lines on a cloud bill, because `DEBUG` in production and "never expire" are both defaults somewhere. A backend developer is expected to wire the three signals, write the three alerts that matter and know what each gigabyte costs.

## The idea

### The three signals and where they land

| Signal | What it answers | AWS | Azure | Spring Boot source |
|---|---|---|---|---|
| Logs | What happened, in words, for one event | CloudWatch Logs (log groups, streams, Logs Insights queries) | Log Analytics workspace, queried with KQL; Application Insights `traces` and `requests` tables | Logback to stdout; `logging.structured.format.console=ecs` for JSON (Spring Boot 3.4 and later) |
| Metrics | How much, how often, how slow, as numbers over time | CloudWatch Metrics (namespaces, dimensions, statistics such as `p99`) | Azure Monitor Metrics; Application Insights custom metrics | Micrometer, through Actuator (`/actuator/prometheus` or an OTLP registry) |
| Traces | Where the time went across services for one request | AWS X-Ray | Application Insights distributed tracing (end-to-end transaction view, application map) | Micrometer Tracing with the OpenTelemetry bridge, or the OpenTelemetry Java agent |

Correlation is the point. A log line carrying `trace_id` lets you jump from an error to the trace that produced it; a metric spike lets you query logs for that minute. Spring Boot adds the trace and span identifiers to the logging MDC when tracing is on, so JSON logs carry them without extra work.

### OpenTelemetry as the neutral path

OpenTelemetry (OTel) defines the API your code uses, the SDK that batches and exports, and the **OTLP** wire protocol. Both providers accept it: AWS through the AWS Distro for OpenTelemetry (ADOT) collector with exporters for X-Ray and CloudWatch, Azure through the Azure Monitor OpenTelemetry Distro and the Application Insights Java agent, which has been OTel-based since version 3. Two ways to instrument a Spring Boot service:

1. **The Java agent.** Add `-javaagent:opentelemetry-javaagent.jar` and set `OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_RESOURCE_ATTRIBUTES`. No code change; it instruments Spring MVC, JDBC, HTTP clients and messaging libraries automatically.
2. **Micrometer in the application.** Spring Boot's Actuator with `micrometer-tracing-bridge-otel` and `opentelemetry-exporter-otlp` exports traces over OTLP, and `micrometer-registry-otlp` does the same for metrics. This keeps instrumentation in code (custom spans, business metrics) and in Spring's own `Observation` API.

Either way, point the exporter at an **OpenTelemetry Collector** rather than straight at the vendor. The collector runs as a sidecar or a daemon, batches, adds resource attributes, samples, and exports to whichever backend the environment uses. Switching cloud or adding a second backend is then a collector configuration change.

### Alerting on symptoms

The SRE book's four golden signals, **latency, traffic, errors and saturation**, are what users experience. An alert on CPU at 80% is a cause, not a symptom: it pages you when nothing is wrong and stays silent when the database is the bottleneck. The rule: a page must be actionable, urgent and user-visible. Everything else is a ticket or a dashboard panel. For a Spring API that means three alerts at the load balancer: p99 latency over the agreed objective for five minutes, 5xx rate over 1% for five minutes, and no traffic at all when there should be. Add saturation alerts that predict the first two: connection pool wait time, queue depth, disk nearly full.

### What a gigabyte of logs costs

Both clouds charge more to **ingest** a gigabyte than to store it for a month, and both default to retention settings you did not choose: a CloudWatch log group keeps data forever unless you set a retention, and a Log Analytics workspace has a retention you should check and set per table. The levers, in order of effect: stop logging what nobody reads (request bodies, health-check hits, `DEBUG`), sample high-volume traces (head sampling at 10% is plenty for latency pictures; keep every error), set retention to the period you actually investigate (30 days for application logs, longer only for audit logs that regulation requires), and archive to S3 or a storage account for anything that must be kept but never queried.

## Example: Spring Boot to a collector to either cloud

The application configuration, backend-neutral:

```properties
management.tracing.sampling.probability=0.1
management.otlp.tracing.endpoint=http://otel-collector:4318/v1/traces
management.otlp.metrics.export.url=http://otel-collector:4318/v1/metrics
management.otlp.metrics.export.step=60s
management.observations.key-values.service=orders-api
logging.structured.format.console=ecs
```

A log line now looks like this (abbreviated), with the trace identifier that links it to the span:

```json
{"@timestamp":"2026-10-29T09:14:02.118Z","log.level":"WARN","message":"payment provider timeout after 2000 ms","service.name":"orders-api","trace.id":"5c8d1f0a6b3e4d2c9a7f1e0b4d6c8a21","span.id":"3f2a1b4c5d6e7f80","process.thread.name":"http-nio-8080-exec-7","log.logger":"com.acme.orders.payment.PaymentClient"}
```

The collector's pipeline, with the exporters for both clouds shown; a given environment enables one of them:

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 5s
  resource:
    attributes:
      - key: deployment.environment
        value: prod
        action: upsert

exporters:
  awsxray: {}
  awsemf:
    namespace: orders-api
  azuremonitor:
    connection_string: ${env:APPLICATIONINSIGHTS_CONNECTION_STRING}

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [resource, batch]
      exporters: [awsxray]
    metrics:
      receivers: [otlp]
      processors: [resource, batch]
      exporters: [awsemf]
```

On Azure the two pipelines list `azuremonitor` instead. `awsxray`, `awsemf` and `azuremonitor` are exporters from the OpenTelemetry Collector Contrib distribution (ADOT ships the AWS ones). The application does not change.

The three alerts, on each cloud. AWS, as a CloudWatch alarm on the ALB's own metrics:

```bash
aws cloudwatch put-metric-alarm --alarm-name orders-api-p99-latency \
  --namespace AWS/ApplicationELB --metric-name TargetResponseTime \
  --dimensions Name=LoadBalancer,Value=app/orders-alb/50dc6c495c0c9188 \
  --extended-statistic p99 --period 60 --evaluation-periods 5 --datapoints-to-alarm 5 \
  --threshold 0.5 --comparison-operator GreaterThanThreshold \
  --alarm-actions arn:aws:sns:eu-north-1:123456789012:oncall
```

Azure, as a log alert rule whose KQL runs every five minutes against Application Insights:

```text
requests
| where timestamp > ago(5m)
| summarize total = count(), failed = countif(success == false), p99 = percentile(duration, 99)
| where failed * 100.0 / total > 1 or p99 > 500
```

The alarm on `HTTPCode_Target_5XX_Count` divided by `RequestCount` (a CloudWatch metric math expression) and the "no traffic" alarm using `TreatMissingData` as breaching complete the set on AWS; on Azure they are two more rows in the same query or a metric alert on the gateway's `FailedRequests`.

## Pitfalls

- Alerting on CPU, memory or instance count. They are inputs; page on latency, errors and saturation that users feel.
- Log groups and workspaces with no retention. Set it on creation, in the infrastructure code, so every new group inherits it.
- `DEBUG` in production "for a day". A thousand requests per second at ten lines each is tens of gigabytes a day, each paid at the ingestion rate.
- High-cardinality metric dimensions. A `user_id` tag on a timer creates a metric per user; CloudWatch bills per metric and Azure per time series. Keep identifiers in traces and logs.
- Sampling 100% of traces. Fine in development, expensive at scale; sample heads at a fixed rate and keep errors with tail sampling in the collector.
- Double instrumentation. The Java agent and Micrometer Tracing both active produce duplicate spans; pick one.
- Losing trace context across queues. HTTP propagation is automatic; for SQS or Service Bus messages the trace identifiers must travel in message attributes, which the instrumentation libraries do only when the client is instrumented.
- Dashboards with no question. Each panel should answer "is something wrong" or "where is it wrong"; everything else is noise during an incident.

## Check yourself

1. A user reports a slow checkout at 09:14. Walk through how you get from that report to the exact span that took the time, and which identifier connects the metric, the log and the trace.
2. Why is "CPU above 80% for five minutes" a bad page, and what three alerts would you set for a Spring API instead? Give a threshold and a window for each.
3. Your log bill tripled last month. List four things you would check, in the order you would check them.
4. What does putting a collector between the service and the backend buy you, and what breaks if the service exports straight to X-Ray and the team later moves to Azure?

## Go deeper

- [OpenTelemetry](https://opentelemetry.io/docs/) · the concepts, the Java agent and SDK, and the collector configuration reference.
- [Amazon CloudWatch](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/WhatIsCloudWatch.html) · metrics, alarms, Logs Insights and the embedded metric format.
- [Azure Monitor: Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview) · the OpenTelemetry-based Java agent, the data model and the KQL tables.
- [Google SRE Book: Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/) · the four golden signals and the rules for when a page is justified.

---

Part of [Cloud](../README.md) · items 8.1, 8.2
