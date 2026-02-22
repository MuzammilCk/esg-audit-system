# AWS Nitro Enclaves Deployment

This guide covers confidential computing using AWS Nitro Enclaves for processing sensitive ESG data.

## Overview

AWS Nitro Enclaves provide hardware-based isolation for processing sensitive data:

- **No operator access** - Even AWS employees cannot access enclave memory
- **Cryptographic attestation** - Verify enclave identity and integrity
- **Secure key management** - Integration with AWS KMS
- **vsock communication** - Secure channel to parent EC2 instance

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           EC2 INSTANCE                                   │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                      PARENT APPLICATION                            │  │
│  │                                                                    │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │  │
│  │  │ FastAPI     │  │  Redis      │  │  Parent     │               │  │
│  │  │ Service     │  │  Client     │  │  Proxy      │               │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘               │  │
│  │         │                │                │                       │  │
│  │         └────────────────┼────────────────┘                       │  │
│  │                          │ vsock                                  │  │
│  └──────────────────────────┼────────────────────────────────────────┘  │
│                             │                                            │
│  ┌──────────────────────────┼────────────────────────────────────────┐  │
│  │                      NITRO ENCLAVE                                  │  │
│  │                          │                                         │  │
│  │  ┌───────────────────────┴───────────────────────────────────────┐│  │
│  │  │                    ENCLAVE APPLICATION                         ││  │
│  │  │                                                                ││  │
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           ││  │
│  │  │  │   Crypto    │  │  Attestation│  │   PII       │           ││  │
│  │  │  │   Utils     │  │   Service   │  │  Processor  │           ││  │
│  │  │  └─────────────┘  └─────────────┘  └─────────────┘           ││  │
│  │  │                                                                ││  │
│  │  └────────────────────────────────────────────────────────────────┘│  │
│  │                                                                    │  │
│  │  ┌────────────────────────────────────────────────────────────────┐│  │
│  │  │                    ISOLATED MEMORY                              ││  │
│  │  │  • No external access  • Encrypted  • Attested                 ││  │
│  │  └────────────────────────────────────────────────────────────────┘│  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Prerequisites

- EC2 instance with Nitro Enclaves support (m5, c5, r5 instance types)
- Nitro Enclaves CLI installed
- Docker for building enclave images
- AWS KMS key for encryption

## Setup

### 1. Install Nitro Enclaves CLI

```bash
# Amazon Linux 2
sudo yum install aws-nitro-enclaves-cli -y
sudo yum install aws-nitro-enclaves-cli-devel -y

# Enable the service
sudo systemctl enable nitro-enclaves-allocator.service
sudo systemctl start nitro-enclaves-allocator.service
```

### 2. Configure Memory Allocation

Edit `/etc/nitro_enclaves/allocator.yaml`:

```yaml
memory_mib: 4096  # 4GB for enclave
cpu_count: 2
```

### 3. Build Enclave Image

```bash
# Build the enclave Docker image
cd enclave
docker build -t esg-enclave .

# Convert to EIF format
nitro-cli build-enclave \
  --docker-uri esg-enclave:latest \
  --output-file esg-enclave.eif
```

### 4. Run Enclave

```bash
# Start the enclave
nitro-cli run-enclave \
  --cpu-count 2 \
  --memory 4096 \
  --enclave-cid 16 \
  --eif-path esg-enclave.eif \
  --debug-mode
```

## Attestation

### Generate Attestation Document

```python
from enclave.attestation import AttestationService

attestation = AttestationService()
doc = await attestation.generate_attestation(nonce="random-nonce")

print(f"PCR0: {doc['pcrs']['sha256']['PCR0']}")
print(f"Enclave ID: {doc['enclave_id']}")
```

### Verify Attestation

```python
from enclave.attestation import verify_attestation

is_valid = await verify_attestation(
    attestation_doc=doc,
    expected_pcrs={
        "PCR0": "expected-hash-value",
        "PCR1": "expected-hash-value",
        "PCR2": "expected-hash-value",
    },
    kms_key_arn="arn:aws:kms:region:account:key/key-id"
)
```

## Communication

### vsock Protocol

Parent-to-enclave communication uses vsock:

```python
# Parent proxy
from enclave.communication import VsockClient

client = VsockClient(cid=16, port=5005)
response = await client.send_request({
    "action": "process_pii",
    "data": encrypted_data,
    "mapping_key": "pii:doc:entities"
})
```

```python
# Enclave server
from enclave.communication import VsockServer

server = VsockServer(port=5005)
await server.start()

async for request in server.receive():
    response = process_request(request)
    await server.send_response(response)
```

## Encryption

### KMS Integration

```python
from enclave.crypto import EnclaveCrypto

crypto = EnclaveCrypto(kms_key_arn="arn:aws:kms:...")

# Encrypt data
encrypted = await crypto.encrypt(b"sensitive data")

# Decrypt data (only inside enclave)
decrypted = await crypto.decrypt(encrypted)
```

## Deployment Scripts

```bash
# Setup EC2 instance
./enclave/scripts/setup.sh

# Build enclave
./enclave/scripts/build.sh

# Deploy enclave
./enclave/scripts/deploy.sh

# Verify enclave
./enclave/scripts/verify.sh
```

## Monitoring

### CloudWatch Metrics

- `NitroEnclave/EnclaveCount` - Running enclaves
- `NitroEnclave/MemoryUsage` - Memory utilization
- `NitroEnclave/CPUUsage` - CPU utilization

### Logs

```bash
# View enclave console output
nitro-cli console --enclave-name esg-enclave

# View enclave logs
nitro-cli describe-enclaves
```

## Security Considerations

1. **PCR Values** - Document and verify expected PCR values
2. **KMS Policies** - Restrict key usage to attested enclaves
3. **Network Isolation** - Enclaves have no network access
4. **Memory Limits** - Set appropriate memory allocation

## Troubleshooting

### Enclave Won't Start

```bash
# Check memory allocation
cat /proc/meminfo | grep MemAvailable

# Increase allocation if needed
sudo sed -i 's/memory_mib:.*/memory_mib: 8192/' /etc/nitro_enclaves/allocator.yaml
sudo systemctl restart nitro-enclaves-allocator.service
```

### Attestation Fails

```bash
# Verify PCR values
nitro-cli describe-enclaves | jq '.[0].Measurements'

# Compare with expected values
openssl dgst -sha256 -binary enclave/main.py | xxd -p
```

### vsock Connection Refused

```bash
# Check if enclave is running
nitro-cli describe-enclaves

# Verify vsock port
netstat -ln | grep vsock
```
