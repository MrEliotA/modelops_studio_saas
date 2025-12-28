import argparse
import json
from pathlib import Path

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allocation-raw-in", required=True)
    parser.add_argument("--rate-card-id", default="default")
    parser.add_argument("--invoice-preview-out", required=True)
    args = parser.parse_args()

    raw = json.loads(Path(args.allocation_raw_in).read_text(encoding="utf-8"))
    # Demo transformation: you will map allocations -> tenant/project using labels/namespace rules.
    invoice = {
        "rate_card_id": args.rate_card_id,
        "currency": "USD",
        "lines": [],
        "notes": "Demo invoice preview. Replace with tenant/project mapping and pricing.",
        "opencost_response_code": raw.get("code"),
    }
    Path(args.invoice_preview_out).write_text(json.dumps(invoice, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
