# Kind mode (demo)

This mode is optimized for a reliable local demo:
- minimal dependencies
- no GPU required
- pools enforced via node labels/taints + the allocator in the control plane

Recommended flow:
```bash
make kind-up
make images
make deploy
make seed
make demo
make port-forward
```

Optional autoscaling (KEDA, CPU-based):
```bash
make keda-kind
```
