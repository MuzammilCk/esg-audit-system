# Architecture Overview

This document describes the key architectural decisions and design patterns used in the ESG Audit System.

## System Architecture

### Design Philosophy

The system follows a **zero-trust security model** with the following principles:

1. **Never trust, always verify** - All documents undergo cryptographic verification
2. **Defense in depth** - Multiple security layers (honeypots, threat detection, enclaves)
3. **Least privilege** - Services have minimal required permissions
4. **Assume breach** - Designed to detect and contain threats

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           EXTERNAL INTERFACES                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │   S3/S3-API  │  │  HTTP/HTTPS  │  │ Google Drive │  │   Webhooks  │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬──────┘ │
└─────────┼─────────────────┼─────────────────┼─────────────────┼─────────┘
          │                 │                 │                 │
          └─────────────────┴─────────────────┴─────────────────┘
                                    │
┌───────────────────────────────────┼───────────────────────────────────────┐
│                          INGESTION LAYER                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                    Document Fetcher (Port 8001)                      │  │
│  │  • S3 Presigned URLs  • HTTP Downloads  • GDrive API Integration    │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                    Document Normalizer                                │  │
│  │  • PDF (PyMuPDF)  • XLSX (OpenPyXL)  • DOCX (Python-Docx)           │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                        LANGGRAPH ORCHESTRATION                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                    Audit Agents Service (Port 8003)                  │  │
│  │                                                                       │  │
│  │   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐            │  │
│  │   │    START    │───▶│ Data        │───▶│ Provenance  │            │  │
│  │   │             │    │ Retrieval   │    │ Verification│            │  │
│  │   └─────────────┘    └─────────────┘    └──────┬──────┘            │  │
│  │                                                 │                    │  │
│  │                          ┌────────────────────┬┴─────────────────┐  │  │
│  │                          │                    │                  │  │  │
│  │                          ▼                    ▼                  │  │  │
│  │                   ┌─────────────┐      ┌─────────────┐           │  │  │
│  │                   │  Security   │      │    PII      │           │  │  │
│  │                   │   Alert     │      │   Masking   │           │  │  │
│  │                   └──────┬──────┘      └──────┬──────┘           │  │  │
│  │                          │                    │                  │  │  │
│  │                          ▼                    ▼                  │  │  │
│  │                   ┌─────────────┐      ┌─────────────┐           │  │  │
│  │                   │    END      │      │ Compliance  │           │  │  │
│  │                   │  (Error)    │      │  Analysis   │           │  │  │
│  │                   └─────────────┘      └──────┬──────┘           │  │  │
│  │                                              │                   │  │  │
│  │                          ┌──────────────────┬┴────────────────┐  │  │  │
│  │                          │                  │                 │  │  │  │
│  │                          ▼                  ▼                 │  │  │  │
│  │                   ┌─────────────┐    ┌─────────────┐          │  │  │  │
│  │                   │   Human     │    │  Reporting  │          │  │  │  │
│  │                   │   Review    │    │   Agent     │          │  │  │  │
│  │                   └──────┬──────┘    └──────┬──────┘          │  │  │  │
│  │                          │                  │                 │  │  │  │
│  │                          └──────────────────┴─────────────────┘  │  │  │
│  │                                              │                    │  │  │
│  │                                              ▼                    │  │  │
│  │                                       ┌─────────────┐            │  │  │
│  │                                       │    END      │            │  │  │
│  │                                       │  (Success)  │            │  │  │
│  │                                       └─────────────┘            │  │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. LangGraph Multiagent System

**Decision**: Use LangGraph over CrewAI for workflow orchestration.

**Rationale**:
- Deterministic DAG execution (required for audit compliance)
- Built-in checkpointing for state persistence
- Human-in-the-loop support with pause/resume
- Type-safe state management with Pydantic

**Trade-offs**:
- ✅ Predictable execution order
- ✅ Easy debugging with state inspection
- ❌ Less flexible than CrewAI for dynamic agent selection

### 2. Vector Store (Qdrant)

**Decision**: Use Qdrant for vector search with hybrid retrieval.

**Rationale**:
- Self-hosted (data sovereignty for enterprise)
- Native hybrid search (dense + sparse vectors)
- gRPC support for high performance
- Rich filtering capabilities

**Configuration**:
```yaml
qdrant:
  host: qdrant
  port: 6333
  collection: esg_documents
  embedding_model: text-embedding-3-small
  dimensions: 1536
```

### 3. LLM Integration (OpenAI GPT-4)

**Decision**: Use GPT-4-turbo with structured outputs for compliance analysis.

**Rationale**:
- Best-in-class reasoning for regulatory interpretation
- Structured output mode ensures consistent JSON responses
- High context window (128K tokens) for long documents
- Fallback to rules-based analysis on API failure

**Prompt Engineering**:
- System prompts define ESG analyst persona
- Few-shot examples for compliance patterns
- Chain-of-thought reasoning for transparency

### 4. Confidential Computing (AWS Nitro Enclaves)

**Decision**: Use Nitro Enclaves for PII processing.

**Rationale**:
- Hardware-based isolation (no operator access)
- Cryptographic attestation
- Secure key management via KMS
- vsock communication with parent instance

**Use Cases**:
- PII decryption for masking
- Sensitive compliance score calculation
- Audit report generation

### 5. Preemptive Cybersecurity

**Decision**: Implement defense-in-depth with honeypots and red teaming.

**Components**:
- **Honeypot Manager**: 6 honeypot types (database, API, file server, etc.)
- **PyRIT Red Teamer**: Automated adversarial testing
- **Threat Detector**: Real-time pattern analysis

## Data Flow

### Document Processing Pipeline

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Upload  │───▶│  Fetch   │───▶│ Normalize│───▶│ Verify   │───▶│   Mask   │
│          │    │          │    │          │    │  (C2PA)  │    │  (PII)   │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
                                                              │
                                                              ▼
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Report  │◀───│ Store    │◀───│ Generate │◀───│ Analyze  │◀───│ Retrieve │
│          │    │ (Qdrant) │    │ Report   │    │ (LLM)    │    │ (RAG)    │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
```

## Security Model

### Zero-Trust Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          SECURITY LAYERS                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Layer 1: Network Security                                               │
│  ├── Kubernetes Network Policies (service isolation)                    │
│  ├── TLS 1.3 for all inter-service communication                        │
│  └── Ingress with rate limiting and WAF                                 │
│                                                                          │
│  Layer 2: Identity & Access                                              │
│  ├── Service accounts with RBAC                                          │
│  ├── JWT tokens with short expiration                                    │
│  └── API keys with scope-limited permissions                             │
│                                                                          │
│  Layer 3: Data Protection                                                │
│  ├── AES-256-GCM encryption at rest (Redis)                              │
│  ├── PII masking before LLM processing                                   │
│  └── Confidential computing (Nitro Enclaves)                             │
│                                                                          │
│  Layer 4: Provenance Verification                                        │
│  ├── C2PA signature validation                                           │
│  ├── AI-generated content detection                                      │
│  └── Document integrity hashing                                          │
│                                                                          │
│  Layer 5: Threat Detection                                               │
│  ├── Honeypot network for attacker detection                             │
│  ├── PyRIT red teaming for vulnerability scanning                         │
│  └── Real-time anomaly detection                                         │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Scalability

### Horizontal Scaling Strategy

```yaml
# Kubernetes HPA Configuration
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: audit-agents-hpa
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

### Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Audit Latency | < 30s | P95 |
| Throughput | 100 docs/min | Steady state |
| Availability | 99.9% | Monthly |
| Error Rate | < 0.1% | Per document |

## Technology Decisions

### Decision Log

| Decision | Choice | Alternatives Considered | Status |
|----------|--------|------------------------|--------|
| Orchestration | LangGraph | CrewAI, AutoGen | ✅ Adopted |
| Vector DB | Qdrant | Pinecone, Weaviate | ✅ Adopted |
| LLM | GPT-4 | Claude, Llama 3 | ✅ Adopted |
| Container Runtime | Docker + K8s | Podman, ECS | ✅ Adopted |
| Secrets | K8s Secrets | Vault, AWS SM | ✅ Adopted |

## Future Considerations

1. **Multi-LLM Support** - Add Claude and Llama for comparison
2. **Streaming Responses** - SSE for real-time audit progress
3. **Agent Memory** - Long-term learning from past audits
4. **Webhook Notifications** - External system integration
5. **Multi-tenant Isolation** - Tenant-specific encryption keys
