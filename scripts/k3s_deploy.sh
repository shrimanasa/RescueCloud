#!/usr/bin/env bash
# ============================================================
# RescueCloud – K3s (via k3d) deploy script
# Usage: ./scripts/k3s_deploy.sh [--rebuild] [--delete]
#
#   --rebuild   Force Docker image rebuild before loading
#   --delete    Tear down the k3d cluster and stop
# ============================================================
set -euo pipefail

CLUSTER_NAME="rescuecloud"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
K3D="${HOME}/.local/bin/k3d"
KUBECTL="kubectl"

# ── helpers ──────────────────────────────────────────────────
info()  { echo -e "\033[1;36m[k3s-deploy]\033[0m $*"; }
ok()    { echo -e "\033[1;32m[  OK  ]\033[0m $*"; }
warn()  { echo -e "\033[1;33m[ WARN ]\033[0m $*"; }
die()   { echo -e "\033[1;31m[ FAIL ]\033[0m $*" >&2; exit 1; }

# ── arg parsing ───────────────────────────────────────────────
REBUILD=false
DELETE=false
for arg in "$@"; do
  case "$arg" in
    --rebuild) REBUILD=true ;;
    --delete)  DELETE=true  ;;
  esac
done

# ── delete cluster ────────────────────────────────────────────
if $DELETE; then
  info "Deleting k3d cluster '${CLUSTER_NAME}'..."
  "${K3D}" cluster delete "${CLUSTER_NAME}" && ok "Cluster deleted." || warn "Cluster didn't exist."
  exit 0
fi

# ── verify tooling ────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || die "Docker is not running. Start Docker Desktop first."
command -v "${KUBECTL}" >/dev/null 2>&1 || die "kubectl not found. Install it first."
"${K3D}" version >/dev/null 2>&1 || die "k3d not found at ${K3D}"

# ── create cluster (idempotent) ───────────────────────────────
if "${K3D}" cluster list | grep -q "${CLUSTER_NAME}"; then
  info "k3d cluster '${CLUSTER_NAME}' already exists – skipping creation."
else
  info "Creating k3d cluster '${CLUSTER_NAME}'..."
  "${K3D}" cluster create "${CLUSTER_NAME}" \
    --port "8001:30001@loadbalancer" \
    --port "3000:30000@loadbalancer" \
    --port "9001:9001@loadbalancer" \
    --agents 1 \
    --wait
  ok "Cluster created."
fi

# ── set kubeconfig context ────────────────────────────────────
"${K3D}" kubeconfig merge "${CLUSTER_NAME}" --kubeconfig-merge-default
"${KUBECTL}" config use-context "k3d-${CLUSTER_NAME}"
ok "kubectl context → k3d-${CLUSTER_NAME}"

# ── build docker images ───────────────────────────────────────
build_images() {
  info "Building rescuecloud-services:latest ..."
  docker build -t rescuecloud-services:latest \
    -f "${SCRIPT_DIR}/services/Dockerfile" \
    "${SCRIPT_DIR}"

  info "Building rescuecloud-frontend:latest ..."
  docker build -t rescuecloud-frontend:latest \
    -f "${SCRIPT_DIR}/frontend/Dockerfile" \
    "${SCRIPT_DIR}/frontend"
}

if $REBUILD || ! docker image inspect rescuecloud-services:latest >/dev/null 2>&1; then
  build_images
else
  info "Images already exist (pass --rebuild to force rebuild)."
fi

# ── load images into k3d cluster ─────────────────────────────
info "Loading images into k3d cluster (this skips Docker Hub)..."
"${K3D}" image import rescuecloud-services:latest -c "${CLUSTER_NAME}"
"${K3D}" image import rescuecloud-frontend:latest -c "${CLUSTER_NAME}"
ok "Images loaded."

# ── apply manifests ───────────────────────────────────────────
info "Applying Kubernetes manifests..."
"${KUBECTL}" apply -k "${SCRIPT_DIR}/k8s/"
ok "Manifests applied."

# ── wait for rollout ──────────────────────────────────────────
info "Waiting for deployments to be ready (up to 3 min)..."
NS="rescuecloud"
for deploy in redis minio ehr-service sentinel-service auditor-service healer-service gateway frontend; do
  "${KUBECTL}" rollout status deployment/"${deploy}" -n "${NS}" --timeout=180s || \
    warn "${deploy} not ready yet – check: kubectl -n ${NS} describe deployment/${deploy}"
done

# ── print access info ─────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  RescueCloud is running on K3s 🚀"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  SOC Dashboard  → http://localhost:3000"
echo "  API Gateway    → http://localhost:8001"
echo "  MinIO Console  → http://localhost:9001"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Useful commands:"
echo "  kubectl -n rescuecloud get pods"
echo "  kubectl -n rescuecloud logs -f deployment/gateway"
echo "  kubectl -n rescuecloud logs -f deployment/sentinel-service"
echo "  ${K3D} cluster delete ${CLUSTER_NAME}   # tear down"
