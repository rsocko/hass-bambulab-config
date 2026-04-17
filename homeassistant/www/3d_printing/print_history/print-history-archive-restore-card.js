class PrintHistoryArchiveRestoreCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._uploadInput = null;
    this._busy = false;
    this._message = "";
    this._error = "";
    this._boundUploadChange = this._handleUploadSelected.bind(this);
  }

  setConfig(config) {
    this._config = {
      workflow_entity: config?.workflow_entity || "sensor.print_history_popup_restore_workflow",
      detail_entity: config?.detail_entity || "sensor.print_history_popup_archive_detail",
      source_archive_helper: config?.source_archive_helper || "input_text.print_history_restore_source_archive_id",
      target_archive_helper: config?.target_archive_helper || "input_text.print_history_restore_target_archive_id",
      upload_session_helper: config?.upload_session_helper || "input_text.print_history_restore_upload_session_id",
      upload_endpoint: config?.upload_endpoint || "/api/bambuddy/print-history/archive-repair/replacement/discover",
    };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._config) {
      this._render();
    }
  }

  connectedCallback() {
    this.shadowRoot.addEventListener("change", this._boundUploadChange);
  }

  disconnectedCallback() {
    this.shadowRoot.removeEventListener("change", this._boundUploadChange);
  }

  getCardSize() {
    return 7;
  }

  _entity(entityId) {
    return this._hass?.states?.[entityId] || null;
  }

  _workflow() {
    return this._entity(this._config.workflow_entity);
  }

  _detail() {
    return this._entity(this._config.detail_entity);
  }

  _workflowAttr(name, fallback = "") {
    const entity = this._workflow();
    return entity?.attributes?.[name] ?? fallback;
  }

  _parseJson(value, fallback) {
    try {
      return JSON.parse(value || "{}");
    } catch (_error) {
      return fallback;
    }
  }

  _sourceArchive() {
    const detail = this._detail();
    return this._parseJson(detail?.attributes?.archive_json || "{}", {});
  }

  async _setHelper(entityId, value) {
    await this._hass.callService("input_text", "set_value", { entity_id: entityId, value: String(value || "") });
  }

  async _callRestoreService(service, data) {
    this._busy = true;
    this._message = "";
    this._error = "";
    this._render();
    try {
      const response = await this._hass.callService("bambuddy", service, data, true);
      this._message = response?.message || "";
      if (response?.target_archive_id) {
        await this._setHelper(this._config.target_archive_helper, response.target_archive_id);
      }
      if (Object.prototype.hasOwnProperty.call(response || {}, "upload_session_id")) {
        await this._setHelper(this._config.upload_session_helper, response?.upload_session_id || "");
      }
      return response || {};
    } catch (error) {
      this._error = error?.message || String(error);
      throw error;
    } finally {
      this._busy = false;
      this._render();
    }
  }

  async _handleUploadSelected(event) {
    const input = event.target;
    if (!input || input.type !== "file" || !input.files || !input.files.length) {
      return;
    }
    const file = input.files[0];
    const sourceArchiveId = this._workflowAttr("source_archive_id", this._sourceArchive().id || "");
    const sourceArchive = this._sourceArchive();
    const printerId = sourceArchive?.printer_id || this._workflowAttr("printer_id", "");
    if (!sourceArchiveId || !printerId) {
      this._error = "Source archive or printer context is missing.";
      this._render();
      input.value = "";
      return;
    }

    this._busy = true;
    this._message = "";
    this._error = "";
    this._render();
    try {
      const formData = new FormData();
      formData.append("source_archive_id", String(sourceArchiveId));
      formData.append("printer_id", String(printerId));
      formData.append("file", file, file.name);
      const headers = {};
      const accessToken = this._hass?.auth?.data?.accessToken;
      if (accessToken) {
        headers.Authorization = `Bearer ${accessToken}`;
      }
      const response = await fetch(this._config.upload_endpoint, {
        method: "POST",
        body: formData,
        headers,
        credentials: "same-origin",
      });
      const payload = await response.json();
      if (!response.ok || payload?.success === false) {
        throw new Error(payload?.message || `Upload failed with HTTP ${response.status}`);
      }
      const upload = payload?.upload || payload;
      await this._setHelper(this._config.source_archive_helper, upload.source_archive_id || sourceArchiveId);
      await this._setHelper(this._config.target_archive_helper, "");
      await this._setHelper(this._config.upload_session_helper, upload.upload_session_id || "");
      this._message = `Staged ${upload.filename || file.name}`;
    } catch (error) {
      this._error = error?.message || String(error);
    } finally {
      this._busy = false;
      input.value = "";
      this._render();
    }
  }

  _button(label, action, disabled = false, tone = "") {
    return `<button class="action ${tone}" data-action="${action}" ${disabled ? "disabled" : ""}>${label}</button>`;
  }

  _bindActions() {
    const fileInput = this.shadowRoot.getElementById("replacement-upload-input");
    this._uploadInput = fileInput;
    const openUpload = this.shadowRoot.getElementById("open-upload");
    if (openUpload) {
      openUpload.onclick = () => fileInput?.click();
    }
    this.shadowRoot.querySelectorAll("button[data-action]").forEach((button) => {
      button.onclick = async () => {
        const action = button.getAttribute("data-action");
        const sourceArchiveId = this._workflowAttr("source_archive_id", this._sourceArchive().id || "");
        const targetArchiveId = this._workflowAttr("target_archive_id", "");
        const uploadSessionId = this._workflowAttr("upload_session_id", "");
        try {
          if (action === "create") {
            const response = await this._callRestoreService("create_print_history_archive_replacement_from_upload", {
              source_archive_id: Number(sourceArchiveId),
              upload_session_id: String(uploadSessionId),
            });
            if (response?.target_archive_id) {
              await this._setHelper(this._config.target_archive_helper, response.target_archive_id);
            }
            await this._setHelper(this._config.upload_session_helper, "");
          } else if (action === "plan") {
            await this._callRestoreService("plan_print_history_archive_restore", {
              source_archive_id: Number(sourceArchiveId),
              target_archive_id: Number(targetArchiveId),
            });
          } else if (action === "apply") {
            await this._callRestoreService("apply_print_history_archive_restore", {
              source_archive_id: Number(sourceArchiveId),
              target_archive_id: Number(targetArchiveId),
            });
          } else if (action === "verify") {
            await this._callRestoreService("verify_print_history_archive_restore", {
              source_archive_id: Number(sourceArchiveId),
              target_archive_id: Number(targetArchiveId),
            });
          } else if (action === "finish") {
            await this._callRestoreService("finish_print_history_archive_restore", {
              source_archive_id: Number(sourceArchiveId),
              target_archive_id: Number(targetArchiveId),
              attempt_reenrich: true,
              retain_original: true,
            });
          } else if (action === "remove") {
            const response = await this._callRestoreService("remove_print_history_restored_source_archive", {
              source_archive_id: Number(sourceArchiveId),
              target_archive_id: Number(targetArchiveId),
            });
            if (response?.removed) {
              await this._setHelper(this._config.target_archive_helper, "");
            }
          } else if (action === "clear") {
            await this._callRestoreService("clear_print_history_archive_restore", {
              source_archive_id: Number(sourceArchiveId),
              target_archive_id: targetArchiveId ? Number(targetArchiveId) : undefined,
            });
            await this._setHelper(this._config.target_archive_helper, "");
            await this._setHelper(this._config.upload_session_helper, "");
          }
        } catch (_error) {
          // State already captured in _callRestoreService.
        }
      };
    });
  }

  _render() {
    if (!this._config) {
      return;
    }
    const workflowEntity = this._workflow();
    const workflowState = workflowEntity?.state || "idle";
    const sourceArchive = this._sourceArchive();
    const sourceArchiveId = this._workflowAttr("source_archive_id", sourceArchive?.id || "");
    const targetArchiveId = this._workflowAttr("target_archive_id", "");
    const uploadSessionId = this._workflowAttr("upload_session_id", "");
    const lastError = String(this._workflowAttr("last_error", "") || this._error || "");
    const lastMessage = String(this._message || this._workflowAttr("summary_json", ""));
    const planWarnings = Number(this._workflowAttr("plan_warning_count", 0) || 0);
    const updatedFields = Number(this._workflowAttr("plan_updated_field_count", 0) || 0);
    const remainingDiffs = Number(this._workflowAttr("verify_remaining_difference_count", 0) || 0);
    const blockingDiffs = Number(this._workflowAttr("verify_blocking_difference_count", 0) || 0);
    const enrichmentStatus = String(this._workflowAttr("enrichment_status", "") || "unknown");
    const removable = !!this._workflowAttr("removable", false);
    const verified = !!this._workflowAttr("verified", false);

    this.shadowRoot.innerHTML = `
      <style>
        ha-card{padding:16px;border-radius:20px;}
        .stack{display:grid;gap:14px;}
        .section{border:1px solid rgba(255,255,255,0.08);border-radius:18px;padding:14px;background:rgba(255,255,255,0.03);}
        .title{font-size:14px;font-weight:700;margin:0 0 8px;}
        .row{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center;}
        .chip{display:inline-flex;align-items:center;padding:4px 10px;border-radius:999px;background:rgba(21,101,192,0.18);font-size:12px;font-weight:600;}
        .meta{font-size:12px;color:var(--secondary-text-color);line-height:1.45;}
        .actions{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;}
        .action{border:none;border-radius:14px;padding:12px 10px;font:inherit;font-weight:600;background:rgba(255,255,255,0.06);color:var(--primary-text-color);cursor:pointer;}
        .action.primary{background:rgba(21,101,192,0.22);}
        .action.warn{background:rgba(239,108,0,0.22);}
        .action.danger{background:rgba(198,40,40,0.22);}
        .action:disabled{opacity:0.45;cursor:default;}
        .status{font-size:13px;line-height:1.5;}
        .status.error{color:var(--error-color);}
        .status.ok{color:var(--secondary-text-color);}
        .hidden{display:none;}
      </style>
      <ha-card>
        <div class="stack">
          <div class="section">
            <div class="row">
              <div>
                <div class="title">Source And Target</div>
                <div class="meta">Source: ${sourceArchiveId || "-"} ${sourceArchive?.print_name ? `• ${this._escapeHtml(sourceArchive.print_name)}` : ""}</div>
                <div class="meta">Target: ${targetArchiveId || "not created"}</div>
              </div>
              <div class="chip">${this._escapeHtml(workflowState)}</div>
            </div>
          </div>

          <div class="section">
            <div class="title">Replacement Upload</div>
            <div class="meta">Use a sliced replacement .gcode.3mf. The browser uploads directly to Home Assistant via multipart HTTP and HA stages the file on disk.</div>
            <div class="actions" style="margin-top:10px;">
              <button id="open-upload" class="action primary" ${this._busy ? "disabled" : ""}>Upload Replacement 3MF</button>
              ${this._button("Create Replacement Archive", "create", !uploadSessionId || !!targetArchiveId || this._busy, "primary")}
            </div>
            <input id="replacement-upload-input" class="hidden" type="file" accept=".3mf,.gcode.3mf" />
            <div class="meta" style="margin-top:8px;">Upload session: ${uploadSessionId || "none"}</div>
          </div>

          <div class="section">
            <div class="title">Workflow Summary</div>
            <div class="meta">Plan warnings: ${planWarnings}</div>
            <div class="meta">Updated fields: ${updatedFields}</div>
            <div class="meta">Remaining differences: ${remainingDiffs}</div>
            <div class="meta">Blocking differences: ${blockingDiffs}</div>
            <div class="meta">Enrichment: ${this._escapeHtml(enrichmentStatus)}</div>
            <div class="meta">Verified: ${verified ? "yes" : "no"}</div>
            <div class="meta">Removable: ${removable ? "yes" : "no"}</div>
          </div>

          <div class="section">
            <div class="title">Actions</div>
            <div class="actions">
              ${this._button("Plan Restore", "plan", !sourceArchiveId || !targetArchiveId || this._busy, "primary")}
              ${this._button("Apply Restore", "apply", workflowState !== "plan_ready" || this._busy, "warn")}
              ${this._button("Verify", "verify", !targetArchiveId || this._busy, "warn")}
              ${this._button("Finish Repair", "finish", !targetArchiveId || this._busy, "primary")}
              ${this._button("Remove Original", "remove", workflowState !== "remove_ready" || this._busy, "danger")}
              ${this._button("Clear", "clear", this._busy, "")}
            </div>
          </div>

          ${(lastError || this._message) ? `<div class="status ${lastError ? "error" : "ok"}">${this._escapeHtml(lastError || this._message)}</div>` : ""}
        </div>
      </ha-card>
    `;
    this._bindActions();
  }

  _escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }
}

customElements.define("print-history-archive-restore-card", PrintHistoryArchiveRestoreCard);
