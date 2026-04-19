class PrintHistoryBrowserCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._querySignature = "";
    this._viewSignature = "";
    this._selectionSignature = "";
    this._queryToken = 0;
    this._refreshTimer = null;
    this._loading = false;
    this._error = "";
    this._response = { archives: [], query: {} };
    this._selectedArchiveIds = {};
    this._handledMultiSelectRequest = "";
    this._bulkDialog = null;
    this._bulkActionBusy = false;
    this._normalizedArchiveCache = {};
    this._mediaGalleryIndices = {};
    this._mediaSwipe = null;
    this._suppressOpenUntil = 0;
    this._suppressOpenArchiveId = "";
    this._debugStats = {
      scheduledRefreshes: 0,
      executedRefreshes: 0,
      coalescedRefreshes: 0,
    };
    this._boundClickHandler = this._handleClick.bind(this);
    this._boundKeydownHandler = this._handleKeydown.bind(this);
    this._boundPointerDownHandler = this._handlePointerDown.bind(this);
    this._boundPointerUpHandler = this._handlePointerUp.bind(this);
    this._boundPointerCancelHandler = this._handlePointerCancel.bind(this);
    this._boundMouseOverHandler = this._handleMouseOver.bind(this);
    this._boundMouseOutHandler = this._handleMouseOut.bind(this);
    this._boundFocusInHandler = this._handleFocusIn.bind(this);
    this._boundFocusOutHandler = this._handleFocusOut.bind(this);
    this._boundTooltipLayoutHandler = this._handleTooltipLayout.bind(this);
  }

  setConfig(config) {
    this._config = {
      title: config && config.title ? config.title : "Print History",
      hide_title: !!(config && config.hide_title),
      show_empty_state: !config || config.show_empty_state !== false,
      variant_entity: config && config.variant_entity ? config.variant_entity : "input_select.print_history_card_variant",
      show_images_entity: config && config.show_images_entity ? config.show_images_entity : "input_boolean.print_history_show_images",
      page_entity: config && config.page_entity ? config.page_entity : "input_number.history_current_page",
      page_size_entity: config && config.page_size_entity ? config.page_size_entity : "input_number.print_history_page_size",
      api_base_entity: config && config.api_base_entity ? config.api_base_entity : "input_text.bambuddy_api_base_url",
      browser_status_entity: config && config.browser_status_entity ? config.browser_status_entity : "sensor.bambuddy_print_history_browser_status",
      filtered_entity: config && config.filtered_entity ? config.filtered_entity : "sensor.bambuddy_print_history_browser_filtered",
      page_info_entity: config && config.page_info_entity ? config.page_info_entity : "sensor.bambuddy_print_history_browser_page_info",
    };
    this._querySignature = "";
    this._viewSignature = "";
    this._selectionSignature = "";
    this._selectedArchiveIds = {};
    this._handledMultiSelectRequest = "";
    this._bulkDialog = null;
    this._bulkActionBusy = false;
    this._normalizedArchiveCache = {};
    this._renderShell();
    this._queueRefresh();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) {
      return;
    }

    var nextQuerySignature = this._buildQuerySignature(hass);
    var nextViewSignature = this._buildViewSignature(hass);
    var nextSelectionSignature = this._buildSelectionSignature(hass);
    var selectionChanged = nextSelectionSignature !== this._selectionSignature;

    if (nextQuerySignature !== this._querySignature) {
      this._querySignature = nextQuerySignature;
      this._selectionSignature = nextSelectionSignature;
      this._queueRefresh();
      return;
    }

    if (nextViewSignature !== this._viewSignature) {
      this._viewSignature = nextViewSignature;
      this._renderBody();
    }

    if (selectionChanged) {
      this._selectionSignature = nextSelectionSignature;
      this._applySelectionOnlyState();
    }
  }

  connectedCallback() {
    this.shadowRoot.addEventListener("click", this._boundClickHandler);
    this.shadowRoot.addEventListener("keydown", this._boundKeydownHandler);
    this.shadowRoot.addEventListener("pointerdown", this._boundPointerDownHandler);
    this.shadowRoot.addEventListener("pointerup", this._boundPointerUpHandler);
    this.shadowRoot.addEventListener("pointercancel", this._boundPointerCancelHandler);
    this.shadowRoot.addEventListener("mouseover", this._boundMouseOverHandler);
    this.shadowRoot.addEventListener("mouseout", this._boundMouseOutHandler);
    this.shadowRoot.addEventListener("focusin", this._boundFocusInHandler);
    this.shadowRoot.addEventListener("focusout", this._boundFocusOutHandler);
    window.addEventListener("resize", this._boundTooltipLayoutHandler);
    window.addEventListener("scroll", this._boundTooltipLayoutHandler, true);
  }

  disconnectedCallback() {
    this.shadowRoot.removeEventListener("click", this._boundClickHandler);
    this.shadowRoot.removeEventListener("keydown", this._boundKeydownHandler);
    this.shadowRoot.removeEventListener("pointerdown", this._boundPointerDownHandler);
    this.shadowRoot.removeEventListener("pointerup", this._boundPointerUpHandler);
    this.shadowRoot.removeEventListener("pointercancel", this._boundPointerCancelHandler);
    this.shadowRoot.removeEventListener("mouseover", this._boundMouseOverHandler);
    this.shadowRoot.removeEventListener("mouseout", this._boundMouseOutHandler);
    this.shadowRoot.removeEventListener("focusin", this._boundFocusInHandler);
    this.shadowRoot.removeEventListener("focusout", this._boundFocusOutHandler);
    window.removeEventListener("resize", this._boundTooltipLayoutHandler);
    window.removeEventListener("scroll", this._boundTooltipLayoutHandler, true);
    if (this._refreshTimer) {
      clearTimeout(this._refreshTimer);
      this._refreshTimer = null;
    }
  }

  getCardSize() {
    return 10;
  }

  _renderShell() {
    this.shadowRoot.innerHTML = "" +
      "<style>" +
      "ha-card{padding:14px 14px 16px;}" +
      ".title{font-size:1rem;font-weight:700;margin:0 0 12px;}" +
      ".status{padding:18px;border-radius:18px;background:rgba(148,163,184,0.12);color:var(--secondary-text-color);line-height:1.5;}" +
      ".status.error{color:var(--error-color);}" +
      ".grid{display:grid;gap:16px;}" +
      ".grid.compact{grid-template-columns:repeat(auto-fit,minmax(360px,1fr));}" +
      ".grid.media{grid-template-columns:repeat(auto-fit,minmax(320px,1fr));}" +
      ".grid.list{grid-template-columns:1fr;}" +
      ".grid.loading{pointer-events:none;}" +
      ".card{position:relative;z-index:0;border:1px solid color-mix(in srgb, var(--divider-color) 78%, rgba(255,255,255,0.12));border-radius:22px;background:linear-gradient(180deg, color-mix(in srgb, var(--ha-card-background,var(--card-background-color)) 95%, rgba(255,255,255,0.04)), color-mix(in srgb, var(--ha-card-background,var(--card-background-color)) 99%, rgba(255,255,255,0.01)));overflow:visible;cursor:pointer;transition:border-color .16s ease, box-shadow .16s ease, background .16s ease, z-index .16s ease;}" +
      ".card::before{content:'';position:absolute;inset:0;border-radius:inherit;box-shadow:inset 0 0 0 1px rgba(255,255,255,0.08);opacity:0;transition:opacity .16s ease;pointer-events:none;}" +
      ".card::after{content:'';position:absolute;left:0;top:0;bottom:0;width:5px;opacity:0;transition:opacity .16s ease, background .16s ease;pointer-events:none;}" +
      ".card:hover,.card:focus-visible,.card:focus-within{z-index:3;border-color:color-mix(in srgb, var(--secondary-text-color) 22%, var(--divider-color));box-shadow:0 0 0 1px rgba(255,255,255,0.05), 0 10px 22px rgba(15,23,42,0.10);background:linear-gradient(180deg, color-mix(in srgb, var(--ha-card-background,var(--card-background-color)) 86%, rgba(148,163,184,0.18)), color-mix(in srgb, var(--ha-card-background,var(--card-background-color)) 92%, rgba(148,163,184,0.10)));}" +
      ".card:hover::before,.card:focus-visible::before,.card:focus-within::before{opacity:1;}" +
      ".card:active{box-shadow:0 0 0 1px rgba(255,255,255,0.06), 0 6px 14px rgba(15,23,42,0.10);background:linear-gradient(180deg, color-mix(in srgb, var(--ha-card-background,var(--card-background-color)) 82%, rgba(148,163,184,0.20)), color-mix(in srgb, var(--ha-card-background,var(--card-background-color)) 90%, rgba(148,163,184,0.12)));}" +
      ".card:focus-visible{outline:none;}" +
      ".card.archive-error-warning::after{opacity:1;background:#EF6C00;}" +
      ".card.archive-error-error::after{opacity:1;background:#C62828;}" +
      ".card.duplicate-source{border-color:color-mix(in srgb, #1565C0 34%, var(--divider-color));}" +
      ".card.duplicate-source::after{opacity:1;background:#1565C0;}" +
      ".card.duplicate-copy{border-color:color-mix(in srgb, #00897B 34%, var(--divider-color));}" +
      ".card.duplicate-copy::after{opacity:1;background:#00897B;}" +
      ".card.related-match{border-color:color-mix(in srgb, #6D4C41 34%, var(--divider-color));}" +
      ".card.related-match::after{opacity:1;background:#6D4C41;}" +
      ".card-shell{display:grid;gap:16px;padding:18px;min-width:0;}" +
      ".card-shell.compact{grid-template-columns:minmax(148px,188px) minmax(0,1fr);align-items:start;}" +
      ".card-shell.compact.no-image{grid-template-columns:minmax(0,1fr);}" +
      ".card-shell.compact{grid-template-columns:minmax(150px,188px) minmax(0,1fr);grid-template-areas:'thumb summary' 'name name' 'details details';column-gap:18px;row-gap:14px;align-items:start;}" +
      ".card-shell.compact.no-image{grid-template-columns:minmax(0,1fr);grid-template-areas:'summary' 'name' 'details';}" +
      ".card-shell.media{grid-template-columns:minmax(0,1fr);min-height:320px;row-gap:14px;}" +
      ".card-shell.list{grid-template-columns:minmax(112px,132px) minmax(0,1fr);align-items:center;column-gap:14px;row-gap:8px;min-height:148px;}" +
      ".card-shell.list.no-image{grid-template-columns:minmax(0,1fr);}" +
      ".thumb-wrap{width:100%;min-width:0;}" +
      ".card-shell.compact .thumb-wrap{grid-area:thumb;align-self:start;}" +
      ".thumb{width:100%;height:132px;object-fit:cover;border-radius:16px;display:block;background:rgba(15,23,42,0.18);}" +
      ".card-shell.media .thumb-wrap{position:relative;}" +
      ".card-shell.list .thumb-wrap{position:relative;align-self:stretch;}" +
      ".media-gallery-surface{position:relative;border-radius:16px;overflow:hidden;background:linear-gradient(180deg,rgba(15,23,42,0.18),rgba(15,23,42,0.08));}" +
      ".thumb.media{height:228px;object-fit:contain;padding:10px;background:rgba(255,255,255,0.04);}" +
      ".thumb.list-thumb{height:116px;object-fit:contain;padding:8px;background:rgba(255,255,255,0.04);}" +
      ".media-gallery-surface .thumb.media{display:block;width:100%;}" +
      ".media-gallery-surface .thumb.list-thumb{display:block;width:100%;}" +
      ".media-thumb-empty{height:228px;display:flex;align-items:center;justify-content:center;padding:24px;text-align:center;color:var(--secondary-text-color);background:rgba(255,255,255,0.04);}" +
      ".list-thumb-empty{height:116px;display:flex;align-items:center;justify-content:center;padding:14px;text-align:center;color:var(--secondary-text-color);background:rgba(255,255,255,0.04);font-size:12px;}" +
      ".media-thumb-overlay{position:absolute;inset:12px 12px auto 12px;display:flex;align-items:flex-start;justify-content:space-between;gap:12px;pointer-events:none;z-index:2;}" +
      ".media-thumb-overlay .action-buttons{pointer-events:auto;}" +
      ".media-thumb-overlay .icon-action,.media-thumb-overlay .chip.icon-chip{background:rgba(15,23,42,0.56);border:1px solid rgba(255,255,255,0.10);backdrop-filter:blur(8px);}" +
      ".media-archive-pill{display:inline-flex;align-items:center;min-height:28px;padding:0 12px;border-radius:999px;background:rgba(15,23,42,0.58);border:1px solid rgba(255,255,255,0.12);backdrop-filter:blur(8px);color:#fff;font-size:12px;font-weight:700;line-height:1.1;white-space:nowrap;max-width:100%;}" +
      ".media-gallery-nav{position:absolute;left:10px;right:10px;top:50%;display:flex;align-items:center;justify-content:space-between;transform:translateY(-50%);pointer-events:none;z-index:2;}" +
      ".media-gallery-nav .icon-action{pointer-events:auto;background:rgba(15,23,42,0.56);border:1px solid rgba(255,255,255,0.10);backdrop-filter:blur(8px);}" +
      ".media-gallery-status{position:absolute;left:50%;bottom:12px;transform:translateX(-50%);display:inline-flex;align-items:center;min-height:24px;padding:0 10px;border-radius:999px;background:rgba(15,23,42,0.58);border:1px solid rgba(255,255,255,0.10);color:#fff;font-size:11px;font-weight:700;line-height:1.1;backdrop-filter:blur(8px);z-index:2;pointer-events:none;}" +
      ".media-header{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;column-gap:16px;row-gap:8px;}" +
      ".media-title-wrap{min-width:0;}" +
      ".media-status-line{display:flex;flex-wrap:wrap;align-items:center;justify-content:flex-end;gap:8px;min-width:0;}" +
      ".media-date{font-size:12px;font-weight:600;white-space:nowrap;}" +
      ".chip-row.media-meta-line{align-items:center;gap:8px;}" +
      ".content.list-content{gap:8px;align-self:center;}" +
      ".list-header{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;column-gap:12px;row-gap:6px;}" +
      ".list-title-wrap{min-width:0;}" +
      ".list-header-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;flex-wrap:wrap;min-width:0;}" +
      ".list-header-actions .chip{white-space:nowrap;}" +
      ".list-header-actions .action-buttons{gap:6px;}" +
      ".list-subheader{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px 12px;min-width:0;}" +
      ".list-status-line{display:flex;flex-wrap:wrap;align-items:center;justify-content:flex-end;gap:8px;min-width:0;}" +
      ".chip-row.list-meta-line{align-items:center;gap:8px;}" +
      ".list-bottom-row{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;min-width:0;}" +
      ".list-bottom-row .dots{flex:0 0 auto;}" +
      ".list-inline-tag-project{display:flex;flex-wrap:wrap;align-items:center;gap:8px;min-width:0;flex:1 1 240px;}" +
      ".list-inline-tag-project .tags{min-width:0;}" +
      ".list-inline-tag-project .project-chip{max-width:180px;}" +
      ".list-chip-mobile-hide{display:inline-flex;}" +
      ".list-row-mobile-hide{display:flex;}" +
      ".card-shell.compact .thumb{height:136px;}" +
      ".content{display:flex;flex-direction:column;gap:10px;min-width:0;}" +
      ".content.compact-summary{grid-area:summary;gap:8px;align-self:start;}" +
      ".content.compact-name{grid-area:name;gap:6px;padding-top:2px;}" +
      ".content.compact-details{grid-area:details;gap:10px;min-width:0;}" +
      ".content-top{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;min-width:0;}" +
      ".content-top.compact{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;column-gap:10px;min-width:0;}" +
      ".action-buttons{display:flex;align-items:center;justify-content:flex-end;gap:8px;flex:0 0 auto;}" +
      ".action-buttons.compact-actions{width:100%;justify-content:flex-end;}" +
      ".compact-archive-id{font-size:12px;line-height:1.2;font-weight:700;color:var(--secondary-text-color);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}" +
      ".role-emblem{display:inline-flex;align-items:center;gap:6px;margin:0 0 2px;padding:5px 10px;border-radius:999px;font-size:11px;font-weight:800;line-height:1.1;text-transform:uppercase;letter-spacing:0.05em;max-width:max-content;}" +
      ".role-emblem.source{background:rgba(21,101,192,0.14);color:#1565C0;}" +
      ".role-emblem.duplicate{background:rgba(0,137,123,0.16);color:#00897B;}" +
      ".role-emblem.related{background:rgba(109,76,65,0.16);color:#6D4C41;}" +
      ".header{display:flex;gap:10px;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;min-width:0;}" +
      ".header.compact{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;column-gap:12px;row-gap:8px;}" +
      ".name{font-size:18px;font-weight:700;line-height:1.2;overflow-wrap:anywhere;word-break:break-word;}" +
      ".name-note-inline{display:inline-flex;align-items:center;justify-content:center;vertical-align:middle;position:relative;top:-3px;margin-left:6px;color:var(--primary-color, var(--accent-color, #03a9f4));}" +
      ".name-note-inline ha-icon{--mdc-icon-size:14px;width:14px;height:14px;min-width:14px;min-height:14px;display:block;}" +
      ".subtle{font-size:12px;color:var(--secondary-text-color);overflow-wrap:anywhere;}" +
      ".chip-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;min-width:0;}" +
      ".chip-row.compact-primary{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;column-gap:12px;row-gap:8px;}" +
      ".chip-row.compact-secondary{gap:6px;}" +
      ".chip-row.compact-status-line{display:flex;flex-wrap:wrap;align-items:center;justify-content:flex-start;gap:6px 8px;min-width:0;}" +
      ".chip-row.compact-meta-line{justify-content:flex-start;align-items:center;gap:8px;}" +
      ".compact-date{font-size:12px;color:var(--secondary-text-color);font-weight:600;line-height:1.2;white-space:nowrap;flex:0 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;}" +
      ".color-enrichment-row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;column-gap:12px;row-gap:8px;}" +
      ".color-enrichment-row .dots{min-width:0;}" +
      ".tag-project-row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;column-gap:12px;row-gap:8px;min-width:0;}" +
      ".tag-project-row .tags{min-width:0;}" +
      ".tag-project-row .project-chip{justify-self:end;}" +
      ".chip{display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border-radius:999px;background:rgba(255,255,255,0.05);color:var(--primary-text-color);font-size:11px;font-weight:600;line-height:1.2;min-width:0;max-width:100%;overflow-wrap:anywhere;}" +
        ".interactive-chip{appearance:none;-webkit-appearance:none;border:none;cursor:pointer;font-family:inherit;text-align:left;position:relative;transition:transform .16s ease,box-shadow .16s ease,background .16s ease,filter .16s ease,color .16s ease;}" +
      ".interactive-chip:hover,.interactive-chip:focus-visible{transform:translateY(-1px);filter:saturate(1.04);box-shadow:inset 0 0 0 1px var(--interactive-chip-border, rgba(255,255,255,0.55)),0 0 0 1px rgba(255,255,255,0.12),0 8px 18px rgba(15,23,42,0.12);}" +
      ".interactive-chip:focus-visible{outline:none;}" +
      ".interactive-chip:active{transform:translateY(0);}" +
      ".status-chip{color:#fff;font-weight:700;}" +
      ".status-chip.interactive-chip:hover,.status-chip.interactive-chip:focus-visible{background:color-mix(in srgb, var(--status-chip-background, #546E7A) 84%, rgba(255,255,255,0.12));}" +
      ".enrichment-chip.interactive-chip:hover,.enrichment-chip.interactive-chip:focus-visible{background:color-mix(in srgb, var(--enrichment-chip-background, #546E7A) 84%, rgba(255,255,255,0.12));}" +
      ".archive-error-chip{color:#fff;font-weight:700;}" +
      ".chip.icon-chip{position:relative;display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;min-width:30px;padding:0;border-radius:999px;flex:0 0 auto;line-height:0;}" +
      ".chip.icon-chip ha-icon{--mdc-icon-size:15px;width:15px;height:15px;min-width:15px;min-height:15px;display:block;}" +
      ".icon-chip-badge{position:absolute;top:-3px;right:-3px;min-width:15px;height:15px;padding:0 4px;border-radius:999px;background:#1565C0;color:#fff;font-size:9px;font-weight:800;line-height:15px;text-align:center;box-sizing:border-box;}" +
      ".project-chip{display:inline-flex;align-items:center;border:1px solid var(--project-chip-color, rgba(255,255,255,0.14));background:var(--project-chip-background, rgba(255,255,255,0.05));color:var(--primary-text-color);padding:3px 8px;gap:4px;min-height:24px;height:24px;font-size:10px;max-width:min(100%,180px);line-height:1;box-sizing:border-box;overflow:hidden;}" +
      ".project-chip ha-icon{color:var(--project-chip-color, var(--primary-text-color));--mdc-icon-size:11px;width:11px;height:11px;min-width:11px;flex:0 0 11px;}" +
      ".project-chip span{display:block;min-width:0;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}" +
      ".project-chip.interactive-chip:hover,.project-chip.interactive-chip:focus-visible{background:color-mix(in srgb, var(--project-chip-background, rgba(255,255,255,0.05)) 82%, rgba(255,255,255,0.12));}" +
      ".metrics{display:grid;gap:10px;}" +
      ".metrics.media{grid-template-columns:repeat(3,minmax(0,1fr));}" +
      ".metrics.compact,.metrics.list{grid-template-columns:repeat(auto-fit,minmax(116px,1fr));}" +
      ".metrics.compact-tight{grid-template-columns:repeat(3,minmax(0,1fr));}" +
      ".metrics.list{grid-template-columns:repeat(3,minmax(92px,1fr));gap:8px;}" +
      ".metric{padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.04);min-width:0;}" +
      ".card-shell.list .metric{padding:8px 10px;border-radius:14px;display:flex;align-items:center;justify-content:space-between;gap:10px;}" +
      ".card:hover .metric,.card:focus-visible .metric,.card:focus-within .metric{background:color-mix(in srgb, rgba(148,163,184,0.16) 100%, rgba(255,255,255,0.04));}" +
      ".metric-label{font-size:11px;color:var(--secondary-text-color);line-height:1.2;margin-bottom:4px;}" +
      ".metric-value{font-size:15px;font-weight:700;line-height:1.2;overflow-wrap:anywhere;}" +
      ".card-shell.list .metric-label{margin-bottom:0;white-space:nowrap;}" +
      ".card-shell.list .metric-value{font-size:14px;text-align:right;}" +
      "@keyframes printHistoryShimmer{0%{background-position:200% 0;}100%{background-position:-200% 0;}}" +
      ".skeleton-card{cursor:default;}" +
      ".skeleton-card:hover,.skeleton-card:focus-visible,.skeleton-card:focus-within,.skeleton-card:active{border-color:color-mix(in srgb, var(--divider-color) 78%, rgba(255,255,255,0.12));box-shadow:none;background:linear-gradient(180deg, color-mix(in srgb, var(--ha-card-background,var(--card-background-color)) 95%, rgba(255,255,255,0.04)), color-mix(in srgb, var(--ha-card-background,var(--card-background-color)) 99%, rgba(255,255,255,0.01)));}" +
      ".skeleton-card::before,.skeleton-card::after{display:none;}" +
      ".skeleton{position:relative;overflow:hidden;border-radius:14px;background:rgba(148,163,184,0.16);}" +
      ".skeleton::after{content:'';position:absolute;inset:0;background:linear-gradient(90deg, rgba(255,255,255,0), rgba(255,255,255,0.18), rgba(255,255,255,0));background-size:200% 100%;animation:printHistoryShimmer 1.35s ease-in-out infinite;}" +
      ".skeleton-pill{height:28px;border-radius:999px;}" +
      ".skeleton-dot{width:14px;height:14px;border-radius:999px;}" +
      ".skeleton-text{height:12px;}" +
      ".skeleton-text.title{height:22px;width:78%;}" +
      ".skeleton-text.subtitle{width:44%;}" +
      ".skeleton-text.medium{width:58%;}" +
      ".skeleton-text.long{width:100%;}" +
      ".skeleton-actions{display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap;}" +
      ".skeleton-icon{width:30px;height:30px;border-radius:999px;}" +
      ".skeleton-thumb{width:100%;height:132px;border-radius:16px;}" +
      ".skeleton-thumb.media{height:228px;}" +
      ".skeleton-thumb.list{height:116px;}" +
      ".skeleton-chip-group{display:flex;gap:8px;flex-wrap:wrap;align-items:center;min-width:0;}" +
      ".skeleton-metrics{display:grid;gap:10px;}" +
      ".skeleton-metrics.compact,.skeleton-metrics.media,.skeleton-metrics.list{grid-template-columns:repeat(3,minmax(0,1fr));}" +
      ".skeleton-metric{padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.04);display:grid;gap:8px;}" +
      ".card-shell.list .skeleton-metric{padding:8px 10px;border-radius:14px;}" +
      ".skeleton-metric .skeleton-text:first-child{width:58%;}" +
      ".skeleton-metric .skeleton-text:last-child{width:72%;height:16px;}" +
      ".dots,.tags{display:flex;gap:6px;flex-wrap:wrap;align-items:center;}" +
      ".dot-button{position:relative;z-index:1;display:inline-flex;align-items:center;justify-content:center;width:14px;height:14px;border-radius:999px;background:var(--dot-color, rgba(255,255,255,0.2));box-shadow:inset 0 0 0 1px rgba(255,255,255,0.25);flex:0 0 auto;outline:none;padding:0;min-width:14px;min-height:14px;}" +
      ".dot-button:focus-visible{box-shadow:inset 0 0 0 1px rgba(255,255,255,0.25),0 0 0 2px var(--primary-color, var(--accent-color, #03a9f4));}" +
      ".dot-button.tooltip-active,.dot-button:hover,.dot-button:focus-visible{z-index:4;}" +
      ".dot-button.interactive-chip:hover,.dot-button.interactive-chip:focus-visible{transform:translateY(-1px) scale(1.08);}" +
      ".dot-button.interactive-chip:active{transform:translateY(0) scale(1.02);}" +
      ".dot-tooltip{position:absolute;left:50%;bottom:calc(100% + 8px);display:block;width:max-content;min-width:min(180px, calc(100vw - 16px));max-width:min(320px, calc(100vw - 16px));transform:translateX(calc(-50% + var(--dot-tooltip-shift, 0px))) translateY(4px);background:rgba(17,24,39,0.94);color:#f9fafb;border-radius:14px;padding:6px 10px;font-size:11px;line-height:1.35;white-space:pre-line;pointer-events:none;opacity:0;transition:opacity .12s ease, transform .12s ease;z-index:4;overflow-wrap:break-word;word-break:normal;text-align:left;}" +
      ".dot-button.tooltip-active .dot-tooltip,.dot-button:hover .dot-tooltip,.dot-button:focus-visible .dot-tooltip{opacity:1;transform:translateX(calc(-50% + var(--dot-tooltip-shift, 0px))) translateY(0);}" +
      ".tag{border-radius:999px;padding:3px 8px;font-size:10px;background:var(--tag-background, rgba(148,163,184,0.16));box-shadow:inset 0 0 0 1px var(--tag-border-color, rgba(148,163,184,0.42)),0 0 0 1px transparent;color:var(--primary-text-color);transition:background .16s ease,box-shadow .16s ease;}" +
      ".tag.interactive-chip:hover,.tag.interactive-chip:focus-visible{background:color-mix(in srgb, var(--tag-background, rgba(148,163,184,0.16)) 88%, rgba(255,255,255,0.10));}" +
      ".icon-action{position:static;width:30px;height:30px;border:none;border-radius:999px;background:rgba(255,255,255,0.06);color:var(--secondary-text-color);cursor:pointer;display:flex;align-items:center;justify-content:center;z-index:2;flex:0 0 auto;transition:background .16s ease,color .16s ease,box-shadow .16s ease,transform .16s ease;}" +
      ".icon-action:hover,.icon-action:focus-visible{background:rgba(148,163,184,0.18);color:var(--primary-text-color);box-shadow:0 0 0 1px rgba(255,255,255,0.10);transform:translateY(-1px);outline:none;}" +
      ".icon-action:active{transform:translateY(0);}" +
      ".icon-action.viewer{background:rgba(0,137,123,0.16);color:#7dd3c8;}" +
      ".icon-action.viewer:hover,.icon-action.viewer:focus-visible{background:rgba(0,137,123,0.28);color:#b6fff3;box-shadow:0 0 0 1px rgba(125,211,200,0.26);transform:translateY(-1px);outline:none;}" +
      ".icon-action.viewer:active{transform:translateY(0);}" +
      ".favorite.active{background:rgba(245,194,66,0.22);color:#f5c242;box-shadow:0 0 0 1px rgba(245,194,66,0.18);}" +
      ".favorite.active:hover,.favorite.active:focus-visible{background:rgba(245,194,66,0.30);color:#ffd55f;box-shadow:0 0 0 1px rgba(245,194,66,0.26);}" +
      ".card.selection-mode{cursor:pointer;}" +
      ".card.selection-mode.selected{border-color:color-mix(in srgb, var(--primary-color, #1976d2) 48%, var(--divider-color));box-shadow:0 0 0 2px color-mix(in srgb, var(--primary-color, #1976d2) 28%, rgba(255,255,255,0.08)),0 12px 24px rgba(15,23,42,0.12);background:linear-gradient(180deg, color-mix(in srgb, var(--ha-card-background,var(--card-background-color)) 84%, rgba(25,118,210,0.16)), color-mix(in srgb, var(--ha-card-background,var(--card-background-color)) 92%, rgba(25,118,210,0.10)));}" +
      ".selection-badge{display:inline-flex;align-items:center;gap:6px;min-height:30px;padding:0 12px;border-radius:999px;background:rgba(15,23,42,0.32);border:1px solid rgba(255,255,255,0.12);color:var(--secondary-text-color);font-size:11px;font-weight:700;line-height:1.1;white-space:nowrap;}" +
      ".selection-badge ha-icon{--mdc-icon-size:15px;width:15px;height:15px;min-width:15px;min-height:15px;display:block;}" +
      ".selection-badge.active{background:rgba(25,118,210,0.18);border-color:rgba(25,118,210,0.44);color:var(--primary-text-color);}" +
      ".selection-meta{display:flex;align-items:center;justify-content:flex-end;gap:8px;flex:0 0 auto;}" +
      ".bulk-dialog-backdrop{position:fixed;inset:0;z-index:50;background:rgba(15,23,42,0.56);backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;padding:16px;box-sizing:border-box;}" +
      ".bulk-dialog{width:min(520px,100%);max-height:min(90vh,780px);overflow:auto;border-radius:24px;border:1px solid rgba(255,255,255,0.12);background:linear-gradient(180deg, color-mix(in srgb, var(--ha-card-background,var(--card-background-color)) 94%, rgba(255,255,255,0.06)), color-mix(in srgb, var(--ha-card-background,var(--card-background-color)) 98%, rgba(255,255,255,0.02)));box-shadow:0 18px 44px rgba(15,23,42,0.28);padding:22px;box-sizing:border-box;}" +
      ".bulk-dialog-header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:14px;}" +
      ".bulk-dialog-title{font-size:18px;font-weight:700;line-height:1.2;}" +
      ".bulk-dialog-subtle{font-size:12px;color:var(--secondary-text-color);line-height:1.45;}" +
      ".bulk-dialog-body{display:grid;gap:14px;}" +
      ".bulk-dialog-field{display:grid;gap:6px;}" +
      ".bulk-dialog-field label{font-size:12px;font-weight:700;color:var(--secondary-text-color);}" +
      ".bulk-dialog-field input,.bulk-dialog-field select{width:100%;min-height:42px;border-radius:14px;border:1px solid rgba(148,163,184,0.34);background:var(--card-background-color,var(--ha-card-background,var(--primary-background-color)));color:var(--primary-text-color);padding:0 14px;box-sizing:border-box;font:inherit;}" +
      ".bulk-dialog-field select{appearance:auto;-webkit-appearance:menulist;color-scheme:light dark;}" +
      ".bulk-dialog-field select option,.bulk-dialog-field select optgroup{background:var(--card-background-color,var(--ha-card-background,var(--primary-background-color)));color:var(--primary-text-color);}" +
      ".bulk-dialog-field input:focus,.bulk-dialog-field select:focus{outline:none;border-color:color-mix(in srgb, var(--primary-color, #1976d2) 54%, rgba(148,163,184,0.34));box-shadow:0 0 0 2px color-mix(in srgb, var(--primary-color, #1976d2) 22%, transparent);}" +
      ".bulk-dialog-actions{display:flex;align-items:center;justify-content:flex-end;gap:10px;margin-top:18px;flex-wrap:wrap;}" +
      ".bulk-dialog-button{appearance:none;-webkit-appearance:none;border:none;border-radius:999px;min-height:38px;padding:0 16px;background:rgba(255,255,255,0.08);color:var(--primary-text-color);font:inherit;font-weight:700;cursor:pointer;transition:transform .16s ease,background .16s ease,box-shadow .16s ease;}" +
      ".bulk-dialog-button:hover,.bulk-dialog-button:focus-visible{outline:none;transform:translateY(-1px);background:rgba(255,255,255,0.12);box-shadow:0 0 0 1px rgba(255,255,255,0.12);}" +
      ".bulk-dialog-button:active{transform:translateY(0);}" +
      ".bulk-dialog-button.primary{background:color-mix(in srgb, var(--primary-color, #1976d2) 88%, rgba(255,255,255,0.12));color:#fff;}" +
      ".bulk-dialog-button.danger{background:rgba(198,40,40,0.18);color:#ffd7d7;}" +
      ".bulk-dialog-button[disabled]{opacity:.52;pointer-events:none;cursor:default;transform:none;box-shadow:none;}" +
      ".archive-error-text{font-size:12px;line-height:1.45;overflow-wrap:anywhere;}" +
      ".archive-error-text.warning{color:#FFD89B;}" +
      ".archive-error-text.error{color:#FFB4AB;}" +
      ".failure{font-size:12px;color:#ffb4ab;line-height:1.4;overflow-wrap:anywhere;}" +
      "@media (max-width: 760px){.card-shell.compact{grid-template-columns:minmax(132px,164px) minmax(0,1fr);}.header.compact,.chip-row.compact-primary,.tag-project-row,.media-header,.list-header{grid-template-columns:minmax(0,1fr);}.metrics.compact-tight{grid-template-columns:repeat(auto-fit,minmax(102px,1fr));}.tag-project-row .project-chip{justify-self:start;}.media-status-line,.list-status-line{justify-content:flex-start;}.list-chip-mobile-hide{display:none;}.list-inline-tag-project .project-chip{max-width:140px;}.list-header-actions{justify-content:flex-start;}.list-subheader{justify-content:flex-start;}}" +
      "@media (max-width: 560px){.card-shell.compact{grid-template-columns:1fr;grid-template-areas:'summary' 'thumb' 'name' 'details';}.card-shell.compact .thumb{max-width:188px;}.content-top.compact{grid-template-columns:minmax(0,1fr);row-gap:8px;}.action-buttons.compact-actions{justify-content:flex-start;}.tag-project-row .project-chip{max-width:100%;}.card-shell.list{grid-template-columns:92px minmax(0,1fr);column-gap:10px;padding:14px;}.thumb.list-thumb,.list-thumb-empty{height:92px;}.list-row-mobile-hide{display:none;}.metrics.list{grid-template-columns:1fr;}.list-header-actions .chip{order:-1;}.list-header-actions .action-buttons{justify-content:flex-start;}}" +
      "</style>" +
      "<ha-card>" +
      (this._config && this._config.hide_title ? "" : '<div class="title"></div>') +
      '<div id="body" class="status">Loading print history…</div>' +
      '<div id="dialog-host"></div>' +
      "</ha-card>";

    var titleNode = this.shadowRoot.querySelector(".title");
    if (titleNode && this._config) {
      titleNode.textContent = this._config.title;
    }
  }

  _buildQuerySignature(hass) {
    return JSON.stringify({
      status: this._stateValue("input_select.print_history_filter_status"),
      archiveError: this._stateValue("input_select.print_history_filter_archive_error"),
      enrichmentStatus: this._stateValue("input_select.print_history_filter_enrichment_status"),
      material: this._stateValue("input_select.print_history_filter_material"),
      printer: this._stateValue("input_select.print_history_filter_printer"),
      dateRange: this._stateValue("input_select.print_history_filter_date_range"),
      startDate: this._stateValue("input_text.print_history_filter_start_date"),
      endDate: this._stateValue("input_text.print_history_filter_end_date"),
      designer: this._stateValue("input_select.print_history_filter_designer"),
      project: this._stateValue("input_select.print_history_filter_project"),
      layerHeight: this._stateValue("input_select.print_history_filter_layer_height"),
      tags: this._stateValue("input_text.print_history_filter_tags"),
      tagMode: this._stateValue("input_select.print_history_filter_tags_mode"),
      tagUntaggedOnly: this._stateValue("input_boolean.print_history_filter_tags_untagged_only"),
      favoritesOnly: this._stateValue("input_boolean.print_history_filter_favorites_only"),
      search: this._stateValue("input_text.print_history_search"),
      colors: this._stateValue("input_text.print_history_filter_colors"),
      sort: this._stateValue("input_select.print_history_sort"),
      page: this._stateValue(this._config.page_entity),
      pageSize: this._stateValue(this._config.page_size_entity),
      filteredRevision: this._entityAttribute(this._config.filtered_entity, "browser_revision"),
      pageInfoRevision: this._entityAttribute(this._config.page_info_entity, "browser_revision"),
    });
  }

  _buildViewSignature() {
    return JSON.stringify({
      variant: this._variant(),
      showImages: this._showImages(),
      apiBase: this._apiBaseUrl(),
      count: Array.isArray(this._response.archives) ? this._response.archives.length : 0,
      error: this._error,
      loading: this._loading,
    });
  }

  _buildSelectionSignature() {
    return JSON.stringify({
      mode: this._isMultiSelectMode(),
      request: String(this._stateValue("input_text.print_history_multi_select_request") || "").trim(),
    });
  }

  _entityAttribute(entityId, attribute) {
    var entity = this._hass && this._hass.states ? this._hass.states[entityId] : null;
    return entity && entity.attributes ? String(entity.attributes[attribute] || "") : "";
  }

  _stateValue(entityId) {
    var entity = this._hass && this._hass.states ? this._hass.states[entityId] : null;
    return entity ? entity.state : "";
  }

  _queueRefresh() {
    if (!this._hass || !this._config) {
      return;
    }
    this._debugStats.scheduledRefreshes += 1;
    if (this._refreshTimer) {
      this._debugStats.coalescedRefreshes += 1;
      clearTimeout(this._refreshTimer);
    }
    this._loading = true;
    this._error = "";
    this._renderBody();
    this._refreshTimer = setTimeout(function () {
      this._refreshTimer = null;
      this._debugStats.executedRefreshes += 1;
      this._refreshData();
    }.bind(this), 180);
  }

  async _refreshData() {
    var token = ++this._queryToken;
    var started = typeof performance !== "undefined" && typeof performance.now === "function" ? performance.now() : Date.now();
    try {
      var response = await this._hass.callWS(this._buildQueryPayload());
      if (token !== this._queryToken) {
        return;
      }
      this._response = response && typeof response === "object" ? response : { archives: [], query: {} };
      this._pruneNormalizedArchiveCache(this._response.archives);
      this._error = "";
      this._recordDebug("browser", response, started);
    } catch (error) {
      if (token !== this._queryToken) {
        return;
      }
      this._response = { archives: [], query: {} };
      this._error = error && error.message ? error.message : String(error);
      this._recordDebug("browser_error", { error: this._error }, started);
    }
    this._loading = false;
    this._viewSignature = this._buildViewSignature(this._hass);
    this._renderBody();
  }

  _debugEnabled() {
    return this._stateValue("input_boolean.print_history_debug_instrumentation") === "on";
  }

  _recordDebug(channel, response, started) {
    if (!this._debugEnabled()) {
      return;
    }
    var ended = typeof performance !== "undefined" && typeof performance.now === "function" ? performance.now() : Date.now();
    var payload = {
      at: new Date().toISOString(),
      channel: channel,
      roundTripMs: Math.round((ended - started) * 10) / 10,
      pageItemCount: Array.isArray(this._response.archives) ? this._response.archives.length : 0,
      filteredCount: this._response && this._response.query ? this._response.query.filtered_count : null,
      scheduledRefreshes: this._debugStats.scheduledRefreshes,
      executedRefreshes: this._debugStats.executedRefreshes,
      coalescedRefreshes: this._debugStats.coalescedRefreshes,
      backend: response && response.debug ? response.debug : null,
      store: response && response.store ? response.store : null,
      error: response && response.error ? response.error : null,
    };
    window.__printHistoryDebug = window.__printHistoryDebug || { events: [], latest: {} };
    window.__printHistoryDebug.events.push(payload);
    if (window.__printHistoryDebug.events.length > 100) {
      window.__printHistoryDebug.events.shift();
    }
    window.__printHistoryDebug.latest[channel] = payload;
    if (typeof console !== "undefined" && typeof console.debug === "function") {
      console.debug("[print-history-debug]", payload);
    }
  }

  _buildQueryPayload() {
    return {
      type: "bambuddy/print_history_query",
      status: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_status")),
      archive_error: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_archive_error")),
      enrichment_status: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_enrichment_status")),
      material: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_material")),
      printer: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_printer")),
      date_range: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_date_range")),
      start_date: String(this._stateValue("input_text.print_history_filter_start_date") || "").trim(),
      end_date: String(this._stateValue("input_text.print_history_filter_end_date") || "").trim(),
      designer: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_designer")),
      project: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_project")),
      layer_height: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_layer_height")),
      tags: String(this._stateValue("input_text.print_history_filter_tags") || "").trim(),
      tag_mode: this._normalizeTagModeValue(this._stateValue("input_select.print_history_filter_tags_mode")),
      tag_untagged_only: this._stateValue("input_boolean.print_history_filter_tags_untagged_only") === "on",
      favorites_only: this._stateValue("input_boolean.print_history_filter_favorites_only") === "on",
      search: String(this._stateValue("input_text.print_history_search") || "").trim(),
      colors: String(this._stateValue("input_text.print_history_filter_colors") || "").trim(),
      sort: this._normalizeFilterValue(this._stateValue("input_select.print_history_sort")),
      page: Math.max(1, Number(this._stateValue(this._config.page_entity) || 1)),
      page_size: Math.max(1, Number(this._stateValue(this._config.page_size_entity) || 1)),
    };
  }

  _normalizeFilterValue(value) {
    var normalized = String(value || "").trim();
    if (!normalized || normalized === "All") {
      return "";
    }
    return normalized;
  }

  _normalizeTagModeValue(value) {
    return String(value || "").trim() === "All" ? "All" : "Any";
  }

  _variant() {
    var value = String(this._stateValue(this._config.variant_entity) || "Compact");
    return ["Compact", "Media", "List"].indexOf(value) >= 0 ? value : "Compact";
  }

  _showImages() {
    return this._stateValue(this._config.show_images_entity) !== "off";
  }

  _apiBaseUrl() {
    return String(this._stateValue(this._config.api_base_entity) || "").replace(/\/$/, "");
  }

  _isMultiSelectMode() {
    return this._stateValue("input_boolean.print_history_multi_select_mode") === "on";
  }

  _selectedArchiveIdList() {
    return Object.keys(this._selectedArchiveIds || {}).filter(function (archiveId) {
      return !!this._selectedArchiveIds[archiveId];
    }.bind(this));
  }

  _selectedArchiveIdsCsv() {
    return this._selectedArchiveIdList().join(",");
  }

  _selectedArchiveCount() {
    return this._selectedArchiveIdList().length;
  }

  _archiveById(archiveId) {
    var archives = Array.isArray(this._response.archives) ? this._response.archives : [];
    for (var index = 0; index < archives.length; index += 1) {
      if (String(archives[index] && archives[index].id || "") === String(archiveId || "")) {
        return archives[index];
      }
    }
    return null;
  }

  _selectedArchivesAllFavorites() {
    var selectedIds = this._selectedArchiveIdList();
    if (!selectedIds.length) {
      return false;
    }
    for (var index = 0; index < selectedIds.length; index += 1) {
      var archive = this._archiveById(selectedIds[index]);
      if (!archive || !archive.is_favorite) {
        return false;
      }
    }
    return true;
  }

  _syncMultiSelectSummary() {
    if (!this._hass) {
      return;
    }
    var selectedCount = this._selectedArchiveCount();
    var helperCount = Math.max(0, Number(this._stateValue("input_number.print_history_multi_select_count") || 0) || 0);
    if (selectedCount !== helperCount) {
      this._hass.callService("input_number", "set_value", {
        entity_id: "input_number.print_history_multi_select_count",
        value: selectedCount,
      });
    }
    var allFavorites = this._selectedArchivesAllFavorites();
    var helperAllFavorites = this._stateValue("input_boolean.print_history_multi_select_all_favorites") === "on";
    if (allFavorites !== helperAllFavorites) {
      this._hass.callService("input_boolean", allFavorites ? "turn_on" : "turn_off", {
        entity_id: "input_boolean.print_history_multi_select_all_favorites",
      });
    }
  }

  _clearLocalMultiSelectState() {
    this._selectedArchiveIds = {};
    this._bulkDialog = null;
    this._bulkActionBusy = false;
  }

  _reconcileMultiSelectState(archives) {
    if (!this._isMultiSelectMode()) {
      if (this._selectedArchiveCount() || this._bulkDialog) {
        this._clearLocalMultiSelectState();
      }
      this._syncMultiSelectSummary();
      return;
    }

    var visibleIds = {};
    (Array.isArray(archives) ? archives : []).forEach(function (archive) {
      var archiveId = String(archive && archive.id || "").trim();
      if (archiveId) {
        visibleIds[archiveId] = true;
      }
    });

    var nextSelection = {};
    Object.keys(this._selectedArchiveIds || {}).forEach(function (archiveId) {
      if (visibleIds[archiveId]) {
        nextSelection[archiveId] = true;
      }
    });
    this._selectedArchiveIds = nextSelection;
    this._syncMultiSelectSummary();
  }

  _applySelectionOnlyState() {
    this._renderBody();
    this._consumePendingMultiSelectRequest();
  }

  _renderBody() {
    var body = this.shadowRoot.getElementById("body");
    if (!body) {
      return;
    }

    if (this._loading) {
      var loadingVariant = this._variant();
      body.className = "grid " + loadingVariant.toLowerCase() + " loading";
      body.innerHTML = this._renderSkeletonGrid(loadingVariant);
      this._renderBulkDialog();
      return;
    }

    if (this._error) {
      body.className = "status error";
      body.textContent = this._error;
      this._renderBulkDialog();
      return;
    }

    var archives = Array.isArray(this._response.archives) ? this._response.archives : [];
    this._reconcileMultiSelectState(archives);
    if (!archives.length && this._config.show_empty_state) {
      body.className = "status";
      body.textContent = "No matching archives. Adjust filters or refresh the archive cache.";
      this._renderBulkDialog();
      return;
    }

    var variant = this._variant();
    var variantClass = variant.toLowerCase();
    body.className = "grid " + variantClass;
    body.innerHTML = archives.map(this._renderArchiveCard.bind(this, variant)).join("");
    this._renderBulkDialog();
  }

  _renderSkeletonGrid(variant) {
    var count = this._skeletonCardCount();
    var cards = [];
    for (var index = 0; index < count; index += 1) {
      cards.push(this._renderSkeletonCard(variant));
    }
    return cards.join("");
  }

  _skeletonCardCount() {
    var configured = Math.max(1, Number(this._stateValue(this._config.page_size_entity) || 0));
    return configured || 6;
  }

  _renderSkeletonCard(variant) {
    if (variant === "Media") {
      return '' +
        '<article class="card skeleton-card" aria-hidden="true">' +
          '<div class="card-shell media">' +
            '<div class="thumb-wrap"><div class="media-gallery-surface"><div class="skeleton skeleton-thumb media"></div><div class="media-thumb-overlay"><span class="skeleton skeleton-pill" style="width:72px;"></span><div class="skeleton-actions">' + this._renderSkeletonIcons(2) + '</div></div></div></div>' +
            '<div class="content">' +
              '<div class="header media-header"><div class="media-title-wrap"><div class="skeleton skeleton-text title"></div></div><div class="media-status-line"><div class="skeleton skeleton-text subtitle"></div><div class="skeleton skeleton-pill" style="width:102px;"></div></div></div>' +
              '<div class="skeleton-metrics media">' + this._renderSkeletonMetric() + this._renderSkeletonMetric() + this._renderSkeletonMetric() + '</div>' +
              '<div class="color-enrichment-row"><div class="skeleton-chip-group">' + this._renderSkeletonDots(3) + '</div><span class="skeleton skeleton-pill" style="width:126px;"></span></div>' +
            '</div>' +
          '</div>' +
        '</article>';
    }

    if (variant === "List") {
      return '' +
        '<article class="card skeleton-card" aria-hidden="true">' +
          '<div class="card-shell list">' +
            '<div class="thumb-wrap"><div class="media-gallery-surface"><div class="skeleton skeleton-thumb list"></div></div></div>' +
            '<div class="content list-content">' +
              '<div class="list-header"><div class="list-title-wrap"><div class="skeleton skeleton-text title"></div></div><div class="list-header-actions"><span class="skeleton skeleton-pill" style="width:62px;"></span><div class="skeleton-actions">' + this._renderSkeletonIcons(2) + '</div></div></div>' +
              '<div class="list-subheader"><div class="skeleton skeleton-text subtitle"></div><div class="list-status-line"><span class="skeleton skeleton-pill" style="width:108px;"></span></div></div>' +
              '<div class="skeleton-metrics list">' + this._renderSkeletonMetric() + this._renderSkeletonMetric() + this._renderSkeletonMetric() + '</div>' +
              '<div class="list-bottom-row list-row-mobile-hide"><div class="skeleton-chip-group">' + this._renderSkeletonDots(3) + '</div><span class="skeleton skeleton-pill" style="width:122px;"></span></div>' +
            '</div>' +
          '</div>' +
        '</article>';
    }

    return '' +
      '<article class="card skeleton-card" aria-hidden="true">' +
        '<div class="card-shell compact">' +
          '<div class="thumb-wrap"><div class="skeleton skeleton-thumb"></div></div>' +
          '<div class="content compact-summary"><div class="content-top compact"><span class="skeleton skeleton-pill" style="width:64px;"></span><div class="skeleton-actions">' + this._renderSkeletonIcons(2) + '</div></div><div class="chip-row compact-status-line"><span class="skeleton skeleton-text subtitle"></span><span class="skeleton skeleton-pill" style="width:102px;"></span></div></div>' +
          '<div class="content compact-name"><div class="skeleton skeleton-text title"></div></div>' +
          '<div class="content compact-details"><div class="skeleton-metrics compact">' + this._renderSkeletonMetric() + this._renderSkeletonMetric() + this._renderSkeletonMetric() + '</div><div class="color-enrichment-row"><div class="skeleton-chip-group">' + this._renderSkeletonDots(3) + '</div><span class="skeleton skeleton-pill" style="width:122px;"></span></div></div>' +
        '</div>' +
      '</article>';
  }

  _renderSkeletonMetric() {
    return '<div class="skeleton-metric"><div class="skeleton skeleton-text"></div><div class="skeleton skeleton-text"></div></div>';
  }

  _renderSkeletonIcons(count) {
    var icons = [];
    for (var index = 0; index < count; index += 1) {
      icons.push('<span class="skeleton skeleton-icon"></span>');
    }
    return icons.join("");
  }

  _renderSkeletonDots(count) {
    var dots = [];
    for (var index = 0; index < count; index += 1) {
      dots.push('<span class="skeleton skeleton-dot"></span>');
    }
    return dots.join("");
  }

  _renderArchiveCard(variant, archive) {
    var normalized = this._normalizeArchive(archive || {});
    var selectionMode = this._isMultiSelectMode();
    var archiveId = String(normalized.id || "");
    var isSelected = !!(selectionMode && archiveId && this._selectedArchiveIds[archiveId]);
    var showImages = this._showImages();
    var mediaShowsImages = variant === 'Media' ? true : showImages;
    var baseUrl = this._apiBaseUrl();
    var hasImage = showImages && !!normalized.thumbnailUrl(baseUrl);
    var archiveJson = this._escapeAttribute(JSON.stringify(archive || {}));
    var tags = normalized.userTags.slice(0, variant === "Media" || variant === "List" ? 4 : 6);
    var hiddenTagCount = Math.max(0, normalized.userTags.length - tags.length);
    var cardClass = "card" + (normalized.roleClass ? (" " + normalized.roleClass) : "") + (normalized.hasArchiveError ? (" archive-error archive-error-" + normalized.archiveErrorSeverity) : "") + (selectionMode ? " selection-mode" : "") + (isSelected ? " selected" : "");
    var statusChip = normalized.statusFilterValue
      ? '<button class="chip status-chip interactive-chip" type="button" data-action="apply-filter" data-filter-action="status_set" data-filter-value="' + this._escapeAttribute(normalized.statusFilterValue) + '" title="' + this._escapeAttribute(this._buildFilterActionTooltip('Status: ' + normalized.statusLabel, 'Click to filter by this status')) + '" aria-label="' + this._escapeAttribute('Status ' + normalized.statusLabel + '. Click to filter by this status.') + '" style="background:' + this._escapeAttribute(normalized.statusColor) + ';--status-chip-background:' + this._escapeAttribute(normalized.statusColor) + ';--interactive-chip-border:rgba(255,255,255,0.68);">' + this._escapeHtml(normalized.statusIcon + ' ' + normalized.statusLabel) + '</button>'
      : '<div class="chip status-chip" style="background:' + this._escapeAttribute(normalized.statusColor) + ';">' + this._escapeHtml(normalized.statusIcon + ' ' + normalized.statusLabel) + '</div>';
    var projectChip = normalized.projectLabel
      ? '<button class="chip project-chip interactive-chip" type="button" data-action="apply-filter" data-filter-action="project_set" data-filter-value="' + this._escapeAttribute(normalized.projectLabel) + '" style="--project-chip-color:' + this._escapeAttribute(normalized.projectColor) + ';--project-chip-background:' + this._escapeAttribute(normalized.projectBackground) + ';--interactive-chip-border:' + this._escapeAttribute(normalized.projectColor) + ';" title="' + this._escapeAttribute(this._buildFilterActionTooltip('Project: ' + normalized.projectLabel, 'Click to filter by this project')) + '" aria-label="' + this._escapeAttribute('Project ' + normalized.projectLabel + '. Click to filter by this project.') + '"><ha-icon icon="mdi:folder-outline"></ha-icon><span>' + this._escapeHtml(normalized.projectLabel) + '</span></button>'
      : '';
    var compactArchiveId = normalized.compactArchiveIdLabel ? '<span class="compact-archive-id">' + this._escapeHtml(normalized.compactArchiveIdLabel) + '</span>' : '';
    var noteInline = normalized.noteText
      ? '<span class="name-note-inline" title="' + this._escapeAttribute(normalized.noteText) + '"><ha-icon icon="mdi:note-text-outline"></ha-icon></span>'
      : '';
    var photoAction = normalized.photoCount > 0
      ? '<span class="chip icon-chip" title="' + this._escapeAttribute(normalized.photoCountLabel) + '"><ha-icon icon="mdi:image-multiple-outline"></ha-icon><span class="icon-chip-badge">' + this._escapeHtml(String(normalized.photoCount)) + '</span></span>'
      : '';
    var selectionBadge = selectionMode
      ? '<span class="selection-badge' + (isSelected ? ' active' : '') + '" aria-hidden="true"><ha-icon icon="' + (isSelected ? 'mdi:checkbox-marked-circle' : 'mdi:checkbox-blank-circle-outline') + '"></ha-icon>' + this._escapeHtml(isSelected ? 'Selected' : 'Select') + '</span>'
      : '';
    var mediaArchivePill = normalized.compactArchiveIdLabel ? '<span class="media-archive-pill">' + this._escapeHtml(normalized.compactArchiveIdLabel) + '</span>' : '';
    var listHeaderId = normalized.compactArchiveIdLabel ? '<span class="chip">' + this._escapeHtml(normalized.compactArchiveIdLabel) + '</span>' : '';
    var favoriteButton = this._renderFavoriteButton(normalized, archiveJson);
    var listHeaderActions = '<div class="list-header-actions">'
      + listHeaderId
      + '<div class="action-buttons">'
      + (selectionMode ? selectionBadge : this._renderPrimaryActionButtons(normalized, archiveJson, favoriteButton, photoAction))
      + '</div>'
      + '</div>';
    var mediaMetaChip = normalized.mediaMetaLabel ? '<span class="chip">' + this._escapeHtml(normalized.mediaMetaLabel) + '</span>' : '';
    var mediaObjectsChip = normalized.mediaObjectsLabel ? '<span class="chip"><ha-icon icon="mdi:cube-outline"></ha-icon>' + this._escapeHtml(normalized.mediaObjectsLabel) + '</span>' : '';
    var mediaImageUrls = variant === 'Media' ? this._mediaImageUrls(archive, baseUrl) : [];
    var mediaGalleryCount = mediaImageUrls.length;
    var mediaGalleryIndex = mediaGalleryCount > 0
      ? (Object.prototype.hasOwnProperty.call(this._mediaGalleryIndices, String(archive && archive.id || ""))
        ? this._mediaGalleryIndex(archive && archive.id, mediaGalleryCount)
        : this._mediaPreferredGalleryIndex(archive, mediaImageUrls, baseUrl))
      : 0;
    var mediaCurrentImageUrl = mediaGalleryCount > 0 ? mediaImageUrls[mediaGalleryIndex] : '';
    var mediaPlaceholderLabel = mediaShowsImages
      ? 'No preview image available'
      : 'Images hidden';
    var listImageUrl = showImages ? normalized.thumbnailUrl(baseUrl) : '';
    var printerChip = normalized.printerFilterValue
      ? '<button class="chip interactive-chip" type="button" data-action="apply-filter" data-filter-action="printer_set" data-filter-value="' + this._escapeAttribute(normalized.printerFilterValue) + '" title="' + this._escapeAttribute(this._buildFilterActionTooltip('Printer: ' + normalized.printerLabel, 'Click to filter by this printer')) + '" aria-label="' + this._escapeAttribute('Printer ' + normalized.printerLabel + '. Click to filter by this printer.') + '">' + this._escapeHtml(normalized.printerLabel) + '</button>'
      : (normalized.printerLabel ? '<span class="chip">' + this._escapeHtml(normalized.printerLabel) + '</span>' : '');
    var primaryChipRow = variant === 'Compact'
      ? '<div class="chip-row compact-secondary compact-meta-line">'
        + (normalized.hasArchiveError ? '<span class="chip archive-error-chip" style="background:' + this._escapeAttribute(normalized.archiveErrorColor) + ';">' + this._escapeHtml(normalized.archiveErrorIcon + ' ' + normalized.archiveErrorLabel) + '</span>' : '')
        + printerChip
        + (normalized.duplicateChipLabel ? '<span class="chip" title="' + this._escapeAttribute(normalized.duplicateTooltip) + '" style="background:' + this._escapeAttribute(normalized.duplicateChipColor) + ';color:#fff;">' + this._escapeHtml(normalized.duplicateChipLabel) + '</span>' : '')
        + '</div>'
      : '';
    var metricsClass = variant === 'Media' ? 'media' : (variant === 'Compact' ? 'compact-tight' : 'list');
    var enrichmentChip = normalized.enrichmentFilterValue
      ? '<button class="chip enrichment-chip interactive-chip" type="button" data-action="apply-filter" data-filter-action="enrichment_status_set" data-filter-value="' + this._escapeAttribute(normalized.enrichmentFilterValue) + '" title="' + this._escapeAttribute(this._buildFilterActionTooltip('Enrichment: ' + normalized.enrichmentLabel, 'Click to filter by this enrichment status')) + '" aria-label="' + this._escapeAttribute('Enrichment ' + normalized.enrichmentLabel + '. Click to filter by this enrichment status.') + '" style="background:' + this._escapeAttribute(normalized.enrichmentColor) + ';color:#fff;--enrichment-chip-background:' + this._escapeAttribute(normalized.enrichmentColor) + ';--interactive-chip-border:rgba(255,255,255,0.68);">Enrichment ' + this._escapeHtml(normalized.enrichmentLabel) + '</button>'
      : '<span class="chip" title="' + this._escapeAttribute(normalized.enrichmentTooltip || normalized.enrichmentLabel) + '" aria-label="' + this._escapeAttribute(normalized.enrichmentTooltip || normalized.enrichmentLabel) + '" style="background:' + this._escapeAttribute(normalized.enrichmentColor) + ';color:#fff;">Enrichment ' + this._escapeHtml(normalized.enrichmentLabel) + '</span>';
    var colorEnrichmentMarkup = normalized.filamentChips.length
      ? '<div class="color-enrichment-row"><div class="dots">' + normalized.filamentChips.slice(0, 6).map(function (chip) {
        return this._renderFilamentDot(chip);
      }.bind(this)).join("") + '</div>' + enrichmentChip + '</div>'
      : '<div class="chip-row" style="justify-content:flex-end;">' + enrichmentChip + '</div>';
    var tagProjectMarkup = ((tags.length || hiddenTagCount || projectChip) ? '<div class="tag-project-row">'
      + ((tags.length || hiddenTagCount) ? '<div class="tags">' + tags.map(function (tag) {
        return this._renderTagChip(tag);
      }.bind(this)).join("") + (hiddenTagCount ? '<span class="chip">… +' + hiddenTagCount + '</span>' : '') + '</div>' : '<div></div>')
      + projectChip
      + '</div>' : '');
    var listDotsMarkup = normalized.filamentChips.length
      ? '<div class="dots">' + normalized.filamentChips.slice(0, 6).map(function (chip) {
        return this._renderFilamentDot(chip);
      }.bind(this)).join("") + '</div>'
      : '';
    var listTagsMarkup = (tags.length || hiddenTagCount)
      ? '<div class="tags">' + tags.map(function (tag) {
        return this._renderTagChip(tag);
      }.bind(this)).join("") + (hiddenTagCount ? '<span class="chip">… +' + hiddenTagCount + '</span>' : '') + '</div>'
      : '';

    var summaryContent = '' +
      '<div class="content compact-summary">' +
        '<div class="content-top compact">' +
        compactArchiveId +
        '<div class="action-buttons compact-actions">' +
        (selectionMode ? selectionBadge : this._renderPrimaryActionButtons(normalized, archiveJson, favoriteButton, photoAction)) +
        '</div>' +
        '</div>' +
      '<div class="chip-row compact-status-line">' +
      '<span class="compact-date">' + this._escapeHtml(normalized.startedLabel) + '</span>' +
      statusChip +
      '</div>' +
      primaryChipRow +
      '</div>';
    var compactNameContent = variant === 'Compact'
      ? '<div class="content compact-name">'
        + (normalized.roleEmblemLabel ? '<div class="role-emblem ' + this._escapeAttribute(normalized.roleEmblemClass) + '">' + this._escapeHtml(normalized.roleEmblemLabel) + '</div>' : '')
        + '<div class="name">' + this._escapeHtml(normalized.printName) + noteInline + '</div>'
        + '</div>'
      : '';
    var detailContent = '' +
      '<div class="content compact-details">' +
      '<div class="metrics ' + metricsClass + '">' +
      this._renderMetric('Duration', normalized.durationLabel) +
      this._renderMetric('Filament', normalized.filamentLabel) +
      this._renderMetric('Cost', normalized.costLabel) +
      '</div>' +
      colorEnrichmentMarkup +
      tagProjectMarkup +
      (normalized.hasArchiveError ? '<div class="archive-error-text ' + this._escapeAttribute(normalized.archiveErrorSeverity) + '">' + this._escapeHtml(normalized.archiveErrorSummary) + '</div>' : '') +
      (normalized.failureReason ? '<div class="failure">' + this._escapeHtml(normalized.failureReason) + '</div>' : '') +
      '</div>';

    if (variant === 'Media') {
      summaryContent = '' +
        '<div class="content">' +
          (normalized.roleEmblemLabel ? '<div class="role-emblem ' + this._escapeAttribute(normalized.roleEmblemClass) + '">' + this._escapeHtml(normalized.roleEmblemLabel) + '</div>' : '') +
          '<div class="header media-header">' +
            '<div class="media-title-wrap">' +
              '<div class="name">' + this._escapeHtml(normalized.printName) + noteInline + '</div>' +
            '</div>' +
            '<div class="media-status-line">' +
              '<div class="subtle media-date">' + this._escapeHtml(normalized.startedLabel) + '</div>' +
              statusChip +
            '</div>' +
          '</div>' +
          '<div class="chip-row media-meta-line">' +
            (normalized.hasArchiveError ? '<span class="chip archive-error-chip" style="background:' + this._escapeAttribute(normalized.archiveErrorColor) + ';">' + this._escapeHtml(normalized.archiveErrorIcon + ' ' + normalized.archiveErrorLabel) + '</span>' : '') +
            printerChip +
            mediaMetaChip +
            mediaObjectsChip +
            (normalized.duplicateChipLabel ? '<span class="chip" title="' + this._escapeAttribute(normalized.duplicateTooltip) + '" style="background:' + this._escapeAttribute(normalized.duplicateChipColor) + ';color:#fff;">' + this._escapeHtml(normalized.duplicateChipLabel) + '</span>' : '') +
          '</div>' +
          '<div class="metrics ' + metricsClass + '">' +
            this._renderMetric('Duration', normalized.durationLabel) +
            this._renderMetric('Filament', normalized.filamentLabel) +
            this._renderMetric('Cost', normalized.costLabel) +
          '</div>' +
          colorEnrichmentMarkup +
          tagProjectMarkup +
          (normalized.hasArchiveError ? '<div class="archive-error-text ' + this._escapeAttribute(normalized.archiveErrorSeverity) + '">' + this._escapeHtml(normalized.archiveErrorSummary) + '</div>' : '') +
          (normalized.failureReason ? '<div class="failure">' + this._escapeHtml(normalized.failureReason) + '</div>' : '') +
        '</div>';
      detailContent = '';
    }

    if (variant === 'List') {
      summaryContent = '' +
        '<div class="content list-content">' +
          (normalized.roleEmblemLabel ? '<div class="role-emblem ' + this._escapeAttribute(normalized.roleEmblemClass) + '">' + this._escapeHtml(normalized.roleEmblemLabel) + '</div>' : '') +
          '<div class="list-header">' +
            '<div class="list-title-wrap">' +
              '<div class="name">' + this._escapeHtml(normalized.printName) + noteInline + '</div>' +
            '</div>' +
            listHeaderActions +
          '</div>' +
          '<div class="list-subheader">' +
            '<div class="subtle media-date">' + this._escapeHtml(normalized.startedLabel) + '</div>' +
            '<div class="list-status-line">' +
              statusChip +
            '</div>' +
          '</div>' +
          '<div class="chip-row list-meta-line">' +
            (normalized.hasArchiveError ? '<span class="chip archive-error-chip" style="background:' + this._escapeAttribute(normalized.archiveErrorColor) + ';">' + this._escapeHtml(normalized.archiveErrorIcon + ' ' + normalized.archiveErrorLabel) + '</span>' : '') +
            printerChip +
            (mediaMetaChip ? mediaMetaChip.replace('class="chip"', 'class="chip list-chip-mobile-hide"') : '') +
            (mediaObjectsChip ? mediaObjectsChip.replace('class="chip"', 'class="chip list-chip-mobile-hide"') : '') +
            (normalized.duplicateChipLabel ? '<span class="chip" title="' + this._escapeAttribute(normalized.duplicateTooltip) + '" style="background:' + this._escapeAttribute(normalized.duplicateChipColor) + ';color:#fff;">' + this._escapeHtml(normalized.duplicateChipLabel) + '</span>' : '') +
          '</div>' +
          '<div class="metrics ' + metricsClass + '">' +
            this._renderMetric('Duration', normalized.durationLabel) +
            this._renderMetric('Filament', normalized.filamentLabel) +
            this._renderMetric('Cost', normalized.costLabel) +
          '</div>' +
          ((listDotsMarkup || listTagsMarkup || projectChip || normalized.enrichmentLabel) ? '<div class="list-bottom-row list-row-mobile-hide">'
            + listDotsMarkup
            + enrichmentChip
            + ((listTagsMarkup || projectChip) ? '<div class="list-inline-tag-project">' + listTagsMarkup + projectChip + '</div>' : '')
            + '</div>' : '') +
          (normalized.hasArchiveError ? '<div class="archive-error-text ' + this._escapeAttribute(normalized.archiveErrorSeverity) + '">' + this._escapeHtml(normalized.archiveErrorSummary) + '</div>' : '') +
          (normalized.failureReason ? '<div class="failure">' + this._escapeHtml(normalized.failureReason) + '</div>' : '') +
        '</div>';
      detailContent = '';
    }

    var thumbMarkup = variant === 'Media'
      ? '<div class="thumb-wrap"><div class="media-gallery-surface" data-archive-id="' + this._escapeAttribute(String(normalized.id || '')) + '" data-gallery-count="' + this._escapeAttribute(String(mediaGalleryCount)) + '" data-gallery-index="' + this._escapeAttribute(String(mediaGalleryIndex)) + '">'
        + (mediaCurrentImageUrl ? '<img class="thumb media" src="' + this._escapeAttribute(mediaCurrentImageUrl) + '" alt="' + this._escapeAttribute(normalized.printName) + '">' : '<div class="media-thumb-empty">' + this._escapeHtml(mediaPlaceholderLabel) + '</div>')
        + '<div class="media-thumb-overlay">' + mediaArchivePill + '<div class="action-buttons media-thumb-actions">' + (selectionMode ? selectionBadge : this._renderPrimaryActionButtons(normalized, archiveJson, favoriteButton, photoAction)) + '</div></div>'
        + (!selectionMode && mediaGalleryCount > 1 ? '<div class="media-gallery-nav"><button class="icon-action" data-action="media-prev" data-archive="' + archiveJson + '" data-gallery-count="' + this._escapeAttribute(String(mediaGalleryCount)) + '" data-gallery-index="' + this._escapeAttribute(String(mediaGalleryIndex)) + '" aria-label="Previous archive image"><ha-icon icon="mdi:chevron-left"></ha-icon></button><button class="icon-action" data-action="media-next" data-archive="' + archiveJson + '" data-gallery-count="' + this._escapeAttribute(String(mediaGalleryCount)) + '" data-gallery-index="' + this._escapeAttribute(String(mediaGalleryIndex)) + '" aria-label="Next archive image"><ha-icon icon="mdi:chevron-right"></ha-icon></button></div><div class="media-gallery-status">' + this._escapeHtml(String(mediaGalleryIndex + 1) + ' / ' + String(mediaGalleryCount)) + '</div>' : '')
        + '</div></div>'
      : (variant === 'List'
        ? (listImageUrl
          ? '<div class="thumb-wrap"><div class="media-gallery-surface"><img class="thumb list-thumb" src="' + this._escapeAttribute(listImageUrl) + '" alt="' + this._escapeAttribute(normalized.printName) + '"></div></div>'
          : (showImages
            ? '<div class="thumb-wrap"><div class="media-gallery-surface"><div class="list-thumb-empty">No preview image available</div></div></div>'
            : ''))
        : (hasImage
        ? '<div class="thumb-wrap"><img class="thumb ' + (variant === "Media" ? 'media' : '') + '" src="' + this._escapeAttribute(normalized.thumbnailUrl(baseUrl)) + '" alt="' + this._escapeAttribute(normalized.printName) + '"></div>'
        : ''));

    return "" +
      '<article class="' + cardClass + '" tabindex="0" role="' + (selectionMode ? 'checkbox' : 'button') + '" data-action="' + (selectionMode ? 'select-archive' : 'open') + '" data-archive="' + archiveJson + '" aria-label="' + this._escapeAttribute((selectionMode ? 'Select ' : 'Open details for ') + normalized.printName) + '"' + (selectionMode ? (' aria-checked="' + (isSelected ? 'true' : 'false') + '"') : '') + '>' +
      '<div class="card-shell ' + variant.toLowerCase() + (hasImage ? '' : ' no-image') + '">' +
      thumbMarkup +
      summaryContent +
      compactNameContent +
      detailContent +
      '</article>';
  }

  _renderMetric(label, value) {
    return '<div class="metric"><div class="metric-label">' + this._escapeHtml(label) + '</div><div class="metric-value">' + this._escapeHtml(value) + '</div></div>';
  }

  _favoriteButtonTitle(isFavorite) {
    return isFavorite ? 'Remove from favorites' : 'Add to favorites';
  }

  _renderPrimaryActionButtons(normalized, archiveJson, favoriteButton, photoAction) {
    return '<button class="icon-action viewer" data-action="viewer" data-archive="' + archiveJson + '" aria-label="Open 3D viewer for ' + this._escapeAttribute(normalized.printName) + '"><ha-icon icon="mdi:cube-scan"></ha-icon></button>'
      + favoriteButton
      + photoAction;
  }

  _renderFavoriteButton(normalized, archiveJson) {
    var isFavorite = !!(normalized && normalized.isFavorite);
    var buttonTitle = this._favoriteButtonTitle(isFavorite);
    return '<button class="icon-action favorite' + (isFavorite ? ' active' : '') + '" data-action="favorite" data-archive-id="' + this._escapeAttribute(String(normalized && normalized.id || "")) + '" data-archive="' + archiveJson + '" aria-label="' + this._escapeAttribute(buttonTitle) + '" aria-pressed="' + (isFavorite ? 'true' : 'false') + '" title="' + this._escapeAttribute(buttonTitle + ' (toggle favorite)') + '"><ha-icon icon="' + (isFavorite ? 'mdi:star' : 'mdi:star-outline') + '"></ha-icon></button>';
  }

  _renderBulkDialog() {
    var host = this.shadowRoot && this.shadowRoot.getElementById ? this.shadowRoot.getElementById("dialog-host") : null;
    if (!host) {
      return;
    }
    if (!this._bulkDialog || !this._isMultiSelectMode()) {
      host.innerHTML = "";
      return;
    }

    var selectedCount = this._selectedArchiveCount();
    var dialogTitle = this._bulkDialog.type === "project" ? "Assign Project" : "Edit Tags";
    var helperText = this._bulkDialog.type === "project"
      ? "Assign one project to all selected prints. This replaces the current project assignment for each selected archive."
      : "Only user tags are changed. Add tags are appended, remove tags are stripped, and Bambuddy system tags are preserved.";
    var bodyMarkup = this._bulkDialog.type === "project"
      ? '<div class="bulk-dialog-field"><label for="bulk-project-select">Project</label><select id="bulk-project-select">' + this._bulkProjectChoices().map(function (choice) {
        return '<option value="' + this._escapeAttribute(choice.value) + '"' + (choice.value === this._bulkDialog.projectValue ? ' selected' : '') + '>' + this._escapeHtml(choice.label) + '</option>';
      }.bind(this)).join("") + '</select></div>'
      : '<div class="bulk-dialog-field"><label for="bulk-tag-add">Add User Tags</label><input id="bulk-tag-add" type="text" value="' + this._escapeAttribute(this._bulkDialog.addTags || "") + '" placeholder="functional, prototype"></div>'
        + '<div class="bulk-dialog-field"><label for="bulk-tag-remove">Remove User Tags</label><input id="bulk-tag-remove" type="text" value="' + this._escapeAttribute(this._bulkDialog.removeTags || "") + '" placeholder="draft, reprint"></div>';
    host.innerHTML = '' +
      '<div class="bulk-dialog-backdrop">' +
        '<div class="bulk-dialog" role="dialog" aria-modal="true" aria-label="' + this._escapeAttribute(dialogTitle) + '">' +
          '<div class="bulk-dialog-header">' +
            '<div>' +
              '<div class="bulk-dialog-title">' + this._escapeHtml(dialogTitle) + '</div>' +
              '<div class="bulk-dialog-subtle">' + this._escapeHtml(String(selectedCount) + (selectedCount === 1 ? ' print selected. ' : ' prints selected. ') + helperText) + '</div>' +
            '</div>' +
          '</div>' +
          '<div class="bulk-dialog-body">' + bodyMarkup + '</div>' +
          '<div class="bulk-dialog-actions">' +
            '<button class="bulk-dialog-button" data-action="multi-select-dialog-cancel"' + (this._bulkActionBusy ? ' disabled' : '') + '>Cancel</button>' +
            '<button class="bulk-dialog-button primary" data-action="multi-select-dialog-submit"' + (this._bulkActionBusy ? ' disabled' : '') + '>' + this._escapeHtml(this._bulkActionBusy ? 'Working...' : (this._bulkDialog.type === 'project' ? 'Assign Project' : 'Apply Tags')) + '</button>' +
          '</div>' +
        '</div>' +
      '</div>';
  }

  _bulkProjectChoices() {
    var choices = [{ value: "__NULL__", label: "No Project" }];
    var projectOptions = this._entityAttribute(this._config.browser_status_entity, "project_options");
    var raw = [];
    try {
      raw = this._hass && this._hass.states && this._hass.states[this._config.browser_status_entity]
        && this._hass.states[this._config.browser_status_entity].attributes
        && Array.isArray(this._hass.states[this._config.browser_status_entity].attributes.project_options)
        ? this._hass.states[this._config.browser_status_entity].attributes.project_options
        : [];
    } catch (error) {
      raw = [];
    }
    raw.forEach(function (option) {
      var optionId = option && option.id != null ? String(option.id).trim() : "";
      var optionLabel = option && option.label ? String(option.label).trim() : "";
      if (optionId && optionLabel) {
        choices.push({ value: optionId, label: optionLabel });
      }
    });
    return choices;
  }

  _openBulkTagDialog() {
    if (!this._selectedArchiveCount()) {
      return;
    }
    this._bulkDialog = { type: "tag", addTags: "", removeTags: "" };
    this._renderBulkDialog();
  }

  _openBulkProjectDialog() {
    if (!this._selectedArchiveCount()) {
      return;
    }
    this._bulkDialog = { type: "project", projectValue: "__NULL__" };
    this._renderBulkDialog();
  }

  _closeBulkDialog() {
    this._bulkDialog = null;
    this._bulkActionBusy = false;
    this._renderBulkDialog();
  }

  _clearMultiSelectRequest() {
    if (!this._hass) {
      return;
    }
    this._hass.callService("input_text", "set_value", {
      entity_id: "input_text.print_history_multi_select_request",
      value: "",
    });
  }

  async _completeBulkActionAndExitMode() {
    this._clearLocalMultiSelectState();
    if (this._hass) {
      await this._hass.callService("script", "cancel_print_history_multi_select_mode", {});
    }
    this._renderBody();
  }

  async _consumePendingMultiSelectRequest() {
    if (!this._hass || !this._isMultiSelectMode()) {
      return;
    }
    var request = String(this._stateValue("input_text.print_history_multi_select_request") || "").trim();
    if (!request || request === this._handledMultiSelectRequest) {
      return;
    }
    this._handledMultiSelectRequest = request;
    this._clearMultiSelectRequest();
    var action = request.split("|")[0];
    if (action === "select_all") {
      this._selectAllVisibleArchives();
      return;
    }
    if (action === "tag") {
      this._openBulkTagDialog();
      return;
    }
    if (action === "project") {
      this._openBulkProjectDialog();
      return;
    }
    if (action === "favorite") {
      await this._runBulkFavoriteToggle();
      return;
    }
    if (action === "delete") {
      await this._runBulkDelete();
    }
  }

  _selectAllVisibleArchives() {
    if (!this._isMultiSelectMode()) {
      return;
    }
    var nextSelection = {};
    (Array.isArray(this._response.archives) ? this._response.archives : []).forEach(function (archive) {
      var archiveId = String(archive && archive.id || "").trim();
      if (archiveId) {
        nextSelection[archiveId] = true;
      }
    });
    this._selectedArchiveIds = nextSelection;
    this._syncMultiSelectSummary();
    this._renderBody();
  }

  _toggleSelectedArchive(archive) {
    if (!this._isMultiSelectMode() || !archive || archive.id == null) {
      return;
    }
    var archiveId = String(archive.id).trim();
    if (!archiveId) {
      return;
    }
    if (this._selectedArchiveIds[archiveId]) {
      delete this._selectedArchiveIds[archiveId];
    } else {
      this._selectedArchiveIds[archiveId] = true;
    }
    this._syncMultiSelectSummary();
    this._renderBody();
  }

  async _submitBulkDialog() {
    if (!this._bulkDialog || this._bulkActionBusy || !this._hass) {
      return;
    }
    this._bulkActionBusy = true;
    this._renderBulkDialog();
    try {
      if (this._bulkDialog.type === "tag") {
        var addInput = this.shadowRoot && this.shadowRoot.getElementById ? this.shadowRoot.getElementById("bulk-tag-add") : null;
        var removeInput = this.shadowRoot && this.shadowRoot.getElementById ? this.shadowRoot.getElementById("bulk-tag-remove") : null;
        await this._hass.callService("script", "bulk_update_print_history_user_tags", {
          archive_ids_csv: this._selectedArchiveIdsCsv(),
          add_tags: addInput && addInput.value ? String(addInput.value).trim() : "",
          remove_tags: removeInput && removeInput.value ? String(removeInput.value).trim() : "",
        });
      } else if (this._bulkDialog.type === "project") {
        var selectNode = this.shadowRoot && this.shadowRoot.getElementById ? this.shadowRoot.getElementById("bulk-project-select") : null;
        var projectValue = selectNode && selectNode.value ? String(selectNode.value).trim() : "__NULL__";
        await this._hass.callService("script", "bulk_assign_print_history_project", {
          archive_ids_csv: this._selectedArchiveIdsCsv(),
          project_id: projectValue || "__NULL__",
        });
      }
      await this._completeBulkActionAndExitMode();
    } catch (error) {
      this._bulkActionBusy = false;
      this._renderBulkDialog();
      throw error;
    }
  }

  async _runBulkFavoriteToggle() {
    if (!this._hass || !this._selectedArchiveCount()) {
      return;
    }
    var nextFavorite = !this._selectedArchivesAllFavorites();
    await this._hass.callService("script", "bulk_set_print_history_archive_favorite", {
      archive_ids_csv: this._selectedArchiveIdsCsv(),
      is_favorite: nextFavorite,
    });
    var selectedIds = this._selectedArchiveIdList();
    this._response.archives = (Array.isArray(this._response.archives) ? this._response.archives : []).map(function (archive) {
      if (selectedIds.indexOf(String(archive && archive.id || "")) >= 0) {
        return Object.assign({}, archive, { is_favorite: nextFavorite });
      }
      return archive;
    });
    await this._completeBulkActionAndExitMode();
  }

  async _runBulkDelete() {
    if (!this._hass || !this._selectedArchiveCount()) {
      return;
    }
    var selectedCount = this._selectedArchiveCount();
    if (!window.confirm("Delete " + selectedCount + (selectedCount === 1 ? " selected print" : " selected prints") + "? This permanently removes them from Bambuddy and cannot be undone.")) {
      return;
    }
    if (window.prompt("Type DELETE to permanently remove the selected prints.", "") !== "DELETE") {
      return;
    }
    var selectedIds = this._selectedArchiveIdList();
    await this._hass.callService("script", "bulk_delete_print_history_archives", {
      archive_ids_csv: selectedIds.join(","),
    });
    this._response.archives = (Array.isArray(this._response.archives) ? this._response.archives : []).filter(function (archive) {
      return selectedIds.indexOf(String(archive && archive.id || "")) === -1;
    });
    await this._completeBulkActionAndExitMode();
  }

  _renderFilamentDot(chip) {
    var dotLabel = String(chip && chip.tooltip ? chip.tooltip : 'Filament color');
    var filterColor = this._normalizeHex(chip && chip.filterColor);
    var tooltipText = filterColor
      ? this._buildFilterActionTooltip(dotLabel, 'Click to filter on this color')
      : dotLabel;
    var tooltip = this._escapeAttribute(tooltipText);
    var dotColor = this._escapeAttribute(chip && chip.dotColor ? chip.dotColor : 'rgba(255,255,255,0.2)');
    if (!filterColor) {
      return '<span class="dot-button" tabindex="0" role="img" aria-label="' + tooltip + '" title="' + tooltip + '" style="--dot-color:' + dotColor + ';"><span class="dot-tooltip" role="tooltip">' + this._escapeHtml(tooltipText) + '</span></span>';
    }
    return '<button class="dot-button interactive-chip" type="button" data-action="apply-filter" data-filter-action="color_toggle" data-filter-value="' + this._escapeAttribute(filterColor) + '" aria-label="' + this._escapeAttribute(dotLabel + '. Click to filter on this color.') + '" title="' + tooltip + '" style="--dot-color:' + dotColor + ';--interactive-chip-border:rgba(255,255,255,0.72);"><span class="dot-tooltip" role="tooltip">' + this._escapeHtml(tooltipText) + '</span></button>';
  }

  _renderInfoChip(label) {
    return '<span class="chip">' + this._escapeHtml(label) + '</span>';
  }

  _duplicateSummary(archive) {
    var archiveId = Math.max(0, Number(archive && archive.id || 0));
    var duplicateCount = Math.max(0, Number(archive && archive.duplicate_count || 0));
    var duplicateSequence = Math.max(0, Number(archive && archive.duplicate_sequence || 0));
    var originalArchiveId = Math.max(0, Number(archive && archive.original_archive_id || 0));
    var isSource = duplicateSequence === 0 && originalArchiveId > 0 && originalArchiveId === archiveId;
    var isDuplicate = !isSource && (originalArchiveId > 0 || duplicateSequence > 0);
    var isRelated = duplicateCount > 0 && !isSource && !isDuplicate;
    var groupSize = duplicateCount > 0 ? (duplicateCount + 1) : 0;

    if (isDuplicate) {
      var duplicatePosition = groupSize > 0 ? Math.min(groupSize, Math.max(1, duplicateSequence + 1)) : Math.max(1, duplicateSequence + 1);
      var duplicateLabel = originalArchiveId > 0 ? ('Dup of #' + originalArchiveId) : (groupSize > 1 ? ('Duplicate ' + duplicatePosition + '/' + groupSize) : 'Duplicate');
      var duplicateTooltip = originalArchiveId > 0
        ? ('Duplicate copy derived from original archive #' + originalArchiveId)
        : 'Duplicate archive in a shared print set';
      return {
        chipLabel: duplicateLabel,
        chipColor: '#00897B',
        tooltip: duplicateTooltip,
        roleClass: 'duplicate-copy',
        roleEmblemLabel: 'Duplicate',
        roleEmblemClass: 'duplicate',
      };
    }

    if (isSource) {
      return {
        chipLabel: groupSize > 1 ? ('Source · ' + groupSize + ' prints') : 'Source',
        chipColor: '#1565C0',
        tooltip: groupSize > 1
          ? ('Original source archive for a duplicate set of ' + groupSize + ' prints')
          : 'Original source archive in a duplicate set',
        roleClass: 'duplicate-source',
        roleEmblemLabel: 'Source',
        roleEmblemClass: 'source',
      };
    }

    if (isRelated) {
      return {
        chipLabel: groupSize > 1 ? ('Related · ' + groupSize + ' prints') : 'Related',
        chipColor: '#6D4C41',
        tooltip: groupSize > 1
          ? ('Bambuddy reports ' + groupSize + ' related prints for this archive without explicit duplicate lineage')
          : 'Bambuddy reports a related print for this archive without explicit duplicate lineage',
        roleClass: 'related-match',
        roleEmblemLabel: 'Related',
        roleEmblemClass: 'related',
      };
    }

    return {
      chipLabel: '',
      chipColor: '',
      tooltip: '',
      roleClass: '',
      roleEmblemLabel: '',
      roleEmblemClass: '',
    };
  }

  _normalizeArchiveCacheKey(archive) {
    if (!archive || typeof archive !== "object") {
      return "";
    }
    var archiveId = archive.id != null ? String(archive.id) : "";
    var payloadHash = String(archive.payload_hash || "").trim();
    if (archiveId && payloadHash) {
      return archiveId + ":" + payloadHash;
    }
    if (!archiveId) {
      return "";
    }
    var sourceUpdatedAt = String(archive.source_updated_at || "").trim();
    var notes = String(archive.notes || "");
    return archiveId + ":" + [
      String(archive.status || ""),
      String(archive.enrichment_status || ""),
      String(archive.is_favorite ? "1" : "0"),
      sourceUpdatedAt,
      String(notes.length),
      notes.slice(-64),
    ].join("|");
  }

  _pruneNormalizedArchiveCache(archives) {
    if (!this._normalizedArchiveCache) {
      this._normalizedArchiveCache = {};
    }
    var keep = {};
    (Array.isArray(archives) ? archives : []).forEach(function (archive) {
      var key = this._normalizeArchiveCacheKey(archive);
      if (key) {
        keep[key] = true;
      }
    }.bind(this));
    Object.keys(this._normalizedArchiveCache).forEach(function (key) {
      if (!keep[key]) {
        delete this._normalizedArchiveCache[key];
      }
    }.bind(this));
  }

  _archiveNoteBoundaryIndex(raw) {
    var markerIndex = raw.indexOf("+>");
    var recoveryIndex = raw.indexOf("[RECOVERY_AUDIT_V1]");
    var indexes = [markerIndex, recoveryIndex].filter(function (index) { return index >= 0; });
    return indexes.length ? Math.min.apply(null, indexes) : -1;
  }

  _splitArchiveNotesLight(value) {
    var raw = String(value || "");
    var cutoff = this._archiveNoteBoundaryIndex(raw);
    if (cutoff < 0) {
      return { userNotes: raw.trimEnd() };
    }
    return { userNotes: raw.slice(0, cutoff).replace(/\n+$/u, "") };
  }

  _filamentChipsFromSlots(slots) {
    if (!Array.isArray(slots) || !slots.length) {
      return [];
    }
    return slots.map(function (slot, index) {
      var name = String(slot && slot.name || "").trim() || ("Filament " + (index + 1));
      var tray = String(slot && slot.tray || "").trim();
      var filterColor = this._normalizeHex(slot && slot.color);
      var dotColor = filterColor || "rgba(255,255,255,0.2)";
      return {
        dotColor: dotColor,
        filterColor: filterColor,
        tooltip: [tray ? name + " (" + tray + ")" : name, filterColor].filter(Boolean).join(" | ") || name,
      };
    }.bind(this)).filter(function (chip) {
      return !!chip.dotColor;
    });
  }

  _filamentChipsFromColors(colors) {
    return colors.map(function (hex) {
      return { dotColor: hex, filterColor: hex, tooltip: hex };
    });
  }

  _normalizeArchive(archive) {
    var cacheKey = this._normalizeArchiveCacheKey(archive);
    if (cacheKey && this._normalizedArchiveCache[cacheKey]) {
      return this._normalizedArchiveCache[cacheKey];
    }
    var notesInfo = this._splitArchiveNotesLight(archive.notes);
    var enrichmentStatus = this._normalizeEnrichmentStatus(archive.enrichment_status, null);
    var colors = String(archive.filament_color || "").split(",").map(this._normalizeHex).filter(Boolean);
    var filamentChips = this._filamentChipsFromSlots(archive.filament_slots);
    if (!filamentChips.length) {
      filamentChips = this._filamentChipsFromColors(colors);
    }
    var metadata = [archive.filament_type || "Unknown material", archive.layer_height ? String(archive.layer_height) + "mm" : "", archive.designer || ""].filter(Boolean).join(" · ");
    var mediaMetaLabel = [
      archive.filament_type ? String(archive.filament_type) : "",
      archive.layer_height ? String(archive.layer_height) + "mm" : "",
      archive.nozzle_diameter ? String(archive.nozzle_diameter) + "mm nozzle" : "",
    ].filter(Boolean).join(" · ");
    var mediaObjectsLabel = Number(archive.object_count || 0) > 1
      ? String(archive.object_count) + " objects"
      : "";
    var printerLabel = archive.printer_name ? String(archive.printer_name) : (archive.printer_id != null && archive.printer_id !== "" ? ("Printer " + String(archive.printer_id)) : "");
    var duplicateSummary = this._duplicateSummary(archive);
    var facts = [
      printerLabel ? "Printer: " + printerLabel : "",
      archive.filament_type ? String(archive.filament_type) : "",
      archive.layer_height ? String(archive.layer_height) + "mm layer" : "",
      archive.nozzle_diameter ? String(archive.nozzle_diameter) + "mm nozzle" : "",
      archive.object_count ? String(archive.object_count) + " object" + (Number(archive.object_count) === 1 ? "" : "s") : "",
      archive.designer ? "Designer: " + String(archive.designer) : "",
    ].filter(Boolean);
    var status = this._normalizeStatus(archive.status);
    var archiveError = this._normalizeArchiveError(archive);
    var card = this;

    var normalized = {
      id: archive.id,
      archive: archive,
      isFavorite: !!archive.is_favorite,
      printName: archive.print_name ? String(archive.print_name) : "Unnamed",
      startedLabel: this._formatDate(archive.started_at || archive.created_at),
      statusLabel: status === "completed" ? "Completed" : status === "archived" ? "Archived" : status === "failed" ? "Failed" : status === "cancelled" ? "Cancelled" : status === "printing" ? "Printing" : "Unknown",
      statusFilterValue: status === "completed" ? "Completed" : status === "archived" ? "Archived" : status === "failed" ? "Failed" : status === "cancelled" ? "Cancelled" : status === "printing" ? "Printing" : "",
      statusColor: status === "completed" ? "#2E7D32" : status === "archived" ? "#546E7A" : status === "failed" ? "#C62828" : status === "cancelled" ? "#EF6C00" : status === "printing" ? "#1565C0" : "#546E7A",
      statusIcon: status === "completed" ? "✅" : status === "archived" ? "📦" : status === "failed" ? "❌" : status === "cancelled" ? "⛔" : status === "printing" ? "🖨️" : "⏳",
      enrichmentLabel: enrichmentStatus === "near complete" ? "Near Complete" : enrichmentStatus === "mostly complete" ? "Mostly Complete" : enrichmentStatus === "partially complete" ? "Partially Complete" : enrichmentStatus === "not defined" ? "Not Defined" : enrichmentStatus.charAt(0).toUpperCase() + enrichmentStatus.slice(1),
      enrichmentFilterValue: enrichmentStatus === "near complete" ? "Near Complete" : enrichmentStatus === "mostly complete" ? "Mostly Complete" : enrichmentStatus === "partially complete" ? "Partially Complete" : enrichmentStatus === "not defined" ? "Not Defined" : enrichmentStatus.charAt(0).toUpperCase() + enrichmentStatus.slice(1),
      enrichmentColor: enrichmentStatus === "complete" ? "#2E7D32" : enrichmentStatus === "near complete" ? "#1565C0" : enrichmentStatus === "mostly complete" ? "#6A1B9A" : enrichmentStatus === "partially complete" ? "#EF6C00" : "#546E7A",
      enrichmentTooltip: this._enrichmentTooltip(enrichmentStatus),
      durationLabel: this._formatDuration(
        archive.effective_duration_seconds != null
          ? archive.effective_duration_seconds
          : (archive.actual_time_seconds != null ? archive.actual_time_seconds : archive.print_time_seconds)
      ),
      filamentLabel: this._formatNumber(archive.filament_used_grams, 1, "g"),
      costLabel: this._formatCurrency(archive.cost),
      objectLabel: String(archive.object_count || 1),
      archiveIdLabel: archive.id != null && archive.id !== "" ? ("Archive #" + archive.id) : "Archive unavailable",
      compactArchiveIdLabel: archive.id != null && archive.id !== "" ? ("#" + archive.id) : "",
      printerLabel: printerLabel,
      printerFilterValue: this._resolvePrinterFilterValue(archive.printer_id, archive.printer_name),
      duplicateChipLabel: duplicateSummary.chipLabel,
      duplicateChipColor: duplicateSummary.chipColor,
      duplicateTooltip: duplicateSummary.tooltip,
      roleClass: duplicateSummary.roleClass,
      roleEmblemLabel: duplicateSummary.roleEmblemLabel,
      roleEmblemClass: duplicateSummary.roleEmblemClass,
      metadata: metadata,
      mediaMetaLabel: mediaMetaLabel,
      mediaObjectsLabel: mediaObjectsLabel,
      facts: facts,
      filamentChips: filamentChips,
      projectLabel: archive.project_name ? String(archive.project_name).trim() : "",
      projectColor: this._projectColorForArchive(archive),
      projectBackground: this._projectBackgroundColorForArchive(archive),
      userTags: this._userTags(archive.tags),
      noteText: this._userNoteText(notesInfo.userNotes),
      photoCount: this._archivePhotoCount(archive),
      photoCountLabel: this._photoCountLabel(this._archivePhotoCount(archive)),
      hasArchiveError: archiveError.hasArchiveError,
      archiveErrorLabel: archiveError.label,
      archiveErrorSeverity: archiveError.severity,
      archiveErrorColor: archiveError.color,
      archiveErrorIcon: archiveError.icon,
      archiveErrorSummary: archiveError.summary,
      failureReason: archive.failure_reason ? String(archive.failure_reason) : "",
      thumbnailUrl: function (baseUrl) {
        return card._mediaPreferredImageUrl(archive, baseUrl);
      },
    };
    if (cacheKey) {
      this._normalizedArchiveCache[cacheKey] = normalized;
    }
    return normalized;
  }

  _normalizeArchiveError(archive) {
    var filePath = String(archive && archive.file_path || "").trim();
    var thumbnailPath = String(archive && archive.thumbnail_path || "").trim();
    var primaryPhotoPath = String(archive && archive.primary_photo_path || "").trim();
    var previewPath = primaryPhotoPath || thumbnailPath;
    var source3mfPath = String(archive && archive.source_3mf_path || "").trim();
    var missingCore3mf = !!(archive && archive.missing_core_3mf);
    var missingThumbnail = !!(archive && archive.missing_thumbnail);
    var hasSourceOnly = !!(archive && archive.has_source_only);
    var hasProjectedArchiveState = !!(archive && (
      Object.prototype.hasOwnProperty.call(archive, "has_archive_error") ||
      Object.prototype.hasOwnProperty.call(archive, "missing_core_3mf") ||
      Object.prototype.hasOwnProperty.call(archive, "missing_thumbnail") ||
      Object.prototype.hasOwnProperty.call(archive, "has_source_only")
    ));

    if (!hasProjectedArchiveState && !missingCore3mf && !missingThumbnail) {
      missingCore3mf = !!(archive && archive.no_3mf_available) || !filePath;
      hasSourceOnly = missingCore3mf && !!source3mfPath;
      missingThumbnail = !missingCore3mf && !previewPath;
    }

    if (hasSourceOnly) {
      return {
        hasArchiveError: true,
        severity: "error",
        label: String(archive && archive.archive_error_label || "Source 3MF Only"),
        summary: String(archive && archive.archive_error_summary || "Primary archive missing; source 3MF is attached separately."),
        color: "#C62828",
        icon: "⚠️",
      };
    }
    if (missingCore3mf) {
      return {
        hasArchiveError: true,
        severity: "error",
        label: String(archive && archive.archive_error_label || "Archive Incomplete"),
        summary: String(archive && archive.archive_error_summary || "Primary archived 3MF is missing and needs repair."),
        color: "#C62828",
        icon: "⚠️",
      };
    }
    if (missingThumbnail) {
      return {
        hasArchiveError: true,
        severity: "warning",
        label: String(archive && archive.archive_error_label || "Thumbnail Missing"),
        summary: String(archive && archive.archive_error_summary || "Preview image is unavailable for this archive."),
        color: "#EF6C00",
        icon: "⚠️",
      };
    }
    return {
      hasArchiveError: false,
      severity: "",
      label: "",
      summary: "",
      color: "",
      icon: "",
    };
  }

  _projectColorForArchive(archive) {
    var projectId = archive && archive.project_id != null ? String(archive.project_id).trim() : "";
    var projectName = archive && archive.project_name != null ? String(archive.project_name).trim().toLowerCase() : "";
    if (!projectId) {
      if (!projectName) {
        return "rgba(255,255,255,0.14)";
      }
    }
    var catalog = this._popupProjectCatalog();
    for (var index = 0; index < catalog.length; index += 1) {
      var option = catalog[index] || {};
      var optionId = String(option.id || "").trim();
      var optionName = String(option.name || "").trim().toLowerCase();
      if ((projectId && optionId === projectId) || (!projectId && projectName && optionName === projectName)) {
        return this._normalizeHex(option.color) || "rgba(255,255,255,0.14)";
      }
    }
    return "rgba(255,255,255,0.14)";
  }

  _projectBackgroundColorForArchive(archive) {
    return this._withAlpha(this._projectColorForArchive(archive), 0.18);
  }

  _withAlpha(color, alpha) {
    var normalized = this._normalizeHex(color);
    if (!normalized) {
      return "rgba(255,255,255,0.05)";
    }
    var red = parseInt(normalized.slice(1, 3), 16);
    var green = parseInt(normalized.slice(3, 5), 16);
    var blue = parseInt(normalized.slice(5, 7), 16);
    return "rgba(" + red + "," + green + "," + blue + "," + alpha + ")";
  }

  _userNoteText(value) {
    var text = String(value || "").trim();
    if (!text || /^system\b/i.test(text)) {
      return "";
    }
    return text;
  }

  _photoCountLabel(value) {
    var count = Math.max(0, Number(value || 0));
    if (!count) {
      return "";
    }
    return String(count) + " photo" + (count === 1 ? "" : "s");
  }

  _archivePhotoCount(archive) {
    var explicitCount = Number(archive && archive.photo_count);
    if (Number.isFinite(explicitCount) && explicitCount > 0) {
      return Math.max(0, Math.round(explicitCount));
    }
    return Array.isArray(archive && archive.photos) ? archive.photos.length : 0;
  }

  _archivePhotoPaths(archive) {
    if (!Array.isArray(archive && archive.photos)) {
      return [];
    }
    return archive.photos.map(function (item) {
      if (typeof item === "string") {
        return item.trim();
      }
      if (item && typeof item === "object") {
        return String(item.path || item.url || item.photo_path || "").trim();
      }
      return "";
    }).filter(Boolean);
  }

  _archiveMediaCacheKey(archive) {
    if (!archive || typeof archive !== "object") {
      return "";
    }
    return JSON.stringify({
      id: archive.id != null ? String(archive.id) : "",
      source_updated_at: archive.source_updated_at || archive.updated_at || archive.completed_at || archive.created_at || "",
      thumbnail_path: archive.thumbnail_path || "",
      primary_photo_path: archive.primary_photo_path || "",
      selected_primary_photo_path: archive.selected_primary_photo_path || "",
      has_primary_photo_override: !!archive.has_primary_photo_override,
      photos: this._archivePhotoPaths(archive),
    });
  }

  _withArchiveMediaCacheKey(url, archive) {
    var normalizedUrl = String(url || "").trim();
    if (!normalizedUrl) {
      return "";
    }
    var cacheKey = this._archiveMediaCacheKey(archive);
    if (!cacheKey) {
      return normalizedUrl;
    }
    return normalizedUrl + (normalizedUrl.indexOf("?") >= 0 ? "&" : "?") + "v=" + encodeURIComponent(cacheKey);
  }

  _archivePhotoUrl(archiveId, photoPath, baseUrl) {
    if (!baseUrl || archiveId == null || !photoPath) {
      return "";
    }
    return baseUrl + "/api/v1/archives/" + encodeURIComponent(String(archiveId)) + "/photos/" + encodeURIComponent(String(photoPath));
  }

  _archiveThumbnailUrl(archive, baseUrl) {
    if (!baseUrl || !archive || archive.id == null || !String(archive.thumbnail_path || "").trim()) {
      return "";
    }
    return this._withArchiveMediaCacheKey(
      baseUrl + "/api/v1/archives/" + encodeURIComponent(String(archive.id)) + "/thumbnail",
      archive
    );
  }

  _mediaImageUrls(archive, baseUrl) {
    var urls = [];
    var seen = {};
    var addUrl = function (url) {
      var normalized = String(url || "").trim();
      if (!normalized || seen[normalized]) {
        return;
      }
      seen[normalized] = true;
      urls.push(normalized);
    };

    addUrl(this._archiveThumbnailUrl(archive, baseUrl));
    this._archivePhotoPaths(archive).forEach(function (photoPath) {
      addUrl(this._withArchiveMediaCacheKey(this._archivePhotoUrl(archive && archive.id, photoPath, baseUrl), archive));
    }.bind(this));

    return urls;
  }

  _mediaPreferredImageUrl(archive, baseUrl) {
    var primaryPhotoPath = String(archive && archive.primary_photo_path || "").trim();
    if (primaryPhotoPath) {
      return this._withArchiveMediaCacheKey(this._archivePhotoUrl(archive && archive.id, primaryPhotoPath, baseUrl), archive);
    }
    return this._archiveThumbnailUrl(archive, baseUrl);
  }

  _mediaPreferredGalleryIndex(archive, imageUrls, baseUrl) {
    if (!Array.isArray(imageUrls) || !imageUrls.length) {
      return 0;
    }
    var preferredUrl = this._mediaPreferredImageUrl(archive, baseUrl);
    var preferredIndex = preferredUrl ? imageUrls.indexOf(preferredUrl) : -1;
    return preferredIndex >= 0 ? preferredIndex : 0;
  }

  _mediaGalleryIndex(archiveId, imageCount) {
    var key = String(archiveId || "");
    var count = Math.max(0, Number(imageCount) || 0);
    if (!key || count <= 0) {
      return 0;
    }
    if (!Object.prototype.hasOwnProperty.call(this._mediaGalleryIndices, key)) {
      return 0;
    }
    var current = Number(this._mediaGalleryIndices[key] || 0);
    if (!Number.isFinite(current) || current < 0) {
      current = 0;
    }
    if (current >= count) {
      current = count - 1;
      this._mediaGalleryIndices[key] = current;
    }
    return current;
  }

  _readRenderedMediaGalleryIndex(node, imageCount) {
    var count = Math.max(0, Number(imageCount) || 0);
    if (count <= 0) {
      return 0;
    }
    var currentNode = node || null;
    while (currentNode) {
      if (currentNode.getAttribute) {
        var rawIndex = currentNode.getAttribute("data-gallery-index");
        if (rawIndex !== null && rawIndex !== "") {
          var parsedIndex = Number(rawIndex);
          if (Number.isFinite(parsedIndex)) {
            while (parsedIndex < 0) {
              parsedIndex += count;
            }
            return parsedIndex % count;
          }
        }
      }
      currentNode = currentNode.closest ? currentNode.closest(".media-gallery-surface") : null;
      if (currentNode === node) {
        break;
      }
      node = currentNode;
    }
    return 0;
  }

  _setMediaGalleryIndex(archiveId, nextIndex, imageCount) {
    var key = String(archiveId || "");
    var count = Math.max(0, Number(imageCount) || 0);
    if (!key || count <= 0) {
      return;
    }
    var normalizedIndex = Number(nextIndex);
    if (!Number.isFinite(normalizedIndex)) {
      normalizedIndex = 0;
    }
    while (normalizedIndex < 0) {
      normalizedIndex += count;
    }
    normalizedIndex = normalizedIndex % count;
    this._mediaGalleryIndices[key] = normalizedIndex;
    this._viewSignature = this._buildViewSignature(this._hass);
    this._renderBody();
  }

  _userTags(value) {
    var systemTagPrefixes = ["f:", "s:", "spoolman:", "vendor:", "material:", "cost:", "status:", "ha enrichment:", "ha_enrichment:"];
    var systemTagValues = ["ha_enriched:true"];
    return String(value || "")
      .split(",")
      .map(function (entry) { return entry.trim(); })
      .filter(Boolean)
      .filter(function (tag) {
        var normalized = tag.toLowerCase();
        return systemTagValues.indexOf(normalized) === -1 && !systemTagPrefixes.some(function (prefix) {
          return normalized.indexOf(prefix) === 0;
        });
      });
  }

  _normalizeStatus(status) {
    var raw = String(status || "").toLowerCase();
    if (raw === "completed" || raw === "success") {
      return "completed";
    }
    if (raw === "archived") {
      return "archived";
    }
    if (raw === "cancelled" || raw === "aborted" || raw === "stopped") {
      return "cancelled";
    }
    return raw;
  }

  _normalizeHex(value) {
    var raw = String(value || "").trim().replace(/^#/, "").replace(/"/g, "");
    if (!raw) {
      return "";
    }
    var trimmed = raw.length === 8 ? raw.slice(0, 6) : raw;
    return /^[0-9a-fA-F]{6}$/.test(trimmed) ? ("#" + trimmed.toUpperCase()) : "";
  }

  _describeEnrichmentAmbiguity(value) {
    var normalized = String(value || "").trim();
    return ({
        a_tc: "Multiple candidate spools or filaments matched type+color",
        a_fb: "Archive-level fallback matched multiple candidate spools or filaments",
      s_uuid: "Multiple Spoolman spools matched archived tray UUID",
      s_tc: "Multiple Spoolman spools matched type+color",
    })[normalized] || normalized;
  }

  _normalizeEnrichmentStatus(statusValue, enrichmentRows) {
    var normalized = String(statusValue || "").trim().toLowerCase();
    var mapped = ({
      c: "complete",
      complete: "complete",
      t: "near complete",
      "near complete": "near complete",
      m: "mostly complete",
      n: "mostly complete",
      "mostly complete": "mostly complete",
      p: "partially complete",
      partial: "partially complete",
      "partially complete": "partially complete",
      u: "unavailable",
      unavailable: "unavailable",
      "not defined": "not defined",
    })[normalized] || "";
    if (!Array.isArray(enrichmentRows) || !enrichmentRows.length) {
      return mapped || "not defined";
    }
    if (enrichmentRows.some(function (item) {
      return !this._hasResolvedEntityId(item && item.f);
    }.bind(this))) {
      return "partially complete";
    }
    if (enrichmentRows.some(function (item) {
      return !this._hasResolvedEntityId(item && item.s);
    }.bind(this))) {
      return "mostly complete";
    }
    if (enrichmentRows.some(function (item) {
      return String(item && item.t || "").trim() === "";
    })) {
      return "near complete";
    }
    return "complete";
  }

  _enrichmentTooltip(status) {
    return ({
      "near complete": "May be missing Tray information",
      "mostly complete": "Missing Spool ID(s)",
      "partially complete": "Missing Filament ID(s)",
      unavailable: "Missing All Data",
      "not defined": "Enrichment status not defined",
      complete: "All enrichment data present",
    })[String(status || "").toLowerCase()] || "Enrichment status";
  }

  _hasResolvedEntityId(value) {
    if (value === null || value === undefined) {
      return false;
    }
    var normalized = String(value).trim().toLowerCase();
    return normalized !== "" && normalized !== "null" && normalized !== "none";
  }

  _splitArchiveNotes(value) {
    var raw = String(value || "");
    var markerIndex = raw.indexOf("+>");
    var cutoff = this._archiveNoteBoundaryIndex(raw);
    if (cutoff < 0) {
      return { userNotes: raw.trimEnd(), payload: null };
    }
    var userNotes = raw.slice(0, cutoff).replace(/\n+$/u, "");
    var payloadRaw = markerIndex >= 0 ? raw.slice(markerIndex + 2).trim() : "";
    try {
      return { userNotes: userNotes, payload: payloadRaw ? JSON.parse(payloadRaw) : null };
    } catch (_error) {
      return { userNotes: userNotes, payload: null };
    }
  }

  _formatDate(value) {
    var parsed = this._parseDate(value);
    if (!parsed) {
      return "Unknown";
    }
    var formatOptions = {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZone: this._haTimeZone(),
    };
    if (this._dateYear(parsed) !== this._dateYear(new Date())) {
      formatOptions.year = "numeric";
    }
    return new Intl.DateTimeFormat(undefined, formatOptions).format(parsed);
  }

  _parseDate(value) {
    if (!value) {
      return null;
    }
    var raw = String(value);
    var normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(raw) ? raw : (raw + "Z");
    var parsed = new Date(normalized);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }

  _dateYear(value) {
    return new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      timeZone: this._haTimeZone(),
    }).format(value);
  }

  _haTimeZone() {
    return this._hass && this._hass.config && this._hass.config.time_zone
      ? String(this._hass.config.time_zone)
      : undefined;
  }

  _formatDuration(secondsValue) {
    var seconds = Number(secondsValue || 0);
    if (!seconds) {
      return "-";
    }
    if (seconds >= 3600) {
      return String(Math.round((seconds / 3600) * 10) / 10) + "h";
    }
    return String(Math.round(seconds / 60)) + "m";
  }

  _formatNumber(value, digits, suffix) {
    var numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) {
      return "-";
    }
    return numeric.toFixed(digits).replace(/\.0$/, "") + suffix;
  }

  _formatCurrency(value) {
    var numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) {
      return "-";
    }
    return "$" + numeric.toFixed(2);
  }

  _tagColor(tag) {
    var helper = window.PrintHistoryTagColors;
    return helper && typeof helper.colorForTag === "function" ? helper.colorForTag(tag) : "#86EFAC";
  }

  _tagStyle(tag) {
    var helper = window.PrintHistoryTagColors;
    if (helper && typeof helper.styleForTag === "function") {
      return helper.styleForTag(tag);
    }

    var fallbackColor = this._tagColor(tag);
    return {
      color: fallbackColor,
      background: "rgba(134, 239, 172, 0.14)",
      border: "rgba(134, 239, 172, 0.58)",
      glow: "rgba(134, 239, 172, 0.2)",
    };
  }

  _renderTagChip(tag) {
    var style = this._tagStyle(tag);
    var tooltip = this._buildFilterActionTooltip('Tag: ' + String(tag || ''), 'Click to add this tag to filters');
    return '<button class="tag interactive-chip" type="button" data-action="apply-filter" data-filter-action="tag_add" data-filter-value="' + this._escapeAttribute(tag) + '" title="' + this._escapeAttribute(tooltip) + '" aria-label="' + this._escapeAttribute('Tag ' + String(tag || '') + '. Click to add this tag to filters.') + '" style="background:' + this._escapeAttribute(style.background) + ';box-shadow:inset 0 0 0 1px ' + this._escapeAttribute(style.border) + ',0 0 0 1px ' + this._escapeAttribute(style.glow) + ';--interactive-chip-border:' + this._escapeAttribute(style.border) + ';">' + this._escapeHtml(tag) + '</button>';
  }

  _buildFilterActionTooltip(primaryLabel, actionHint) {
    var primary = String(primaryLabel || '').trim();
    var hint = String(actionHint || '').trim();
    return [primary, hint].filter(Boolean).join('\n');
  }

  _statusEntityAttributes() {
    var state = this._hass && this._hass.states ? this._hass.states["sensor.bambuddy_print_history_browser_status"] : null;
    return state && state.attributes ? state.attributes : {};
  }

  _resolvedEntryId() {
    var attributes = this._statusEntityAttributes();
    return attributes && attributes.entry_id ? String(attributes.entry_id).trim() : "";
  }

  _buildArchiveViewerCardConfig(archive) {
    return {
      type: "custom:print-history-3d-viewer-card",
      archive_id: archive && archive.id != null ? String(archive.id) : "",
      archive_name: archive && archive.print_name ? String(archive.print_name) : "",
      archive_json: archive ? JSON.stringify(archive) : "{}",
      entry_id: this._resolvedEntryId(),
      bambuddy_base: this._apiBaseUrl(),
    };
  }

  _buildArchiveViewerPopupContent(archive) {
    return {
      type: "vertical-stack",
      cards: [this._buildArchiveViewerCardConfig(archive)],
    };
  }

  _openArchiveViewerPopup(archive) {
    if (!archive || archive.id == null) {
      return;
    }
    this._fireBrowserModEvent("browser_mod.popup", {
      title: "3D Viewer",
      size: "wide",
      content: this._buildArchiveViewerPopupContent(archive),
    });
  }

  _popupProjectCatalog() {
    var attributes = this._statusEntityAttributes();
    return Array.isArray(attributes.project_options) ? attributes.project_options : [];
  }

  _printerFilterOptions() {
    var state = this._hass && this._hass.states ? this._hass.states["input_select.print_history_filter_printer"] : null;
    return state && state.attributes && Array.isArray(state.attributes.options) ? state.attributes.options : [];
  }

  _resolvePrinterFilterValue(printerId, printerName) {
    var printerIdText = printerId == null ? "" : String(printerId).trim();
    var printerNameText = printerName == null ? "" : String(printerName).trim();
    var options = this._printerFilterOptions();

    for (var index = 0; index < options.length; index += 1) {
      var option = String(options[index] || "").trim();
      if (!option || option === "All") {
        continue;
      }
      if (printerIdText && option === printerIdText) {
        return option;
      }
      if (printerNameText && option === printerNameText) {
        return option;
      }
      if (printerIdText && printerNameText && option === (printerNameText + " (" + printerIdText + ")")) {
        return option;
      }
    }

    if (printerNameText) {
      return printerNameText;
    }
    if (printerIdText) {
      return printerIdText;
    }
    return "";
  }

  _popupProjectLabel(projectId, projectName) {
    var projectIdText = projectId == null ? "" : String(projectId).trim();
    var projectNameText = projectName == null ? "" : String(projectName).trim();
    var catalog = this._popupProjectCatalog();
    for (var index = 0; index < catalog.length; index += 1) {
      var option = catalog[index] || {};
      if (String(option.id || "").trim() === projectIdText && String(option.label || "").trim()) {
        return String(option.label).trim();
      }
    }
    if (projectNameText) {
      return projectIdText ? projectNameText + " [" + projectIdText + "]" : projectNameText;
    }
    if (projectIdText) {
      return "Project [" + projectIdText + "]";
    }
    return "No Project";
  }

  _popupProjectOptions(archive) {
    var labels = ["No Project"];
    var catalog = this._popupProjectCatalog();
    for (var index = 0; index < catalog.length; index += 1) {
      var label = catalog[index] && catalog[index].label ? String(catalog[index].label).trim() : "";
      if (label && labels.indexOf(label) === -1) {
        labels.push(label);
      }
    }
    var selected = this._popupProjectLabel(archive && archive.project_id, archive && archive.project_name);
    if (selected !== "No Project" && labels.indexOf(selected) === -1) {
      labels.push(selected);
    }
    return {
      options: labels,
      selected: selected,
    };
  }

  async _handleClick(event) {
    var actionNode = event.target && event.target.closest ? event.target.closest("[data-action]") : null;
    if (!actionNode) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();

    var action = actionNode.getAttribute("data-action");
    var rawArchive = actionNode.getAttribute("data-archive") || actionNode.closest("[data-archive]")?.getAttribute("data-archive") || "{}";
    var archive = this._parseJson(rawArchive, {});

    if (action === "select-archive") {
      this._toggleSelectedArchive(archive);
      return;
    }

    if (action === "multi-select-dialog-cancel") {
      this._closeBulkDialog();
      return;
    }

    if (action === "multi-select-dialog-submit") {
      await this._submitBulkDialog();
      return;
    }

    if (action === "favorite") {
      await this._toggleFavorite(archive);
      return;
    }

    if (action === "apply-filter") {
      await this._applyCardFilterAction(actionNode);
      return;
    }

    if (action === "viewer") {
      this._openArchiveViewerPopup(archive);
      return;
    }

    if (action === "media-prev" || action === "media-next") {
      var galleryCount = Number(actionNode.getAttribute("data-gallery-count") || 0);
      if (archive && archive.id != null && galleryCount > 1) {
        var currentGalleryIndex = this._readRenderedMediaGalleryIndex(actionNode, galleryCount);
        if (!Number.isFinite(currentGalleryIndex)) {
          currentGalleryIndex = this._mediaGalleryIndex(archive.id, galleryCount);
        }
        this._setMediaGalleryIndex(archive.id, currentGalleryIndex + (action === "media-next" ? 1 : -1), galleryCount);
      }
      return;
    }

    if (action === "open") {
      if (Date.now() < this._suppressOpenUntil && String(this._suppressOpenArchiveId || "") === String(archive && archive.id || "")) {
        return;
      }
      await this._openArchivePopup(archive);
    }
  }

  _handlePointerDown(event) {
    if (this._isMultiSelectMode()) {
      this._mediaSwipe = null;
      return;
    }
    if (!event || (event.target && event.target.closest && event.target.closest("[data-action]"))) {
      return;
    }
    var surface = event.target && event.target.closest ? event.target.closest(".media-gallery-surface") : null;
    if (!surface) {
      this._mediaSwipe = null;
      return;
    }
    this._mediaSwipe = {
      archiveId: String(surface.getAttribute("data-archive-id") || ""),
      galleryCount: Number(surface.getAttribute("data-gallery-count") || 0),
      galleryIndex: this._readRenderedMediaGalleryIndex(surface, Number(surface.getAttribute("data-gallery-count") || 0)),
      startX: Number(event.clientX || 0),
      startY: Number(event.clientY || 0),
    };
  }

  _handlePointerUp(event) {
    if (this._isMultiSelectMode()) {
      this._mediaSwipe = null;
      return;
    }
    if (!this._mediaSwipe) {
      return;
    }
    var swipe = this._mediaSwipe;
    this._mediaSwipe = null;
    if (!swipe.archiveId || swipe.galleryCount <= 1) {
      return;
    }
    var deltaX = Number(event.clientX || 0) - swipe.startX;
    var deltaY = Number(event.clientY || 0) - swipe.startY;
    if (Math.abs(deltaX) < 40 || Math.abs(deltaX) <= Math.abs(deltaY)) {
      return;
    }
    this._suppressOpenArchiveId = swipe.archiveId;
    this._suppressOpenUntil = Date.now() + 450;
    var currentGalleryIndex = Number.isFinite(swipe.galleryIndex) ? swipe.galleryIndex : this._mediaGalleryIndex(swipe.archiveId, swipe.galleryCount);
    this._setMediaGalleryIndex(swipe.archiveId, currentGalleryIndex + (deltaX < 0 ? 1 : -1), swipe.galleryCount);
  }

  _handlePointerCancel() {
    this._mediaSwipe = null;
  }

  _handleMouseOver(event) {
    var dotNode = event && event.target && event.target.closest ? event.target.closest('.dot-button') : null;
    if (!dotNode) {
      return;
    }
    this._setDotTooltipState(dotNode, true);
  }

  _handleMouseOut(event) {
    var dotNode = event && event.target && event.target.closest ? event.target.closest('.dot-button') : null;
    var nextNode = event && event.relatedTarget && event.relatedTarget.closest ? event.relatedTarget.closest('.dot-button') : null;
    if (!dotNode || dotNode === nextNode) {
      return;
    }
    this._setDotTooltipState(dotNode, false);
  }

  _handleFocusIn(event) {
    var dotNode = event && event.target && event.target.closest ? event.target.closest('.dot-button') : null;
    if (!dotNode) {
      return;
    }
    this._setDotTooltipState(dotNode, true);
  }

  _handleFocusOut(event) {
    var dotNode = event && event.target && event.target.closest ? event.target.closest('.dot-button') : null;
    var nextNode = event && event.relatedTarget && event.relatedTarget.closest ? event.relatedTarget.closest('.dot-button') : null;
    if (!dotNode || dotNode === nextNode) {
      return;
    }
    this._setDotTooltipState(dotNode, false);
  }

  _handleTooltipLayout() {
    var dotNode = this.shadowRoot ? this.shadowRoot.querySelector('.dot-button.tooltip-active') : null;
    if (!dotNode) {
      return;
    }
    this._updateDotTooltipPosition(dotNode);
  }

  _setDotTooltipState(dotNode, isActive) {
    if (!dotNode) {
      return;
    }
    if (!isActive) {
      dotNode.classList.remove('tooltip-active');
      dotNode.style.removeProperty('--dot-tooltip-shift');
      return;
    }

    var currentActive = this.shadowRoot ? this.shadowRoot.querySelector('.dot-button.tooltip-active') : null;
    if (currentActive && currentActive !== dotNode) {
      currentActive.classList.remove('tooltip-active');
      currentActive.style.removeProperty('--dot-tooltip-shift');
    }

    dotNode.classList.add('tooltip-active');
    this._updateDotTooltipPosition(dotNode);
  }

  _updateDotTooltipPosition(dotNode) {
    var tooltip = dotNode && dotNode.querySelector ? dotNode.querySelector('.dot-tooltip') : null;
    if (!tooltip) {
      return;
    }

    var previousVisibility = tooltip.style.visibility;
    var previousOpacity = tooltip.style.opacity;
    tooltip.style.visibility = 'hidden';
    tooltip.style.opacity = '1';

    var tooltipRect = tooltip.getBoundingClientRect();
    var dotRect = dotNode.getBoundingClientRect();

    tooltip.style.visibility = previousVisibility;
    tooltip.style.opacity = previousOpacity;

    if (!tooltipRect.width || !dotRect.width) {
      dotNode.style.removeProperty('--dot-tooltip-shift');
      return;
    }

    var minViewportPadding = 8;
    var centeredLeft = dotRect.left + (dotRect.width / 2) - (tooltipRect.width / 2);
    var centeredRight = centeredLeft + tooltipRect.width;
    var shift = 0;

    if (centeredLeft < minViewportPadding) {
      shift = minViewportPadding - centeredLeft;
    } else if (centeredRight > window.innerWidth - minViewportPadding) {
      shift = (window.innerWidth - minViewportPadding) - centeredRight;
    }

    dotNode.style.setProperty('--dot-tooltip-shift', String(Math.round(shift)) + 'px');
  }

  async _handleKeydown(event) {
    if (!event || (event.key !== "Enter" && event.key !== " ")) {
      return;
    }
    var target = event.target || null;
    if (!target || target.closest("[data-action=\"favorite\"]")) {
      return;
    }
    var cardNode = target.closest ? target.closest('.card[data-action="open"],.card[data-action="select-archive"]') : null;
    if (!cardNode || cardNode !== target) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    var archive = this._parseJson(cardNode.getAttribute("data-archive") || "{}", {});
    if (cardNode.getAttribute("data-action") === "select-archive") {
      this._toggleSelectedArchive(archive);
      return;
    }
    await this._openArchivePopup(archive);
  }

  async _toggleFavorite(archive) {
    if (!archive || archive.id == null || !this._hass) {
      return;
    }
    await this._hass.callService("script", "toggle_print_history_archive_favorite", {
      archive_id: String(archive.id),
    });
    var archives = Array.isArray(this._response.archives) ? this._response.archives.slice() : [];
    this._response.archives = archives.map(function (item) {
      if (String(item && item.id) !== String(archive.id)) {
        return item;
      }
      return Object.assign({}, item, { is_favorite: !item.is_favorite });
    });
    this._viewSignature = this._buildViewSignature(this._hass);
    this._renderBody();
  }

  async _applyCardFilterAction(actionNode) {
    if (!actionNode || !this._hass) {
      return;
    }

    var filterAction = String(actionNode.getAttribute("data-filter-action") || "").trim().toLowerCase();
    var filterValue = String(actionNode.getAttribute("data-filter-value") || "").trim();
    if (!filterAction || !filterValue) {
      return;
    }

    await this._hass.callService("script", "apply_print_history_card_filter_action", {
      action: filterAction,
      value: filterValue,
    });
  }

  _buildPopupActionButton(name, icon, background, tapAction) {
    return {
      type: "custom:button-card",
      name: name,
      icon: icon,
      show_name: true,
      show_icon: true,
      show_state: false,
      tap_action: tapAction,
      hold_action: { action: "none" },
      styles: {
        card: [
          { padding: "12px 10px" },
          { "border-radius": "16px" },
          { "box-shadow": "none" },
          { border: "1px solid rgba(255,255,255,0.08)" },
          { background: background },
        ],
        grid: [
          { "grid-template-areas": '"i" "n"' },
          { "grid-template-columns": "1fr" },
          { "justify-items": "center" },
          { gap: "6px" },
        ],
        icon: [
          { width: "22px" },
          { height: "22px" },
          { color: "var(--primary-text-color)" },
        ],
        name: [
          { "font-size": "12px" },
          { "font-weight": "600" },
          { color: "var(--primary-text-color)" },
        ],
      },
    };
  }

  _popupTextFieldCardMod() {
    return {
      style: {
        "hui-input-text-entity-row $ ha-textfield $ ha-input $ wa-input $": [
          ".control::placeholder {",
          "  color: transparent !important;",
          "}",
          ".text-field:focus-within .control::placeholder {",
          "  color: var(--secondary-text-color) !important;",
          "}",
        ].join("\n"),
      },
    };
  }

  async _openArchivePopup(archive) {
    if (!archive || archive.id == null || !this._hass) {
      return;
    }

    var archiveId = archive.id;
    var archiveName = archive.print_name || ("Archive " + archiveId);
      var popupTitle = archiveName + " · #" + archiveId;
    var archiveInfo = this._splitArchiveNotes(archive.notes);
    var archiveUserTags = this._userTags(archive.tags);
    var archiveStatus = this._normalizeStatus(archive.status || "completed");
    var archiveFailureReason = String(archive.failure_reason || "").trim();
    var projectPicker = this._popupProjectOptions(archive);
    var statusOptions = ["Completed", "Failed", "Cancelled", "Printing"];
    var archiveStatusOption = archiveStatus ? archiveStatus.charAt(0).toUpperCase() + archiveStatus.slice(1) : "Completed";
    if (statusOptions.indexOf(archiveStatusOption) === -1) {
      statusOptions.push(archiveStatusOption);
    }
    var failureReasonOptions = [
      "Unspecified",
      "Adhesion failure",
      "Spaghetti / Detached",
      "Layer shift",
      "Clogged nozzle",
      "Filament runout",
      "Warping",
      "Stringing",
      "Under-extrusion",
      "Power failure",
      "User cancelled",
      "Other",
    ];
    if (archiveFailureReason && failureReasonOptions.indexOf(archiveFailureReason) === -1) {
      failureReasonOptions.push(archiveFailureReason);
    }
    var editablePrintName = String(archive.print_name || "").slice(0, 255);
    var editableTags = archiveUserTags.join(", ").slice(0, 255);
    var editableNotes = String(archiveInfo.userNotes || "").slice(0, 255);
    var archiveJson = JSON.stringify(archive);
    var cards = [
      {
        type: "custom:print-history-photo-gallery-card",
        archive_json: archiveJson,
        detail_entity: "sensor.print_history_popup_archive_detail",
        api_base_entity: "input_text.bambuddy_api_base_url",
        visibility_entity: "input_boolean.print_history_show_images",
        include_thumbnail: true,
      },
      {
        type: "custom:button-card",
        template: "print_history_archive_popup_content",
        entity: "sensor.print_history_popup_archive_detail",
        triggers_update: ["sensor.print_history_popup_archive_detail", "input_boolean.print_history_popup_is_favorite"],
        variables: {
          archive_json: archiveJson,
        },
        tap_action: { action: "none" },
        hold_action: { action: "none" },
      },
      {
        type: "custom:tabbed-card",
        options: {},
        tabs: [
          {
            card: {
              type: "custom:print-filament-breakdown-card",
              source: "archive",
              mode: "weight",
              archive_entity: "sensor.print_history_popup_archive_detail",
              archive_json: archiveJson,
              show_title: false,
              show_issues: true,
            },
            attributes: {
              label: "Print Weight",
              icon: "mdi:weight-gram",
            },
          },
          {
            card: {
              type: "custom:print-filament-breakdown-card",
              source: "archive",
              mode: "cost",
              archive_entity: "sensor.print_history_popup_archive_detail",
              archive_json: archiveJson,
              show_title: false,
              show_issues: false,
            },
            attributes: {
              label: "Print Cost",
              icon: "mdi:currency-usd",
            },
          },
        ],
      },
      {
        type: "custom:print-history-tag-editor-card",
        entity: "input_text.print_history_popup_tags",
        suggestions_entity: "input_select.print_history_filter_tag",
        title: "Tags",
        placeholder: "Add a tag and press Enter",
        helper: "Reuse an existing tag or create a new one. Press Enter or comma to add.",
      },
      {
        type: "entities",
        show_header_toggle: false,
        card_mod: this._popupTextFieldCardMod(),
        entities: [
          { entity: "input_text.print_history_popup_print_name", name: "Print Name", icon: "mdi:printer-3d" },
          { entity: "input_select.print_history_popup_project", name: "Project", icon: "mdi:folder-outline" },
          { entity: "input_select.print_history_popup_status", name: "Status", icon: "mdi:list-status" },
          {
            type: "conditional",
            conditions: [{
              condition: "or",
              conditions: [
                { condition: "state", entity: "input_select.print_history_popup_status", state: "Failed" },
                { condition: "state", entity: "input_select.print_history_popup_status", state: "Cancelled" },
              ],
            }],
            row: { entity: "input_select.print_history_popup_failure_reason", name: "Failure Reason", icon: "mdi:alert-circle-outline" },
          },
          { entity: "input_text.print_history_popup_notes", name: "Notes", icon: "mdi:text-box-outline" },
        ],
      },
      {
        type: "grid",
        columns: archiveStatus === "printing" ? 4 : 5,
        square: false,
        cards: [
          ...(archiveStatus === "printing" ? [] : [this._buildPopupActionButton(
            "Re-Enrich",
            "mdi:refresh-circle",
            "rgba(46,125,50,0.18)",
            { action: "call-service", service: "script.reenrich_print_history_archive", data: { archive_id: String(archiveId) } }
          )]),
          this._buildPopupActionButton(
            "3D View",
            "mdi:cube-scan",
            "rgba(0,137,123,0.18)",
            {
              action: "fire-dom-event",
              browser_mod: {
                service: "browser_mod.popup",
                data: {
                  title: "3D Viewer",
                  size: "wide",
                  content: this._buildArchiveViewerPopupContent(archive),
                },
              },
            }
          ),
          this._buildPopupActionButton(
            "Save",
            "mdi:content-save-outline",
            "rgba(21,101,192,0.18)",
            { action: "call-service", service: "script.save_print_history_archive_popup_edits" }
          ),
          this._buildPopupActionButton(
            "Close",
            "mdi:close",
            "rgba(255,255,255,0.04)",
            { action: "fire-dom-event", browser_mod: { service: "browser_mod.close_popup" } }
          ),
        ],
      },
    ];

    this._fireBrowserModEvent("browser_mod.sequence", {
      sequence: [
        {
          service: "input_text.set_value",
          data: {
            entity_id: "input_text.print_history_popup_archive_id",
            value: String(archiveId),
          },
        },
        {
          service: archive.is_favorite ? "input_boolean.turn_on" : "input_boolean.turn_off",
          data: {
            entity_id: "input_boolean.print_history_popup_is_favorite",
          },
        },
        {
          service: "input_text.set_value",
          data: {
            entity_id: "input_text.print_history_popup_print_name",
            value: editablePrintName,
          },
        },
        {
          service: "input_text.set_value",
          data: {
            entity_id: "input_text.print_history_popup_tags",
            value: editableTags,
          },
        },
        {
          service: "input_text.set_value",
          data: {
            entity_id: "input_text.print_history_popup_notes",
            value: editableNotes,
          },
        },
        {
          service: "input_select.set_options",
          data: {
            entity_id: "input_select.print_history_popup_project",
            options: projectPicker.options,
          },
        },
        {
          service: "input_select.select_option",
          data: {
            entity_id: "input_select.print_history_popup_project",
            option: projectPicker.selected,
          },
        },
        {
          service: "input_select.set_options",
          data: {
            entity_id: "input_select.print_history_popup_status",
            options: statusOptions,
          },
        },
        {
          service: "input_select.select_option",
          data: {
            entity_id: "input_select.print_history_popup_status",
            option: archiveStatusOption,
          },
        },
        {
          service: "input_select.set_options",
          data: {
            entity_id: "input_select.print_history_popup_failure_reason",
            options: failureReasonOptions,
          },
        },
        {
          service: "input_select.select_option",
          data: {
            entity_id: "input_select.print_history_popup_failure_reason",
            option: archiveFailureReason || "Unspecified",
          },
        },
        {
          service: "browser_mod.popup",
          data: {
              title: popupTitle,
            size: "normal",
            content: {
              type: "vertical-stack",
              cards: cards,
            },
          },
        },
      ],
    });
  }

  _fireBrowserModEvent(service, data) {
    var event = new CustomEvent("ll-custom", {
      bubbles: true,
      composed: true,
      detail: {
        browser_mod: {
          service: service,
          data: data,
          target: {},
        },
      },
    });

    if (document && document.body) {
      document.body.dispatchEvent(event);
      return;
    }

    this.dispatchEvent(event);
  }

  _parseJson(value, fallback) {
    try {
      return JSON.parse(value || "{}");
    } catch (_error) {
      return fallback;
    }
  }

  _escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  _escapeAttribute(value) {
    return this._escapeHtml(value).replace(/`/g, "&#96;");
  }
}

customElements.define("print-history-browser-card", PrintHistoryBrowserCard);