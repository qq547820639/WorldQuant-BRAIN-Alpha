"""Manual live API root and data-fields probe."""

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


def main() -> int:
    try:
        session = _login()
        fields_url = (
            f"{BASE_URL}/data-fields?limit=1&offset=0"
            "&instrumentType=EQUITY&region=USA&delay=1&universe=TOP3000"
        )
        response = session.get(fields_url, timeout=60)
        print(f"data-fields status: {response.status_code}")
        if response.status_code == 200:
            payload = response.json()
            print(f"field count: {payload.get('count', 'N/A')}; page size: {len(payload.get('results', []))}")
        else:
            print("data-fields response body redacted")

        root = session.get(f"{BASE_URL}/", timeout=60)
        print(f"root status: {root.status_code}; body redacted")
        return 0 if response.status_code == 200 else 1
    except Exception as exc:
        print(f"ERROR: {redact_error_message(exc)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
