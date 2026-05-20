"""Fetch official BRAIN fields, operators, and derived datasets.

This is a manual maintenance script. It requires live WorldQuant BRAIN
credentials via BRAIN_USERNAME and BRAIN_PASSWORD. Sensitive authentication
responses are never printed.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import time
from typing import Any

import requests

from brain_alpha_ops.redaction import redact_error_message


BASE_URL = "https://api.worldquantbrain.com"
DATA_DIR = Path("data")
FIELDS_PATH = DATA_DIR / "official_fields.json"
OPERATORS_PATH = DATA_DIR / "official_operators.json"
DATASETS_PATH = DATA_DIR / "official_datasets.json"


def _credentials() -> tuple[str, str]:
    username = os.getenv("BRAIN_USERNAME", "")
    password = os.getenv("BRAIN_PASSWORD", "")
    if not username or not password:
        raise RuntimeError("BRAIN_USERNAME and BRAIN_PASSWORD environment variables are required")
    return username, password


def _login() -> requests.Session:
    username, password = _credentials()
    session = requests.Session()
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    response = session.post(
        f"{BASE_URL}/authentication",
        headers={"Content-Type": "application/json", "Authorization": f"Basic {token}"},
        timeout=30,
    )
    print(f"Authentication status: {response.status_code}")
    if response.status_code not in {200, 201}:
        raise RuntimeError(f"authentication failed: HTTP {response.status_code}")
    print("Authentication succeeded; token/cookie details redacted")
    return session


def _get_json(session: requests.Session, url: str, *, timeout: int = 60) -> Any:
    while True:
        response = session.get(url, timeout=timeout)
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60) or 60)
            print(f"Rate limited (429). Waiting {retry_after} seconds...")
            time.sleep(max(1, retry_after))
            continue
        response.raise_for_status()
        return response.json()


def fetch_fields(session: requests.Session) -> list[dict]:
    print("\nFetching data fields...")
    fields: list[dict] = []
    offset = 0
    limit = 50
    total: int | None = None

    while True:
        url = (
            f"{BASE_URL}/data-fields?limit={limit}&offset={offset}"
            "&instrumentType=EQUITY&region=USA&delay=1&universe=TOP3000"
        )
        payload = _get_json(session, url)
        if not isinstance(payload, dict):
            raise RuntimeError(f"unexpected data-fields payload type: {type(payload).__name__}")
        page_items = payload.get("results") or []
        if not isinstance(page_items, list):
            raise RuntimeError("unexpected data-fields results payload")
        if total is None:
            total = int(payload.get("count", 0) or 0)
            print(f"Total fields reported: {total}")

        fields.extend(item for item in page_items if isinstance(item, dict))
        print(f"  fetched {len(page_items)} fields; accumulated {len(fields)}")

        if not page_items or len(fields) >= total:
            break
        offset += limit
        time.sleep(3)

    return fields


def fetch_operators(session: requests.Session) -> list[dict]:
    print("\nFetching operators...")
    payload = _get_json(session, f"{BASE_URL}/operators")
    if isinstance(payload, list):
        operators = [item for item in payload if isinstance(item, dict)]
    elif isinstance(payload, dict) and isinstance(payload.get("results"), list):
        operators = [item for item in payload["results"] if isinstance(item, dict)]
    else:
        raise RuntimeError(f"unexpected operators payload type: {type(payload).__name__}")
    print(f"Fetched {len(operators)} operators")
    return operators


def derive_datasets(fields: list[dict]) -> list[dict]:
    datasets: dict[str, dict] = {}
    for field in fields:
        dataset = field.get("dataset")
        if not isinstance(dataset, dict):
            continue
        dataset_id = str(dataset.get("id") or "").strip()
        if not dataset_id:
            continue
        row = datasets.setdefault(
            dataset_id,
            {
                "id": dataset_id,
                "name": str(dataset.get("name") or ""),
                "field_count": 0,
            },
        )
        row["field_count"] += 1
    return sorted(datasets.values(), key=lambda item: (-int(item["field_count"]), str(item["id"])))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {path} ({len(payload) if hasattr(payload, '__len__') else 'n/a'} rows)")


def main() -> int:
    try:
        session = _login()
        fields = fetch_fields(session)
        if not fields:
            raise RuntimeError("no fields fetched")
        operators = fetch_operators(session)
        datasets = derive_datasets(fields)

        _write_json(FIELDS_PATH, fields)
        _write_json(OPERATORS_PATH, operators)
        _write_json(DATASETS_PATH, datasets)
        print("\nOfficial context fetch complete")
        return 0
    except Exception as exc:
        print(f"ERROR: {redact_error_message(exc)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
