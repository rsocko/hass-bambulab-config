// Bulk Intake (Working Groups) — neutered placeholder.
//
// PR D of the Working Groups Deprecation Plan strips the legacy bulk import
// workflow that depended on the removed `model_catalog_bulk_discover_working_groups`
// and `model_catalog_bulk_import_working_groups` REST commands and on the
// retired `/api/working-groups/*` endpoints (now 410 Gone).
//
// This card is intentionally a placeholder until the repurpose lands. See
// issue #1567 for the follow-up scope:
//   "Allow user to pick a Root folder from Working files as the destination
//    for 'existing' choice OR simply import to root of Working Files when
//    'new'."
//
// Once the new folder-first bulk intake ships, replace this placeholder with
// the rebuilt card and bump the cache-bust version in
// homeassistant/packages/3d_printing/common/dashboards/_resources.yaml.

class ModelCatalogBulkImportCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
  }

  setConfig(config) {
    this._config = config || {};
    this._render();
  }

  set hass(_hass) {
    // No-op: placeholder card has no hass-driven state.
  }

  getCardSize() {
    return 3;
  }

  _render() {
    if (!this.shadowRoot) {
      return;
    }
    var title = (this._config && this._config.title)
      ? String(this._config.title)
      : "Bulk Intake (Folder Import)";
    this.shadowRoot.innerHTML = ""
      + "<style>"
      + ":host{display:block;font-family:var(--primary-font-family,Segoe UI,sans-serif);}"
      + ".card{background:var(--card-background-color,#fff);border:1px solid rgba(120,120,120,.22);border-radius:14px;padding:16px;}"
      + ".title{font-size:1.05rem;font-weight:650;margin-bottom:8px;color:var(--primary-text-color);}"
      + ".body{font-size:.92rem;color:var(--secondary-text-color,#555);line-height:1.45;}"
      + ".chip{display:inline-block;margin-top:10px;padding:4px 10px;border-radius:999px;background:var(--secondary-background-color,#f0f3f4);color:var(--primary-text-color);font-size:.8rem;}"
      + "</style>"
      + "<ha-card class=\"card\">"
      + "<div class=\"title\">" + title + "</div>"
      + "<div class=\"body\">"
      + "Bulk intake is being rebuilt around the folder-first Working Files API. "
      + "The legacy working-group import workflow has been removed."
      + "<br><br>"
      + "Follow-up will let you pick an existing Working Files folder as the "
      + "destination, or import a batch to the root of Working Files when "
      + "creating a new folder."
      + "<div class=\"chip\">Tracked in issue #1567</div>"
      + "</div>"
      + "</ha-card>";
  }
}

if (!customElements.get("model-catalog-bulk-import-card")) {
  customElements.define("model-catalog-bulk-import-card", ModelCatalogBulkImportCard);
}
