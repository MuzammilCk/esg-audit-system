# ESG Audit System Documentation

Welcome to the Zero-Trust Multiagent ESG Audit System documentation.

## Overview

This system is an enterprise-grade AI engineering portfolio project for automated ESG (Environmental, Social, Governance) compliance auditing. It integrates cutting-edge technologies including:

- **LangGraph Multiagent Orchestration** - Deterministic DAG-based workflow
- **GPT-4 + RAG** - LLM-enhanced compliance analysis
- **Qdrant Vector Database** - Hybrid search for regulatory context
- **AWS Nitro Enclaves** - Confidential computing for sensitive data
- **Preemptive Cybersecurity** - Honeypots and PyRIT red teaming

## Documentation Sections

### Getting Started

- [README](../README.md) - Project overview and quick start
- [Contributing](../CONTRIBUTING.md) - How to contribute

### Architecture

- [Architecture Overview](architecture/overview.md) - System design decisions
- [Multiagent System](../AGENTS.md) - LangGraph workflow details
- [Security Architecture](../SECURITY.md) - Zero-trust security model

### API Reference

- [Audit API](api/audit-api.md) - Multiagent audit endpoints
- [Vector Store API](api/vectorstore-api.md) - Document indexing and search
- [Security API](api/security-api.md) - Threat detection endpoints

### Deployment

- [Docker Compose](deployment/docker-compose.md) - Local development
- [Kubernetes](deployment/kubernetes.md) - Production deployment
- [AWS Nitro Enclaves](deployment/nitro-enclaves.md) - Confidential computing

### Operations

- [Monitoring](deployment/monitoring.md) - Observability stack
- [Troubleshooting](deployment/troubleshooting.md) - Common issues

## Quick Links

| Component | Port | Description |
|-----------|------|-------------|
| Audit Agents | 8003 | Multiagent orchestration API |
| Vector Store | 8004 | Qdrant document retrieval |
| Security | 8006 | Threat detection service |
| Ingestion | 8001 | Document fetching/parsing |
| Privacy | 8002 | PII masking service |
| Verification | 8005 | C2PA provenance validation |

## Technology Stack

```
┌─────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                       │
│  FastAPI REST APIs  │  OpenAPI Docs  │  Webhook Callbacks   │
├─────────────────────────────────────────────────────────────┤
│                    ORCHESTRATION LAYER                      │
│  LangGraph DAG  │  Ray Distributed  │  Kubernetes HPA      │
├─────────────────────────────────────────────────────────────┤
│                    AGENT LAYER                              │
│  Data Retrieval  │  Provenance  │  PII  │  Compliance      │
│  Human Review    │  Reporting   │  Security Alert          │
├─────────────────────────────────────────────────────────────┤
│                    AI/ML LAYER                              │
│  OpenAI GPT-4  │  Embeddings  │  RAG Retrieval  │  PyRIT   │
├─────────────────────────────────────────────────────────────┤
│                    DATA LAYER                               │
│  Qdrant Vector DB  │  Redis Encrypted  │  S3 Storage        │
├─────────────────────────────────────────────────────────────┤
│                    INFRASTRUCTURE LAYER                     │
│  AWS Nitro Enclaves  │  Kubernetes  │  Docker Compose       │
└─────────────────────────────────────────────────────────────┘
```

## Compliance Frameworks Supported

| Framework | Region | Coverage |
|-----------|--------|----------|
| CSRD/ESRS | EU | E1-E5 (Environmental), S1 (Social), G1 (Governance) |
| SEC Climate | US | GHG emissions, climate risks, governance |
| CSDDD | EU | Supply chain due diligence |
| CBAM | EU | Carbon border adjustment |

## Version History

See [CHANGELOG.md](../CHANGELOG.md) for release history.

## License

MIT License - See [LICENSE](../LICENSE) for details.
