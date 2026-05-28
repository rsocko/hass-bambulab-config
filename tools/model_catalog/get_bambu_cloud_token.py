#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import getpass
import json
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any


DEFAULT_BASE_URL = "https://api.bambulab.com"
LOGIN_PATH = "/v1/user-service/user/login"
VERIFY_PATH = "/v1/design-user-service/my/preference"
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://makerworld.com",
    "Referer": "https://makerworld.com/",
    # The Bambu API is fronted by Cloudflare. Python's default urllib
    # fingerprint is blocked here, so send a stable app-like client profile.
    "User-Agent": "BambuHandy/3.0.1 (Android 14; Pixel 8)",
}


def _json_request(
    *,
    url: str,
    method: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> tuple[int, Any]:
    request_headers = dict(DEFAULT_HEADERS)
    if headers:
        request_headers.update(headers)

    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=body, method=method.upper(), headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return int(response.status), json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload_obj = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            payload_obj = raw
        return int(exc.code), payload_obj


def _decode_jwt_expiry(access_token: str) -> datetime | None:
    parts = access_token.split(".")
    if len(parts) != 3:
        return None

    payload_segment = parts[1]
    padding = "=" * (-len(payload_segment) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload_segment + padding)
        payload = json.loads(decoded.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None

    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        return None
    return datetime.fromtimestamp(float(exp), tz=UTC)


def _prompt_login_payload() -> dict[str, str]:
    print("Bambu Cloud login")
    account = input("Email: ").strip()
    if not account:
        raise ValueError("Email is required")

    login_mode = input("Login with password or verification code? [password/code] (default: password): ").strip().lower()
    if login_mode in {"", "password", "p"}:
        password = getpass.getpass("Password: ")
        if not password:
            raise ValueError("Password is required")
        return {"account": account, "password": password}

    if login_mode in {"code", "c", "verification", "verification-code"}:
        code = getpass.getpass("Verification code: ")
        if not code:
            raise ValueError("Verification code is required")
        return {"account": account, "code": code}

    raise ValueError(f"Unsupported login mode: {login_mode}")


def _format_expiry(*, expires_in: int | None, jwt_expiry: datetime | None) -> str:
    lines: list[str] = []
    if isinstance(expires_in, int) and expires_in > 0:
        approx_expiry = datetime.now(tz=UTC) + timedelta(seconds=expires_in)
        lines.append(f"API expiresIn: {expires_in} seconds (~ until {approx_expiry.isoformat()})")
    if jwt_expiry is not None:
        lines.append(f"JWT exp claim: {jwt_expiry.isoformat()}")
    return "\n".join(lines)


def _maybe_complete_verify_code_login(
    *,
    login_url: str,
    account: str,
    status: int,
    response: Any,
) -> tuple[int, Any]:
    if status != 200 or not isinstance(response, dict):
        return status, response

    login_type = str(response.get("loginType") or "").strip()
    access_token = str(response.get("accessToken") or "").strip()
    if access_token or login_type != "verifyCode":
        return status, response

    tfa_key = str(response.get("tfaKey") or "").strip()
    print("\nBambu accepted the password login, but this account requires a verification code before issuing a token.")
    print("Check your Bambu sign-in channel for the one-time code, then enter it below.")
    if tfa_key:
        print(f"Server returned tfaKey: {tfa_key}")

    code = getpass.getpass("Verification code (leave blank to abort): ").strip()
    if not code:
        return status, response

    print("Retrying login with verification code...")
    return _json_request(
        url=login_url,
        method="POST",
        payload={"account": account, "code": code},
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Interactively log in to Bambu Cloud and print the MakerWorld Bearer token for model-catalog setup."
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Bambu Cloud API base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip the follow-up /design-user-service/my/preference verification call.",
    )
    args = parser.parse_args(argv)

    base_url = args.base_url.rstrip("/")
    login_url = f"{base_url}{LOGIN_PATH}"
    verify_url = f"{base_url}{VERIFY_PATH}"

    try:
        payload = _prompt_login_payload()
    except ValueError as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2

    print("\nRequesting Bambu Cloud token...")
    status, response = _json_request(url=login_url, method="POST", payload=payload)
    status, response = _maybe_complete_verify_code_login(
        login_url=login_url,
        account=str(payload.get("account") or "").strip(),
        status=status,
        response=response,
    )

    if status != 200 or not isinstance(response, dict):
        print(f"Login failed: HTTP {status}", file=sys.stderr)
        if response is not None:
            print(json.dumps(response, indent=2, sort_keys=True), file=sys.stderr)
        return 1

    access_token = str(response.get("accessToken") or "").strip()
    refresh_token = str(response.get("refreshToken") or "").strip()
    login_type = str(response.get("loginType") or "").strip() or "password"
    expires_in_raw = response.get("expiresIn")
    expires_in = int(expires_in_raw) if isinstance(expires_in_raw, (int, float)) else None

    if not access_token:
        login_type_hint = str(response.get("loginType") or "").strip()
        if login_type_hint == "verifyCode":
            print("Login did not return an accessToken because the account still requires verification-code completion.", file=sys.stderr)
        else:
            print("Login succeeded but no accessToken was returned.", file=sys.stderr)
        print(json.dumps(response, indent=2, sort_keys=True), file=sys.stderr)
        return 1

    print("Login succeeded.")
    print(f"Login type: {login_type}")
    if refresh_token:
        print(f"Refresh token matches access token: {refresh_token == access_token}")

    jwt_expiry = _decode_jwt_expiry(access_token)
    expiry_text = _format_expiry(expires_in=expires_in, jwt_expiry=jwt_expiry)
    if expiry_text:
        print(expiry_text)

    if not args.skip_verify:
        print("\nVerifying token with /design-user-service/my/preference...")
        verify_status, verify_response = _json_request(
            url=verify_url,
            method="GET",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if verify_status != 200 or not isinstance(verify_response, dict):
            print(f"Verification failed: HTTP {verify_status}", file=sys.stderr)
            if verify_response is not None:
                print(json.dumps(verify_response, indent=2, sort_keys=True), file=sys.stderr)
            return 1

        handle = str(verify_response.get("handle") or "").strip()
        name = str(verify_response.get("name") or "").strip()
        uid = verify_response.get("uid")
        print(f"Verified profile: name={name or '<unknown>'} handle={handle or '<unknown>'} uid={uid}")

    print("\nUse this on the model-catalog host:")
    print(f"MODEL_CATALOG_MAKERWORLD_AUTH_TOKEN={access_token}")
    print("\nKeep this token out of shell history, chat logs, and committed files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))