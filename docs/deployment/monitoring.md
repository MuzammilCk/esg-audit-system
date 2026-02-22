# Monitoring and Observability

This guide covers monitoring, logging, and alerting for the ESG Audit System.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        OBSERVABILITY STACK                               │
│                                                                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐         │
│  │   Prometheus    │  │    Grafana      │  │    Loki         │         │
│  │   (Metrics)     │  │  (Dashboards)   │  │    (Logs)       │         │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘         │
│           │                    │                    │                   │
│           └────────────────────┼────────────────────┘                   │
│                                │                                        │
│  ┌─────────────────────────────┴─────────────────────────────────────┐  │
│  │                      APPLICATIONS                                  │  │
│  │                                                                    │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │  │
│  │  │audit-agents │  │vector-store │  │  security   │               │  │
│  │  │ /metrics    │  │ /metrics    │  │ /metrics    │               │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘               │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Metrics

### Key Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `audit_requests_total` | Counter | Total audit requests |
| `audit_duration_seconds` | Histogram | Audit processing time |
| `audit_compliance_score` | Gauge | Latest compliance score |
| `llm_tokens_used_total` | Counter | Total LLM tokens consumed |
| `vector_search_duration` | Histogram | Vector search latency |
| `pii_entities_masked_total` | Counter | PII entities detected |
| `security_alerts_total` | Counter | Security alerts generated |

### Prometheus Configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 30s

scrape_configs:
  - job_name: 'audit-agents'
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
            - esg-audit
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        regex: audit-agents
        action: keep

  - job_name: 'vector-store'
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
            - esg-audit
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        regex: vector-store
        action: keep

  - job_name: 'security'
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
            - esg-audit
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        regex: security
        action: keep
```

## Dashboards

### Audit Overview Dashboard

Key panels:
1. **Request Rate** - Audit requests per minute
2. **Latency P95** - 95th percentile processing time
3. **Compliance Distribution** - APPROVE/REJECT/REVIEW breakdown
4. **Error Rate** - Failed requests percentage
5. **LLM Token Usage** - Token consumption over time
6. **Active Audits** - Currently processing documents

### Security Dashboard

Key panels:
1. **Threat Level** - Current security posture
2. **Honeypot Interactions** - Decoy system activity
3. **Alerts by Severity** - CRITICAL/HIGH/MEDIUM/LOW breakdown
4. **Top Threat IPs** - Risky source addresses
5. **Red Team Results** - Vulnerability assessment status

### Infrastructure Dashboard

Key panels:
1. **Pod CPU/Memory** - Resource utilization
2. **Qdrant Collection Stats** - Vector count, segments
3. **Redis Memory** - Cache hit rate, memory usage
4. **Network I/O** - Inter-service communication

## Alerting

### Alert Rules

```yaml
# alerts.yml
groups:
  - name: audit-agents
    rules:
      - alert: HighErrorRate
        expr: rate(audit_requests_total{status="error"}[5m]) > 0.01
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate in audit agents"
          description: "Error rate is {{ $value }} errors/sec"

      - alert: HighLatency
        expr: histogram_quantile(0.95, rate(audit_duration_seconds_bucket[5m])) > 30
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Audit latency is high"
          description: "P95 latency is {{ $value }}s"

      - alert: LLMTokensHigh
        expr: rate(llm_tokens_used_total[1h]) > 100000
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "High LLM token usage"
          description: "Token usage is {{ $value }} tokens/hour"

  - name: security
    rules:
      - alert: CriticalThreatDetected
        expr: security_alerts_total{severity="CRITICAL"} > 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Critical security threat detected"
          description: "{{ $value }} critical alert(s) triggered"

      - alert: HoneypotTriggered
        expr: rate(honeypot_interactions_total[5m]) > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High honeypot activity"
          description: "{{ $value }} honeypot interactions/sec"

  - name: infrastructure
    rules:
      - alert: PodCrashLooping
        expr: rate(kube_pod_container_status_restarts_total[15m]) > 0.1
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "Pod is crash looping"
          description: "Pod {{ $labels.pod }} has restarted {{ $value }} times"

      - alert: QdrantDown
        expr: up{job="qdrant"} == 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Qdrant is down"
          description: "Qdrant vector database is unreachable"
```

## Logging

### Log Format

All services output structured JSON logs:

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "INFO",
  "service": "audit-agents",
  "trace_id": "abc-123",
  "thread_id": "thread-456",
  "message": "Audit completed",
  "duration_ms": 1523,
  "compliance_score": 0.85
}
```

### Log Levels

| Level | Use Case |
|-------|----------|
| DEBUG | Detailed debugging information |
| INFO | Normal operational events |
| WARNING | Unexpected but handled conditions |
| ERROR | Error conditions requiring attention |
| CRITICAL | System-critical failures |

### Loki Queries

```logql
# All errors from audit-agents
{service="audit-agents"} |= "ERROR"

# Slow requests (>5s)
{service="audit-agents"} | json | duration_ms > 5000

# Compliance failures
{service="audit-agents"} | json | compliance_score < 0.5

# Security alerts
{service="security"} | json | level="CRITICAL"
```

## Tracing

### OpenTelemetry Integration

```python
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider

trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer(__name__)

otlp_exporter = OTLPSpanExporter(endpoint="tempo:4317")
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(otlp_exporter)
)
```

### Trace Context

```python
with tracer.start_as_current_span("audit_workflow") as span:
    span.set_attribute("thread_id", thread_id)
    span.set_attribute("document_id", document_id)
    # ... audit processing
```

## Health Checks

### Liveness Probe

```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8003
  initialDelaySeconds: 10
  periodSeconds: 10
```

### Readiness Probe

```yaml
readinessProbe:
  httpGet:
    path: /healthz
    port: 8003
  initialDelaySeconds: 5
  periodSeconds: 5
```

## Runbooks

### High Error Rate

1. Check recent deployments: `kubectl rollout history deployment/audit-agents`
2. View error logs: `kubectl logs -l app=audit-agents | grep ERROR`
3. Check dependencies: Qdrant, Redis, OpenAI API status
4. Rollback if needed: `kubectl rollout undo deployment/audit-agents`

### High Latency

1. Check pod resources: `kubectl top pods -n esg-audit`
2. Scale up if needed: `kubectl scale deployment audit-agents --replicas=5`
3. Check LLM API latency
4. Review vector search performance

### Security Alert

1. Review alert details in Grafana
2. Check honeypot logs for attack patterns
3. Block IP if necessary: Update NetworkPolicy
4. Run red team assessment: `POST /api/redteam/run`

## SLI/SLO

| SLI | SLO | Measurement Window |
|-----|-----|-------------------|
| Availability | 99.9% | Monthly |
| Latency P95 | < 30s | Weekly |
| Error Rate | < 0.1% | Weekly |
| MTTR | < 15min | Monthly |
