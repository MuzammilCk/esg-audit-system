# Troubleshooting Guide

This guide covers common issues and solutions for the ESG Audit System.

## Quick Diagnostics

```bash
# Check all service health
curl -s http://localhost:8003/healthz
curl -s http://localhost:8004/healthz
curl -s http://localhost:8006/healthz

# Check Qdrant
curl -s http://localhost:6333/collections/esg_documents

# Check Redis
redis-cli ping
```

## Common Issues

### 1. Audit Workflow Stuck

**Symptoms**:
- Audit shows PENDING or ANALYZING status indefinitely
- No progress in audit trail

**Diagnosis**:
```bash
# Check audit agents logs
kubectl logs -l app=audit-agents -n esg-audit --tail=100

# Check thread state
curl http://localhost:8003/api/audit/{thread_id}
```

**Solutions**:
1. Check if OpenAI API is reachable
2. Verify Qdrant connection
3. Check for memory pressure on pods
4. Restart the audit agents deployment

```bash
kubectl rollout restart deployment/audit-agents -n esg-audit
```

---

### 2. Vector Search Returns No Results

**Symptoms**:
- Search endpoint returns empty results
- RAG context is empty in compliance analysis

**Diagnosis**:
```bash
# Check Qdrant collection
curl http://localhost:6333/collections/esg_documents

# Check vector count
curl http://localhost:8004/api/stats
```

**Solutions**:
1. Index documents if collection is empty
2. Check embedding service connectivity
3. Verify search query is not too restrictive
4. Check Qdrant logs for errors

```bash
# Re-index a document
curl -X POST http://localhost:8004/api/index \
  -H "Content-Type: application/json" \
  -d '{"content": "test content", "document_id": "test-123"}'
```

---

### 3. PII Not Being Masked

**Symptoms**:
- Personal data appears in masked text
- No PII entities detected

**Diagnosis**:
```bash
# Check privacy service logs
kubectl logs -l app=privacy -n esg-audit --tail=100

# Test PII masking directly
curl -X POST http://localhost:8002/api/mask \
  -H "Content-Type: application/json" \
  -d '{"text": "John Smith can be reached at john@example.com"}'
```

**Solutions**:
1. Verify Presidio model is loaded
2. Check if spaCy model is installed
3. Ensure text language is supported

```bash
# Install spaCy model
pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.7.1/en_core_web_lg-3.7.1-py3-none-any.whl
```

---

### 4. Provenance Verification Fails

**Symptoms**:
- All documents show UNSIGNED status
- C2PA validation errors

**Diagnosis**:
```bash
# Check verification service logs
kubectl logs -l app=verification -n esg-audit --tail=100

# Test C2PA validation
curl -X POST http://localhost:8005/api/verify \
  -H "Content-Type: application/json" \
  -d '{"document_url": "https://example.com/signed.pdf"}'
```

**Solutions**:
1. Check if c2patool is installed
2. Verify document has C2PA manifest
3. Check certificate chain validity

---

### 5. High Memory Usage

**Symptoms**:
- Pods being OOMKilled
- Memory limit exceeded

**Diagnosis**:
```bash
# Check pod resource usage
kubectl top pods -n esg-audit

# Check memory metrics
kubectl describe pod <pod-name> -n esg-audit | grep -A 5 "Limits:"
```

**Solutions**:
1. Increase memory limits in deployment
2. Check for memory leaks in logs
3. Reduce batch size for embeddings
4. Enable checkpoint cleanup

```yaml
# Increase memory limit
resources:
  limits:
    memory: 4Gi
```

---

### 6. LLM Rate Limiting

**Symptoms**:
- 429 errors from OpenAI API
- Compliance analysis fails intermittently

**Diagnosis**:
```bash
# Check for rate limit errors
kubectl logs -l app=audit-agents -n esg-audit | grep -i "rate limit"
```

**Solutions**:
1. Implement exponential backoff
2. Reduce concurrent requests
3. Use OpenAI batch API for bulk processing
4. Consider using alternative LLM providers

```python
# Implement backoff in LLM client
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=60)
)
async def call_llm(prompt):
    return await client.complete(prompt)
```

---

### 7. Redis Connection Issues

**Symptoms**:
- "Connection refused" errors
- PII mapping not persisted

**Diagnosis**:
```bash
# Check Redis connectivity
kubectl exec -it <pod-name> -n esg-audit -- redis-cli -h redis ping

# Check Redis logs
kubectl logs -l app=redis -n esg-audit --tail=50
```

**Solutions**:
1. Verify Redis is running
2. Check network policies
3. Verify credentials
4. Check Redis memory usage

```bash
# Check Redis memory
kubectl exec -it <redis-pod> -n esg-audit -- redis-cli info memory
```

---

### 8. Kubernetes Deployment Issues

**Symptoms**:
- Pods not starting
- ImagePullBackOff errors

**Diagnosis**:
```bash
# Check pod events
kubectl describe pod <pod-name> -n esg-audit

# Check deployment status
kubectl rollout status deployment/audit-agents -n esg-audit
```

**Solutions**:
1. Verify image exists in registry
2. Check image pull secrets
3. Verify resource quotas
4. Check node resources

```bash
# Check events
kubectl get events -n esg-audit --sort-by='.lastTimestamp'
```

---

### 9. Security Alerts Not Working

**Symptoms**:
- No alerts generated
- Honeypot interactions not recorded

**Diagnosis**:
```bash
# Check security service logs
kubectl logs -l app=security -n esg-audit --tail=100

# Check honeypot status
curl http://localhost:8006/api/honeypots
```

**Solutions**:
1. Verify honeypots are active
2. Check threat detection rules
3. Verify alert routing

---

### 10. Ingress/TLS Issues

**Symptoms**:
- 502 Bad Gateway
- TLS certificate errors

**Diagnosis**:
```bash
# Check ingress status
kubectl get ingress -n esg-audit

# Check ingress controller logs
kubectl logs -l app=ingress-nginx -n ingress-nginx --tail=100
```

**Solutions**:
1. Verify service endpoints
2. Check TLS certificate validity
3. Verify ingress annotations

```bash
# Check certificate
kubectl get certificate -n esg-audit
```

## Log Analysis

### Find Errors in Logs

```bash
# All error logs
kubectl logs -l app=audit-agents -n esg-audit | grep ERROR

# Specific error pattern
kubectl logs -l app=audit-agents -n esg-audit | grep "connection refused"

# JSON log parsing
kubectl logs -l app=audit-agents -n esg-audit | jq 'select(.level=="ERROR")'
```

### Trace Request Flow

```bash
# Follow trace_id through logs
TRACE_ID="abc-123"
kubectl logs -l app=audit-agents -n esg-audit | grep $TRACE_ID
kubectl logs -l app=vector-store -n esg-audit | grep $TRACE_ID
```

## Performance Tuning

### Reduce Latency

1. Enable connection pooling
2. Use async I/O throughout
3. Cache frequently accessed data
4. Optimize vector search parameters

### Increase Throughput

1. Scale horizontally with HPA
2. Use Ray for distributed processing
3. Batch LLM requests
4. Enable response caching

## Getting Help

1. Check logs first
2. Review metrics dashboards
3. Consult this troubleshooting guide
4. Open an issue on GitHub with:
   - Error messages
   - Steps to reproduce
   - Environment details
   - Log excerpts (sanitized)
