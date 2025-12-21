# Meeting-ready FAQ

## What is the product?
A B2B-first ModelOps platform that provides an opinionated workflow:
- run standardized ML pipelines (preprocess/train/evaluate/register/deploy/monitor)
- enforce resource plans and GPU pools
- offer a model registry and audit-friendly cost visibility

## Why is it credible for hosting customers?
Because it is Kubernetes-native, multi-tenant by design, and implements:
- pool-level capacity, tenant quotas, and auditable metering
- artifact storage and model lifecycle management
- an operational serving surface with predict/explain and request metering

## Why two GPU pools?
- Pro (A30 MIG): stronger isolation and predictable billing for serious workloads
- Economy (T4 time-slice): best-effort, lower cost, for lighter workloads

## Why allocation-based metering?
It is simple, auditable, contract-friendly, and avoids disputed attribution in shared GPU scenarios.

## What is needed for production hardening?
OIDC/SSO, RBAC, network policies, BYOC sandboxing, autoscaling, and full KFP/KServe/Katib backends.
Scaffolds exist in this repo.
