"""Small manual authentication probe for WorldQuant BRAIN.

This script is intentionally not part of the pytest suite. It requires live
credentials in environment variables and prints only redacted diagnostics.
"""

from __future__ import annotations

import base64
import os

import requests

from brain_alpha_ops.redaction import redact_error_message


BASE_URL = "https://api.worldquantbrain.com"


def _credentials() -> tuple[str, str]:
    username = os.getenv("BRAIN_USERNAME", "")
    password = os.getenv("BRAIN_PASSWORD", "")
    if not username or not password:
        raise RuntimeError("BRAIN_USERNAME / BRAIN_PASSWORD environment variables are required")
    return username, password


def _basic_auth_header(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {
        "Content-Type": "application/json",
        "Authorization": f"Basic {token}",
    }


def main() -> int:
    try:
        username, password = _credentials()
        print("Authenticating against WorldQuant BRAIN...")
        response = requests.post(
            f"{BASE_URL}/authentication",
            headers=_basic_auth_header(username, password),
            timeout=30,
        )
        print(f"Authentication status: {response.status_code}")
        if response.status_code not in {200, 201}:
            print("Authentication failed")
            return 1

        auth_data = response.json()
        access_token = auth_data.get("token") or auth_data.get("access_token") or ""
        print(f"Token returned: {'yes (redacted)' if access_token else 'no'}")
        print(f"Cookie returned: {'yes (redacted)' if response.cookies else 'no'}")

        fields_url = (
            f"{BASE_URL}/data-fields?limit=5&offset=0"
            "&instrumentType=EQUITY&region=USA&delay=1&universe=TOP3000"
        )
        if access_token:
            probe = requests.get(fields_url, headers={"Authorization": f"Bearer {access_token}"}, timeout=30)
            print(f"Bearer data-fields probe status: {probe.status_code}")
            if probe.status_code != 401:
                return 0

        session = requests.Session()
        session.cookies.update(response.cookies)
        probe = session.get(fields_url, timeout=30)
        print(f"Cookie data-fields probe status: {probe.status_code}")
        return 0 if probe.status_code == 200 else 1
    except Exception as exc:
        print(f"ERROR: {redact_error_message(exc)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
