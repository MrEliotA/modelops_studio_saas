import argparse
import json
from pathlib import Path

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics-in", required=True)
    parser.add_argument("--acceptance-metric", default="rmse")
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument("--decision-out", required=True)
    parser.add_argument("--report-out", required=True)
    args = parser.parse_args()

    metrics = json.loads(Path(args.metrics_in).read_text(encoding="utf-8"))
    # Demo decision logic: lower is better for rmse; higher is better otherwise.
    v = float(metrics.get(args.acceptance_metric, 0.0))
    if args.acceptance_metric.lower() in {"rmse", "mae", "mse"}:
        passed = v <= args.threshold
    else:
        passed = v >= args.threshold

    decision = {"passed": passed, "metric": args.acceptance_metric, "value": v, "threshold": args.threshold}
    Path(args.decision_out).write_text(json.dumps(decision, indent=2), encoding="utf-8")
    Path(args.report_out).write_text(json.dumps({"metrics": metrics, "decision": decision}, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
