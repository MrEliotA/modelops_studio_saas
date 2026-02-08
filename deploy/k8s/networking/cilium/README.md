# Cilium

This repo standardizes on **Cilium** as the Kubernetes CNI.

- In **production**, install Cilium via ArgoCD using:
  - `deploy/argocd/apps-prod/cilium.yaml`
- In **kind demos**, `scripts/kind/create-cluster.sh` installs Cilium automatically.

For this MVP we use standard Kubernetes `NetworkPolicy` (see `../tenants/generated`).

References:
- https://docs.cilium.io/en/stable/installation/k8s-install-helm/
- https://docs.cilium.io/en/stable/security/policy/
