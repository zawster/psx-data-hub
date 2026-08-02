from __future__ import annotations

import argparse
import time

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--path", default="/v1/health")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()

    deadline = time.time() + args.timeout
    while time.time() < deadline:
        try:
            response = httpx.get(f"{args.base_url}{args.path}", timeout=2.0)
            if response.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(args.interval)

    raise SystemExit(f"timeout waiting for {args.base_url}{args.path}")


if __name__ == "__main__":
    main()
