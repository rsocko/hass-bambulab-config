#!/usr/bin/env python3
"""Export ha-bambulab printer cache files from Home Assistant over SSH."""

from __future__ import annotations

import argparse
import shutil
import tarfile
import tempfile
from pathlib import Path
from shlex import quote

import paramiko


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export ha-bambulab cache files from Home Assistant over SSH.")
    parser.add_argument("--host", required=True, help="Home Assistant host or IP address")
    parser.add_argument("--username", required=True, help="SSH username")
    parser.add_argument("--password", required=True, help="SSH password")
    parser.add_argument(
        "--remote-root",
        required=True,
        help="Remote directory to export, for example /config/www/media/ha-bambulab/<printer>/prints",
    )
    parser.add_argument("--output-root", required=True, help="Local directory where the export should be extracted")
    parser.add_argument("--port", type=int, default=22, help="SSH port. Defaults to 22.")
    parser.add_argument("--timeout", type=int, default=30, help="SSH connect timeout in seconds. Defaults to 30.")
    parser.add_argument(
        "--clear-output",
        action="store_true",
        help="Delete the output directory first if it already exists.",
    )
    return parser.parse_args()


def connect(args: argparse.Namespace) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        args.host,
        port=args.port,
        username=args.username,
        password=args.password,
        look_for_keys=False,
        allow_agent=False,
        timeout=args.timeout,
    )
    return client


def run_command(client: paramiko.SSHClient, command: str) -> tuple[int, str, str]:
    stdin, stdout, stderr = client.exec_command(command)
    exit_status = stdout.channel.recv_exit_status()
    return exit_status, stdout.read().decode("utf-8", errors="replace"), stderr.read().decode("utf-8", errors="replace")


def ensure_remote_root(client: paramiko.SSHClient, remote_root: str) -> tuple[int, int]:
    command = (
        "sh -lc "
        + quote(
            f"test -d {quote(remote_root)} && "
            f"find {quote(remote_root)} -type f | wc -l && "
            f"find {quote(remote_root)} -type d | wc -l"
        )
    )
    exit_status, stdout_text, stderr_text = run_command(client, command)
    if exit_status != 0:
        detail = stderr_text.strip() or stdout_text.strip() or f"exit status {exit_status}"
        raise RuntimeError(f"Remote path check failed for {remote_root}: {detail}")

    lines = [line.strip() for line in stdout_text.splitlines() if line.strip()]
    if len(lines) < 2:
        raise RuntimeError(f"Unexpected remote path check output for {remote_root}: {stdout_text!r}")

    return int(lines[0]), int(lines[1])


def export_tar_stream(client: paramiko.SSHClient, remote_root: str, tar_path: Path) -> None:
    command = "tar -C {root} -cf - .".format(root=quote(remote_root))
    stdin, stdout, stderr = client.exec_command(command)
    with tar_path.open("wb") as handle:
        shutil.copyfileobj(stdout, handle)
    exit_status = stdout.channel.recv_exit_status()
    stderr_text = stderr.read().decode("utf-8", errors="replace")
    if exit_status != 0:
        detail = stderr_text.strip() or f"exit status {exit_status}"
        raise RuntimeError(f"Remote tar export failed: {detail}")


def extract_tarball(tar_path: Path, output_root: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path) as archive:
        archive.extractall(output_root)


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_root).resolve()
    if output_root.exists() and args.clear_output:
        shutil.rmtree(output_root)
    elif output_root.exists() and any(output_root.iterdir()):
        raise SystemExit(f"Output directory is not empty: {output_root}. Use --clear-output to replace it.")

    client = connect(args)
    try:
        file_count, directory_count = ensure_remote_root(client, args.remote_root)
        with tempfile.TemporaryDirectory(prefix="ha-bambulab-export-") as temp_dir:
            tar_path = Path(temp_dir) / "ha_bambulab_cache_export.tar"
            export_tar_stream(client, args.remote_root, tar_path)
            extract_tarball(tar_path, output_root)
    finally:
        client.close()

    print(f"Exported {file_count} files across {directory_count} directories from {args.remote_root}")
    print(f"Local output: {output_root}")


if __name__ == "__main__":
    main()