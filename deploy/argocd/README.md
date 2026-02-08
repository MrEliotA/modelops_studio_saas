# ArgoCD (App-of-Apps) templates

These manifests are **templates** for ArgoCD.

> Replace:
> - `<REPO_URL>` with your Git repository
> - `<REVISION>` with branch/tag (e.g. `main`)
> - adjust namespaces as needed

Apply the root `app-of-apps.yaml` once; it will create the child Applications.


## Environments
- `app-of-apps.yaml`: base platform apps (no GPU add-ons)
- `app-of-apps-prod.yaml`: production add-ons (includes NVIDIA GPU Operator)
