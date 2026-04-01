class PrintHistoryArchiveGridCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._signature = "";
  }

  setConfig(config) {
    if (!config || !config.source_entity) {
      throw new Error("print-history-archive-grid-card requires source_entity");
    }

    this._config = {
      source_entity: config.source_entity,
      variant_entity: config.variant_entity || "input_select.print_history_card_variant",
      show_images_entity:
        config.show_images_entity || "input_boolean.print_history_show_images",
      api_base_entity: config.api_base_entity || "input_text.bambuddy_api_base_url",
      popup_size: config.popup_size || "wide",
    };

    this._signature = "";
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) {
      return;
    }

    const source = hass.states?.[this._config.source_entity];
    const variant = hass.states?.[this._config.variant_entity]?.state || "Compact";
    const showImages = hass.states?.[this._config.show_images_entity]?.state || "on";
    const apiBase = hass.states?.[this._config.api_base_entity]?.state || "";
    const signature = [
      source?.state || "",
      JSON.stringify(source?.attributes?.archives || ""),
      variant,
      showImages,
      apiBase,
    ].join("|");

    if (signature === this._signature) {
      return;
    }

    this._signature = signature;
    this._render();
  }

  getCardSize() {
    return 8;
  }

  _getState(entityId) {
    return this._hass?.states?.[entityId];
  }

  _getArchives() {
    const raw = this._getState(this._config.source_entity)?.attributes?.archives ?? [];
    if (Array.isArray(raw)) {
      return raw;
    }
    if (typeof raw === "string") {
      try {
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : [];
      } catch (_error) {
        return [];
      }
    }
    return [];
  }

  _variant() {
    return this._getState(this._config.variant_entity)?.state || "Compact";
  }

  _showImages() {
    return this._getState(this._config.show_images_entity)?.state !== "off";
  }

  _apiBase() {
    return String(this._getState(this._config.api_base_entity)?.state || "").replace(/\/$/, "");
  }

  _normalizeStatus(status) {
    const raw = String(status || "").toLowerCase();
    if (raw === "completed" || raw === "success") {
      return "completed";
    }
    if (raw === "cancelled" || raw === "aborted") {
      return "failed";
    }
    return raw;
  }

  _statusLabel(status) {
    const raw = this._normalizeStatus(status);
    if (raw === "completed") return "Completed";
    if (raw === "failed") return "Failed";
    if (raw === "stopped") return "Stopped";
    if (raw === "printing") return "Printing";
    return raw ? raw.charAt(0).toUpperCase() + raw.slice(1) : "Unknown";
  }

  _statusIcon(status) {
    const raw = this._normalizeStatus(status);
    if (raw === "completed") return "✅";
    if (raw === "failed") return "❌";
    if (raw === "stopped") return "⛔";
    if (raw === "printing") return "🖨️";
    return "⏳";
  }

  _statusColor(status) {
    const raw = this._normalizeStatus(status);
    if (raw === "completed") return "#2E7D32";
    if (raw === "failed") return "#C62828";
    if (raw === "stopped") return "#EF6C00";
    if (raw === "printing") return "#1565C0";
    return "#546E7A";
  }

  _escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  _formatDate(value) {
    if (!value) {
      return "Unknown";
    }

    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return "Unknown";
    }

    return parsed.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  _formatDuration(secondsValue) {
    const seconds = Number(secondsValue || 0);
    if (!seconds) {
      return "-";
    }

    if (seconds >= 3600) {
      return `${Math.round((seconds / 3600) * 10) / 10}h`;
    }

    return `${Math.round(seconds / 60)}m`;
  }

  _formatNumber(value, digits = 1, suffix = "") {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return "-";
    }
    return `${numeric.toFixed(digits).replace(/\.0$/, "")}${suffix}`;
  }

  _formatCurrency(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) {
      return "-";
    }
    return `$${numeric.toFixed(2)}`;
  }

  _parseTags(tags) {
    if (Array.isArray(tags)) {
      return tags.map((tag) => String(tag || "").trim()).filter(Boolean);
    }
    return String(tags || "")
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean);
  }

  _tagColor(tag) {
    if (tag.startsWith("status:")) {
      return tag.includes("completed") ? "#2E7D32" : "#C62828";
    }
    if (tag.startsWith("vendor:")) {
      return "#6A1B9A";
    }
    if (tag.startsWith("material:")) {
      return "#00695C";
    }
    if (tag.startsWith("cost:")) {
      return "#E65100";
    }
    if (tag.startsWith("spoolman:")) {
      return "#0277BD";
    }
    return "#1565C0";
  }

  _renderTagChips(archive, limit) {
    return this._parseTags(archive.tags)
      .slice(0, limit)
      .map((tag) => {
        const color = this._tagColor(tag);
        return `<span class="tag-chip" style="background:${color}">${this._escapeHtml(tag)}</span>`;
      })
      .join("");
  }

  _renderColorDots(archive) {
    const colors = String(archive.filament_color || "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);

    if (!colors.length) {
      return "";
    }

    return `<div class="color-dots">${colors
      .slice(0, 6)
      .map(
        (hex) =>
          `<span class="color-dot" style="background:${this._escapeHtml(hex)}"></span>`
      )
      .join("")}</div>`;
  }

  _thumbnailUrl(archive) {
    const baseUrl = this._apiBase();
    if (!baseUrl || !archive?.id) {
      return "";
    }
    return `${baseUrl}/api/v1/archives/${archive.id}/thumbnail`;
  }

  _archiveUrl(archive) {
    const baseUrl = this._apiBase();
    if (!baseUrl || !archive?.id) {
      return "";
    }
    return `${baseUrl}/archives/${archive.id}`;
  }

  _facts(archive) {
    return [
      archive.filament_type || "Unknown material",
      archive.layer_height ? `${archive.layer_height}mm layer` : "",
      archive.nozzle_diameter ? `${archive.nozzle_diameter}mm nozzle` : "",
      archive.object_count ? `${archive.object_count} object${Number(archive.object_count) === 1 ? "" : "s"}` : "",
      archive.designer ? `Designer: ${archive.designer}` : "",
    ].filter(Boolean);
  }

  _metadata(archive) {
    return [archive.filament_type || "Unknown material", archive.layer_height ? `${archive.layer_height}mm` : "", archive.designer || ""]
      .filter(Boolean)
      .join(" · ");
  }

  _renderArchiveCard(archive, index, variant, showImages) {
    const date = this._formatDate(archive.started_at || archive.created_at);
    const duration = this._formatDuration(archive.actual_time_seconds || archive.print_time_seconds);
    const grams = Number(archive.filament_used_grams)
      ? `${this._formatNumber(archive.filament_used_grams, 1, "g")}`
      : "-";
    const cost = this._formatCurrency(archive.cost);
    const metadata = this._metadata(archive);
    const facts = this._facts(archive);
    const tagLimit = variant === "Compact" ? 2 : variant === "Detail" ? 6 : 4;
    const favorite = archive.is_favorite
      ? '<span class="favorite" aria-label="Favorite archive">★</span>'
      : "";
    const failure = archive.failure_reason
      ? `<div class="failure-text">${this._escapeHtml(archive.failure_reason)}</div>`
      : "";
    const thumbHeight = variant === "Media" ? "220px" : variant === "Detail" ? "156px" : "180px";
    const thumbnailUrl = this._thumbnailUrl(archive);
    const thumb = !showImages
      ? ""
      : thumbnailUrl
        ? `<img src="${this._escapeHtml(thumbnailUrl)}" class="thumb-image" style="height:${thumbHeight}" loading="lazy" alt="${this._escapeHtml(archive.print_name || "Print thumbnail")}" />`
        : `<div class="thumb-placeholder" style="height:${thumbHeight}">🖨️</div>`;
    const statusPill = `<span class="status-pill" style="background:${this._statusColor(archive.status)}">${this._statusIcon(archive.status)} ${this._escapeHtml(this._statusLabel(archive.status))}</span>`;
    const archiveKey = this._escapeHtml(String(archive.id || `index-${index}`));
    const title = this._escapeHtml(archive.print_name || "Unnamed");
    const tagChips = this._renderTagChips(archive, tagLimit);
    const colorDots = this._renderColorDots(archive);

    if (variant === "Media") {
      return `<button type="button" class="archive-card archive-card--media" data-archive-key="${archiveKey}">
        ${showImages ? thumb : ""}
        <div class="archive-card__body archive-card__body--media">
          <div class="archive-card__header">
            <div class="archive-card__title-wrap">
              <div class="archive-card__title">${title}</div>
              <div class="archive-card__date">${this._escapeHtml(date)}</div>
            </div>
            <div class="archive-card__status-wrap">${favorite}${statusPill}</div>
          </div>
          <div class="archive-card__meta">${this._escapeHtml(metadata || "No additional metadata")}</div>
          <div class="stat-row">
            <span>Duration: <strong>${this._escapeHtml(duration)}</strong></span>
            <span>Filament: <strong>${this._escapeHtml(grams)}</strong></span>
            <span>Cost: <strong>${this._escapeHtml(cost)}</strong></span>
          </div>
          ${colorDots}
          ${tagChips ? `<div class="tag-row">${tagChips}</div>` : ""}
          ${failure}
        </div>
      </button>`;
    }

    if (variant === "Detail") {
      return `<button type="button" class="archive-card archive-card--detail ${showImages ? "" : "archive-card--detail-no-image"}" data-archive-key="${archiveKey}">
        ${showImages ? `<div class="archive-card__thumb-wrap">${thumb}</div>` : ""}
        <div class="archive-card__body archive-card__body--detail">
          <div class="archive-card__detail-main">
            <div class="archive-card__header">
              <div class="archive-card__title-wrap">
                <div class="archive-card__title archive-card__title--detail">${title}</div>
                <div class="archive-card__date">${this._escapeHtml(date)}</div>
              </div>
              <div class="archive-card__status-wrap">${favorite}${statusPill}</div>
            </div>
            ${facts.length ? `<div class="fact-row">${facts.map((fact) => `<span class="fact-chip">${this._escapeHtml(fact)}</span>`).join("")}</div>` : ""}
            <div class="archive-card__meta">${this._escapeHtml(metadata || "No additional metadata")}</div>
            ${failure}
          </div>
          <div class="detail-stats">
            <div class="detail-stat"><div class="detail-stat__label">Duration</div><div class="detail-stat__value">${this._escapeHtml(duration)}</div></div>
            <div class="detail-stat"><div class="detail-stat__label">Filament</div><div class="detail-stat__value">${this._escapeHtml(grams)}</div></div>
            <div class="detail-stat"><div class="detail-stat__label">Cost</div><div class="detail-stat__value">${this._escapeHtml(cost)}</div></div>
            <div class="detail-stat"><div class="detail-stat__label">Objects</div><div class="detail-stat__value">${this._escapeHtml(String(archive.object_count || 1))}</div></div>
          </div>
          ${(colorDots || tagChips) ? `<div class="detail-extras">${colorDots ? `<div>${colorDots}</div>` : ""}${tagChips ? `<div class="tag-row">${tagChips}</div>` : ""}</div>` : ""}
        </div>
      </button>`;
    }

    return `<button type="button" class="archive-card archive-card--compact" data-archive-key="${archiveKey}">
      <div class="archive-card__compact-grid ${showImages ? "archive-card__compact-grid--with-image" : ""}">
        ${showImages ? `<div class="archive-card__thumb-wrap">${thumb}</div>` : ""}
        <div class="archive-card__body archive-card__body--compact">
          <div class="archive-card__header">
            <div class="archive-card__title-wrap">
              <div class="archive-card__title">${title}</div>
              <div class="archive-card__date">${this._escapeHtml(date)}</div>
            </div>
            <div class="archive-card__status-wrap">${favorite}${statusPill}</div>
          </div>
          <div class="stat-grid">
            <div class="stat-box"><div class="stat-box__label">Duration</div><div class="stat-box__value">${this._escapeHtml(duration)}</div></div>
            <div class="stat-box"><div class="stat-box__label">Filament</div><div class="stat-box__value">${this._escapeHtml(grams)}</div></div>
            <div class="stat-box"><div class="stat-box__label">Cost</div><div class="stat-box__value">${this._escapeHtml(cost)}</div></div>
          </div>
          <div class="archive-card__meta">${this._escapeHtml(metadata || "No additional metadata")}</div>
          ${colorDots}
          ${tagChips ? `<div class="tag-row">${tagChips}</div>` : ""}
          ${failure}
        </div>
      </div>
    </button>`;
  }

  _detailValue(value) {
    return this._escapeHtml(value || "-");
  }

  _buildPopupDetailsHtml(archive) {
    const tags = this._parseTags(archive.tags);
    const infoRows = [
      ["Status", this._statusLabel(archive.status)],
      ["Printer", archive.printer_id || "-"],
      ["Started", this._formatDate(archive.started_at)],
      ["Completed", this._formatDate(archive.completed_at)],
      ["Created", this._formatDate(archive.created_at)],
      ["Duration", this._formatDuration(archive.actual_time_seconds || archive.print_time_seconds)],
      ["Filament", Number(archive.filament_used_grams) ? `${this._formatNumber(archive.filament_used_grams, 1, "g")}` : "-"],
      ["Cost", this._formatCurrency(archive.cost)],
      ["Objects", archive.object_count || "-"],
      ["Material", archive.filament_type || "-"],
      ["Layer Height", archive.layer_height ? `${archive.layer_height} mm` : "-"],
      ["Nozzle", archive.nozzle_diameter ? `${archive.nozzle_diameter} mm` : "-"],
      ["Total Layers", archive.total_layers || "-"],
      ["Designer", archive.designer || "-"],
    ];

    const rowsHtml = infoRows
      .map(
        ([label, value]) =>
          `<div class="popup-row"><div class="popup-row__label">${this._escapeHtml(label)}</div><div class="popup-row__value">${this._detailValue(String(value))}</div></div>`
      )
      .join("");

    const notesHtml = archive.notes
      ? `<div class="popup-section"><div class="popup-section__title">Notes</div><div class="popup-note">${this._escapeHtml(archive.notes)}</div></div>`
      : "";
    const failureHtml = archive.failure_reason
      ? `<div class="popup-section"><div class="popup-section__title">Failure Reason</div><div class="popup-failure">${this._escapeHtml(archive.failure_reason)}</div></div>`
      : "";
    const tagsHtml = tags.length
      ? `<div class="popup-section"><div class="popup-section__title">Tags</div><div class="tag-row">${tags
          .map((tag) => `<span class="tag-chip" style="background:${this._tagColor(tag)}">${this._escapeHtml(tag)}</span>`)
          .join("")}</div></div>`
      : "";

    return `
      <div class="popup-details">
        <div class="popup-summary">
          <span class="status-pill" style="background:${this._statusColor(archive.status)}">${this._statusIcon(archive.status)} ${this._escapeHtml(this._statusLabel(archive.status))}</span>
          ${archive.is_favorite ? '<span class="favorite" aria-label="Favorite archive">★ Favorite</span>' : ""}
        </div>
        <div class="popup-grid">${rowsHtml}</div>
        ${tagsHtml}
        ${notesHtml}
        ${failureHtml}
      </div>`;
  }

  _buildPopupContent(archive) {
    const thumbnailUrl = this._thumbnailUrl(archive);
    const archiveUrl = this._archiveUrl(archive);
    const cards = [];

    if (thumbnailUrl) {
      cards.push({
        type: "picture",
        image: thumbnailUrl,
        tap_action: archiveUrl
          ? { action: "url", url_path: archiveUrl }
          : { action: "none" },
        hold_action: { action: "none" },
      });
    }

    cards.push({
      type: "custom:button-card",
      show_icon: false,
      show_name: false,
      show_state: false,
      tap_action: { action: "none" },
      hold_action: { action: "none" },
      custom_fields: {
        body: this._buildPopupDetailsHtml(archive),
      },
      styles: {
        grid: [{ "grid-template-areas": '"body"' }],
        card: [
          { padding: "0" },
          { border: "none" },
          { background: "transparent" },
          { box-shadow: "none" },
        ],
        custom_fields: {
          body: [
            { "text-align": "left" },
          ],
        },
      },
    });

    if (archiveUrl) {
      cards.push({
        type: "button",
        name: "Open in Bambuddy",
        icon: "mdi:open-in-new",
        tap_action: {
          action: "url",
          url_path: archiveUrl,
        },
      });
    }

    return {
      type: "vertical-stack",
      cards,
    };
  }

  async _openArchivePopup(archive) {
    const archiveUrl = this._archiveUrl(archive);
    try {
      await this._hass.callService("browser_mod", "popup", {
        title: archive.print_name || `Archive ${archive.id || ""}`,
        size: this._config.popup_size,
        content: this._buildPopupContent(archive),
      });
    } catch (_error) {
      if (archiveUrl) {
        window.open(archiveUrl, "_blank", "noopener");
      }
    }
  }

  _styles() {
    return `
      :host {
        display: block;
      }

      ha-card {
        background: transparent;
        border: none;
        box-shadow: none;
      }

      .grid {
        display: grid;
        gap: 16px;
        justify-content: center;
        align-items: start;
      }

      .grid--default {
        grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr));
      }

      .grid--detail {
        grid-template-columns: minmax(0, 1fr);
      }

      .empty {
        padding: 16px;
        color: var(--secondary-text-color);
        text-align: center;
      }

      .archive-card {
        width: 100%;
        border: 1px solid var(--divider-color);
        border-radius: 22px;
        background: var(--ha-card-background, var(--card-background-color));
        color: var(--primary-text-color);
        text-align: left;
        padding: 0;
        cursor: pointer;
        overflow: hidden;
        box-sizing: border-box;
        transition: transform 0.12s ease, border-color 0.12s ease, box-shadow 0.12s ease;
      }

      .archive-card:hover,
      .archive-card:focus-visible {
        transform: translateY(-1px);
        border-color: var(--accent-color);
        box-shadow: 0 10px 28px rgba(0, 0, 0, 0.18);
        outline: none;
      }

      .archive-card__body {
        display: flex;
        flex-direction: column;
        gap: 10px;
        min-width: 0;
      }

      .archive-card__body--media {
        padding: 16px 18px 18px;
      }

      .archive-card__body--compact {
        padding: 16px 18px;
        gap: 12px;
      }

      .archive-card__body--detail {
        min-width: 0;
        display: grid;
        grid-template-columns: minmax(0, 1.65fr) minmax(260px, 0.95fr);
        grid-template-areas:
          "main stats"
          "extras extras";
        gap: 14px 18px;
        align-items: start;
        padding: 18px 20px;
      }

      .archive-card__detail-main {
        grid-area: main;
        min-width: 0;
        display: flex;
        flex-direction: column;
        gap: 10px;
      }

      .archive-card__header {
        display: flex;
        justify-content: space-between;
        gap: 10px;
        row-gap: 8px;
        align-items: flex-start;
        flex-wrap: wrap;
        min-width: 0;
      }

      .archive-card__title-wrap {
        min-width: 0;
        flex: 1 1 220px;
        max-width: 100%;
      }

      .archive-card__title {
        font-weight: 700;
        font-size: 16px;
        line-height: 1.2;
        white-space: normal;
        overflow-wrap: anywhere;
        word-break: break-word;
        max-width: 100%;
      }

      .archive-card__title--detail {
        font-size: 19px;
        line-height: 1.15;
      }

      .archive-card__date,
      .archive-card__meta {
        font-size: 12px;
        color: var(--secondary-text-color);
      }

      .archive-card__meta {
        font-size: 13px;
        overflow-wrap: anywhere;
      }

      .archive-card__status-wrap {
        display: flex;
        align-items: center;
        gap: 8px;
        flex: 0 0 auto;
        max-width: 100%;
        margin-left: auto;
      }

      .status-pill {
        color: #fff;
        border-radius: 999px;
        padding: 4px 10px;
        font-size: 11px;
        font-weight: 700;
        display: inline-flex;
        align-items: center;
        gap: 6px;
      }

      .favorite {
        font-size: 18px;
        color: #f5c242;
      }

      .archive-card__compact-grid {
        display: flex;
        flex-direction: column;
        gap: 14px;
      }

      .archive-card__compact-grid--with-image {
        display: grid;
        grid-template-columns: 120px minmax(0, 1fr);
        gap: 14px;
        align-items: start;
      }

      .archive-card--detail {
        display: grid;
        grid-template-columns: 220px minmax(0, 1fr);
        align-items: start;
      }

      .archive-card--detail-no-image {
        grid-template-columns: minmax(0, 1fr);
      }

      .archive-card__thumb-wrap {
        min-width: 0;
        padding: 18px 0 18px 18px;
      }

      .archive-card--compact .archive-card__thumb-wrap {
        padding: 16px 0 16px 16px;
      }

      .thumb-image {
        width: 100%;
        object-fit: cover;
        border-radius: 16px;
        display: block;
      }

      .thumb-placeholder {
        width: 100%;
        background: #37474f;
        border-radius: 16px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 34px;
      }

      .stat-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 8px;
        font-size: 12px;
        min-width: 0;
      }

      .stat-box,
      .detail-stat {
        padding: 8px 10px;
        border-radius: 14px;
        background: rgba(255, 255, 255, 0.04);
      }

      .detail-stats {
        grid-area: stats;
        display: grid;
        gap: 10px;
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      .detail-stat__label,
      .stat-box__label {
        color: var(--secondary-text-color);
        font-size: 12px;
      }

      .detail-stat__value,
      .stat-box__value {
        font-weight: 700;
        font-size: 15px;
      }

      .stat-row,
      .color-dots,
      .fact-row,
      .tag-row,
      .detail-extras,
      .popup-summary {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        align-items: center;
      }

      .stat-row {
        justify-content: space-between;
        gap: 12px;
        font-size: 13px;
      }

      .color-dot {
        width: 14px;
        height: 14px;
        border-radius: 999px;
        box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.25);
      }

      .fact-chip,
      .tag-chip {
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        color: #fff;
        font-size: 11px;
      }

      .fact-chip {
        padding: 5px 10px;
        background: rgba(255, 255, 255, 0.05);
        color: var(--primary-text-color);
      }

      .tag-chip {
        padding: 3px 8px;
      }

      .failure-text,
      .popup-failure {
        font-size: 12px;
        color: #ffb4ab;
        line-height: 1.4;
      }

      .detail-extras {
        grid-area: extras;
        flex-direction: column;
        align-items: flex-start;
      }

      .popup-details {
        display: flex;
        flex-direction: column;
        gap: 16px;
      }

      .popup-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 10px;
      }

      .popup-row {
        padding: 12px 14px;
        border-radius: 14px;
        background: rgba(255, 255, 255, 0.04);
      }

      .popup-row__label {
        color: var(--secondary-text-color);
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 4px;
      }

      .popup-row__value,
      .popup-note {
        font-size: 14px;
        line-height: 1.4;
        overflow-wrap: anywhere;
      }

      .popup-section {
        display: flex;
        flex-direction: column;
        gap: 8px;
      }

      .popup-section__title {
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: var(--secondary-text-color);
      }

      @media (max-width: 900px) {
        .archive-card--detail {
          grid-template-columns: minmax(0, 1fr);
        }

        .archive-card__thumb-wrap,
        .archive-card--compact .archive-card__thumb-wrap {
          padding: 18px 18px 0;
        }

        .archive-card__body--detail {
          grid-template-columns: minmax(0, 1fr);
          grid-template-areas:
            "main"
            "stats"
            "extras";
        }
      }

      @media (max-width: 720px) {
        .archive-card__compact-grid--with-image {
          grid-template-columns: minmax(0, 1fr);
        }

        .archive-card__thumb-wrap,
        .archive-card--compact .archive-card__thumb-wrap {
          padding: 16px 16px 0;
        }

        .stat-grid,
        .detail-stats {
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }

        .stat-row {
          flex-direction: column;
          align-items: flex-start;
        }
      }
    `;
  }

  _render() {
    if (!this.shadowRoot || !this._config) {
      return;
    }

    const variant = this._variant();
    const showImages = this._showImages();
    const archives = this._getArchives();
    const gridClass = variant === "Detail" ? "grid grid--detail" : "grid grid--default";

    const archiveButtons = archives.length
      ? archives
          .map((archive, index) => this._renderArchiveCard(archive, index, variant, showImages))
          .join("")
      : '<div class="empty">No matching archives. Adjust filters or refresh the archive cache.</div>';

    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <ha-card>
        <div class="${gridClass}">${archiveButtons}</div>
      </ha-card>
    `;

    const archivesByKey = new Map(
      archives.map((archive, index) => [String(archive.id || `index-${index}`), archive])
    );

    this.shadowRoot.querySelectorAll(".archive-card").forEach((button) => {
      button.addEventListener("click", () => {
        const archive = archivesByKey.get(button.dataset.archiveKey || "");
        if (archive) {
          this._openArchivePopup(archive);
        }
      });
    });
  }
}

customElements.define("print-history-archive-grid-card", PrintHistoryArchiveGridCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "print-history-archive-grid-card",
  name: "Print History Archive Grid Card",
  description: "Responsive print-history archive grid with per-archive popup details.",
});