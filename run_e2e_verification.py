"""Read-only HTTP smoke checks; this is not cloud-generation E2E evidence.

Safe to import. No workflow creation, queue submission, cancellation, deletion,
account changes, or provider calls. Run real generation acceptance separately.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request


def read_endpoint(url: str, *, timeout: float):
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.headers, response.read().decode("utf-8")


def require(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def verify_service(base_url="http://127.0.0.1:8088", *, timeout=5, fetch=None):
    """Inspect pages and overview APIs without writing to the live database."""
    fetch = fetch or read_endpoint
    checked = []
    for path in ("/", "/vids", "/static/app.js", "/static/vids.js"):
        status, headers, body = fetch(base_url.rstrip("/") + path, timeout=timeout)
        require(status == 200, f"{path}: HTTP {status}")
        require("no-cache" in headers.get("Cache-Control", ""), f"{path}: missing no-cache")
        require(bool(body.strip()), f"{path}: empty response")
        checked.append(path)

    snapshots = {}
    for path in ("/api/overview", "/api/vids/overview"):
        status, _, body = fetch(base_url.rstrip("/") + path, timeout=timeout)
        require(status == 200, f"{path}: HTTP {status}")
        snapshot = json.loads(body)
        require(isinstance(snapshot, dict), f"{path}: invalid overview object")
        snapshots[path] = snapshot
        checked.append(path)

    overview = snapshots["/api/overview"]
    require(isinstance(overview.get("tasks"), dict), "Missing task overview")
    require(isinstance(overview.get("profiles"), dict), "Missing account overview")
    vids = snapshots["/api/vids/overview"]
    require("total_workflows" in vids and "total_shots" in vids, "Missing Vids overview")
    return {"read_only": True, "generation_verified": False,
            "checked_paths": checked, "overview": overview, "vids_overview": vids}


def main(argv=None):
    parser = argparse.ArgumentParser(description="只读 HTTP 烟雾检查：不创建、不入队、不生成视频")
    parser.add_argument("--base-url", default="http://127.0.0.1:8088")
    parser.add_argument("--timeout", type=float, default=5)
    args = parser.parse_args(argv)
    if not 0 < args.timeout <= 60:
        parser.error("--timeout must be between 0 and 60 seconds")
    try:
        report = verify_service(args.base_url, timeout=args.timeout)
    except Exception as exc:
        print(f"只读 HTTP 检查失败: {exc}", file=sys.stderr)
        return 1
    for path in report["checked_paths"]:
        print(f"PASS GET {path}")
    print("只读 HTTP 检查通过；未提交云端任务，不代表视频生成、停止或下载 E2E 已验收。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
