# GPU Scheduler

This platform uses an internal scheduler to provide:
- Fairness across tenants (noisy-neighbor control)
- Plan-based priority (SLA / billing tier)
- Pool-aware dispatch (T4 shared vs MIG isolated)

## Core idea
A job is created as `QUEUED`, then the scheduler transitions it to `DISPATCHED` and publishes an event with a `dispatch_token`.
Workers only start jobs that are `DISPATCHED` with a matching token.

## Tenant policies
Table: `tenant_gpu_policies`

Fields:
- `t4_max_concurrency`: max RUNNING jobs on shared T4 pool
- `mig_max_concurrency`: max RUNNING jobs on MIG pool
- `max_queued_jobs`: max queued/dispatching jobs per tenant
- `priority_boost`: additive boost applied at enqueue time

## Admin API
Use `gpu-scheduler-service` to update tenant policies.

