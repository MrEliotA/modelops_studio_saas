#!/usr/bin/env bash
set -euo pipefail

# Applies SQL migrations inside the kind cluster using a short-lived Job.
# This is required for demos (templates/runs/training/deployments/gpu-jobs/feature-store).

NS="${NS:-mlops-system}"

echo "[bootstrap-db] Creating/updating migrations ConfigMap..."
kubectl -n "$NS" create configmap mlops-migrations \
  --from-file=migrations/ \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null

echo "[bootstrap-db] Running migrations job..."
# Recreate the job if it exists
kubectl -n "$NS" delete job mlops-migrate --ignore-not-found >/dev/null

kubectl -n "$NS" apply -f - <<'YAML'
apiVersion: batch/v1
kind: Job
metadata:
  name: mlops-migrate
spec:
  backoffLimit: 3
  template:
    spec:
      restartPolicy: OnFailure
      containers:
      - name: psql
        image: postgres:16
        env:
        - name: PGPASSWORD
          value: postgres
        command: ["bash","-lc"]
        args:
        - |
          set -e
          echo "==> waiting for postgres..."
          until pg_isready -h postgres -U postgres -d mlops; do sleep 1; done
          echo "==> applying migrations..."
          # Lexicographic order works because filenames are 0001_...sql
          for f in /migrations/*.sql; do
            echo "Applying $f"
            psql -h postgres -U postgres -d mlops -f "$f"
          done
          echo "Done."
        volumeMounts:
        - name: migrations
          mountPath: /migrations
      volumes:
      - name: migrations
        configMap:
          name: mlops-migrations
YAML

kubectl -n "$NS" wait --for=condition=complete job/mlops-migrate --timeout=300s
echo "[bootstrap-db] Migrations applied."
