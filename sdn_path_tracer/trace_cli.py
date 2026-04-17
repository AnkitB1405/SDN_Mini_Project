from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib import error, parse, request

try:
    from sdn_path_tracer.core import format_trace
except ModuleNotFoundError:
    from core import format_trace


def build_trace_url(base_url: str, src: str, dst: str) -> str:
    query = parse.urlencode({"src": src, "dst": dst})
    return f"{base_url.rstrip('/')}/trace?{query}"


def fetch_trace(base_url: str, src: str, dst: str) -> dict:
    url = build_trace_url(base_url, src, dst)
    with request.urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))


def save_trace(trace: dict, output_path: str) -> None:
    output_file = Path(output_path)
    output_file.write_text(json.dumps(trace, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch and display a traced SDN path from the Ryu controller.")
    parser.add_argument("--src", required=True, help="Source host name, IP, or MAC")
    parser.add_argument("--dst", required=True, help="Destination host name, IP, or MAC")
    parser.add_argument("--controller-url", default="http://127.0.0.1:8080")
    parser.add_argument("--output", help="Optional file path to save the JSON trace")
    args = parser.parse_args()

    try:
        trace = fetch_trace(args.controller_url, args.src, args.dst)
    except error.HTTPError as exc:
        message = exc.read().decode("utf-8") or exc.reason
        print(f"Trace request failed: {message}")
        return 1
    except error.URLError as exc:
        print(f"Controller is unreachable: {exc.reason}")
        return 1

    print(format_trace(trace))
    if args.output:
        save_trace(trace, args.output)
        print(f"\nSaved JSON trace to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
