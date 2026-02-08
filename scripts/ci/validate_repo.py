import os, sys, glob, json
from pathlib import Path
import py_compile

repo = Path(__file__).resolve().parents[2]

# --- python compile ---
errs=[]
for py in glob.glob(str(repo/'**/*.py'), recursive=True):
    try:
        py_compile.compile(py, doraise=True)
    except Exception as e:
        errs.append((py,str(e)))

# --- required service skeletons ---
required = {
  'services/template-service': ['Dockerfile','requirements.txt','app/main.py','README.md'],
  'services/run-service': ['Dockerfile','requirements.txt','app/main.py','README.md'],
  'services/training-service': ['Dockerfile','requirements.txt','app/main.py','README.md'],
  'services/registry-service': ['Dockerfile','requirements.txt','app/main.py','README.md'],
  'services/artifact-service': ['Dockerfile','requirements.txt','app/main.py','README.md'],
  'services/metering-service': ['Dockerfile','requirements.txt','app/main.py','README.md'],
  'services/control-plane-api': ['Dockerfile','requirements.txt','app/main.py','README.md'],
  'services/llm-embeddings-service': ['Dockerfile','requirements.txt','app/main.py','README.md'],
  'services/llm-rag-service': ['Dockerfile','requirements.txt','app/main.py','README.md'],
}
missing=[]
for base, files in required.items():
    for f in files:
        p = repo/base/f
        if not p.exists():
            missing.append(str(p.relative_to(repo)))

# --- openapi yaml presence ---
openapi = list((repo/'openapi').glob('*.yaml'))
if not openapi:
    missing.append('openapi/*.yaml')

# --- migrations ---
if not (repo/'migrations/0001_core.sql').exists():
    missing.append('migrations/0001_core.sql')

summary = {
    'python_compile_errors': errs,
    'missing_files': missing,
    'openapi_count': len(openapi),
}

print(json.dumps(summary, indent=2))

if errs or missing:
    sys.exit(1)
