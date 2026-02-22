#!/bin/bash
#
# Enclave Build Script
# Builds the AWS Nitro Enclave Image File (EIF) for ESG Audit
#

set -e

ENCLAVE_NAME="esg-audit-enclave"
DOCKER_IMAGE="esg-audit-enclave"
EIF_OUTPUT="build/${ENCLAVE_NAME}.eif"

echo "=========================================="
echo "Building ESG Audit Nitro Enclave"
echo "=========================================="

# Check prerequisites
command -v docker >/dev/null 2>&1 || { echo "Docker is required but not installed."; exit 1; }
command -v nitro-cli >/dev/null 2>&1 || { echo "nitro-cli is required but not installed."; exit 1; }

# Build the Docker image
echo ""
echo "[1/3] Building Docker image..."
docker build -t ${DOCKER_IMAGE} -f enclave/Dockerfile .

# Build the EIF
echo ""
echo "[2/3] Building Enclave Image File (EIF)..."
mkdir -p build

nitro-cli build-enclave \
  --docker-uri ${DOCKER_IMAGE}:latest \
  --output-file ${EIF_OUTPUT}

# Show EIF info
echo ""
echo "[3/3] EIF Information:"
nitro-cli describe-eif --eif-path ${EIF_OUTPUT}

echo ""
echo "=========================================="
echo "Build complete!"
echo "EIF: ${EIF_OUTPUT}"
echo "=========================================="
echo ""
echo "To run the enclave:"
echo "  sudo nitro-cli run-enclave --eif-path ${EIF_OUTPUT} --cpu-count 2 --memory 4096"
