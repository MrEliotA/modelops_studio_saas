#!/usr/bin/env bash
set -euo pipefail

# Compile pipeline sources into IR YAML (checked in or built in CI).
# Usage:
#   ./pipelines/kfp/compiler/compile.sh pipelines/kfp/templates/KFP-003_classic_train/pipeline.py classic_train_pipeline out.yaml

PIPELINE_PY="${1:?pipeline source path required}"
FUNC_NAME="${2:?pipeline function name required}"
OUT_YAML="${3:?output path required}"

python - <<'PY'
import importlib.util
import sys
from kfp.compiler import Compiler

pipeline_py = sys.argv[1]
func_name = sys.argv[2]
out_yaml = sys.argv[3]

spec = importlib.util.spec_from_file_location("pipeline_mod", pipeline_py)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)  # type: ignore

pipeline_func = getattr(mod, func_name)
Compiler().compile(pipeline_func=pipeline_func, package_path=out_yaml)
print(f"Wrote IR YAML to: {out_yaml}")
PY "${PIPELINE_PY}" "${FUNC_NAME}" "${OUT_YAML}"
