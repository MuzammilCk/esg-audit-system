# Kubernetes Deployment

This guide covers production deployment on Kubernetes.

## Prerequisites

- Kubernetes 1.28+
- kubectl configured
- Helm 3.0+ (optional)
- AWS CLI configured (for Nitro Enclaves)

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           KUBERNETES CLUSTER                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                      INGRESS (nginx)                             │    │
│  │  • TLS termination  • Rate limiting  • WAF rules                 │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                     │
│  ┌─────────────────────────────────┼─────────────────────────────────┐  │
│  │                      SERVICES                                     │  │
│  │                                                                   │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │  │
│  │  │audit-agents │  │vector-store │  │  security   │               │  │
│  │  │  (2-10 pods)│  │  (2 pods)   │  │  (2 pods)   │               │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘               │  │
│  │                                                                   │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │  │
│  │  │  ingestion  │  │   privacy   │  │ verification│               │  │
│  │  │  (2 pods)   │  │  (2 pods)   │  │  (2 pods)   │               │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘               │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    DATA SERVICES                                  │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │    │
│  │  │   Qdrant    │  │    Redis    │  │  Postgres   │               │    │
│  │  │  (3 nodes)  │  │  (cluster)  │  │  (primary)  │               │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘               │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    RAY CLUSTER                                    │    │
│  │  ┌─────────────┐  ┌─────────────┐                                │    │
│  │  │  Ray Head   │  │  Ray Workers│                                │    │
│  │  │  (1 pod)    │  │  (2-5 pods) │                                │    │
│  │  └─────────────┘  └─────────────┘                                │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Quick Deploy

```bash
# Create namespace and secrets
kubectl apply -f k8s/base/namespace.yaml
kubectl apply -f k8s/base/secrets.yaml

# Deploy infrastructure
kubectl apply -f k8s/services/redis.yaml
kubectl apply -f k8s/services/qdrant.yaml

# Deploy applications
kubectl apply -f k8s/services/audit-agents.yaml
kubectl apply -f k8s/services/support-services.yaml

# Deploy ingress
kubectl apply -f k8s/services/ingress.yaml
```

## Configuration

### Secrets

Create `k8s/base/secrets.yaml`:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: esg-audit-secrets
  namespace: esg-audit
type: Opaque
stringData:
  OPENAI_API_KEY: "sk-your-api-key"
  API_KEY: "your-secure-api-key"
  ENCRYPTION_KEY: "your-32-byte-key"
  REDIS_PASSWORD: "your-redis-password"
```

### ConfigMaps

Create `k8s/base/configmaps.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: esg-audit-config
  namespace: esg-audit
data:
  OPENAI_MODEL: "gpt-4-turbo-preview"
  QDRANT_COLLECTION: "esg_documents"
  LOG_LEVEL: "INFO"
  USE_SQLITE_CHECKPOINT: "false"
```

## Resource Requirements

| Service | CPU Request | CPU Limit | Memory Request | Memory Limit |
|---------|-------------|-----------|----------------|--------------|
| audit-agents | 500m | 2000m | 1Gi | 4Gi |
| vector-store | 250m | 1000m | 512Mi | 2Gi |
| security | 250m | 1000m | 512Mi | 1Gi |
| qdrant | 500m | 2000m | 1Gi | 4Gi |
| redis | 250m | 500m | 256Mi | 512Mi |

## Horizontal Pod Autoscaling

HPA is configured for the audit-agents service:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: audit-agents-hpa
  namespace: esg-audit
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: audit-agents
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          averageUtilization: 80
```

## Network Policies

Service isolation is enforced via NetworkPolicies:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: audit-agents-policy
  namespace: esg-audit
spec:
  podSelector:
    matchLabels:
      app: audit-agents
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: ingress-nginx
      ports:
        - protocol: TCP
          port: 8003
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: qdrant
      ports:
        - protocol: TCP
          port: 6333
    - to:
        - podSelector:
            matchLabels:
              app: redis
      ports:
        - protocol: TCP
          port: 6379
```

## Monitoring

### Prometheus ServiceMonitor

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: audit-agents-monitor
  namespace: esg-audit
spec:
  selector:
    matchLabels:
      app: audit-agents
  endpoints:
    - port: metrics
      path: /metrics
      interval: 30s
```

### Grafana Dashboard

Import the provided dashboard from `k8s/monitoring/grafana-dashboard.json`.

## Rolling Updates

```bash
# Update image
kubectl set image deployment/audit-agents \
  audit-agents=esg-audit:v2.0.0 \
  -n esg-audit

# Check rollout status
kubectl rollout status deployment/audit-agents -n esg-audit

# Rollback if needed
kubectl rollout undo deployment/audit-agents -n esg-audit
```

## Troubleshooting

### Check Pod Status

```bash
kubectl get pods -n esg-audit
kubectl describe pod <pod-name> -n esg-audit
kubectl logs <pod-name> -n esg-audit -f
```

### Check Service Connectivity

```bash
kubectl exec -it <pod-name> -n esg-audit -- curl http://qdrant:6333/collections
kubectl exec -it <pod-name> -n esg-audit -- redis-cli -h redis ping
```

### Resource Issues

```bash
kubectl top pods -n esg-audit
kubectl describe resourcequota -n esg-audit
```

## Production Checklist

- [ ] Secrets created and rotated regularly
- [ ] Network policies applied
- [ ] HPA configured and tested
- [ ] Monitoring dashboards set up
- [ ] Alert rules configured
- [ ] Backup strategy implemented
- [ ] Disaster recovery tested
- [ ] TLS certificates valid
- [ ] Resource quotas set
- [ ] Pod disruption budgets configured
