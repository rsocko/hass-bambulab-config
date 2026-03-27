You’re right, I’ll broaden this to the full v2.2.21 surface area and produce an impact matrix by feature (entities, services, logging, UI/frontend, and stage/state handling), not just stage names.

Searched for regex `airduct|vortek|chamber.*target|chamber_temperature|retry.*load|done.*load|print_history|hms|current_stage|print_status|spoolman|bambu_lab|ha-bambulab` (`**/homeassistant/packages/3d_printing/**`), 200 results

Searched for regex `airduct|vortek|chamber.*target|retry.*load|done.*load|CURRENT_STAGE_IDS|GCODE_STATE_OPTIONS|AIRDUCT_MODES|print history cleanup|HMS errors as warnings` (`**/docs/**`), 4 results

Read [](file:///c%3A/Users/rysock/AppData/Roaming/Code/User/workspaceStorage/f1e8c86c09b454e54dac17743f1b3091/GitHub.copilot-chat/chat-session-resources/fdc0195f-23b7-4b64-8a63-bd156cdacf46/call_UqUTursVjeiZa04cSoTsu7gr__vscode-1773966968232/content.txt)

I’m now pulling the raw GitHub compare payload so we can systematically cover every changed file category in v2.2.21 and map each one to whether this repo depends on it.

Ran terminal command: $ProgressPreference='SilentlyContinue'; $cmp = Invoke-RestMethod -Uri 'https://api.github.com/repos/greghesp/ha-bambulab/compare/v2.2.20...v2.2.21'; $cmp | Select-Object -Property status,ahead_by,behind_by,total_commits,files | ConvertTo-Json -Depth 6

Read [](file:///c%3A/Users/rysock/AppData/Roaming/Code/User/workspaceStorage/f1e8c86c09b454e54dac17743f1b3091/GitHub.copilot-chat/chat-session-resources/fdc0195f-23b7-4b64-8a63-bd156cdacf46/call_nMd3eirmC0dShNiEhn4KAAG1__vscode-1773966968238/content.txt#1-1), lines 1 to 340

Ran terminal command: $ProgressPreference='SilentlyContinue'; $cmp = Invoke-RestMethod -Uri 'https://api.github.com/repos/greghesp/ha-bambulab/compare/v2.2.20...v2.2.21'; 'status=' + $cmp.status + '; commits=' + $cmp.total_commits + '; files=' + $cmp.files.Count; $cmp.files | Select-Object filename,status,additions,deletions,changes | Sort-Object filename | Format-Table -AutoSize | Out-String -Width 220

I now have the full 36-file change inventory; next I’m extracting the functional diffs from core integration files (not translations/docs noise) to map concrete behavioral impact to your automations and dashboards.

Ran terminal command: $ProgressPreference='SilentlyContinue'; $cmp = Invoke-RestMethod -Uri 'https://api.github.com/repos/greghesp/ha-bambulab/compare/v2.2.20...v2.2.21'; $targets = @('custom_components/bambu_lab/coordinator.py','custom_components/bambu_lab/definitions.py','custom_components/bambu_lab/number.py','custom_components/bambu_lab/select.py','custom_components/bambu_lab/sensor.py','custom_components/bambu_lab/services.yaml','custom_components/bambu_lab/switch.py','custom_components/bambu_lab/pybambu/commands.py','custom_components/bambu_lab/pybambu/const.py','custom_components/bambu_lab/pybambu/models.py','custom_components/bambu_lab/pybambu/utils.py','custom_components/bambu_lab/models.py'); foreach($f in $cmp.files){ if($targets -contains $f.filename){ '===== ' + $f.filename + ' ====='; if($f.patch){ $f.patch } else { '[no patch field in API response]' }; '' } }

Read [](file:///c%3A/Users/rysock/AppData/Roaming/Code/User/workspaceStorage/f1e8c86c09b454e54dac17743f1b3091/GitHub.copilot-chat/chat-session-resources/fdc0195f-23b7-4b64-8a63-bd156cdacf46/call_g1YeYADcjNF9otH0uA8uAeMY__vscode-1773966968241/content.txt#1-1), lines 1 to 420

Read [](file:///c%3A/Users/rysock/AppData/Roaming/Code/User/workspaceStorage/f1e8c86c09b454e54dac17743f1b3091/GitHub.copilot-chat/chat-session-resources/fdc0195f-23b7-4b64-8a63-bd156cdacf46/call_g1YeYADcjNF9otH0uA8uAeMY__vscode-1773966968241/content.txt#421-421), lines 421 to 506

Ran terminal command: $ProgressPreference='SilentlyContinue'; $cmp = Invoke-RestMethod -Uri 'https://api.github.com/repos/greghesp/ha-bambulab/compare/v2.2.20...v2.2.21'; $name='custom_components/bambu_lab/pybambu/const.py'; $f = $cmp.files | Where-Object { $_.filename -eq $name }; '===== ' + $name + ' ====='; $f.patch

Ran terminal command: $ProgressPreference='SilentlyContinue'; $cmp = Invoke-RestMethod -Uri 'https://api.github.com/repos/greghesp/ha-bambulab/compare/v2.2.20...v2.2.21'; $name='custom_components/bambu_lab/pybambu/commands.py'; $f = $cmp.files | Where-Object { $_.filename -eq $name }; '===== ' + $name + ' ====='; $f.patch

Ran terminal command: $ProgressPreference='SilentlyContinue'; $cmp = Invoke-RestMethod -Uri 'https://api.github.com/repos/greghesp/ha-bambulab/compare/v2.2.20...v2.2.21'; $name='custom_components/bambu_lab/coordinator.py'; $f = $cmp.files | Where-Object { $_.filename -eq $name }; '===== ' + $name + ' ====='; $f.patch

I’ve now captured the core command/constant/service wiring deltas upstream; I’m doing one more pass on entity-definition diffs and then I’ll give you a full release-impact breakdown across this repo, with risk level and suggested actions per item.

Ran terminal command: $ProgressPreference='SilentlyContinue'; $cmp = Invoke-RestMethod -Uri 'https://api.github.com/repos/greghesp/ha-bambulab/compare/v2.2.20...v2.2.21'; foreach($name in @('custom_components/bambu_lab/definitions.py','custom_components/bambu_lab/number.py','custom_components/bambu_lab/models.py','custom_components/bambu_lab/sensor.py','custom_components/bambu_lab/select.py','custom_components/bambu_lab/switch.py','custom_components/bambu_lab/services.yaml','custom_components/bambu_lab/frontend/ha-bambulab-cards.js')){ $f = $cmp.files | Where-Object { $_.filename -eq $name }; '===== ' + $name + ' ====='; if($f.patch){ $f.patch } else {'[no patch field]'}; '' }



Searched for regex `airduct_mode|switch\..*airduct|select\..*airduct|target_chamber_temp|target_chamber_temperature|retry_load_filament|done_load_filament|ams_control` (`**/*.{yaml,yml,md,js,ts,json}`), 6 results

Searched for regex `tray_uuid|cols|ctype|dry_temp|dry_time|bed_temp|remaining_weight|remaining filament|color type` (`**/homeassistant/packages/3d_printing/**`), 106 results

Searched for regex `homeassistant\.components\.bambulab|HMS ERRORS|hms error|warning|logger|promtail|bambulab` (`**/homelab/logging-integrations/**`), 42 results

Fetched 6 resources

**Findings (Full v2.2.21 Review, ordered by impact)**

1. **High: Smart Status and WLED can miss new upstream stages (not just 52–58 anymore)**
- Upstream now recognizes additional stage strings including 59–66 and 77 in v2.2.21.
- Your Smart Status template currently maps through thermal_preconditioning-era stages but does not include the newer cluster (for example homing_blade_holder, preparing_hotend, preparing_ams), so those can resolve as Unmapped Printer State.
- When that happens, downstream consumers (WLED orchestrator, OpenHASP state logic, dashboards) rely on fallback behavior rather than explicit intent.
- Relevant local files:
  - smart_status.yaml
  - smart-status-unmapped-alert.yaml
  - wled_3dprinter_state_machine_orchestrator.yaml
  - wled_3dprinter_reset_to_working_state-script.yaml

2. **Medium: HMS log-level behavior changed upstream (warning to debug), which can affect your log dashboards/alerts**
- v2.2.21 changed HMS error logging from warning to debug in upstream integration internals.
- You have Grafana/Loki queries that explicitly include WARNING for bambulab streams. HMS signal volume in those panels can drop after upgrade (even though HMS entities still work).
- Relevant local files:
  - grafana-dashboard.json
  - promtail-config.yml

3. **Medium (potential external break): Airduct entities are a true breaking change upstream**
- Upstream removed prior airduct switch/binary style and replaced with select + enum sensor model.
- I did not find repo-managed references to old airduct entities, so your checked-in YAML appears safe.
- Risk remains for any live/UI automations outside git that may still reference old airduct switch/binary names.
- Relevant local area where custom AMS control exists (not directly broken, but adjacent control path):
  - bambu_mqtt_commands.yaml

4. **Low: Upstream frontend/card updates are likely beneficial for your dashboards (not risky)**
- v2.2.21 includes frontend updates/fixes for missing confirmation dialog buttons.
- You use upstream custom cards, so this is likely a positive UX fix rather than a regression risk.
- Relevant local files:
  - view_main.yaml
  - lovelace.3d_printing.original.2026-03-02.yaml

5. **Low: New chamber target temp controls and expanded airduct model (X1E/H2 families)**
- Upstream added chamber target temperature control behavior and expanded airduct handling.
- I found no direct repo dependency on those new number/select entities, so no immediate break in your package YAML.
- This is an enhancement opportunity if you want chamber target controls surfaced in your temp cards.
- Relevant local temp dashboard:
  - printer-temps.yaml

6. **Low: New retry/done filament loading actions added upstream**
- Upstream now exposes explicit retry_load_filament and done_load_filament actions.
- Your repo currently uses a custom AMS control script path; nothing breaks, but this gives you a cleaner native action option.
- Relevant local file:
  - bambu_mqtt_commands.yaml

7. **Low: AMS tray attribute expansion upstream (cols, ctype, bed/drying fields) appears non-breaking for your current logic**
- Your repo primarily uses tray_uuid and Spoolman-driven attributes, which are still present.
- No direct dependency found on newly added upstream tray attrs, so impact is minimal now.
- Relevant local files:
  - spoolman_tray_map.yaml
  - ams_tray_popup.yaml

8. **Low: Startup print-history cleanup async + X1E-specific fixes**
- These are mostly upstream internal robustness improvements and model-specific fixes.
- I did not find tight coupling in your repo that would regress from these changes.

---

**Coverage summary**
- I reviewed the v2.2.21 release notes and the full compare inventory (22 commits, 36 changed files), not just stage changes.
- Functional changes were assessed across integration internals (services, coordinator, models, sensors/select/switch/number), plus docs/frontend implications and how those map to this repo.

---

**Most important practical takeaway for your setup**
- Your stage concern was correct.
- The single biggest repo-impact item is still Smart Status/WLED mapping drift for newly recognized upstream stages.
- The second biggest is observability drift from HMS warning-to-debug logging if you rely on WARNING-level dashboards.

---

If you want, I can do the follow-up implementation now:
1. Extend Smart Status mappings for all newly known stages (including 59–66 and 77) in smart_status.yaml.
2. Update WLED prep/maintenance stage lists to keep transitions deterministic in wled_3dprinter_state_machine_orchestrator.yaml and wled_3dprinter_reset_to_working_state-script.yaml.
3. Add a small logging dashboard tweak so HMS events stay visible post-upgrade in grafana-dashboard.json.