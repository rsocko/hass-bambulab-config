#!/usr/bin/env python3
"""Queue a selected Windows Explorer file into model catalog intake for StreamDeck."""

from __future__ import annotations

import argparse
import base64
import json
import json as json_module
import os
import subprocess
import sys
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Sequence

SUPPORTED_FILE_EXTENSIONS = {
    ".3mf",
    ".gif",
    ".jpeg",
    ".jpg",
    ".obj",
    ".png",
    ".step",
    ".stl",
    ".stp",
    ".svg",
    ".webp",
    ".zip",
}


class StreamDeckUploadError(RuntimeError):
    """Base error for the StreamDeck uploader."""


class SelectionError(StreamDeckUploadError):
    """Raised when Explorer selection resolution fails."""


class UploadError(StreamDeckUploadError):
    """Raised when sidecar upload fails."""


@dataclass(frozen=True)
class ResolverResult:
    selected_path: Path
    window_title: str | None


class StdlibResponse:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text

    def json(self) -> dict[str, Any]:
        payload = json.loads(self.text or "{}")
        if not isinstance(payload, dict):
            raise ValueError("response payload is not a JSON object")
        return payload


class StdlibSession:
    def post(self, url: str, json: dict[str, Any], timeout: float) -> StdlibResponse:
        payload_bytes = json_module.dumps(json).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload_bytes,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
                return StdlibResponse(int(getattr(response, "status", 200)), body)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return StdlibResponse(int(exc.code), body)
        except urllib.error.URLError as exc:
            raise OSError(str(exc.reason or exc)) from exc

    def close(self) -> None:
        return None


def build_http_session() -> StdlibSession:
    return StdlibSession()


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def build_action_id() -> str:
    return f"streamdeck-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"


def default_log_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return Path(local_app_data) / "hass-bambulab-config" / "model-catalog-streamdeck" / "logs"
    return Path.cwd() / ".streamdeck-logs"


def resolver_script_path() -> Path:
    return Path(__file__).with_name("resolve_explorer_selection.ps1")


def parse_resolver_output(stdout: str, stderr: str = "") -> ResolverResult:
    raw_output = (stdout or "").strip()
    if not raw_output:
        raise SelectionError(f"Explorer resolver returned no output. {stderr.strip()}".strip())

    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise SelectionError(f"Explorer resolver returned invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise SelectionError("Explorer resolver returned an invalid payload shape.")

    if not payload.get("ok"):
        message = str(payload.get("error") or "Explorer selection could not be resolved.").strip()
        raise SelectionError(message)

    selected_paths = payload.get("selected_paths") or []
    if not isinstance(selected_paths, list):
        raise SelectionError("Explorer resolver returned an invalid selected_paths value.")
    if len(selected_paths) != 1:
        raise SelectionError(
            "StreamDeck MVP requires exactly one selected file in the focused Explorer window."
        )

    selected_path = Path(str(selected_paths[0])).expanduser().resolve()
    return ResolverResult(
        selected_path=selected_path,
        window_title=str(payload.get("window_title") or "").strip() or None,
    )


def resolve_selected_path(
    *,
    override_path: str | None,
    powershell_executable: str,
    script_path: Path | None = None,
    runner: Any | None = None,
) -> ResolverResult:
    if override_path:
        return ResolverResult(
            selected_path=Path(override_path).expanduser().resolve(),
            window_title=None,
        )

    runner = runner or subprocess.run
    script = (script_path or resolver_script_path()).resolve()
    completed = runner(
        [
            powershell_executable,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        raise SelectionError(f"Explorer resolver failed with exit code {completed.returncode}. {stderr}".strip())

    return parse_resolver_output(completed.stdout or "", completed.stderr or "")


def validate_selected_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise SelectionError(f"Selected path does not exist: {resolved}")
    if not resolved.is_file():
        raise SelectionError(f"Selected path is not a file: {resolved}")
    if resolved.suffix.lower() not in SUPPORTED_FILE_EXTENSIONS:
        raise SelectionError(
            "Unsupported file extension for StreamDeck intake: "
            f"{resolved.suffix.lower() or '<none>'}"
        )
    return resolved


def build_browser_payload(path: Path, *, cleanup_policy: str, idempotency_key: str | None = None) -> dict[str, Any]:
    encoded_content = base64.b64encode(path.read_bytes()).decode("ascii")
    payload: dict[str, Any] = {
        "browser_files": [
            {
                "filename": path.name,
                "relative_path": path.name,
                "content_base64": encoded_content,
            }
        ],
        "cleanup_policy": cleanup_policy,
    }
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key
    return payload


def summarize_error_response(response: Any) -> str:
    try:
        payload = response.json()
    except Exception:
        text = response.text.strip()
        return text or f"HTTP {response.status_code}"

    if isinstance(payload, dict):
        message = str(payload.get("message") or payload.get("error") or "").strip()
        if message:
            return message
    return f"HTTP {response.status_code}"


def upload_queue_only(
    path: Path,
    *,
    base_url: str,
    timeout_seconds: float,
    cleanup_policy: str,
    idempotency_key: str | None = None,
    session: Any | None = None,
) -> dict[str, Any]:
    payload = build_browser_payload(
        path,
        cleanup_policy=cleanup_policy,
        idempotency_key=idempotency_key,
    )
    session = session or build_http_session()
    endpoint = f"{base_url.rstrip('/')}/api/intake/uploads/browser"

    try:
        response = session.post(endpoint, json=payload, timeout=timeout_seconds)
    except Exception as exc:
        raise UploadError(f"Queue upload request failed: {exc}") from exc

    if response.status_code != 200:
        raise UploadError(summarize_error_response(response))

    try:
        response_payload = response.json()
    except ValueError as exc:
        raise UploadError("Queue upload returned invalid JSON.") from exc

    upload_id = str(response_payload.get("upload_id") or "").strip()
    if not response_payload.get("success") or not upload_id:
        raise UploadError("Queue upload did not return a valid upload_id.")

    return response_payload


def write_log_record(log_dir: Path, record: dict[str, Any]) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"streamdeck-uploader-{datetime.now(UTC).strftime('%Y-%m-%d')}.jsonl"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return log_path


def render_success(result: dict[str, Any], *, action_id: str, selected_path: Path, log_path: Path, output: str) -> str:
    payload = {
        "ok": True,
        "state": str(result.get("status") or "queued"),
        "action_id": action_id,
        "upload_id": str(result.get("upload_id") or ""),
        "selected_path": str(selected_path),
        "warning_count": len(result.get("warnings") or []),
        "log_path": str(log_path),
    }
    if output == "json":
        return json.dumps(payload, sort_keys=True)
    warning_suffix = ""
    if payload["warning_count"]:
        warning_suffix = f" warnings={payload['warning_count']}"
    return (
        f"QUEUED upload_id={payload['upload_id']}"
        f" file={selected_path.name}{warning_suffix}"
        f" log={log_path}"
    )


def render_failure(message: str, *, action_id: str, log_path: Path | None, output: str) -> str:
    payload = {
        "ok": False,
        "state": "failed",
        "action_id": action_id,
        "message": message,
        "log_path": str(log_path) if log_path else None,
    }
    if output == "json":
        return json.dumps(payload, sort_keys=True)
    log_suffix = f" log={log_path}" if log_path else ""
    return f"FAILED message={message}{log_suffix}"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Queue the selected Explorer file into model catalog intake for StreamDeck.",
    )
    parser.add_argument("--base-url", required=True, help="Model catalog sidecar base URL")
    parser.add_argument(
        "--path",
        help="Override Explorer selection with an explicit local file path.",
    )
    parser.add_argument(
        "--powershell-executable",
        default="powershell",
        help="PowerShell executable used for Explorer selection resolution.",
    )
    parser.add_argument(
        "--resolver-script",
        help="Optional path to the PowerShell resolver script.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds for the queue request.",
    )
    parser.add_argument(
        "--cleanup-policy",
        default="delete_on_verified",
        help="Cleanup policy to send with the queue request.",
    )
    parser.add_argument(
        "--idempotency-key",
        help="Optional idempotency key for deterministic replay.",
    )
    parser.add_argument(
        "--log-dir",
        help="Directory for structured JSONL invocation logs.",
    )
    parser.add_argument(
        "--output",
        choices=("text", "json"),
        default="text",
        help="Terminal output format.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    action_id = build_action_id()
    log_dir = Path(args.log_dir).expanduser().resolve() if args.log_dir else default_log_dir().resolve()
    request_started = perf_counter()
    selected_path: Path | None = None
    log_path: Path | None = None
    session = build_http_session()

    try:
        resolved_selection = resolve_selected_path(
            override_path=args.path,
            powershell_executable=args.powershell_executable,
            script_path=Path(args.resolver_script).expanduser().resolve() if args.resolver_script else None,
        )
        selected_path = validate_selected_path(resolved_selection.selected_path)
        response_payload = upload_queue_only(
            selected_path,
            base_url=args.base_url,
            timeout_seconds=args.timeout_seconds,
            cleanup_policy=args.cleanup_policy,
            idempotency_key=args.idempotency_key,
            session=session,
        )
        log_record = {
            "action_id": action_id,
            "timestamp": utc_now_iso(),
            "selected_path": str(selected_path),
            "selected_file_size_bytes": selected_path.stat().st_size,
            "base_url": args.base_url.rstrip("/"),
            "cleanup_policy": args.cleanup_policy,
            "mode": "queue",
            "status": str(response_payload.get("status") or "queued"),
            "success": True,
            "upload_id": str(response_payload.get("upload_id") or ""),
            "warning_count": len(response_payload.get("warnings") or []),
            "latency_ms": round((perf_counter() - request_started) * 1000, 3),
        }
        log_path = write_log_record(log_dir, log_record)
        print(
            render_success(
                response_payload,
                action_id=action_id,
                selected_path=selected_path,
                log_path=log_path,
                output=args.output,
            )
        )
        return 0
    except StreamDeckUploadError as exc:
        log_record = {
            "action_id": action_id,
            "timestamp": utc_now_iso(),
            "selected_path": str(selected_path) if selected_path else None,
            "base_url": args.base_url.rstrip("/"),
            "cleanup_policy": args.cleanup_policy,
            "mode": "queue",
            "success": False,
            "error": str(exc),
            "latency_ms": round((perf_counter() - request_started) * 1000, 3),
        }
        log_path = write_log_record(log_dir, log_record)
        print(
            render_failure(
                str(exc),
                action_id=action_id,
                log_path=log_path,
                output=args.output,
            ),
            file=sys.stderr,
        )
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
