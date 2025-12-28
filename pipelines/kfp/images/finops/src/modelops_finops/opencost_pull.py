import argparse
import json
from pathlib import Path
import requests

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--window", default="7d")
    parser.add_argument("--aggregate", default="namespace")
    parser.add_argument("--resolution", default="1m")
    parser.add_argument("--include-idle", default="false")
    parser.add_argument("--share-idle", default="true")
    parser.add_argument("--raw-out", required=True)
    args = parser.parse_args()

    url = args.base_url.rstrip("/") + "/allocation"
    params = {
        "window": args.window,
        "aggregate": args.aggregate,
        "resolution": args.resolution,
        "includeIdle": args.include_idle,
        "shareIdle": args.share_idle,
    }

    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    Path(args.raw_out).write_text(r.text, encoding="utf-8")

if __name__ == "__main__":
    main()
