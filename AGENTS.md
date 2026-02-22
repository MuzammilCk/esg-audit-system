# AGENTS.md - Multiagent System Documentation

## Overview

This document provides detailed technical documentation for the LangGraph-based multiagent system that orchestrates ESG compliance auditing.

---

## Architecture

### State Machine Design

The system implements a **Directed Acyclic Graph (DAG)** using LangGraph, where each node represents an agent with a specific responsibility.

```
┌─────────────────────────────────────────────────────────────────────┐
│                      LANGGRAPH STATE MACHINE                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────┐                                                │
│  │  START          │                                                │
│  └────────┬────────┘                                                │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────┐                                                │
│  │ data_retrieval  │  Normalizes document, extracts metadata        │
│  └────────┬────────┘                                                │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────┐                                                │
│  │ provenance_     │  Validates C2PA signatures, detects AI content │
│  │ verification    │                                                │
│  └────────┬────────┘                                                │
│           │                                                          │
│     ┌─────┴─────┐                                                   │
│     │           │                                                   │
│     │ TAMPERED  │ VERIFIED                                          │
│     ▼           ▼                                                   │
│  ┌─────────┐  ┌─────────────────┐                                   │
│  │security │  │ pii_masking     │  Masks PII with Presidio         │
│  │_alert   │  └────────┬────────┘                                   │
│  └────┬────┘           │                                            │
│       │                ▼                                            │
│       │         ┌─────────────────┐                                 │
│       │         │ compliance_     │  LLM + RAG analysis             │
│       │         │ analysis        │                                 │
│       │         └────────┬────────┘                                 │
│       │                  │                                          │
│       │           ┌──────┴──────┐                                   │
│       │           │             │                                   │
│       │        REVIEW       APPROVE                                 │
│       │           │             │                                   │
│       │           ▼             ▼                                   │
│       │    ┌───────────┐  ┌─────────────────┐                       │
│       │    │ human_    │  │ reporting       │  Generates audit      │
│       │    │ review    │  └────────┬────────┘  report               │
│       │    └─────┬─────┘           │                               │
│       │          │                 │                               │
│       │    PAUSE │                 │                               │
│       │          │                 │                               │
│       │          └─────────────────┼───────────────┐               │
│       │                            │               │               │
│       ▼                            ▼               ▼               │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                         END                                  │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Agent Specifications

### 1. Data Retrieval Agent

**Purpose**: Normalize incoming documents and prepare for analysis

**Inputs**:
- `raw_content`: Document text
- `document_metadata`: Source, filename, MIME type

**Outputs**:
- `normalized_text`: Cleaned text
- Status: `INGESTING` → `VERIFYING`

**Implementation**: `services/agents/nodes/data_retrieval.py`

```python
async def data_retrieval_node(state: AuditState) -> Dict[str, Any]:
    """
    1. Validate raw content exists
    2. Extract text content
    3. Update state with normalized text
    4. Route to provenance verification
    """
```

### 2. Provenance Verification Agent

**Purpose**: Validate C2PA cryptographic signatures

**Inputs**:
- `normalized_text` or raw bytes
- Document metadata

**Outputs**:
- `provenance_result`: Trust score, is_ai_generated, is_signed
- Routes: `security_alert` (TAMPERED) or `pii_masking` (VERIFIED)

**Implementation**: `services/agents/nodes/provenance_verification.py`

**Risk Thresholds**:
| Trust Score | Action |
|-------------|--------|
| 1.0 | VERIFIED - Continue |
| 0.5 | UNSIGNED - Warning, continue |
| 0.0 | TAMPERED - Security alert |

### 3. PII Masking Agent

**Purpose**: Algorithmically mask personally identifiable information

**Inputs**:
- `normalized_text`
- `document_id` for Redis key

**Outputs**:
- `pii_result`: Masked text, entities found, mapping key

**Implementation**: `services/agents/nodes/pii_masking.py`

**Entity Types Detected**:
- PERSON (names)
- LOCATION (addresses, cities)
- ORGANIZATION
- EMAIL_ADDRESS
- PHONE_NUMBER
- CREDIT_CARD
- DATE_TIME

**Masking Format**: `<ENTITY_TYPE_N>` where N is sequence number

### 4. Compliance Analysis Agent

**Purpose**: Perform ESG regulatory compliance analysis

**Inputs**:
- `normalized_text` (PII-masked)
- RAG context from Qdrant
- Document metadata

**Outputs**:
- `compliance_result`: Findings, score, decision

**Implementation**: `services/agents/nodes/compliance_analysis.py`

**Decision Logic**:
```python
if compliance_score >= 0.8:
    overall_decision = APPROVE
elif compliance_score >= 0.5:
    overall_decision = REVIEW
else:
    overall_decision = REJECT
```

**RAG Enhancement**: Retrieves historical compliance documents for context enrichment.

### 5. Security Alert Agent

**Purpose**: Handle security-relevant events

**Inputs**:
- `provenance_result` with TAMPERED status
- Error conditions

**Outputs**:
- Security alert with severity
- Logs incident

**Implementation**: `services/agents/nodes/security_alert.py`

**Alert Severities**:
| Event | Severity |
|-------|----------|
| DOCUMENT_TAMPERED | CRITICAL |
| AI_GENERATED_UNSIGNED | HIGH |
| UNSIGNED_DOCUMENT | MEDIUM |

### 6. Human Review Agent

**Purpose**: Enable human-in-the-loop workflows

**Inputs**:
- `compliance_result` with REVIEW status
- Human decision (if provided)

**Outputs**:
- Pauses workflow (no decision)
- Routes to reporting (decision provided)

**Implementation**: `services/agents/nodes/human_review.py`

**Resume API**:
```bash
POST /api/audit/{thread_id}/resume
{
  "human_decision": "APPROVE",
  "reviewer": "john.doe@example.com"
}
```

### 7. Reporting Agent

**Purpose**: Generate comprehensive audit reports

**Inputs**:
- All previous agent outputs
- `compliance_result`
- `provenance_result`

**Outputs**:
- `audit_report`: Complete report with findings

**Implementation**: `services/agents/nodes/reporting.py`

---

## State Model

### AuditState Definition

```python
class AuditState(BaseModel):
    # Identification
    thread_id: str                    # Unique workflow ID
    
    # Processing status
    status: ProcessingStatus          # Current stage
    current_node: str                 # Active agent
    
    # Document data
    document_metadata: DocumentMetadata
    raw_content: str
    normalized_text: str
    
    # Agent results
    provenance_result: ProvenanceResult
    pii_result: PIIResult
    compliance_result: ComplianceResult
    audit_report: Optional[AuditReport]
    
    # Error handling
    errors: List[str]
    warnings: List[str]
    
    # Audit trail
    audit_trail: List[Dict[str, Any]]
    
    # Extensible metadata
    metadata: Dict[str, Any]
```

### Processing Status Enum

```python
class ProcessingStatus(str, Enum):
    PENDING = "PENDING"
    INGESTING = "INGESTING"
    VERIFYING = "VERIFYING"
    ANALYZING = "ANALYZING"
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    ERROR = "ERROR"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
```

---

## Routing Logic

### Conditional Edges

```python
def _provenance_router(state: AuditState) -> Literal["security_alert", "pii_masking"]:
    if state.provenance_result.status == "TAMPERED":
        return "security_alert"
    return "pii_masking"

def _compliance_router(state: AuditState) -> Literal["reporting", "human_review"]:
    if state.compliance_result.requires_human_review:
        return "human_review"
    if state.compliance_result.overall_decision == AgentDecision.REVIEW:
        return "human_review"
    return "reporting"

def _human_review_router(state: AuditState) -> Literal["reporting", "end"]:
    if state.metadata.get("human_decision"):
        return "reporting"
    return "end"
```

---

## Checkpointing & Persistence

### Memory Checkpointing

```python
from langgraph.checkpoint.memory import MemorySaver

graph = builder.compile(checkpointer=MemorySaver())
```

### SQLite Checkpointing (Production)

```python
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3

conn = sqlite3.connect("checkpoints.db")
graph = builder.compile(checkpointer=SqliteSaver(conn))
```

### State Recovery

```python
# Get current state
state = graph.get_state({"configurable": {"thread_id": "thread-123"}})

# Resume from checkpoint
graph.update_state(
    {"configurable": {"thread_id": "thread-123"}},
    {"metadata": {"human_decision": "APPROVE"}}
)
```

---

## Usage Examples

### Basic Audit

```python
from services.agents import create_audit_graph, AuditState, DocumentMetadata

graph = create_audit_graph()

metadata = DocumentMetadata(
    source_url="https://example.com/report.pdf",
    original_filename="sustainability_2024.pdf",
    supplier_id="SUPP-001",
    region="EU",
)

result = await graph.run_audit(
    raw_content=document_text,
    metadata=metadata,
)

print(f"Status: {result.status}")
print(f"Score: {result.compliance_result.compliance_score}")
```

### With Human-in-the-Loop

```python
# Initial run (pauses at human_review)
result = await graph.run_audit(content, metadata)

if result.status == ProcessingStatus.REQUIRES_REVIEW:
    # Later: provide human decision
    final = await graph.resume_audit(
        thread_id=result.thread_id,
        human_decision="APPROVE",
        reviewer="auditor@example.com"
    )
```

### Query State

```python
# Get current state
state = graph.get_state("thread-123")

if state:
    print(f"Current node: {state.current_node}")
    print(f"Compliance score: {state.compliance_result.compliance_score}")
```

---

## Performance Considerations

### Concurrency

LangGraph supports concurrent node execution for independent branches:

```python
# Parallel execution of independent agents
builder.add_edge("start", ["agent_a", "agent_b"])
builder.add_edge(["agent_a", "agent_b"], "merge")
```

### Resource Limits

Configure in Kubernetes:
```yaml
resources:
  requests:
    cpu: 500m
    memory: 1Gi
  limits:
    cpu: 2000m
    memory: 4Gi
```

### Scaling

Horizontal Pod Autoscaler:
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: audit-agents-hpa
spec:
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          averageUtilization: 70
```

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Workflow stuck at PENDING | Redis connection failed | Check REDIS_HOST/PORT |
| Low compliance scores | Missing RAG context | Index documents in Qdrant |
| PII not masked | Presidio model not loaded | Install spaCy model |
| State not persisting | Checkpointer not configured | Add checkpointer to compile() |

### Debugging

Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Inspect state at each node:
```python
state.add_audit_event("node_name", "DEBUG", {"key": "value"})
```

---

## Future Enhancements

1. **Multi-tenant support**: Isolated state per tenant
2. **Streaming responses**: Server-Sent Events for real-time updates
3. **Agent memory**: Long-term memory for learning from past audits
4. **Parallel analysis**: Concurrent compliance framework checks
5. **Webhook notifications**: External system integration on completion

---

Last Updated: January 2026
