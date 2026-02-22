#!/bin/bash
#
# Undeploy ESG Audit System from Kubernetes
#

set -e

NAMESPACE="esg-audit"
K8S_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/k8s"

echo "=========================================="
echo "Undeploying ESG Audit System"
echo "=========================================="

echo ""
echo "[1/3] Deleting Ray resources..."
kubectl delete -f "${K8S_DIR}/ray/ray-jobs.yaml" --ignore-not-found=true
kubectl delete -f "${K8S_DIR}/ray/ray-cluster.yaml" --ignore-not-found=true

echo ""
echo "[2/3] Deleting services..."
kubectl delete -f "${K8S_DIR}/services/" --ignore-not-found=true

echo ""
echo "[3/3] Deleting base resources..."
kubectl delete -f "${K8S_DIR}/base/" --ignore-not-found=true

echo ""
echo "=========================================="
echo "Undeploy complete!"
echo "=========================================="

echo ""
echo "Persistent volumes retained. To delete:"
echo "  kubectl -n ${NAMESPACE} delete pvc --all"
