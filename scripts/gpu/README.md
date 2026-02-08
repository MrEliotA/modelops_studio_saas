# GPU node setup helpers (production)

These scripts are meant for bare-metal nodes.
They help validate NVIDIA driver + container runtime integration.

- `setup-nvidia-runtime.sh`: configures containerd/CRI-O via nvidia-ctk (requires root)
