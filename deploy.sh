#!/bin/bash
#
# Kubernetes Deployment Script for ESG Audit System
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="${SCRIPT_DIR}/k8s"
NAMESPACE="esg-audit"

echo "=========================================="
echo "ESG Audit System - Kubernetes Deployment"
echo "=========================================="

# Check prerequisites
command -v kubectl >/dev/null 2>&1 || { echo "kubectl is required"; exit 1; }

# Set environment variables
export DOCKER_REGISTRY="${DOCKER_REGISTRY:-localhost:5000}"
export IMAGE_TAG="${IMAGE_TAG:-latest}"

echo ""
echo "[1/5] Creating namespace and RBAC..."
kubectl apply -f "${K8S_DIR}/base/namespace.yaml"
kubectl apply -f "${K8S_DIR}/base/rbac.yaml"

echo ""
echo "[2/5] Creating secrets..."
kubectl apply -f "${K8S_DIR}/base/secrets.yaml"

echo ""
echo "[3/5] Creating configmaps..."
kubectl apply -f "${K8S_DIR}/base/configmaps.yaml"

echo ""
echo "[4/5] Deploying services..."
kubectl apply -f "${K8S_DIR}/services/redis.yaml"
kubectl apply -f "${K8S_DIR}/services/qdrant.yaml"
kubectl apply -f "${K8S_DIR}/services/audit-agents.yaml"
kubectl apply -f "${K8S_DIR}/services/support-services.yaml"

echo ""
echo "[5/5] Deploying Ray cluster..."
kubectl apply -f "${K8S_DIR}/ray/ray-cluster.yaml"
kubectl apply -f "${K8S_DIR}/ray/ray-jobs.yaml"

echo ""
echo "=========================================="
echo "Deployment complete!"
echo "=========================================="
echo ""
echo "Waiting for pods to be ready..."
kubectl -n ${NAMESPACE} wait --for=condition=ready pod -l app=redis --timeout=60s
kubectl -n ${NAMESPACE} wait --for=condition=ready pod -l app=qdrant --timeout=60s
kubectl -n ${NAMESPACE} wait --for=condition=ready pod -l app=audit-agents --timeout=120s

echo ""
echo "Pod status:"
kubectl -n ${NAMESPACE} get pods

echo ""
echo "Services:"
kubectl -n ${NAMESPACE} get services

echo ""
echo "To access the API:"
echo "  kubectl -n ${NAMESPACE} port-forward svc/audit-agents 8003:8003"
echo ""
echo "To access Ray dashboard:"
echo "  kubectl -n ${NAMESPACE} port-forward svc/ray-head 8265:8265"
