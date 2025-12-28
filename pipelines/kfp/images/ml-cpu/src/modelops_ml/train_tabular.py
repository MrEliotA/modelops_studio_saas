import argparse
import json
from pathlib import Path
import joblib

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-uri", required=True)
    parser.add_argument("--label-col", required=True)
    parser.add_argument("--algorithm", default="xgboost")
    parser.add_argument("--model-out", required=True)
    parser.add_argument("--metrics-out", required=True)
    args = parser.parse_args()

    # Demo: do not download data. Replace with S3/MinIO read and real training.
    model = {"algorithm": args.algorithm, "label_col": args.label_col, "dataset_uri": args.dataset_uri}
    Path(args.model_out).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, args.model_out)

    metrics = {"rmse": 0.123, "auc": 0.987, "notes": "Demo metrics. Replace with real evaluation."}
    Path(args.metrics_out).write_text(json.dumps(metrics, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
