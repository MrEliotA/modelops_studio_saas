# ModelOps Studio - KFP YAML Pack (v1)

This pack provides:
- A YAML-first template catalog
- Container-based component specs (component.yaml)
- Minimal pipeline sources that compile to IR YAML in CI

## Why "YAML-first"
- KFP components are defined as YAML specs and can be loaded from files/URLs.
- Pipelines are compiled into IR YAML, which is the portable runtime artifact.

## Layout
- catalog/kfp/templates.v1.yaml
- pipelines/kfp/components/**/component.yaml
- pipelines/kfp/images/* (Dockerfiles + minimal demo logic)
- pipelines/kfp/templates/* (pipeline sources)
- pipelines/kfp/compiler (containerized compiler + compile script)
- .github/workflows/compile-kfp-pipelines.yaml

## Build images (local)
```bash
docker build -t modelops/kfp-glue:0.1.0 pipelines/kfp/images/glue
docker build -t modelops/kfp-ml-cpu:0.1.0 pipelines/kfp/images/ml-cpu
docker build -t modelops/kfp-finops:0.1.0 pipelines/kfp/images/finops
```

## Compile pipelines to IR YAML (local)
```bash
docker build -t modelops/kfp-compiler:local -f pipelines/kfp/compiler/Dockerfile pipelines/kfp/compiler

./pipelines/kfp/compiler/compile.sh   pipelines/kfp/templates/KFP-003_classic_train/pipeline.py   classic_train_pipeline   pipelines/kfp/compiled/KFP-003.yaml
```

## Notes
- Component implementations in this pack are placeholders intended for scaffolding.
- Replace placeholder API calls with your platform control-plane endpoints.
