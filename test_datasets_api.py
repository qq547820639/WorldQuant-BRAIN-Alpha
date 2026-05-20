"""Manual live datasets endpoint probe."""

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
    return session


def _summarize(response: requests.Response) -> None:
    print(f"status: {response.status_code}")
    if response.status_code != 200:
        print("response body redacted")
        return
    payload = response.json()
    if isinstance(payload, list):
        print(f"list length: {len(payload)}")
    elif isinstance(payload, dict):
        print(f"keys: {sorted(payload.keys())[:20]}")
        if isinstance(payload.get("results"), list):
            print(f"results length: {len(payload['results'])}")
    else:
        print(f"payload type: {type(payload).__name__}")


def main() -> int:
    endpoints = [
        "/data/datasets?limit=5",
        "/datasets",
        "/data-fields?limit=1",
    ]
    try:
        session = _login()
        for endpoint in endpoints:
            print(f"\nProbe: {endpoint}")
            _summarize(session.get(f"{BASE_URL}{endpoint}", timeout=60))
        return 0
    except Exception as exc:
        print(f"ERROR: {redact_error_message(exc)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
