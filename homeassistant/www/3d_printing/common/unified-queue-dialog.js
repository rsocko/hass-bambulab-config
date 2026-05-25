const QUEUE_DIALOG_ALLOWED_STATES = ["backlog", "up_next", "preparing", "ready"];

function normalizeQueueDialogTargetState(state) {
  const normalized = String(state || "").trim().toLowerCase();
  return QUEUE_DIALOG_ALLOWED_STATES.includes(normalized) ? normalized : "up_next";
}

function queueDialogTargetStateLabel(state) {
  const map = {
    backlog: "Backlog",
    up_next: "Up Next",
    preparing: "Preparing",
    ready: "Ready",
  };
  return map[String(state || "").trim()] || String(state || "Up Next");
}

export class UnifiedQueueDialogController {
  constructor(host, options = {}) {
    this.host = host;
    this.options = { ...options };
    this.resetState();
  }

  resetState() {
    this.host._queueDialogOpen = false;
    this.host._queueDialogMode = "quick";
    this.host._queueDialogModelRef = "";
    this.host._queueDialogModelName = "";
    this.host._queueDialogIntent = "add";
    this.host._queueDialogExistingCount = 0;
    this.host._queueDialogTargetState = "up_next";
    this.host._queueDialogNotes = "";
    this.host._queueDialogLoading = false;
    this.host._queueDialogSubmitting = false;
    this.host._queueDialogError = "";
    this.host._queueDialogFiles = [];
    this.host._queueDialogEntityType = "model";
  }

  isIdeaMode() {
    if (this.host._queueDialogLoading) {
      return false;
    }
    if (String(this.host._queueDialogEntityType || "").toLowerCase() === "idea") {
      return true;
    }
    return !Array.isArray(this.host._queueDialogFiles) || this.host._queueDialogFiles.length === 0;
  }

  getPrinterId() {
    if (typeof this.options.getPrinterId === "function") {
      return String(this.options.getPrinterId() || "p1").trim() || "p1";
    }
    return String((this.host._config && this.host._config.queue_printer_id) || "p1").trim() || "p1";
  }

  getQueueApiBase() {
    if (typeof this.options.getQueueApiBase === "function") {
      return String(this.options.getQueueApiBase() || "").trim();
    }
    if (typeof this.host._resolveModelSidecarUrl === "function") {
      const resolved = String(this.host._resolveModelSidecarUrl() || "").trim();
      return resolved ? `${resolved}/api/v1` : "";
    }
    return "";
  }

  async open(modelRef, modelName, entries, options = {}) {
    this.host._queueDialogOpen = true;
    this.host._queueDialogMode = "quick";
    this.host._queueDialogModelRef = String(modelRef || "").trim();
    this.host._queueDialogModelName = String(modelName || "Model").trim() || "Model";
    this.host._queueDialogIntent = options.intent === "re-add" ? "re-add" : "add";
    this.host._queueDialogExistingCount = Array.isArray(entries) ? entries.length : 0;
    this.host._queueDialogTargetState = normalizeQueueDialogTargetState(options.defaultState || "up_next");
    this.host._queueDialogNotes = "";
    this.host._queueDialogLoading = true;
    this.host._queueDialogSubmitting = false;
    this.host._queueDialogError = "";
    this.host._queueDialogFiles = [];
    this.host._render();

    try {
      const loader = this.options.loadSourceDetail;
      if (typeof loader !== "function") {
        throw new Error("Queue dialog loader is unavailable.");
      }
      this.host._queueDialogFiles = await loader.call(this.host, this.host._queueDialogModelRef);
    } catch (error) {
      this.host._queueDialogError = error && error.message ? String(error.message) : "Could not load model queue defaults.";
      this.host._queueDialogFiles = [];
    } finally {
      this.host._queueDialogLoading = false;
      this.host._render();
    }
  }

  close() {
    this.resetState();
    this.host._render();
  }

  setMode(mode) {
    const normalized = String(mode || "").trim().toLowerCase();
    if (normalized !== "quick" && normalized !== "plan") {
      return;
    }
    this.host._queueDialogMode = normalized;
    this.host._render();
  }

  setAllPlatesSelected(selected) {
    const nextSelected = !!selected;
    this.host._queueDialogFiles = (Array.isArray(this.host._queueDialogFiles) ? this.host._queueDialogFiles : []).map(file => ({
      ...file,
      selected: nextSelected,
      plates: Array.isArray(file.plates)
        ? file.plates.map(plate => ({ ...plate, selected: nextSelected }))
        : [],
    }));
    this.host._render();
  }

  toggleFileSelection(fileId) {
    const targetFileId = String(fileId || "").trim();
    if (!targetFileId) {
      return;
    }
    this.host._queueDialogFiles = (Array.isArray(this.host._queueDialogFiles) ? this.host._queueDialogFiles : []).map(file => {
      if (String(file.file_id || "").trim() !== targetFileId) {
        return file;
      }
      const nextSelected = !file.selected;
      return {
        ...file,
        selected: nextSelected,
        plates: Array.isArray(file.plates)
          ? file.plates.map((plate, index) => ({
              ...plate,
              selected: nextSelected ? index === 0 || !!plate.selected : false,
            }))
          : [],
      };
    });
    this.host._render();
  }

  togglePlateSelection(fileId, plateId) {
    const targetFileId = String(fileId || "").trim();
    const targetPlateId = String(plateId || "").trim();
    if (!targetFileId || !targetPlateId) {
      return;
    }
    this.host._queueDialogFiles = (Array.isArray(this.host._queueDialogFiles) ? this.host._queueDialogFiles : []).map(file => {
      if (String(file.file_id || "").trim() !== targetFileId) {
        return file;
      }
      const nextPlates = (Array.isArray(file.plates) ? file.plates : []).map(plate => {
        if (String(plate.plate_id || "").trim() !== targetPlateId) {
          return plate;
        }
        return { ...plate, selected: !plate.selected };
      });
      return {
        ...file,
        selected: nextPlates.some(plate => !!plate.selected),
        plates: nextPlates,
      };
    });
    this.host._render();
  }

  getMetrics() {
    const files = Array.isArray(this.host._queueDialogFiles) ? this.host._queueDialogFiles : [];
    const selectedFiles = files.filter(file => !!file.selected);
    const selectedPlates = selectedFiles.reduce((sum, file) => {
      return sum + (Array.isArray(file.plates) ? file.plates.filter(plate => !!plate.selected).length : 0);
    }, 0);
    return {
      totalFiles: files.length,
      selectedFiles: selectedFiles.length,
      selectedPlates,
    };
  }

  canSubmit() {
    if (this.host._queueDialogLoading || this.host._queueDialogSubmitting) {
      return false;
    }
    if (this.isIdeaMode()) {
      return !!String(this.host._queueDialogModelRef || "").trim();
    }
    if (!Array.isArray(this.host._queueDialogFiles) || this.host._queueDialogFiles.length === 0) {
      return false;
    }
    if (this.host._queueDialogMode !== "plan") {
      return true;
    }
    return this.getMetrics().selectedPlates > 0;
  }

  primarySummary() {
    if (this.host._queueDialogLoading) {
      return "Loading queue defaults...";
    }
    if (this.isIdeaMode()) {
      const ideaState = this.host._queueDialogMode === "quick"
        ? "up_next"
        : normalizeQueueDialogTargetState(this.host._queueDialogTargetState);
      const label = String(this.host._queueDialogEntityType || "").toLowerCase() === "idea" ? "idea" : "entry";
      return `Will queue ${label} ${String(this.host._queueDialogModelName || "Idea")} on ${this.getPrinterId()} in state ${queueDialogTargetStateLabel(ideaState)} (no files to select).`;
    }
    if (!Array.isArray(this.host._queueDialogFiles) || !this.host._queueDialogFiles.length) {
      return "Loading queue defaults...";
    }
    const primaryFile = this.host._queueDialogFiles[0] || {};
    const primaryPlate = Array.isArray(primaryFile.plates) && primaryFile.plates.length > 0 ? primaryFile.plates[0] : null;
    return `Will queue ${String(primaryFile.file_name || "Primary file")} · ${String(primaryPlate && primaryPlate.plate_name ? primaryPlate.plate_name : "Primary Plate")} on ${this.getPrinterId()} in state ${queueDialogTargetStateLabel("up_next")}.`;
  }

  buildPayload() {
    const ideaMode = this.isIdeaMode();
    if (ideaMode) {
      const ideaSourceKind = String(this.host._queueDialogEntityType || "").toLowerCase() === "idea" ? "idea" : "catalog_model";
      const ideaTargetState = this.host._queueDialogMode === "quick"
        ? "up_next"
        : normalizeQueueDialogTargetState(this.host._queueDialogTargetState);
      const ideaPayload = {
        source_kind: ideaSourceKind,
        source_id: String(this.host._queueDialogModelRef || "").trim(),
        title: String(this.host._queueDialogModelName || "").trim() || "Idea",
        state: ideaTargetState,
        queue_notes: String(this.host._queueDialogNotes || "").trim(),
      };
      return ideaPayload;
    }
    const quick = this.host._queueDialogMode !== "plan";
    const files = Array.isArray(this.host._queueDialogFiles) ? this.host._queueDialogFiles : [];
    const primaryFile = files[0] || {};
    const primaryPlate = Array.isArray(primaryFile.plates) && primaryFile.plates.length > 0 ? primaryFile.plates[0] : null;
    const targetState = quick ? "up_next" : normalizeQueueDialogTargetState(this.host._queueDialogTargetState);
    const payload = {
      source_kind: "catalog_model",
      source_id: String(this.host._queueDialogModelRef || "").trim(),
      title: String(this.host._queueDialogModelName || "").trim() || "Model",
      queue_notes: String(this.host._queueDialogNotes || "").trim(),
      selection_mode: "selected_plates",
      selected_files: quick
        ? [{
            file_id: primaryFile.file_id,
            file_name: primaryFile.file_name,
            selected: true,
            plates: primaryPlate ? [{ plate_id: primaryPlate.plate_id, selected: true }] : [],
          }]
        : files.map(file => ({
            file_id: file.file_id,
            file_name: file.file_name,
            selected: !!file.selected,
            plates: (Array.isArray(file.plates) ? file.plates : []).map(plate => ({
              plate_id: plate.plate_id,
              selected: !!plate.selected,
            })),
          })),
    };
    if (targetState !== "up_next") {
      payload.state = targetState;
    }
    return payload;
  }

  async submit() {
    if (!this.host._queueDialogModelRef || this.host._queueDialogLoading || this.host._queueDialogSubmitting) {
      return;
    }
    if (!this.canSubmit()) {
      this.host._queueDialogError = this.isIdeaMode()
        ? "Cannot add to queue right now."
        : (this.host._queueDialogMode === "plan"
            ? "Select at least one file plate before adding to queue."
            : "No queueable files were found for this model.");
      this.host._render();
      return;
    }

    const submitEntry = this.options.addEntry;
    if (typeof submitEntry !== "function") {
      this.host._queueDialogError = "Queue submit is unavailable.";
      this.host._render();
      return;
    }

    this.host._queueDialogSubmitting = true;
    this.host._queueDialogError = "";
    this.host._render();

    try {
      await submitEntry.call(this.host, {
        queueApiBase: this.getQueueApiBase(),
        printerId: this.getPrinterId(),
        payload: this.buildPayload(),
      });
      this.close();
      if (typeof this.options.afterSubmit === "function") {
        await this.options.afterSubmit.call(this.host);
      }
    } catch (error) {
      this.host._queueDialogSubmitting = false;
      this.host._queueDialogError = error && error.message ? String(error.message) : "Could not add to queue.";
      this.host._render();
    }
  }

  render() {
    if (!this.host._queueDialogOpen) {
      return "";
    }
    const escapeHtml = typeof this.host._escapeHtml === "function"
      ? value => this.host._escapeHtml(value)
      : value => String(value || "");
    const metrics = this.getMetrics();
    const canSubmit = this.canSubmit();
    const ideaMode = this.isIdeaMode();
    const existingNote = this.host._queueDialogExistingCount > 0
      ? `<div class="queue-dialog-existing-note">This model already has ${escapeHtml(String(this.host._queueDialogExistingCount))} queue entr${this.host._queueDialogExistingCount === 1 ? "y" : "ies"}. Re-adding will create another independent entry.</div>`
      : "";
    const ideaBody = ''
      + `<div class="queue-dialog-summary">${escapeHtml(this.primarySummary())}</div>`
      + '<label class="queue-dialog-field"><span>Target state</span><select class="queue-dialog-target-state">'
      + `<option value="backlog"${this.host._queueDialogTargetState === "backlog" ? " selected" : ""}>Backlog</option>`
      + `<option value="up_next"${this.host._queueDialogTargetState === "up_next" ? " selected" : ""}>Up Next</option>`
      + `<option value="preparing"${this.host._queueDialogTargetState === "preparing" ? " selected" : ""}>Preparing</option>`
      + `<option value="ready"${this.host._queueDialogTargetState === "ready" ? " selected" : ""}>Ready</option>`
      + '</select></label>'
      + `<label class="queue-dialog-field"><span>Notes</span><textarea class="queue-dialog-notes" data-queue-dialog-notes="true" rows="3" placeholder="Optional operator notes...">${escapeHtml(this.host._queueDialogNotes)}</textarea></label>`
      + '<div class="queue-dialog-note">This entry has no printable files. It will be queued as a placeholder for planning.</div>';
    const planBody = this.host._queueDialogLoading
      ? '<div class="queue-dialog-note">Loading model files and plates...</div>'
      : !Array.isArray(this.host._queueDialogFiles) || this.host._queueDialogFiles.length === 0
      ? '<div class="queue-dialog-note">No queueable files available for this model.</div>'
      : '<div class="queue-dialog-toolbar"><button class="toolbar-btn" type="button" data-action="queue-dialog-select-all">Select all</button><button class="toolbar-btn ghost" type="button" data-action="queue-dialog-clear-all">Deselect all</button></div>'
        + '<div class="queue-dialog-file-list">'
        + (Array.isArray(this.host._queueDialogFiles) ? this.host._queueDialogFiles : []).map(file => {
            const plateCount = Array.isArray(file.plates) ? file.plates.length : 0;
            const selectedPlates = Array.isArray(file.plates) ? file.plates.filter(plate => !!plate.selected).length : 0;
            return '<section class="queue-dialog-file-block">'
              + `  <button class="queue-dialog-file-toggle${file.selected ? " active" : ""}" type="button" data-action="queue-dialog-toggle-file" data-file-id="${escapeHtml(String(file.file_id || ""))}">${escapeHtml(String(file.file_name || "Queue file"))}<span>${escapeHtml(`${selectedPlates}/${plateCount} plates`)}</span></button>`
              + '  <div class="queue-dialog-plates">'
              + (Array.isArray(file.plates) ? file.plates : []).map(plate => {
                  return `<button class="queue-dialog-plate-toggle${plate.selected ? " active" : ""}" type="button" data-action="queue-dialog-toggle-plate" data-file-id="${escapeHtml(String(file.file_id || ""))}" data-plate-id="${escapeHtml(String(plate.plate_id || ""))}">${escapeHtml(String(plate.plate_name || "Plate"))}</button>`;
                }).join("")
              + '  </div>'
              + '</section>';
          }).join("")
        + '</div>';

    return ''
      + '<div class="queue-dialog-backdrop" data-action="close-queue-dialog">'
      + '  <div class="queue-dialog" role="dialog" aria-modal="true" aria-label="Add to Queue">'
      + '    <div class="queue-dialog-header">'
      + `      <div><h3>Add to Queue</h3><div class="queue-dialog-subtitle">${escapeHtml(this.host._queueDialogModelName)}</div></div>`
      + '      <button class="modal-close-btn" type="button" data-action="close-queue-dialog" aria-label="Close">✕</button>'
      + '    </div>'
      + '    <div class="queue-dialog-tabs">'
      + (ideaMode
          ? ''
          : `      <button class="queue-dialog-tab${this.host._queueDialogMode === "quick" ? " active" : ""}" type="button" data-action="queue-dialog-mode" data-mode="quick">Quick</button>`
            + `      <button class="queue-dialog-tab${this.host._queueDialogMode === "plan" ? " active" : ""}" type="button" data-action="queue-dialog-mode" data-mode="plan">Plan</button>`)
      + '    </div>'
      + '    <div class="queue-dialog-body">'
      + existingNote
      + (ideaMode
          ? ideaBody
          : (this.host._queueDialogMode === "quick"
          ? `<div class="queue-dialog-summary">${escapeHtml(this.primarySummary())}</div>`
          : '<div class="queue-dialog-summary">Choose plates, target state, and notes before creating the queue entry.</div>'
            + '<label class="queue-dialog-field"><span>Target state</span><select class="queue-dialog-target-state">'
            + `<option value="backlog"${this.host._queueDialogTargetState === "backlog" ? " selected" : ""}>Backlog</option>`
            + `<option value="up_next"${this.host._queueDialogTargetState === "up_next" ? " selected" : ""}>Up Next</option>`
            + `<option value="preparing"${this.host._queueDialogTargetState === "preparing" ? " selected" : ""}>Preparing</option>`
            + `<option value="ready"${this.host._queueDialogTargetState === "ready" ? " selected" : ""}>Ready</option>`
            + '</select></label>'
            + `<label class="queue-dialog-field"><span>Notes</span><textarea class="queue-dialog-notes" data-queue-dialog-notes="true" rows="3" placeholder="Optional operator notes...">${escapeHtml(this.host._queueDialogNotes)}</textarea></label>`
            + `<div class="queue-dialog-metrics">Selected ${escapeHtml(String(metrics.selectedPlates))} plates across ${escapeHtml(String(metrics.selectedFiles))} files.</div>`
            + planBody))
      + (this.host._queueDialogError ? `<div class="queue-dialog-error">${escapeHtml(this.host._queueDialogError)}</div>` : '')
      + '    </div>'
      + '    <div class="queue-dialog-footer">'
      + '      <button class="toolbar-btn ghost" type="button" data-action="close-queue-dialog">Cancel</button>'
      + `      <button class="toolbar-btn queue-dialog-submit" type="button" data-action="queue-dialog-submit"${canSubmit ? "" : " disabled"}>${this.host._queueDialogSubmitting ? "Adding..." : "Add to Queue"}</button>`
      + '    </div>'
      + '  </div>'
      + '</div>';
  }

  handleClick(event) {
    const target = event && event.target instanceof Element ? event.target : null;
    if (!target) {
      return false;
    }
    if (target.classList && target.classList.contains("queue-dialog-backdrop")) {
      event.preventDefault();
      this.close();
      return true;
    }
    const action = target.getAttribute ? target.getAttribute("data-action") : null;
    if (action === "close-queue-dialog") {
      event.preventDefault();
      this.close();
      return true;
    }
    if (action === "queue-dialog-mode") {
      event.preventDefault();
      this.setMode(target.getAttribute("data-mode") || "quick");
      return true;
    }
    if (action === "queue-dialog-submit") {
      event.preventDefault();
      this.submit();
      return true;
    }
    if (action === "queue-dialog-select-all") {
      event.preventDefault();
      this.setAllPlatesSelected(true);
      return true;
    }
    if (action === "queue-dialog-clear-all") {
      event.preventDefault();
      this.setAllPlatesSelected(false);
      return true;
    }
    if (action === "queue-dialog-toggle-file") {
      event.preventDefault();
      this.toggleFileSelection(target.getAttribute("data-file-id") || "");
      return true;
    }
    if (action === "queue-dialog-toggle-plate") {
      event.preventDefault();
      this.togglePlateSelection(target.getAttribute("data-file-id") || "", target.getAttribute("data-plate-id") || "");
      return true;
    }
    return false;
  }

  handleChange(event) {
    const target = event && event.target instanceof Element ? event.target : null;
    if (!target) {
      return false;
    }
    if (target.tagName === "SELECT" && target.classList.contains("queue-dialog-target-state")) {
      this.host._queueDialogTargetState = normalizeQueueDialogTargetState(target.value || "up_next");
      return true;
    }
    if (target.tagName === "TEXTAREA" && target.getAttribute("data-queue-dialog-notes")) {
      this.host._queueDialogNotes = String(target.value || "");
      return true;
    }
    return false;
  }

  handleInput(event) {
    const target = event && event.target instanceof Element ? event.target : null;
    if (target && target.tagName === "TEXTAREA" && target.getAttribute("data-queue-dialog-notes")) {
      this.host._queueDialogNotes = String(target.value || "");
      return true;
    }
    return false;
  }
}

export { normalizeQueueDialogTargetState, queueDialogTargetStateLabel };