#!/usr/bin/env bash
set -euo pipefail

# Node-level prerequisite installer for NVIDIA GPU workloads.
# This configures NVIDIA Container Toolkit integration with Docker or containerd.
#
# Usage (as root):
#   sudo RUNTIME=docker ./scripts/gpu/setup-nvidia-runtime.sh
#   sudo RUNTIME=containerd ./scripts/gpu/setup-nvidia-runtime.sh
#   sudo RUNTIME=auto ./scripts/gpu/setup-nvidia-runtime.sh
#
# Notes:
# - This script modifies container runtime config and restarts the runtime service.
# - You still need NVIDIA drivers installed on the host (nvidia-smi).

RUNTIME=${RUNTIME:-auto}   # auto|docker|containerd
KIND_WORKAROUND=${KIND_WORKAROUND:-false} # true to set accept-nvidia-visible-devices-as-volume-mounts=true

if [[ $EUID -ne 0 ]]; then
  echo "[ERROR] Run as root (sudo)." >&2
  exit 1
fi

if ! command -v nvidia-ctk >/dev/null 2>&1; then
  echo "[ERROR] nvidia-ctk not found. Install NVIDIA Container Toolkit first:" >&2
  echo "  https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html" >&2
  exit 1
fi

if [[ "$RUNTIME" == "auto" ]]; then
  if systemctl is-active --quiet docker 2>/dev/null; then
    RUNTIME=docker
  elif systemctl is-active --quiet containerd 2>/dev/null; then
    RUNTIME=containerd
  else
    echo "[ERROR] Could not detect an active runtime. Set RUNTIME=docker or RUNTIME=containerd." >&2
    exit 1
  fi
fi

case "$RUNTIME" in
  docker)
    echo "==> Configuring NVIDIA runtime for Docker (default runtime)"
    nvidia-ctk runtime configure --runtime=docker --set-as-default
    systemctl restart docker
    ;;
  containerd)
    echo "==> Configuring NVIDIA runtime for containerd (default runtime)"
    nvidia-ctk runtime configure --runtime=containerd --set-as-default
    systemctl restart containerd
    ;;
  *)
    echo "[ERROR] Unknown RUNTIME=$RUNTIME (use auto|docker|containerd)" >&2
    exit 1
    ;;
esac

if [[ "$KIND_WORKAROUND" == "true" ]]; then
  CFG=/etc/nvidia-container-runtime/config.toml
  if [[ -f "$CFG" ]]; then
    echo "==> Enabling kind GPU workaround in $CFG"
    if grep -q '^accept-nvidia-visible-devices-as-volume-mounts' "$CFG"; then
      sed -i 's/^accept-nvidia-visible-devices-as-volume-mounts.*/accept-nvidia-visible-devices-as-volume-mounts = true/' "$CFG"
    else
      echo "accept-nvidia-visible-devices-as-volume-mounts = true" >> "$CFG"
    fi
    # Restart docker/containerd again to make sure config is picked up
    if [[ "$RUNTIME" == "docker" ]]; then
      systemctl restart docker
    else
      systemctl restart containerd
    fi
  else
    echo "[WARN] $CFG not found; skipping KIND_WORKAROUND" >&2
  fi
fi

echo "Done. You can validate with:"
echo "  nvidia-smi"
if command -v docker >/dev/null 2>&1; then
  echo "  docker run --rm --gpus all nvidia/cuda:12.5.0-base-ubuntu22.04 nvidia-smi"
fi
