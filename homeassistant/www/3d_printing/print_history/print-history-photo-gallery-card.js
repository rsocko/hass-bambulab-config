class PrintHistoryPhotoGalleryCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._activeIndex = 0;
    this._expanded = false;
    this._boundKeydownHandler = this._handleKeydown.bind(this);
    this._boundClickHandler = this._handleHostClick.bind(this);
  }

  setConfig(config) {
    this._config = {
      archive_json: config && config.archive_json ? config.archive_json : "{}",
      archive_entity: config && config.archive_entity ? config.archive_entity : "sensor.print_history_archives",
      api_base_entity: config && config.api_base_entity ? config.api_base_entity : "input_text.bambuddy_api_base_url",
      visibility_entity: config && config.visibility_entity ? config.visibility_entity : "",
      title: config && config.title ? config.title : "Archive Photos",
      include_thumbnail: !config || config.include_thumbnail !== false,
      compact: !!(config && config.compact),
    };
    this._activeIndex = 0;
    this._expanded = false;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  connectedCallback() {
    window.addEventListener("keydown", this._boundKeydownHandler);
    this.addEventListener("click", this._boundClickHandler);
  }

  disconnectedCallback() {
    window.removeEventListener("keydown", this._boundKeydownHandler);
    this.removeEventListener("click", this._boundClickHandler);
  }

  getCardSize() {
    return 4;
  }

  _handleKeydown(event) {
    if (!this._expanded) {
      return;
    }
    if (event.key === "Escape") {
      event.stopPropagation();
      this._expanded = false;
      this._render();
      return;
    }
    if (event.key === "ArrowLeft") {
      event.stopPropagation();
      this._moveActiveIndex(-1);
      return;
    }
    if (event.key === "ArrowRight") {
      event.stopPropagation();
      this._moveActiveIndex(1);
    }
  }

  _handleHostClick(event) {
    event.stopPropagation();
  }

  _parseArchive() {
    if (!this._config) {
      return {};
    }
    if (typeof this._config.archive_json === "string") {
      try {
        return JSON.parse(this._config.archive_json || "{}");
      } catch (_error) {
        return {};
      }
    }
    if (this._config.archive_json && typeof this._config.archive_json === "object") {
      return this._config.archive_json;
    }
    return {};
  }

  _resolveArchive() {
    var snapshotArchive = this._parseArchive();
    var archiveId = snapshotArchive && snapshotArchive.id != null ? snapshotArchive.id : null;
    var entityId = this._config ? this._config.archive_entity : "sensor.print_history_archives";
    var raw = this._hass && this._hass.states && this._hass.states[entityId] && this._hass.states[entityId].attributes
      ? this._hass.states[entityId].attributes.archives_json
      : [];

    if (archiveId == null) {
      return snapshotArchive;
    }

    try {
      var archiveCache = Array.isArray(raw) ? raw : JSON.parse(raw || "[]");
      if (Array.isArray(archiveCache)) {
        return archiveCache.find(function (item) {
          return String(item && item.id) === String(archiveId);
        }) || snapshotArchive;
      }
    } catch (_error) {
      return snapshotArchive;
    }

    return snapshotArchive;
  }

  _getBaseUrl() {
    var entityId = this._config ? this._config.api_base_entity : "input_text.bambuddy_api_base_url";
    var raw = this._hass && this._hass.states && this._hass.states[entityId]
      ? this._hass.states[entityId].state
      : "";
    return String(raw || "").replace(/\/$/, "");
  }

  _isVisible() {
    var entityId = this._config ? this._config.visibility_entity : "";
    if (!entityId) {
      return true;
    }
    var state = this._hass && this._hass.states && this._hass.states[entityId]
      ? this._hass.states[entityId].state
      : "on";
    return state !== "off";
  }

  _buildImages(archive) {
    var baseUrl = this._getBaseUrl();
    var archiveId = archive && archive.id != null ? archive.id : null;
    var images = [];
    var seen = {};

    if (!baseUrl || archiveId == null) {
      return images;
    }

    if (this._config.include_thumbnail && archive && archive.thumbnail_path) {
      images.push({
        key: "thumbnail",
        label: "Thumbnail",
        src: baseUrl + "/api/v1/archives/" + encodeURIComponent(String(archiveId)) + "/thumbnail",
        kind: "thumbnail",
      });
      seen.thumbnail = true;
    }

    var photos = Array.isArray(archive && archive.photos) ? archive.photos : [];
    photos.forEach(function (filename, index) {
      var value = String(filename || "").trim();
      if (!value || seen[value]) {
        return;
      }
      seen[value] = true;
      images.push({
        key: value,
        label: "Photo " + String(index + 1),
        src: baseUrl + "/api/v1/archives/" + encodeURIComponent(String(archiveId)) + "/photos/" + encodeURIComponent(value),
        kind: "photo",
        filename: value,
      });
    });

    return images;
  }

  _moveActiveIndex(direction) {
    var archive = this._resolveArchive();
    var images = this._buildImages(archive);
    if (!images.length) {
      return;
    }
    var nextIndex = this._activeIndex + direction;
    if (nextIndex < 0) {
      nextIndex = images.length - 1;
    } else if (nextIndex >= images.length) {
      nextIndex = 0;
    }
    this._activeIndex = nextIndex;
    this._render();
  }

  _escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  _render() {
    if (!this.shadowRoot || !this._config) {
      return;
    }

    if (!this._isVisible()) {
      this.shadowRoot.innerHTML = "<style>:host{display:none}</style>";
      return;
    }

    var archive = this._resolveArchive();
    var images = this._buildImages(archive);
    if (!images.length) {
      this.shadowRoot.innerHTML = "<style>:host{display:none}</style>";
      return;
    }

    if (this._activeIndex >= images.length) {
      this._activeIndex = 0;
    }

    var active = images[this._activeIndex];
    var archiveName = archive && archive.print_name ? String(archive.print_name) : "Archive Photos";
    var photoCount = Math.max(0, images.length - (images[0] && images[0].kind === "thumbnail" ? 1 : 0));
    var subtitle = photoCount > 0
      ? photoCount + (photoCount === 1 ? " additional photo" : " additional photos")
      : "Thumbnail only";
    var compact = !!this._config.compact;

    this.shadowRoot.innerHTML =
      "<style>" +
      ":host{display:block;}" +
      "ha-card{padding:0;overflow:hidden;border-radius:18px;box-shadow:none;background:none;}" +
      ".wrap{display:flex;flex-direction:column;gap:10px;padding:0;}" +
      ".stage{position:relative;border-radius:18px;overflow:hidden;background:rgba(15,23,42,0.32);min-height:220px;}" +
      ".stage-button{appearance:none;border:none;background:none;padding:0;display:block;width:100%;cursor:zoom-in;}" +
      ".stage-image{display:block;width:100%;max-height:320px;min-height:220px;object-fit:cover;background:rgba(15,23,42,0.32);}" +
      ".topbar{position:absolute;top:12px;left:12px;right:12px;display:flex;justify-content:space-between;gap:8px;pointer-events:none;}" +
      ".badge{display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border-radius:999px;background:rgba(0,0,0,0.58);color:#fff;font-size:11px;font-weight:700;backdrop-filter:blur(10px);}" +
      ".nav{appearance:none;border:none;position:absolute;top:50%;transform:translateY(-50%);width:38px;height:38px;border-radius:999px;background:rgba(0,0,0,0.54);color:#fff;font-size:22px;line-height:1;cursor:pointer;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(10px);}" +
      ".nav.prev{left:12px;}" +
      ".nav.next{right:12px;}" +
      ".meta{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:0 2px;}" +
      ".title{font-size:12px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;color:var(--secondary-text-color);}" +
      ".subtitle{font-size:13px;line-height:1.45;color:var(--secondary-text-color);margin-top:4px;}" +
      ".expand{appearance:none;border:none;border-radius:999px;padding:8px 12px;background:rgba(21,101,192,0.14);color:#bbdefb;font-size:12px;font-weight:700;cursor:pointer;white-space:nowrap;}" +
      ".thumbs{display:flex;gap:8px;overflow-x:auto;padding-bottom:2px;}" +
      ".thumb{appearance:none;border:1px solid transparent;background:none;padding:0;border-radius:14px;overflow:hidden;cursor:pointer;flex:0 0 auto;position:relative;}" +
      ".thumb.active{border-color:rgba(59,130,246,0.9);box-shadow:0 0 0 2px rgba(59,130,246,0.2);}" +
      ".thumb img{display:block;width:72px;height:72px;object-fit:cover;background:rgba(15,23,42,0.28);}" +
      ".thumb-label{position:absolute;left:6px;bottom:6px;padding:3px 6px;border-radius:999px;background:rgba(0,0,0,0.58);color:#fff;font-size:10px;font-weight:700;backdrop-filter:blur(10px);}" +
      ".overlay{position:fixed;inset:0;z-index:9999;background:rgba(5,8,14,0.94);display:flex;flex-direction:column;justify-content:space-between;gap:14px;padding:20px 20px 18px;box-sizing:border-box;}" +
      ".overlay[hidden]{display:none;}" +
      ".overlay-header{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;color:#fff;}" +
      ".overlay-title{font-size:1rem;font-weight:700;line-height:1.35;}" +
      ".overlay-subtitle{font-size:13px;line-height:1.45;color:rgba(255,255,255,0.72);margin-top:4px;}" +
      ".overlay-actions{display:flex;align-items:center;gap:8px;}" +
      ".overlay-button{appearance:none;border:none;border-radius:999px;padding:10px 14px;background:rgba(255,255,255,0.12);color:#fff;font-size:12px;font-weight:700;cursor:pointer;}" +
      ".overlay-stage{flex:1;display:flex;align-items:center;justify-content:center;position:relative;min-height:0;}" +
      ".overlay-image{display:block;max-width:100%;max-height:100%;object-fit:contain;border-radius:18px;background:rgba(15,23,42,0.35);}" +
      ".overlay-nav{appearance:none;border:none;position:absolute;top:50%;transform:translateY(-50%);width:50px;height:50px;border-radius:999px;background:rgba(255,255,255,0.12);color:#fff;font-size:28px;line-height:1;cursor:pointer;display:flex;align-items:center;justify-content:center;}" +
      ".overlay-nav.prev{left:10px;}" +
      ".overlay-nav.next{right:10px;}" +
      ".overlay-filmstrip{display:flex;gap:10px;overflow-x:auto;padding-bottom:4px;}" +
      ".overlay-thumb{appearance:none;border:2px solid transparent;background:none;padding:0;border-radius:14px;overflow:hidden;cursor:pointer;flex:0 0 auto;}" +
      ".overlay-thumb.active{border-color:#90caf9;}" +
      ".overlay-thumb img{display:block;width:88px;height:88px;object-fit:cover;background:rgba(15,23,42,0.35);}" +
      ":host([compact]) .wrap{gap:8px;}" +
      ":host([compact]) .stage{border-radius:16px;}" +
      ":host([compact]) .stage-image{max-height:220px;min-height:220px;}" +
      ":host([compact]) .thumb img{width:64px;height:64px;}" +
      "@media (max-width: 640px){.stage-image{max-height:260px;min-height:180px;}.overlay{padding:14px 14px 12px;}.overlay-thumb img{width:72px;height:72px;}.overlay-nav{width:44px;height:44px;}}" +
      "</style>" +
      "<ha-card>" +
      '<div class="wrap">' +
      '<div class="stage">' +
      '<button class="stage-button" type="button" data-action="expand">' +
      '<img class="stage-image" src="' + this._escapeHtml(active.src) + '" alt="' + this._escapeHtml(active.filename || active.label || archiveName) + '">' +
      "</button>" +
      '<div class="topbar">' +
      '<span class="badge">' + this._escapeHtml(active.label) + "</span>" +
      '<span class="badge">' + this._escapeHtml(subtitle) + "</span>" +
      "</div>" +
      (images.length > 1 ? '<button class="nav prev" type="button" data-action="prev" aria-label="Previous image">&#8249;</button><button class="nav next" type="button" data-action="next" aria-label="Next image">&#8250;</button>' : "") +
      "</div>" +
      (compact ? "" : ('<div class="meta">' +
      '<div><div class="title">' + this._escapeHtml(this._config.title) + "</div><div class=\"subtitle\">" + this._escapeHtml(archiveName) + " \u00b7 " + this._escapeHtml(subtitle) + "</div></div>" +
      '<button class="expand" type="button" data-action="expand">Expand</button>' +
      "</div>")) +
      '<div class="thumbs">' + images.map(function (image, index) {
        return '<button class="thumb' + (index === this._activeIndex ? ' active' : '') + '" type="button" data-index="' + this._escapeHtml(String(index)) + '">' +
          '<img src="' + this._escapeHtml(image.src) + '" alt="' + this._escapeHtml(image.filename || image.label || archiveName) + '">' +
          '<span class="thumb-label">' + this._escapeHtml(image.label) + '</span>' +
          '</button>';
      }.bind(this)).join("") + '</div>' +
      "</div>" +
      "</ha-card>" +
      '<div class="overlay"' + (this._expanded ? "" : " hidden") + '>' +
      '<div class="overlay-header">' +
      '<div><div class="overlay-title">' + this._escapeHtml(archiveName) + '</div><div class="overlay-subtitle">' + this._escapeHtml(active.label) + ' \u00b7 ' + this._escapeHtml(subtitle) + '</div></div>' +
      '<div class="overlay-actions"><button class="overlay-button" type="button" data-action="collapse">Close</button></div>' +
      "</div>" +
      '<div class="overlay-stage">' +
      '<img class="overlay-image" src="' + this._escapeHtml(active.src) + '" alt="' + this._escapeHtml(active.filename || active.label || archiveName) + '">' +
      (images.length > 1 ? '<button class="overlay-nav prev" type="button" data-action="prev" aria-label="Previous image">&#8249;</button><button class="overlay-nav next" type="button" data-action="next" aria-label="Next image">&#8250;</button>' : "") +
      "</div>" +
      '<div class="overlay-filmstrip">' + images.map(function (image, index) {
        return '<button class="overlay-thumb' + (index === this._activeIndex ? ' active' : '') + '" type="button" data-index="' + this._escapeHtml(String(index)) + '">' +
          '<img src="' + this._escapeHtml(image.src) + '" alt="' + this._escapeHtml(image.filename || image.label || archiveName) + '">' +
          '</button>';
      }.bind(this)).join("") + "</div>" +
      "</div>";

    var self = this;
    Array.from(this.shadowRoot.querySelectorAll("[data-index]"))
      .forEach(function (button) {
        button.addEventListener("click", function (event) {
          event.stopPropagation();
          var index = Number(button.getAttribute("data-index"));
          if (!Number.isFinite(index)) {
            return;
          }
          self._activeIndex = index;
          self._render();
        });
      });

    Array.from(this.shadowRoot.querySelectorAll("[data-action]"))
      .forEach(function (button) {
        button.addEventListener("click", function (event) {
          event.stopPropagation();
          var action = button.getAttribute("data-action");
          if (action === "prev") {
            self._moveActiveIndex(-1);
            return;
          }
          if (action === "next") {
            self._moveActiveIndex(1);
            return;
          }
          if (action === "expand") {
            self._expanded = true;
            self._render();
            return;
          }
          if (action === "collapse") {
            self._expanded = false;
            self._render();
          }
        });
      });

    if (compact) {
      this.setAttribute("compact", "");
    } else {
      this.removeAttribute("compact");
    }
  }
}

if (!customElements.get("print-history-photo-gallery-card")) {
  customElements.define("print-history-photo-gallery-card", PrintHistoryPhotoGalleryCard);
}