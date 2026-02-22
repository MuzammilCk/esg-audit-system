#!/bin/bash
#
# Enclave Deployment Script
# Deploys the ESG Audit Enclave to AWS EC2 with Nitro Enclaves
#

set -e

ENCLAVE_NAME="esg-audit-enclave"
EIF_PATH="build/${ENCLAVE_NAME}.eif"
CPU_COUNT=${ENCLAVE_CPU_COUNT:-2}
MEMORY_MB=${ENCLAVE_MEMORY_MB:-4096}

echo "=========================================="
echo "Deploying ESG Audit Enclave"
echo "=========================================="

# Check if running on EC2 with Nitro Enclaves enabled
if [ ! -d /dev/nitro_enclaves ]; then
    echo "Error: Nitro Enclaves not available on this instance."
    echo "Please ensure you're running on an EC2 instance with Nitro Enclaves enabled."
    exit 1
fi

# Check if EIF exists
if [ ! -f "${EIF_PATH}" ]; then
    echo "Error: EIF not found at ${EIF_PATH}"
    echo "Run ./build_enclave.sh first."
    exit 1
fi

# Stop any existing enclave with same name
echo "Stopping any existing enclaves..."
sudo nitro-cli terminate-enclave --enclave-name ${ENCLAVE_NAME} 2>/dev/null || true

# Run the enclave
echo ""
echo "Starting enclave with:"
echo "  CPU Count: ${CPU_COUNT}"
echo "  Memory: ${MEMORY_MB} MB"

sudo nitro-cli run-enclave \
    --eif-path ${EIF_PATH} \
    --enclave-name ${ENCLAVE_NAME} \
    --cpu-count ${CPU_COUNT} \
    --memory ${MEMORY_MB} \
    --debug-mode=false

# Show enclave status
echo ""
echo "Enclave Status:"
sudo nitro-cli describe-enclaves

echo ""
echo "=========================================="
echo "Enclave deployed successfully!"
echo "=========================================="
echo ""
echo "To connect to the enclave:"
echo "  vsock-proxy 5005 3 5005  # Proxy vsock to localhost"
echo ""
echo "To view enclave console:"
echo "  sudo nitro-cli console --enclave-name ${ENCLAVE_NAME}"
