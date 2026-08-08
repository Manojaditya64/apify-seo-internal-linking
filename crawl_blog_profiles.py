#!/usr/bin/env python3
"""
Batch crawl blog URLs with scrapegraph-deepseek (blog_profile preset).

Input:  data/urls.txt  (one URL per line)
Output: data/crawl-results-YYYY-MM-DD.json + merged blog-profiles.json

Usage:
  python crawl_blog_profiles.py --dry-run
  python crawl_blog_profiles.py --batch-size 10
  python crawl_blog_profiles.py --merge-only data/crawl-results-2026-03-04.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = PROJECT_ROOT / "data" / "urls.txt"
DEFAULT_PROFILES = PROJECT_ROOT / "data" / "blog-profiles.json"
APIFY_API_BASE = "https://api.apify.com/v2"
POLL_INTERVAL_SEC = 10
DEFAULT_ACTOR_ID = "manojaditya64/scrapegraph-deepseek"
DEFAULT_BATCH_SIZE = 10


def load_env() -> dict[str, str]:
    env_path = PROJECT_ROOT / ".env"
    out: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            out[key.strip()] = val.strip().strip('"').strip("'")
    for k, v in os.environ.items():
        if k.startswith("APIFY_") or k.startswith("DEEPSEEK_"):
            out[k] = v
    return out


def get_token(cli: str | None) -> str:
    if cli and cli.strip():
        return cli.strip()
    env = load_env()
    for key in ("APIFY_API_TOKEN", "APIFY_REVENUE_API_TOKEN"):
        token = env.get(key, "").strip()
        if token:
            return token
    print("Missing APIFY_API_TOKEN in .env", file=sys.stderr)
    sys.exit(1)


def get_actor_id(cli: str | None) -> str:
    if cli and cli.strip():
        return cli.strip()
    env = load_env()
    return env.get("APIFY_SCRAPEGRAPH_ACTOR_ID", "").strip() or DEFAULT_ACTOR_ID


def apify_request(
    method: str,
    path: str,
    token: str,
    body: dict | None = None,
    timeout: int = 180,
) -> dict | list:
    url = f"{APIFY_API_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def actor_path(actor_id: str) -> str:
    return actor_id.replace("/", "~") if "/" in actor_id else actor_id


def start_run(token: str, actor_id: str, urls: list[str]) -> tuple[str, str]:
    payload = {
        "start_urls": "\n".join(urls),
        "mode": "markdown_and_extract",
        "preset": "blog_profile",
        "max_concurrency": 3,
    }
    result = apify_request("POST", f"/acts/{actor_path(actor_id)}/runs", token, payload)
    run = result["data"]
    return run["id"], run["defaultDatasetId"]


def wait_for_run(token: str, run_id: str) -> str:
    while True:
        result = apify_request("GET", f"/actor-runs/{run_id}", token)
        status = result["data"]["status"] if isinstance(result, dict) else result["status"]
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            if status != "SUCCEEDED":
                raise RuntimeError(f"Run {run_id} ended with {status}")
            return status
        time.sleep(POLL_INTERVAL_SEC)


def fetch_dataset(token: str, dataset_id: str) -> list[dict]:
    items: list[dict] = []
    offset = 0
    limit = 500
    while True:
        qs = urllib.parse.urlencode(
            {"offset": offset, "limit": limit, "clean": "true", "format": "json"}
        )
        batch = apify_request("GET", f"/datasets/{dataset_id}/items?{qs}", token, timeout=120)
        if not isinstance(batch, list) or not batch:
            break
        items.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return items


def load_urls(path: Path) -> list[str]:
    urls: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def merge_profiles(existing_path: Path, rows: list[dict], out_path: Path) -> dict[str, int]:
    profiles: dict[str, dict] = {}
    if existing_path.exists():
        data = json.loads(existing_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            profiles = data
        elif isinstance(data, list):
            for item in data:
                slug = item.get("slug")
                if slug:
                    profiles[slug] = item

    stats = {"merged": 0, "skipped": 0, "validation_failed": 0}
    for row in rows:
        status = row.get("status")
        if status == "validation_failed":
            stats["validation_failed"] += 1
            continue
        if status != "success":
            stats["skipped"] += 1
            continue
        profile = row.get("blog_profile")
        if not profile or not profile.get("slug"):
            stats["skipped"] += 1
            continue
        profiles[profile["slug"]] = profile
        stats["merged"] += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(profiles, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl blog URLs with scrapegraph-deepseek")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--token", default=None)
    parser.add_argument("--actor-id", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--merge-only", type=Path, default=None, help="Merge rows from saved JSON")
    args = parser.parse_args()

    token = get_token(args.token)
    actor_id = get_actor_id(args.actor_id)

    if args.merge_only:
        rows = json.loads(args.merge_only.read_text(encoding="utf-8"))
        stats = merge_profiles(args.profiles, rows, args.profiles)
        print(json.dumps({"merge": stats, "profiles_file": str(args.profiles)}, indent=2))
        return

    urls = load_urls(args.input)
    if not urls:
        print(f"No URLs in {args.input}", file=sys.stderr)
        sys.exit(1)

    batches = [urls[i : i + args.batch_size] for i in range(0, len(urls), args.batch_size)]
    print(f"URLs: {len(urls)} in {len(batches)} batch(es), actor={actor_id}")

    if args.dry_run:
        for i, batch in enumerate(batches, 1):
            print(f"Batch {i}: {len(batch)} URLs")
            for url in batch:
                print(f"  - {url}")
        return

    all_rows: list[dict] = []
    for i, batch in enumerate(batches, 1):
        print(f"Batch {i}/{len(batches)}: starting run ({len(batch)} URLs)...")
        run_id, dataset_id = start_run(token, actor_id, batch)
        print(f"  Run: https://console.apify.com/actors/runs/{run_id}")
        wait_for_run(token, run_id)
        rows = fetch_dataset(token, dataset_id)
        print(f"  Dataset rows: {len(rows)}")
        all_rows.extend(rows)

    stamp = date.today().isoformat()
    results_path = PROJECT_ROOT / "data" / f"crawl-results-{stamp}.json"
    results_path.write_text(json.dumps(all_rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    stats = merge_profiles(args.profiles, all_rows, args.profiles)
    print(json.dumps({"results_file": str(results_path), "merge": stats}, indent=2))


if __name__ == "__main__":
    main()
