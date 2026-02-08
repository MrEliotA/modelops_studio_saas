#!/usr/bin/env bash
set -euo pipefail

# v2: tenant isolation is generated via scripts/generate_tenant_manifests.py.
# This helper applies the generated tenant namespaces/policies.

TENANT_MANIFEST="${TENANT_MANIFEST:-deploy/k8s/networking/tenants/generated/tenants.generated.yaml}"

echo "Applying tenant manifests: ${TENANT_MANIFEST}"
kubectl apply -f "${TENANT_MANIFEST}"
