#!/bin/bash
# =============================================================================
# deploy.sh — Deploy task-management to all 3 clusters
#
# Usage:
#   ./deploy.sh              # Deploy to all 3 clusters (dev -> staging -> prod)
#   ./deploy.sh dev          # Deploy only to dev
#   ./deploy.sh staging      # Deploy only to staging
#   ./deploy.sh prod         # Deploy only to prod
#   ./deploy.sh clean        # Remove from all clusters
#   ./deploy.sh clean dev    # Remove only from dev
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHART_DIR="${SCRIPT_DIR}/helm"
LOG_FILE="${SCRIPT_DIR}/deploy.log"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo -e "${msg}" | tee -a "$LOG_FILE"
}

info() {
    log "${GREEN}[INFO]${NC} $1"
}

warn() {
    log "${YELLOW}[WARN]${NC} $1"
}

error() {
    log "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    local missing=0
    for cmd in kubectl helm docker; do
        if ! command -v "$cmd" &>/dev/null; then
            error "$cmd is not installed"
            missing=1
        fi
    done
    if [ $missing -eq 1 ]; then
        error "Please install missing prerequisites (kubectl, helm, docker)"
        exit 1
    fi
}

# Build and push Docker images
build_images() {
    info "Building Docker images..."
    local compose_file="${SCRIPT_DIR}/docker-compose.yml"

    cd "$SCRIPT_DIR"
    docker compose build task-service notification-service web-ui
    info "Docker images built successfully"
}

# Deploy to a single cluster
deploy_to() {
    local env=$1
    local release_name="task-management-${env}"
    local namespace="task-management-${env}"
    local values_file="${CHART_DIR}/values-${env}.yaml"

    if [ ! -f "$values_file" ]; then
        error "Values file not found: $values_file"
        return 1
    fi

    info "============================================"
    info "Deploying to ${env^^} cluster"
    info "============================================"

    # Select the correct kubectl context
    local context="k8s-${env}"
    if kubectl config get-contexts "$context" &>/dev/null; then
        info "Using kubectl context: $context"
        kubectl config use-context "$context" >/dev/null 2>&1
    else
        warn "Context '$context' not found, using current context"
    fi

    # Create namespace if it doesn't exist
    if ! kubectl get namespace "$namespace" &>/dev/null; then
        info "Creating namespace: $namespace"
        kubectl create namespace "$namespace" --dry-run=client -o yaml | kubectl apply -f -
    fi

    # Install or upgrade Helm release
    if kubectl get namespace "$namespace" &>/dev/null && \
       kubectl get deployment -n "$namespace" -l release="$release_name" &>/dev/null 2>&1; then
        info "Upgrading existing release: $release_name"
        helm upgrade "$release_name" "$CHART_DIR" \
            --namespace "$namespace" \
            --values "$values_file" \
            --install \
            --create-namespace \
            --wait \
            --timeout 300s \
            --atomic \
            --recreate-pods
    else
        info "Installing new release: $release_name"
        helm install "$release_name" "$CHART_DIR" \
            --namespace "$namespace" \
            --values "$values_file" \
            --create-namespace \
            --wait \
            --timeout 300s \
            --atomic \
            --recreate-pods
    fi

    # Wait for all pods to be ready
    info "Waiting for pods to be ready..."
    kubectl wait --for=condition=ready pod \
        -l app=task-service,component=task-service \
        -n "$namespace" --timeout=120s 2>/dev/null || warn "task-service pods not ready in time"

    kubectl wait --for=condition=ready pod \
        -l app=notification-service,component=notification-service \
        -n "$namespace" --timeout=120s 2>/dev/null || warn "notification-service pods not ready in time"

    kubectl wait --for=condition=ready pod \
        -l app=web-ui,component=web-ui \
        -n "$namespace" --timeout=120s 2>/dev/null || warn "web-ui pods not ready in time"

    # Show deployment status
    info "Deployment status for ${env^^}:"
    kubectl get pods -n "$namespace" -l release="$release_name" -o wide
    kubectl get svc -n "$namespace" -l release="$release_name"

    info "${env^^} deployment completed!"
}

# Clean deployment from a single cluster
clean_from() {
    local env=$1
    local release_name="task-management-${env}"
    local namespace="task-management-${env}"

    info "Cleaning up ${env^^} cluster..."

    # Select the correct kubectl context
    local context="k8s-${env}"
    if kubectl config get-contexts "$context" &>/dev/null; then
        kubectl config use-context "$context" >/dev/null 2>&1
    fi

    helm uninstall "$release_name" --namespace "$namespace" 2>/dev/null || warn "Release not found"
    kubectl delete namespace "$namespace" 2>/dev/null || warn "Namespace not found"

    info "${env^^} cleanup completed!"
}

# Main
main() {
    check_prerequisites

    case "${1:-all}" in
        dev)
            build_images
            deploy_to "dev"
            ;;
        staging)
            build_images
            deploy_to "staging"
            ;;
        prod)
            build_images
            deploy_to "prod"
            ;;
        all)
            build_images
            deploy_to "dev"
            deploy_to "staging"
            deploy_to "prod"
            info "============================================"
            info "All deployments completed!"
            info "============================================"
            ;;
        clean)
            if [ "${2:-all}" = "all" ]; then
                clean_from "dev"
                clean_from "staging"
                clean_from "prod"
            else
                clean_from "$2"
            fi
            ;;
        status)
            for env in dev staging prod; do
                local namespace="task-management-${env}"
                info "=== ${env^^} ==="
                kubectl get ns "$namespace" 2>/dev/null && \
                    kubectl get pods -n "$namespace" 2>/dev/null || \
                    warn "Namespace $namespace not found"
                echo ""
            done
            ;;
        *)
            echo "Usage: $0 {dev|staging|prod|all|clean|status}"
            echo ""
            echo "Commands:"
            echo "  dev        - Deploy to dev cluster"
            echo "  staging    - Deploy to staging cluster"
            echo "  prod       - Deploy to prod cluster"
            echo "  all        - Deploy to all 3 clusters"
            echo "  clean      - Remove from all clusters"
            echo "  clean <env> - Remove from specific cluster"
            echo "  status     - Show status of all clusters"
            exit 1
            ;;
    esac
}

main "$@"
