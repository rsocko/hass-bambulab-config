I’m extracting the full per-archive `t_hist` row details from the scan result now, then I’ll verify the exact control flow so the time-heuristic gating answer is precise rather than inferred.

Ran terminal command: c:/dev/hass-bambulab-config/.venv/Scripts/python.exe -c "import json, pathlib; p = pathlib.Path(r'c:\Users\rysock\AppData\Roaming\Code\User\workspaceStorage\f1e8c86c09b454e54dac17743f1b3091\GitHub.copilot-chat\chat-session-resources\5683827a-d8b3-4d39-963f-657ba2ceec76\call_Tzdsi8RHvvnKfnAnJt8itcnf__vscode-1776477843472\content.json'); data = json.loads(p.read_text(encoding='utf-8')); archives = data['result']['service_response'].get('archives') or []; out=[]
for a in archives:
    notes = str(a.get('notes') or '')
    marker = notes.find('+>')
    payload = {}
    if marker >= 0:
        raw = notes[marker+2:].strip()
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {}
    rows = payload.get('F') if isinstance(payload, dict) else None
    matched_rows = []
    if isinstance(rows, list):
        for idx, row in enumerate(rows):
            if isinstance(row, dict) and str(row.get('pm') or '').strip().lower() == 't_hist':
                matched_rows.append({'row_index': idx, 'spool_id': row.get('s'), 'filament_id': row.get('f'), 'name': row.get('n')})
    if matched_rows:
        out.append({'archive_id': int(a.get('id')), 'print_name': a.get('print_name'), 'matched_rows': matched_rows})
out.sort(key=lambda x: x['archive_id'])
print(json.dumps(out, indent=2))"

The detailed extraction succeeded. I’m reading the full result and pairing it with the exact logic gates in the reenrich script.

Read [](file:///c%3A/dev/hass-bambulab-config/homeassistant/packages/3d_printing/print_history/scripts/reenrich_print_history_archive.yaml#430-430), lines 430 to 610

Read [](file:///c%3A/Users/rysock/AppData/Roaming/Code/User/workspaceStorage/f1e8c86c09b454e54dac17743f1b3091/GitHub.copilot-chat/chat-session-resources/5683827a-d8b3-4d39-963f-657ba2ceec76/call_M3MKgkvr4SKKBft1FKu2wcEW__vscode-1776477843502/content.txt#1-1), lines 1 to 320

The extraction is complete but the first read cut off after archive 317. I’m reading the remainder so the per-print list is complete.

Read [](file:///c%3A/Users/rysock/AppData/Roaming/Code/User/workspaceStorage/f1e8c86c09b454e54dac17743f1b3091/GitHub.copilot-chat/chat-session-resources/5683827a-d8b3-4d39-963f-657ba2ceec76/call_M3MKgkvr4SKKBft1FKu2wcEW__vscode-1776477843502/content.txt#320-320), lines 320 to 520

Read [](file:///c%3A/Users/rysock/AppData/Roaming/Code/User/workspaceStorage/f1e8c86c09b454e54dac17743f1b3091/GitHub.copilot-chat/chat-session-resources/5683827a-d8b3-4d39-963f-657ba2ceec76/call_M3MKgkvr4SKKBft1FKu2wcEW__vscode-1776477843502/content.txt#520-520), lines 520 to 568

Yes. I extracted the exact heuristic-matched spool rows for each affected archive.

**Per-Archive Heuristic Matches**
- `87` → spool `180`, filament `6`
- `202` → spool `232`, filament `104`
- `203` → spool `232`, filament `104`
- `205` → spool `232`, filament `104`
- `213` → spool `260`, filament `5`
- `222` → spool `236`, filament `8`; spool `156`, filament `11`
- `229` → spool `225`, filament `6`
- `230` → spool `225`, filament `6`
- `231` → spool `225`, filament `6`
- `246` → spool `125`, filament `91`
- `250` → spool `125`, filament `91`
- `255` → spool `160`, filament `5`
- `282` → spool `129`, filament `47`
- `284` → spool `129`, filament `47`
- `289` → spool `102`, filament `77`
- `300` → spool `8`, filament `1`
- `308` → spool `161`, filament `5`; spool `166`, filament `53`
- `313` → spool `166`, filament `53`
- `317` → spool `181`, filament `13`
- `337` → spool `102`, filament `77`
- `340` → spool `166`, filament `53`
- `341` → spool `166`, filament `53`
- `343` → spool `29`, filament `3`
- `361` → spool `247`, filament `77`
- `371` → spool `260`, filament `5`; spool `225`, filament `6`
- `408` → spool `89`, filament `13`
- `410` → spool `89`, filament `13`
- `411` → spool `79`, filament `58`
- `424` → spool `260`, filament `5`; spool `225`, filament `6`
- `426` → spool `237`, filament `8`; spool `40`, filament `7`
- `429` → spool `236`, filament `8`
- `430` → spool `236`, filament `8`
- `433` → spool `237`, filament `8`
- `436` → spool `260`, filament `5`; spool `225`, filament `6`
- `440` → spool `260`, filament `5`; spool `225`, filament `6`
- `441` → spool `260`, filament `5`; spool `225`, filament `6`

**Heuristic Gate**
No. It does not only drop into time-based matching after a proven color-plus-type match with multiple spools for the same filament.

What the code actually does in reenrich_print_history_archive.yaml is:

1. Try UUID first.
2. If UUID fails, build a candidate pool from color matching, with vendor narrowing when available.
3. If that color-based pool has more than one candidate, it can already apply a temporal narrowing pass before filament-family resolution.
4. Then it uses material/profile metadata to try to collapse candidates to a unique filament family.
5. If it gets a unique filament ID, it expands back out to all spools for that filament and can then apply the print-start temporal heuristic and the later strict temporal fallback across those multiple spools.

So the true statement is:

- A time-based heuristic match only happens when stronger paths failed and there were multiple remaining candidates at that stage.
- Those candidates may be:
  - multiple same-color candidates before unique filament-family proof, or
  - multiple spools within a uniquely identified filament family after color/material/profile narrowing.

The type/material match helps narrow the pool, but it is not a mandatory prerequisite for every `t_hist` match.

If you want, I can next format this into:
1. A CSV with `archive_id,spool_id,filament_id`
2. A grouped summary by spool ID so you can see which spools were most affected
3. A CSV list of archive IDs with repeated IDs expanded per heuristic-matched row