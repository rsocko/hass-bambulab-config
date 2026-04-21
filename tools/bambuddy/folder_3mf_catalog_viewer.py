#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import tempfile
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from tools.bambuddy.folder_3mf_catalog_state import CatalogStateStore, load_json, merge_manifest_with_state
from tools.bambuddy.run_folder_3mf_catalog_import import run_catalog_import


class CatalogDataset:
    def __init__(self, manifest_path: Path, state_path: Path | None = None) -> None:
        self.manifest_path = manifest_path
        self.state_path = state_path
        self.state_store = CatalogStateStore(state_path) if state_path is not None else None
        self.reload()

    @property
    def write_enabled(self) -> bool:
        return self.state_store is not None

    def reload(self) -> None:
        manifest = load_json(self.manifest_path)
        state_payload = self.state_store.export_payload() if self.state_store is not None else {"entries": []}
        self.payload = merge_manifest_with_state(manifest, state_payload)
        self.records = [row for row in self.payload.get("candidates", []) if isinstance(row, dict)]
        self.record_map = {str(row.get("record_id") or ""): row for row in self.records}
        self.summary = dict((self.payload.get("summary") or {}))

    def filtered_records(self, view: str) -> list[dict[str, Any]]:
        if view == "all":
            return self.records
        return [row for row in self.records if str(row.get("reconciliation_status") or "") == view or str(row.get("file_status") or "") == view]

    def update_state(self, record_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        if self.state_store is None:
            raise ValueError("Viewer is read-only because no state file was configured.")
        self.state_store.patch(record_id, updates)
        self.reload()
        record = self.record_map.get(record_id)
        if record is None:
            raise ValueError("Unknown record id.")
        return record

    def run_queue_action(
        self,
        action: str,
        *,
        synthetic_manifest_path: str | None = None,
        base_url: str | None = None,
        printer_id: int | None = None,
        api_key: str | None = None,
        backfill_action: str = "Full",
        confirmed: bool = False,
    ) -> dict[str, Any]:
        if self.state_path is None:
            raise ValueError("Queue actions require a configured state file.")
        if action not in {"inspect", "dry-run", "run-backfill"}:
            raise ValueError("Unsupported queue action.")
        resolved_manifest_path: Path | None = None
        if synthetic_manifest_path:
            resolved_manifest_path = Path(synthetic_manifest_path).expanduser().resolve()
        elif action in {"dry-run", "run-backfill"}:
            resolved_manifest_path = Path(tempfile.gettempdir()) / f"folder_catalog_viewer_{action}_{Path(self.manifest_path).stem}.json"
        if action == "run-backfill" and not confirmed:
            raise ValueError("Run-backfill requires explicit confirmation.")
        payload = run_catalog_import(
            manifest_path=self.manifest_path,
            state_path=self.state_path,
            action=action,
            synthetic_manifest_path=resolved_manifest_path,
            base_url=base_url,
            printer_id=printer_id,
            api_key=api_key,
            backfill_action=backfill_action,
            write_back_results=action == "run-backfill",
        )
        self.reload()
        return payload


def parse_csv_list(value: object) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def parse_optional_int(value: object) -> int | None:
    text = str(value or "").strip()
    return int(text) if text else None


def render_runner_actions(write_enabled: bool) -> str:
        if not write_enabled:
                return ""
        return """
<section class=\"section\">
    <h3>Queue Actions</h3>
    <p class="section-copy">Run inspect, dry-run, or a confirmed backfill from the browser. Dry-run and backfill can use a custom synthetic manifest path outside the scanned source tree.</p>
    <div class="runner-controls">
        <label>Synthetic Manifest Path<input id="runner-synthetic-manifest-path" placeholder="Optional custom path for dry-run or run-backfill output" /></label>
        <label>Base URL<input id="runner-base-url" placeholder="Required for run-backfill, e.g. http://bambuddy.local" /></label>
        <label>Printer ID<input id="runner-printer-id" placeholder="Required for run-backfill" /></label>
        <label>API Key<input id="runner-api-key" placeholder="Optional Bambuddy API key" /></label>
        <label>Backfill Action<select id="runner-backfill-action"><option value="Full">Full</option><option value="Upload">Upload</option><option value="Inspect">Inspect</option></select></label>
        <label>Confirmation Phrase<input id="runner-confirmation" placeholder="Type RUN-BACKFILL to enable browser execution" /></label>
    </div>
    <div class="action-row">
        <button type="button" class="runner-action" data-action="inspect">Inspect Queue</button>
        <button type="button" class="runner-action" data-action="dry-run">Dry Run</button>
        <button type="button" class="runner-action warn" data-action="run-backfill">Run Backfill</button>
    </div>
    <pre id="runner-result" class="runner-result">No queue action run yet.</pre>
</section>
"""


def render_editor(record: dict[str, Any], view: str, write_enabled: bool) -> str:
    if not write_enabled:
        return '<section class="section"><div class="empty">Open the viewer with --state to enable edits.</div></section>'
    state = record.get("state") or {}
    export_workflow = state.get("export_workflow") or {}
    import_plan = state.get("import_plan") or {}
    selected_archive = state.get("selected_archive_id") or record.get("selected_archive_id") or ""
    manual_tags = ", ".join(state.get("manual_tags") or [])
    return f"""
<section class="section">
  <h3>Catalog State</h3>
  <form class="editor-form" data-endpoint="/api/state" data-view="{html.escape(view)}" data-record-id="{html.escape(str(record.get('record_id') or ''))}">
    <label>Disposition<select name="disposition"><option value="">Unspecified</option><option value="Keep" {'selected' if state.get('disposition') == 'Keep' else ''}>Keep</option><option value="Investigate" {'selected' if state.get('disposition') == 'Investigate' else ''}>Investigate</option><option value="Skip" {'selected' if state.get('disposition') == 'Skip' else ''}>Skip</option></select></label>
    <label>Selected Archive ID<input name="selected_archive_id" value="{html.escape(str(selected_archive))}" /></label>
    <label>Manual Tags<input name="manual_tags" value="{html.escape(manual_tags)}" /></label>
    <label>Operator Note<textarea name="operator_note">{html.escape(str(state.get('operator_note') or ''))}</textarea></label>
    <label>Export Status<select name="export_status"><option value="">Not needed</option><option value="needs_export" {'selected' if export_workflow.get('status') == 'needs_export' else ''}>Needs export</option><option value="opened_in_studio" {'selected' if export_workflow.get('status') == 'opened_in_studio' else ''}>Opened in Studio</option><option value="export_in_progress" {'selected' if export_workflow.get('status') == 'export_in_progress' else ''}>Export in progress</option><option value="export_waiting_for_pickup" {'selected' if export_workflow.get('status') == 'export_waiting_for_pickup' else ''}>Waiting for pickup</option><option value="export_verified" {'selected' if export_workflow.get('status') == 'export_verified' else ''}>Export verified</option><option value="blocked" {'selected' if export_workflow.get('status') == 'blocked' else ''}>Blocked</option></select></label>
    <label>Target Export Folder<input name="target_export_folder" value="{html.escape(str(export_workflow.get('target_export_folder') or ''))}" /></label>
    <label>Target Export Filename<input name="target_export_filename" value="{html.escape(str(export_workflow.get('target_export_filename') or ''))}" /></label>
    <label>Blocked Reason<input name="blocked_reason" value="{html.escape(str(export_workflow.get('blocked_reason') or ''))}" /></label>
    <button type="submit">Save state</button>
  </form>
</section>
<section class="section">
  <h3>Import Plan</h3>
  <form class="editor-form" data-endpoint="/api/import-plan" data-view="{html.escape(view)}" data-record-id="{html.escape(str(record.get('record_id') or ''))}">
    <label>Mode<select name="mode"><option value="undecided" {'selected' if import_plan.get('mode') in (None, 'undecided') else ''}>Undecided</option><option value="create_archive_upload" {'selected' if import_plan.get('mode') == 'create_archive_upload' else ''}>Create archive upload</option><option value="attach_source_only" {'selected' if import_plan.get('mode') == 'attach_source_only' else ''}>Attach source only</option></select></label>
    <label>Inferred Started At<input name="inferred_started_at" value="{html.escape(str(import_plan.get('inferred_started_at') or record.get('best_inferred_print_time') or ''))}" /></label>
    <label>Override Started At<input name="override_started_at" value="{html.escape(str(import_plan.get('override_started_at') or ''))}" /></label>
    <label>Inferred Completed At<input name="inferred_completed_at" value="{html.escape(str(import_plan.get('inferred_completed_at') or ''))}" /></label>
    <label>Override Completed At<input name="override_completed_at" value="{html.escape(str(import_plan.get('override_completed_at') or ''))}" /></label>
    <label>Provenance Mode<select name="provenance_tag_mode"><option value="tags_and_notes" {'selected' if import_plan.get('provenance_tag_mode') in (None, '', 'tags_and_notes') else ''}>Tags and notes</option><option value="notes_only" {'selected' if import_plan.get('provenance_tag_mode') == 'notes_only' else ''}>Notes only</option><option value="none" {'selected' if import_plan.get('provenance_tag_mode') == 'none' else ''}>None</option></select></label>
    <label>Missing Requirements<input name="missing_requirements" value="{html.escape(', '.join(import_plan.get('missing_requirements') or []))}" /></label>
    <label>Plan Notes<textarea name="notes">{html.escape(str(import_plan.get('notes') or ''))}</textarea></label>
    <button type="submit">Save import plan</button>
  </form>
</section>"""


def render_list_item(record: dict[str, Any], view: str, selected_id: str | None) -> str:
    href = "/?" + urlencode({"view": view, "selected": str(record.get("record_id") or "")})
    badges = [
        f'<span class="badge emphasis">{html.escape(str(record.get("primary_artifact_kind") or "unknown"))}</span>',
        f'<span class="badge">{html.escape(str(record.get("file_status") or "unknown"))}</span>',
        f'<span class="badge warn">{html.escape(str(record.get("reconciliation_status") or "not_reconciled"))}</span>',
    ]
    if (record.get("state") or {}).get("disposition"):
        badges.append(f'<span class="badge keep">{html.escape(str((record.get("state") or {}).get("disposition")))}</span>')
    return (
        f'<a class="record {"active" if str(record.get("record_id") or "") == selected_id else ""}" href="{href}">'
        f'<div class="record-name">{html.escape(str(record.get("relative_path") or ""))}</div>'
        f'<div class="badges">{"".join(badges)}</div>'
        '</a>'
    )


def render_detail(record: dict[str, Any] | None, view: str, write_enabled: bool) -> str:
    if record is None:
        return '<div class="panel empty">No matching record.</div>'
    state = record.get("state") or {}
    metadata = [
        ("Relative Path", str(record.get("relative_path") or "")),
        ("File Status", str(record.get("file_status") or "")),
        ("Artifact Kind", str(record.get("primary_artifact_kind") or "")),
        ("Archive Ready", str(bool(record.get("canonical_archive_ready")))),
        ("Reconciliation", str(record.get("reconciliation_status") or "")),
        ("Best Inferred Print Time", str(record.get("best_inferred_print_time") or "")),
        ("Selected Archive", str(record.get("selected_archive_id") or state.get("selected_archive_id") or "")),
        ("Disposition", str(state.get("disposition") or "")),
    ]
    meta_markup = "".join(
        f'<div class="meta"><div class="meta-label">{html.escape(label)}</div><div class="meta-value">{html.escape(value)}</div></div>'
        for label, value in metadata if value
    )
    support_markup = "".join(
        f'<li>{html.escape(str(row.get("relative_path") or row.get("path") or ""))} ({html.escape(str(row.get("extension") or ""))})</li>'
        for row in record.get("supporting_files") or []
    ) or '<li>No supporting files recorded.</li>'
    match_markup = "".join(f'<li>{html.escape(str(reason))}</li>' for reason in record.get("match_reasons") or []) or '<li>No match reasons recorded.</li>'
    export_workflow = state.get("export_workflow") or {}
    export_markup = "".join(
        f'<div class="meta"><div class="meta-label">{html.escape(label)}</div><div class="meta-value">{html.escape(str(value))}</div></div>'
        for label, value in [
            ("Export Status", export_workflow.get("status")),
            ("Target Folder", export_workflow.get("target_export_folder")),
            ("Target Filename", export_workflow.get("target_export_filename")),
            ("Exported Artifact", export_workflow.get("exported_artifact_path")),
            ("Blocked Reason", export_workflow.get("blocked_reason")),
        ] if value
    ) or '<div class="empty">No export workflow state recorded yet.</div>'
    editor_markup = render_editor(record, view, write_enabled)
    runner_markup = render_runner_actions(write_enabled)
    return f"""
<div class="panel">
  <h2>{html.escape(str(record.get('relative_path') or ''))}</h2>
  <div class="meta-grid">{meta_markup}</div>
  <section class="section"><h3>Match Reasons</h3><ul>{match_markup}</ul></section>
  <section class="section"><h3>Supporting Files</h3><ul>{support_markup}</ul></section>
    <section class="section"><h3>Export Workflow</h3><div class="meta-grid">{export_markup}</div></section>
    {runner_markup}
    {editor_markup}
  <section class="section"><h3>Full Candidate</h3><pre>{html.escape(json.dumps(record, indent=2, ensure_ascii=False))}</pre></section>
</div>"""


def render_page(dataset: CatalogDataset, view: str, selected_id: str | None) -> str:
    records = dataset.filtered_records(view)
    selected = dataset.record_map.get(selected_id or "")
    if selected not in records:
        selected = records[0] if records else None
    counts = dataset.summary.get("reconciliation_status_counts") or {}
    filters = [
        ("all", f"All ({len(dataset.records)})"),
        ("already_represented", f"Already represented ({counts.get('already_represented', 0)})"),
        ("likely_represented", f"Likely represented ({counts.get('likely_represented', 0)})"),
        ("ambiguous", f"Ambiguous ({counts.get('ambiguous', 0)})"),
        ("not_represented", f"Not represented ({counts.get('not_represented', 0)})"),
        ("needs_export", f"Needs export ({counts.get('needs_export', 0)})"),
        ("missing_on_rescan", f"Missing on rescan ({(dataset.summary.get('file_status_counts') or {}).get('missing_on_rescan', 0)})"),
        ("offline_onedrive", f"Offline OneDrive ({(dataset.summary.get('file_status_counts') or {}).get('offline_onedrive', 0)})"),
    ]
    filter_markup = "".join(
        f'<a class="filter {"active" if key == view else ""}" href="/?{urlencode({"view": key})}">{html.escape(label)}</a>'
        for key, label in filters
    )
    list_markup = "".join(render_list_item(record, view, str(selected.get("record_id") or "") if selected else None) for record in records) or '<div class="empty">No records for this filter.</div>'
    detail_markup = render_detail(selected, view, dataset.write_enabled)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Folder 3MF Catalog Viewer</title>
<style>
:root {{ color-scheme: light; --bg: #f3efe8; --panel: #fffaf2; --border: #d6c7b2; --ink: #2d2a26; --muted: #6c655c; --accent: #006d77; --accent-soft: #d7eceb; --warn: #b45309; --warn-soft: #fce7c7; --good-soft: #dbeee2; --good: #1d6f42; }}
* {{ box-sizing: border-box; }} body {{ margin:0; font-family:"Segoe UI", sans-serif; background: var(--bg); color: var(--ink); }}
.layout {{ display:grid; grid-template-columns: 360px 1fr; min-height:100vh; }} .sidebar {{ border-right:1px solid var(--border); background:rgba(255,250,242,0.92); padding:20px; overflow:auto; }} .content {{ padding:24px; overflow:auto; }}
.filters {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:16px; }} .filter {{ padding:8px 12px; border-radius:999px; text-decoration:none; color:var(--ink); background:#f8f0e2; }} .filter.active {{ background:var(--accent-soft); color:var(--accent); }}
.record-list {{ display:grid; gap:10px; }} .record {{ display:block; padding:12px 14px; border:1px solid var(--border); border-radius:14px; text-decoration:none; color:inherit; background:var(--panel); }} .record.active {{ border-color: var(--accent); box-shadow:0 0 0 2px rgba(0,109,119,0.12); }}
.record-name {{ font-weight:600; font-size:13px; line-height:1.35; margin-bottom:8px; word-break:break-word; }} .badges {{ display:flex; gap:6px; flex-wrap:wrap; }} .badge {{ font-size:11px; padding:4px 8px; border-radius:999px; background:#f8f0e2; color:var(--muted); }} .badge.emphasis {{ background:var(--accent-soft); color:var(--accent); }} .badge.warn {{ background:var(--warn-soft); color:var(--warn); }} .badge.keep {{ background:var(--good-soft); color:var(--good); }}
.panel {{ background:rgba(255,250,242,0.92); border:1px solid var(--border); border-radius:18px; padding:18px; }} .meta-grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:12px; margin:16px 0; }} .meta {{ background:var(--panel); border:1px solid var(--border); border-radius:14px; padding:12px; }} .meta-label {{ font-size:11px; text-transform:uppercase; letter-spacing:0.08em; color:var(--muted); margin-bottom:6px; }} .meta-value {{ font-weight:600; line-height:1.4; word-break:break-word; }}
.empty {{ color:var(--muted); padding:16px; border:1px dashed var(--border); border-radius:14px; }} pre {{ margin:0; white-space:pre-wrap; word-break:break-word; font-size:12px; line-height:1.5; background:#f5ede0; border-radius:14px; padding:14px; border:1px solid var(--border); }}
.editor-form {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:12px; }} .editor-form label, .runner-controls label {{ display:grid; gap:6px; font-size:12px; color:var(--muted); }} .editor-form input, .editor-form select, .editor-form textarea, .runner-controls input, .runner-controls select {{ width:100%; padding:10px 12px; border-radius:12px; border:1px solid var(--border); background:#fffdf9; color:var(--ink); font:inherit; }} .editor-form textarea {{ min-height:88px; resize:vertical; }} .editor-form button, .runner-action {{ width:max-content; padding:10px 16px; border:0; border-radius:999px; background:var(--accent); color:#fff; cursor:pointer; font-weight:600; }} .runner-action.warn {{ background:var(--warn); }} .flash {{ display:none; margin-bottom:16px; padding:12px 14px; border-radius:14px; background:var(--accent-soft); color:var(--accent); }} .flash.visible {{ display:block; }} .section-copy {{ color:var(--muted); margin:0 0 12px; }} .action-row {{ display:flex; gap:10px; flex-wrap:wrap; margin-bottom:12px; }} .runner-controls {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:12px; margin-bottom:12px; }} .runner-result {{ min-height:120px; }}
@media (max-width:1080px) {{ .layout {{ grid-template-columns:1fr; }} .sidebar {{ border-right:0; border-bottom:1px solid var(--border); }} }}
</style></head><body><div class="layout"><aside class="sidebar"><h1>Folder 3MF Catalog Viewer</h1><p>{'Editable state + import-plan viewer for the folder-driven historical archive catalog.' if dataset.write_enabled else 'Read-only viewer for the new folder-driven historical archive catalog.'}</p><div class="filters">{filter_markup}</div><div class="record-list">{list_markup}</div></aside><main class="content"><div id="flash" class="flash"></div>{detail_markup}</main></div><script>
async function postJson(url, payload) {{
    const response = await fetch(url, {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: JSON.stringify(payload) }});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Request failed');
    return data;
}}
for (const form of document.querySelectorAll('.editor-form')) {{
    form.addEventListener('submit', async (event) => {{
        event.preventDefault();
        const payload = Object.fromEntries(new FormData(form).entries());
        payload.record_id = form.dataset.recordId;
        try {{
            await postJson(form.dataset.endpoint, payload);
            const url = new URL(window.location.href);
            url.searchParams.set('view', form.dataset.view || 'all');
            url.searchParams.set('selected', form.dataset.recordId || '');
            window.location.href = url.toString();
        }} catch (error) {{
            const flash = document.getElementById('flash');
            flash.textContent = error.message;
            flash.classList.add('visible');
        }}
    }});
}}
for (const button of document.querySelectorAll('.runner-action')) {{
    button.addEventListener('click', async () => {{
        const flash = document.getElementById('flash');
        const result = document.getElementById('runner-result');
        const syntheticManifestPath = document.getElementById('runner-synthetic-manifest-path').value.trim();
        const baseUrl = document.getElementById('runner-base-url').value.trim();
        const printerId = document.getElementById('runner-printer-id').value.trim();
        const apiKey = document.getElementById('runner-api-key').value.trim();
        const backfillAction = document.getElementById('runner-backfill-action').value;
        const confirmation = document.getElementById('runner-confirmation').value.trim();
        flash.classList.remove('visible');
        result.textContent = 'Running ' + button.dataset.action + '...';
        try {{
            const data = await postJson('/api/runner', {{
                action: button.dataset.action,
                synthetic_manifest_path: syntheticManifestPath,
                base_url: baseUrl,
                printer_id: printerId,
                api_key: apiKey,
                backfill_action: backfillAction,
                confirmation_phrase: confirmation,
            }});
            result.textContent = JSON.stringify(data.payload, null, 2);
        }} catch (error) {{
            flash.textContent = error.message;
            flash.classList.add('visible');
            result.textContent = 'Queue action failed.';
        }}
    }});
}}
</script></body></html>"""


class CatalogHandler(BaseHTTPRequestHandler):
    dataset: CatalogDataset

    def send_text(self, status_code: int, content_type: str, body: bytes) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status_code: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_text(status_code, "application/json; charset=utf-8", body)

    def parse_payload(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        content_type = self.headers.get("Content-Type", "")
        if content_type.startswith("application/json"):
            return json.loads(raw_body.decode("utf-8")) if raw_body else {}
        values = parse_qs(raw_body.decode("utf-8"))
        return {key: values[key][0] if len(values[key]) == 1 else values[key] for key in values}

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        view = params.get("view", ["all"])[0]
        selected = params.get("selected", [None])[0]
        if parsed.path not in {"/", ""}:
            self.send_error(404, "Not found")
            return
        rendered = render_page(self.dataset, view, selected)
        body = rendered.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path not in {"/api/state", "/api/import-plan", "/api/runner"}:
            self.send_error(404, "Not found")
            return
        try:
            payload = self.parse_payload()
            if parsed.path == "/api/runner":
                result = self.dataset.run_queue_action(
                    str(payload.get("action") or "").strip(),
                    synthetic_manifest_path=str(payload.get("synthetic_manifest_path") or "").strip() or None,
                    base_url=str(payload.get("base_url") or "").strip() or None,
                    printer_id=parse_optional_int(payload.get("printer_id")),
                    api_key=str(payload.get("api_key") or "").strip() or None,
                    backfill_action=str(payload.get("backfill_action") or "Full").strip() or "Full",
                    confirmed=str(payload.get("confirmation_phrase") or "").strip() == "RUN-BACKFILL",
                )
                self.send_json(200, {"message": "Queue action complete.", "payload": result})
                return
            record_id = str(payload.get("record_id") or "").strip()
            if not record_id or record_id not in self.dataset.record_map:
                raise ValueError("Unknown record id.")
            if parsed.path == "/api/state":
                entry = self.dataset.update_state(
                    record_id,
                    {
                        "disposition": str(payload.get("disposition") or "").strip() or None,
                        "selected_archive_id": parse_optional_int(payload.get("selected_archive_id")),
                        "manual_tags": parse_csv_list(payload.get("manual_tags")),
                        "operator_note": str(payload.get("operator_note") or "").strip() or None,
                        "export_workflow": {
                            "status": str(payload.get("export_status") or "not_needed").strip() or "not_needed",
                            "target_export_folder": str(payload.get("target_export_folder") or "").strip() or None,
                            "target_export_filename": str(payload.get("target_export_filename") or "").strip() or None,
                            "blocked_reason": str(payload.get("blocked_reason") or "").strip() or None,
                        },
                    },
                )
                self.send_json(200, {"message": "Catalog state saved.", "entry": entry})
                return
            entry = self.dataset.update_state(
                record_id,
                {
                    "import_plan": {
                        "mode": str(payload.get("mode") or "undecided").strip() or "undecided",
                        "inferred_started_at": str(payload.get("inferred_started_at") or "").strip() or None,
                        "override_started_at": str(payload.get("override_started_at") or "").strip() or None,
                        "inferred_completed_at": str(payload.get("inferred_completed_at") or "").strip() or None,
                        "override_completed_at": str(payload.get("override_completed_at") or "").strip() or None,
                        "missing_requirements": parse_csv_list(payload.get("missing_requirements")),
                        "notes": str(payload.get("notes") or "").strip() or None,
                        "provenance_tag_mode": str(payload.get("provenance_tag_mode") or "tags_and_notes").strip() or "tags_and_notes",
                    }
                },
            )
            self.send_json(200, {"message": "Import plan saved.", "entry": entry})
        except Exception as exc:  # noqa: BLE001
            self.send_json(400, {"error": str(exc)})

    def log_message(self, format_string: str, *args) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch a folder 3MF catalog viewer")
    parser.add_argument("--manifest", required=True, help="Folder 3MF catalog manifest path")
    parser.add_argument("--state", help="Optional folder 3MF catalog state path")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host")
    parser.add_argument("--port", type=int, default=8766, help="HTTP bind port")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open a browser window")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset = CatalogDataset(Path(args.manifest), Path(args.state) if args.state else None)
    CatalogHandler.dataset = dataset
    server = ThreadingHTTPServer((args.host, args.port), CatalogHandler)
    url = f"http://{args.host}:{args.port}/?view=all"
    print(f"Serving folder 3MF catalog viewer at {url}")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())