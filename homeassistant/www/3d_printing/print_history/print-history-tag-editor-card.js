class PrintHistoryTagEditorCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._elements = null;
    this._entityValue = "";
    this._suggestionsSignature = "";
    this._tags = [];
    this._draft = "";
    this._focused = false;
    this._highlightedIndex = 0;
  }

  setConfig(config) {
    if (!config || (!config.entity && !config.local_only)) {
      throw new Error("print-history-tag-editor-card requires an entity");
    }

    this._config = {
      entity: config.entity || "",
      local_only: !!config.local_only,
      suggestions_entity: config.suggestions_entity || "input_select.print_history_filter_tag",
      mode_entity: config.mode_entity || "",
      mode_options: Array.isArray(config.mode_options) && config.mode_options.length ? config.mode_options : ["Any", "All"],
      title: config.title || "Tags",
      placeholder: config.placeholder || "Add a tag and press Enter",
      helper:
        config.helper ||
        "Reuse an existing tag or create a new one. Press Enter or comma to add.",
      icon: config.icon || "mdi:tag-multiple-outline",
      max_suggestions: Number(config.max_suggestions || 8),
    };

    if (this._config.local_only) {
      this._entityValue = Array.isArray(config.initial_tags)
        ? config.initial_tags.join(", ")
        : String(config.initial_tags || "");
      this._tags = this._parseTags(this._entityValue);
      this._suggestionsSignature = JSON.stringify(this._readSuggestionPool());
    } else {
      this._syncTagsFromEntity();
    }
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) {
      return;
    }

    if (!this._config.local_only) {
      const nextEntityValue = this._readEntityValue();
      if (nextEntityValue !== this._entityValue) {
        this._entityValue = nextEntityValue;
        this._tags = this._parseTags(nextEntityValue);
      }
    }

    const nextSuggestionsSignature = JSON.stringify(this._readSuggestionPool());
    if (nextSuggestionsSignature !== this._suggestionsSignature) {
      this._suggestionsSignature = nextSuggestionsSignature;
    }

    this._render();
  }

  getCardSize() {
    return 3;
  }

  _readEntityValue() {
    return String(this._hass?.states?.[this._config?.entity]?.state || "");
  }

  _readModeValue() {
    return String(this._hass?.states?.[this._config?.mode_entity]?.state || "").trim();
  }

  _syncTagsFromEntity() {
    this._entityValue = this._readEntityValue();
    this._tags = this._parseTags(this._entityValue);
    this._suggestionsSignature = JSON.stringify(this._readSuggestionPool());
  }

  _escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  _normalizeTag(value) {
    return String(value || "").trim().toLowerCase();
  }

  _parseTags(rawValue) {
    const seen = new Set();
    return String(rawValue || "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean)
      .filter((value) => {
        const normalized = this._normalizeTag(value);
        if (!normalized || seen.has(normalized)) {
          return false;
        }
        seen.add(normalized);
        return true;
      });
  }

  _isSystemTag(tag) {
    const normalized = this._normalizeTag(tag);
    if (!normalized) {
      return false;
    }

    const systemTagValues = ["ha_enriched:true"];
    const systemTagPrefixes = [
      "f:",
      "s:",
      "spoolman:",
      "vendor:",
      "material:",
      "cost:",
      "status:",
      "ha enrichment:",
      "ha_enrichment:",
    ];

    return systemTagValues.includes(normalized) || systemTagPrefixes.some((prefix) => normalized.startsWith(prefix));
  }

  _readSuggestionPool() {
    const rawOptions = this._hass?.states?.[this._config?.suggestions_entity]?.attributes?.options;
    const options = Array.isArray(rawOptions) ? rawOptions : [];
    const seen = new Set();

    return options
      .map((option) => String(option || "").trim())
      .filter(Boolean)
      .filter((option) => !["all", "none"].includes(this._normalizeTag(option)))
      .filter((option) => !this._isSystemTag(option))
      .filter((option) => {
        const normalized = this._normalizeTag(option);
        if (seen.has(normalized)) {
          return false;
        }
        seen.add(normalized);
        return true;
      })
      .sort((left, right) => left.localeCompare(right, undefined, { sensitivity: "base" }));
  }

  _tagColor(tag) {
    const helper = window.PrintHistoryTagColors;
    if (!helper || typeof helper.colorForTag !== "function") {
      return "#86EFAC";
    }

    return helper.colorForTag(tag);
  }

  _tagStyle(tag) {
    const helper = window.PrintHistoryTagColors;
    if (helper && typeof helper.styleForTag === "function") {
      return helper.styleForTag(tag);
    }

    return {
      color: this._tagColor(tag),
      background: "rgba(134, 239, 172, 0.14)",
      border: "rgba(134, 239, 172, 0.58)",
      glow: "rgba(134, 239, 172, 0.2)",
    };
  }

  _filteredSuggestions() {
    const selected = new Set(this._tags.map((tag) => this._normalizeTag(tag)));
    const query = this._normalizeTag(this._draft);
    const available = this._readSuggestionPool().filter((option) => !selected.has(this._normalizeTag(option)));

    if (!query) {
      return available.slice(0, this._config.max_suggestions);
    }

    const startsWith = [];
    const contains = [];
    available.forEach((option) => {
      const normalized = this._normalizeTag(option);
      if (normalized.startsWith(query)) {
        startsWith.push(option);
      } else if (normalized.includes(query)) {
        contains.push(option);
      }
    });

    return startsWith.concat(contains).slice(0, this._config.max_suggestions);
  }

  _canonicalTagLabel(tag) {
    const cleaned = String(tag || "").trim();
    if (!cleaned) {
      return "";
    }

    const match = this._readSuggestionPool().find(
      (option) => this._normalizeTag(option) === this._normalizeTag(cleaned)
    );
    return match || cleaned;
  }

  async _persistTags() {
    const joinedValue = this._tags.join(", ");
    this._entityValue = joinedValue;

    if (this._config?.local_only) {
      return;
    }

    if (!this._hass || !this._config?.entity) {
      return;
    }

    await this._hass.callService("input_text", "set_value", {
      entity_id: this._config.entity,
      value: joinedValue,
    });
  }

  getTags() {
    return this._tags.slice();
  }

  setTags(value) {
    const nextValue = Array.isArray(value) ? value.join(", ") : String(value || "");
    this._entityValue = nextValue;
    this._tags = this._parseTags(nextValue);
    this._draft = "";
    this._highlightedIndex = 0;
    this._render();
  }

  async _persistMode(option) {
    const targetOption = String(option || "").trim();
    if (!this._hass || !this._config?.mode_entity || !targetOption) {
      return;
    }

    await this._hass.callService("input_select", "select_option", {
      entity_id: this._config.mode_entity,
      option: targetOption,
    });
  }

  async _addTagsFromText(rawValue) {
    const incoming = String(rawValue || "")
      .split(",")
      .map((value) => this._canonicalTagLabel(value))
      .map((value) => value.trim())
      .filter(Boolean);

    if (!incoming.length) {
      return false;
    }

    const existing = new Set(this._tags.map((tag) => this._normalizeTag(tag)));
    let changed = false;
    incoming.forEach((value) => {
      const normalized = this._normalizeTag(value);
      if (!normalized || existing.has(normalized) || this._isSystemTag(value)) {
        return;
      }
      existing.add(normalized);
      this._tags = this._tags.concat(value);
      changed = true;
    });

    if (!changed) {
      return false;
    }

    this._draft = "";
    this._highlightedIndex = 0;
    this._render();
    await this._persistTags();
    return true;
  }

  async _removeTag(index) {
    if (index < 0 || index >= this._tags.length) {
      return;
    }

    this._tags = this._tags.filter((_tag, tagIndex) => tagIndex !== index);
    this._highlightedIndex = 0;
    this._render();
    await this._persistTags();
  }

  async _handleBackspace() {
    if (this._draft || !this._tags.length) {
      return;
    }
    await this._removeTag(this._tags.length - 1);
  }

  async _commitDraft(preferredSuggestion) {
    const suggestions = this._filteredSuggestions();
    if (preferredSuggestion) {
      await this._addTagsFromText(preferredSuggestion);
      return;
    }

    if (!this._draft.trim()) {
      return;
    }

    if (suggestions.length && this._highlightedIndex >= 0 && this._highlightedIndex < suggestions.length) {
      const highlighted = suggestions[this._highlightedIndex];
      if (this._normalizeTag(highlighted) === this._normalizeTag(this._draft)) {
        await this._addTagsFromText(highlighted);
        return;
      }
    }

    await this._addTagsFromText(this._draft);
  }

  _bindEvents() {
    const input = this._elements?.input;
    if (!input) {
      return;
    }

    input.addEventListener("focus", () => {
      this._focused = true;
      this._renderSuggestions();
    });

    input.addEventListener("blur", () => {
      window.setTimeout(async () => {
        this._focused = false;
        if (this._draft.trim()) {
          await this._commitDraft();
        } else {
          this._renderSuggestions();
        }
      }, 0);
    });

    input.addEventListener("input", async (event) => {
      const nextValue = String(event.target.value || "");
      if (nextValue.includes(",")) {
        const segments = nextValue.split(",");
        const trailingSegment = segments.pop() || "";
        await this._addTagsFromText(segments.join(","));
        this._draft = trailingSegment.trimStart();
      } else {
        this._draft = nextValue;
      }
      this._highlightedIndex = 0;
      this._renderInputValue();
      this._renderSuggestions();
    });

    input.addEventListener("keydown", async (event) => {
      const suggestions = this._filteredSuggestions();
      if (event.key === "ArrowDown" && suggestions.length) {
        event.preventDefault();
        this._highlightedIndex = Math.min(this._highlightedIndex + 1, suggestions.length - 1);
        this._renderSuggestions();
        return;
      }

      if (event.key === "ArrowUp" && suggestions.length) {
        event.preventDefault();
        this._highlightedIndex = Math.max(this._highlightedIndex - 1, 0);
        this._renderSuggestions();
        return;
      }

      if (event.key === "Enter") {
        event.preventDefault();
        await this._commitDraft(suggestions[this._highlightedIndex] || "");
        return;
      }

      if (event.key === ",") {
        event.preventDefault();
        await this._commitDraft();
        return;
      }

      if (event.key === "Backspace") {
        await this._handleBackspace();
        return;
      }

      if (event.key === "Escape") {
        this._focused = false;
        this._highlightedIndex = 0;
        input.blur();
      }
    });
  }

  _ensureFrame() {
    if (!this._config || !this.shadowRoot || this._elements) {
      return;
    }

    const safeTitle = this._escapeHtml(this._config.title);
    const safePlaceholder = this._escapeHtml(this._config.placeholder);
    const safeHelper = this._escapeHtml(this._config.helper);
    const safeIcon = this._escapeHtml(this._config.icon);

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
        }

        ha-card {
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 16px;
          box-shadow: none;
          padding: 14px;
        }

        .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 12px;
        }

        .header-main {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          min-width: 0;
          font-size: 14px;
          font-weight: 600;
        }

        .header-title {
          overflow-wrap: anywhere;
        }

        .header-actions {
          display: inline-flex;
          align-items: center;
          justify-content: flex-end;
          gap: 6px;
          flex: 0 0 auto;
        }

        .mode-chip {
          appearance: none;
          -webkit-appearance: none;
          border-radius: 999px;
          border: 1px solid rgba(255, 255, 255, 0.08);
          background: rgba(255, 255, 255, 0.04);
          color: var(--primary-text-color);
          cursor: pointer;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          min-width: 54px;
          min-height: 28px;
          padding: 0 12px;
          font-size: 11px;
          font-weight: 700;
          line-height: 1;
          letter-spacing: 0.01em;
          box-shadow: none;
          transition: background 0.16s ease, border-color 0.16s ease, color 0.16s ease;
        }

        .mode-chip.active {
          border-color: rgba(21, 101, 192, 0.42);
          background: rgba(21, 101, 192, 0.18);
        }

        .mode-chip:hover,
        .mode-chip:focus-visible {
          outline: none;
          border-color: rgba(96, 165, 250, 0.36);
        }

        @media (max-width: 520px) {
          .header {
            align-items: flex-start;
          }

          .header-main {
            flex: 1 1 auto;
          }

          .mode-chip {
            min-width: 48px;
            padding: 0 10px;
          }
        }

        .editor {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }

        .tag-list {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          min-height: 18px;
        }

        .tag-pill {
          appearance: none;
          -webkit-appearance: none;
          border: none;
          border-radius: 999px;
          background: var(--tag-background, rgba(148, 163, 184, 0.16));
          color: var(--primary-text-color);
          cursor: pointer;
          display: inline-flex;
          align-items: center;
          gap: 8px;
          font-size: 12px;
          font-weight: 600;
          padding: 6px 10px;
          box-shadow: inset 0 0 0 1px var(--tag-border-color, rgba(148, 163, 184, 0.42)), 0 0 0 1px transparent;
        }

        .tag-pill:hover {
          filter: brightness(0.99);
        }

        .tag-label {
          overflow-wrap: anywhere;
        }

        .tag-remove {
          font-size: 15px;
          line-height: 1;
        }

        .empty-state {
          color: var(--secondary-text-color);
          font-size: 12px;
        }

        .input-shell {
          position: relative;
        }

        .input-row {
          display: flex;
          align-items: center;
          gap: 10px;
          background: rgba(255, 255, 255, 0.04);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 14px;
          padding: 10px 12px;
        }

        input {
          background: transparent;
          border: none;
          color: var(--primary-text-color);
          flex: 1;
          font: inherit;
          outline: none;
          width: 100%;
        }

        input::placeholder {
          color: var(--secondary-text-color);
        }

        .suggestions {
          position: absolute;
          top: calc(100% + 8px);
          left: 0;
          right: 0;
          z-index: 2;
          display: flex;
          flex-direction: column;
          gap: 6px;
          padding: 8px;
          background: rgba(17, 24, 39, 0.96);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 14px;
          box-shadow: 0 12px 32px rgba(0, 0, 0, 0.28);
        }

        .suggestion {
          appearance: none;
          -webkit-appearance: none;
          background: rgba(255, 255, 255, 0.04);
          border: 1px solid transparent;
          border-radius: 12px;
          color: var(--primary-text-color);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          padding: 10px 12px;
          text-align: left;
          font: inherit;
        }

        .suggestion:hover,
        .suggestion.active {
          background: rgba(96, 165, 250, 0.16);
          border-color: rgba(96, 165, 250, 0.32);
        }

        .suggestion-meta {
          color: #bfdbfe;
          font-size: 11px;
          font-weight: 600;
          white-space: nowrap;
        }

        .helper {
          color: var(--secondary-text-color);
          font-size: 11px;
          line-height: 1.45;
        }
      </style>
      <ha-card>
        <div class="header">
          <div class="header-main">
            <ha-icon icon="${safeIcon}" style="--mdc-icon-size:18px;"></ha-icon>
            <span class="header-title">${safeTitle}</span>
          </div>
          <div class="header-actions"></div>
        </div>
        <div class="editor">
          <div class="tag-list"></div>
          <div class="input-shell">
            <div class="input-row">
              <ha-icon icon="mdi:magnify" style="--mdc-icon-size:18px;color:var(--secondary-text-color);"></ha-icon>
              <input type="text" placeholder="${safePlaceholder}" />
            </div>
            <div class="suggestions" role="listbox"></div>
          </div>
          <div class="helper">${safeHelper}</div>
        </div>
      </ha-card>`;

    this._elements = {
      headerActions: this.shadowRoot.querySelector(".header-actions"),
      tagList: this.shadowRoot.querySelector(".tag-list"),
      input: this.shadowRoot.querySelector("input"),
      suggestions: this.shadowRoot.querySelector(".suggestions"),
    };
    this._bindEvents();
  }

  _renderHeaderActions() {
    const headerActions = this._elements?.headerActions;
    if (!headerActions) {
      return;
    }

    const modeEntity = String(this._config?.mode_entity || "").trim();
    const options = Array.isArray(this._config?.mode_options) ? this._config.mode_options.filter(Boolean) : [];
    if (!modeEntity || !options.length) {
      headerActions.innerHTML = "";
      headerActions.style.display = "none";
      return;
    }

    const currentValue = this._readModeValue();
    headerActions.style.display = "inline-flex";
    headerActions.innerHTML = options
      .map((option) => {
        const safeOption = this._escapeHtml(option);
        const isActive = currentValue === option;
        return '<button class="mode-chip' + (isActive ? ' active' : '') + '" type="button" data-mode-option="' + safeOption + '">' + safeOption + '</button>';
      })
      .join("");

    headerActions.querySelectorAll("button[data-mode-option]").forEach((button) => {
      button.addEventListener("click", async () => {
        await this._persistMode(button.dataset.modeOption || "");
      });
    });
  }

  _renderInputValue() {
    const input = this._elements?.input;
    if (!input) {
      return;
    }

    if (input.value !== this._draft) {
      input.value = this._draft;
    }
  }

  _renderTagList() {
    const tagList = this._elements?.tagList;
    if (!tagList) {
      return;
    }

    if (!this._tags.length) {
      tagList.innerHTML = '<div class="empty-state">No tags yet. Start typing to add one.</div>';
      return;
    }

    tagList.innerHTML = this._tags
      .map((tag, index) => {
        const style = this._tagStyle(tag);
        return `
          <button class="tag-pill" type="button" data-tag-index="${index}" style="background:${style.background};box-shadow:inset 0 0 0 1px ${style.border},0 0 0 1px ${style.glow};">
            <span class="tag-label">${this._escapeHtml(tag)}</span>
            <span class="tag-remove" aria-hidden="true">×</span>
          </button>`;
      })
      .join("");

    tagList.querySelectorAll("button[data-tag-index]").forEach((button) => {
      button.addEventListener("click", async () => {
        await this._removeTag(Number(button.dataset.tagIndex));
      });
    });
  }

  _renderSuggestions() {
    const suggestionsRoot = this._elements?.suggestions;
    if (!suggestionsRoot) {
      return;
    }

    const suggestions = this._filteredSuggestions();
    const showSuggestions = (this._focused || this._draft.trim()) && suggestions.length > 0;

    if (!showSuggestions) {
      suggestionsRoot.innerHTML = "";
      suggestionsRoot.style.display = "none";
      return;
    }

    suggestionsRoot.style.display = "flex";
    suggestionsRoot.innerHTML = suggestions
      .map((suggestion, index) => {
        const isActive = index === this._highlightedIndex;
        return `
          <button
            class="suggestion ${isActive ? "active" : ""}"
            type="button"
            data-suggestion="${this._escapeHtml(suggestion)}"
            role="option"
            aria-selected="${isActive ? "true" : "false"}"
          >
            <span>${this._escapeHtml(suggestion)}</span>
            <span class="suggestion-meta">Existing tag</span>
          </button>`;
      })
      .join("");

    suggestionsRoot.querySelectorAll("button[data-suggestion]").forEach((button) => {
      button.addEventListener("mousedown", (event) => {
        event.preventDefault();
      });
      button.addEventListener("click", async () => {
        await this._commitDraft(button.dataset.suggestion || "");
      });
    });
  }

  _render() {
    if (!this._config || !this.shadowRoot) {
      return;
    }

    this._ensureFrame();
    this._renderHeaderActions();
    this._renderInputValue();
    this._renderTagList();
    this._renderSuggestions();
  }
}

if (!customElements.get("print-history-tag-editor-card")) {
  customElements.define("print-history-tag-editor-card", PrintHistoryTagEditorCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.find((card) => card.type === "print-history-tag-editor-card")) {
  window.customCards.push({
    type: "print-history-tag-editor-card",
    name: "Print History Tag Editor Card",
    description: "Tokenized print history tag editor with type-ahead suggestions.",
  });
}