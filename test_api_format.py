"""Manual live API shape probe.

Requires BRAIN_USERNAME and BRAIN_PASSWORD. Prints response shapes only; sample
payload fields are summarized to avoid leaking account-specific data.
"""

from __future__ import annotations

import base64
import os

import requests

from brain_alpha_ops.redaction import redact_error_message


BASE_URL = "https://api.worldquantbrain.com"


def _login() -> requests.Session:
    username = os.getenv("BRAIN_USERNAME", "")
    password = os.getenv("BRAIN_PASSWORD", "")
    if not username or not password:
        raise RuntimeError("BRAIN_USERNAME / BRAIN_PASSWORD environment variables are required")

    session = requests.Session()
    auth = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    response = session.post(
        f"{BASE_URL}/authentication",
        headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"},
        timeout=30,
    )
    print(f"Authentication status: {response.status_code}")
    if response.status_code not in {200, 201}:
        raise RuntimeError(f"authentication failed: HTTP {response.status_code}")
    print("Authentication succeeded; token/cookie details redacted")
    return session


def _summarize_payload(payload: object) -> dict:
    if isinstance(payload, list):
        first = payload[0] if payload and isinstance(payload[0], dict) else {}
        return {"type": "list", "length": len(payload), "first_keys": sorted(first.keys())[:20]}
    if isinstance(payload, dict):
        results = payload.get("results")
        summary = {"type": "dict", "keys": sorted(payload.keys())[:20]}
        if isinstance(results, list):
            first = results[0] if results and isinstance(results[0], dict) else {}
            summary["results_length"] = len(results)
            summary["first_result_keys"] = sorted(first.keys())[:20]
        if "count" in payload:
            summary["count"] = payload.get("count")
        return summary
    return {"type": type(payload).__name__}


def _probe(session: requests.Session, label: str, path: str) -> None:
    response = session.get(f"{BASE_URL}{path}", timeout=60)
    print(f"\n{label}: HTTP {response.status_code}")
    if response.status_code != 200:
        print("Request failed; response body redacted")
        return
    print(_summarize_payload(response.json()))


def main() -> int:
    try:
        session = _login()
        _probe(session, "operators", "/operators?limit=5&offset=0")
        _probe(session, "datasets", "/datasets?limit=5&offset=0")
        _probe(session, "data-fields", "/data-fields?limit=5&offset=0")
        return 0
    except Exception as exc:
        print(f"ERROR: {redact_error_message(exc)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
