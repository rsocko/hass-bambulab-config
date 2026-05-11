/**
 * Unified Production Queue Board Card
 * 
 * Displays the unified print queue with:
 * - Compact top widget showing overnight-fit count, AMS-ready count, started count
 * - Main area with queue entries grouped by state
 * - State chips (todo, ready, started, done, blocked)
 * - Empty, loading, and error states
 * - Responsive layout for desktop and mobile
 */

class UnifiedQueueBoardCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = null;
    this._hass = null;
    this._entries = [];
    this._loading = false;
    this._error = null;
    this._refreshTimer = null;
  }

  setConfig(config) {
    if (!config.printer_id) {
      throw new Error('unified-queue-board-card: printer_id required in config');
    }
    this._config = config;
    this.printerId = config.printer_id || 'p1';
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  _update() {
    if (!this._hass || !this._config) return;
    this._render();
  }

  async _loadQueueData() {
    if (!this._hass) return;
    
    this._loading = true;
    this._error = null;
    
    try {
      const response = await fetch(
        `http://model-catalog.socko.us/api/v1/queues/${this.printerId}/entries`,
        {
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      this._entries = data.entries || [];
      this._error = null;
    } catch (err) {
      console.error('Failed to load queue:', err);
      this._error = `Failed to load queue: ${err.message}`;
      this._entries = [];
    } finally {
      this._loading = false;
      this._render();
    }
  }

  connectedCallback() {
    this._loadQueueData();
    
    // Auto-refresh every 30 seconds
    this._refreshTimer = setInterval(() => {
      this._loadQueueData();
    }, 30000);
  }

  disconnectedCallback() {
    if (this._refreshTimer) {
      clearInterval(this._refreshTimer);
      this._refreshTimer = null;
    }
  }

  _getStats() {
    const stats = {
      overnightFit: 0,
      amsReady: 0,
      started: 0,
      total: this._entries.length,
    };

    for (const entry of this._entries) {
      if (entry.state === 'started') stats.started++;
      if ((entry.overnight_fit_score || 0) >= 50) stats.overnightFit++;
      if ((entry.ams_ready_score || 0) >= 50) stats.amsReady++;
    }

    return stats;
  }

  _getStateColor(state) {
    const stateColors = {
      'idea': '#9eacba',      // text-muted
      'todo': '#7cc7ff',      // accent-blue
      'ready': '#6ee7c8',     // accent (teal)
      'started': '#f2c35b',   // accent-amber
      'done': '#7ddc97',      // accent-green
      'blocked': '#f59090',   // accent-red
    };
    return stateColors[state] || '#9eacba';
  }

  _getSourceBadgeStyles(sourceKind) {
    const styles = {
      'catalog_model': { bg: 'rgba(124,199,255,0.10)', color: '#7cc7ff' },
      'working_group': { bg: 'rgba(110,231,200,0.10)', color: '#6ee7c8' },
      'working_file': { bg: 'rgba(110,231,200,0.10)', color: '#6ee7c8' },
      'idea': { bg: 'rgba(242,195,91,0.10)', color: '#f2c35b' },
    };
    return styles[sourceKind] || { bg: 'rgba(255,255,255,0.05)', color: '#9eacba' };
  }

  _renderTopWidget() {
    const stats = this._getStats();

    return `
      <div class="top-widget">
        <div class="stat-card">
          <div class="stat-label">Overnight Fit</div>
          <div class="stat-value">${stats.overnightFit}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">AMS Ready</div>
          <div class="stat-value">${stats.amsReady}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Started</div>
          <div class="stat-value">${stats.started}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Total Queue</div>
          <div class="stat-value">${stats.total}</div>
        </div>
      </div>
    `;
  }

  _renderQueueList() {
    if (this._entries.length === 0) {
      return `
        <div class="empty-state">
          <div class="empty-icon">📋</div>
          <div class="empty-title">Queue is Empty</div>
          <div class="empty-subtitle">Add items to start planning your prints</div>
        </div>
      `;
    }

    const grouped = this._groupEntriesByState();
    let html = '<div class="queue-list">';

    for (const state of ['started', 'ready', 'todo', 'idea', 'blocked', 'done']) {
      if (!grouped[state] || grouped[state].length === 0) continue;

      html += `<div class="state-group"><div class="state-group-header">${this._formatStateLabel(state)}</div>`;

      for (const entry of grouped[state]) {
        html += this._renderQueueEntry(entry);
      }

      html += '</div>';
    }

    html += '</div>';
    return html;
  }

  _groupEntriesByState() {
    const grouped = {};
    for (const entry of this._entries) {
      if (!grouped[entry.state]) grouped[entry.state] = [];
      grouped[entry.state].push(entry);
    }
    return grouped;
  }

  _formatStateLabel(state) {
    const labels = {
      'idea': 'Ideas',
      'todo': 'To Do',
      'ready': 'Ready',
      'started': 'Currently Printing',
      'done': 'Done',
      'blocked': 'Blocked',
    };
    return labels[state] || state;
  }

  _renderQueueEntry(entry) {
    const sourceStyles = this._getSourceBadgeStyles(entry.source_kind);
    const stateColor = this._getStateColor(entry.state);
    const durationMinutes = entry.estimated_total_minutes || 0;
    const durationStr = this._formatDuration(durationMinutes);

    const sourceLabel = entry.source_kind.replace(/_/g, ' ').toUpperCase();

    return `
      <div class="queue-entry" data-entry-id="${entry.queue_entry_id}">
        <div class="entry-header">
          <div class="entry-title">
            <span class="entry-rank">${entry.rank || '—'}</span>
            <span class="entry-name">${this._escapeHtml(entry.title)}</span>
          </div>
          <div class="entry-badges">
            <span class="source-badge" style="background: ${sourceStyles.bg}; color: ${sourceStyles.color};">
              ${sourceLabel}
            </span>
            <span class="state-chip" style="color: ${stateColor}; border-color: ${stateColor};">
              ${entry.state.toUpperCase()}
            </span>
          </div>
        </div>
        
        <div class="entry-meta">
          <span class="meta-item">⏱ ${durationStr}</span>
          ${entry.ams_ready_score !== undefined ? `<span class="meta-item">🔌 AMS ${entry.ams_ready_score}%</span>` : ''}
          ${entry.overnight_fit_score !== undefined ? `<span class="meta-item">🌙 Overnight ${entry.overnight_fit_score}%</span>` : ''}
          ${entry.last_attempt_outcome ? `<span class="meta-item outcome-${entry.last_attempt_outcome}">Latest: ${entry.last_attempt_outcome}</span>` : ''}
        </div>
      </div>
    `;
  }

  _formatDuration(minutes) {
    if (!minutes || minutes === 0) return '—';
    if (minutes < 60) return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
  }

  _escapeHtml(text) {
    const map = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#039;',
    };
    return text.replace(/[&<>"']/g, (m) => map[m]);
  }

  _render() {
    const css = `
      :host {
        --bg-page: #0c1117;
        --bg-panel: rgba(21, 28, 38, 0.95);
        --bg-card: rgba(28, 36, 47, 0.96);
        --bg-card-alt: rgba(18, 24, 33, 0.9);
        --border: rgba(148, 163, 184, 0.18);
        --border-strong: rgba(148, 163, 184, 0.34);
        --text: #e8edf2;
        --text-secondary: #9eacba;
        --text-muted: #6f7c8a;
        --accent: #6ee7c8;
        --accent-blue: #7cc7ff;
        --accent-amber: #f2c35b;
        --accent-red: #f59090;
        --accent-green: #7ddc97;
        --shadow: 0 20px 60px rgba(0, 0, 0, 0.34);
      }

      * {
        box-sizing: border-box;
      }

      .shell {
        background: var(--bg-panel);
        border: 1px solid var(--border);
        border-radius: 22px;
        box-shadow: var(--shadow);
        overflow: hidden;
      }

      .card-title {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 18px 20px;
        border-bottom: 1px solid var(--border);
        background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01));
      }

      .card-title h2 {
        margin: 0;
        font-size: 18px;
        font-weight: 700;
        color: var(--text);
      }

      .refresh-btn {
        padding: 6px 10px;
        border: 1px solid var(--border);
        border-radius: 8px;
        background: rgba(255,255,255,0.05);
        color: var(--text-secondary);
        font-size: 12px;
        cursor: pointer;
        transition: all 0.2s;
      }

      .refresh-btn:hover {
        background: rgba(255,255,255,0.08);
        color: var(--text);
      }

      .refresh-btn.loading {
        opacity: 0.6;
        pointer-events: none;
      }

      .content {
        padding: 18px;
        display: flex;
        flex-direction: column;
        gap: 18px;
      }

      .top-widget {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
        gap: 12px;
      }

      .stat-card {
        background: var(--bg-card-alt);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 14px;
        text-align: center;
      }

      .stat-label {
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.07em;
        text-transform: uppercase;
        color: var(--text-muted);
        margin-bottom: 8px;
      }

      .stat-value {
        font-size: 28px;
        font-weight: 800;
        letter-spacing: -0.04em;
        color: var(--text);
      }

      .queue-list {
        display: flex;
        flex-direction: column;
        gap: 16px;
      }

      .state-group {
        display: flex;
        flex-direction: column;
        gap: 10px;
      }

      .state-group-header {
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.07em;
        text-transform: uppercase;
        color: var(--text-secondary);
        padding: 0 2px;
      }

      .queue-entry {
        background: var(--bg-card-alt);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 12px 14px;
        transition: all 0.2s;
      }

      .queue-entry:hover {
        border-color: var(--border-strong);
        background: rgba(28, 36, 47, 1);
      }

      .entry-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 12px;
        flex-wrap: wrap;
        margin-bottom: 10px;
      }

      .entry-title {
        display: flex;
        align-items: center;
        gap: 10px;
        flex: 1;
        min-width: 0;
      }

      .entry-rank {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 28px;
        height: 28px;
        background: rgba(110, 231, 200, 0.10);
        border: 1px solid rgba(110, 231, 200, 0.28);
        border-radius: 8px;
        font-size: 12px;
        font-weight: 700;
        color: var(--accent);
        flex-shrink: 0;
      }

      .entry-name {
        font-size: 14px;
        font-weight: 600;
        color: var(--text);
        word-break: break-word;
      }

      .entry-badges {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
      }

      .source-badge {
        display: inline-flex;
        align-items: center;
        padding: 4px 8px;
        border-radius: 6px;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.04em;
        border: 1px solid rgba(148, 163, 184, 0.18);
      }

      .state-chip {
        display: inline-flex;
        align-items: center;
        padding: 4px 10px;
        border: 1.5px solid currentColor;
        border-radius: 999px;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.04em;
        white-space: nowrap;
      }

      .entry-meta {
        display: flex;
        align-items: center;
        gap: 12px;
        flex-wrap: wrap;
        font-size: 12px;
        color: var(--text-secondary);
      }

      .meta-item {
        display: inline-flex;
        align-items: center;
        gap: 4px;
      }

      .outcome-success {
        color: var(--accent-green);
      }

      .outcome-failed {
        color: var(--accent-red);
      }

      .outcome-aborted {
        color: var(--accent-amber);
      }

      .loading-state {
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 40px;
        color: var(--text-secondary);
      }

      .loading-spinner {
        display: inline-block;
        width: 24px;
        height: 24px;
        border: 2px solid rgba(148, 163, 184, 0.2);
        border-top-color: var(--accent);
        border-radius: 50%;
        animation: spin 0.8s linear infinite;
      }

      @keyframes spin {
        to { transform: rotate(360deg); }
      }

      .error-state {
        padding: 24px;
        background: rgba(245, 144, 144, 0.1);
        border: 1px solid rgba(245, 144, 144, 0.2);
        border-radius: 14px;
        color: #f59090;
        font-size: 13px;
        line-height: 1.5;
      }

      .error-state strong {
        display: block;
        margin-bottom: 4px;
      }

      .empty-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 48px 24px;
        text-align: center;
      }

      .empty-icon {
        font-size: 48px;
        margin-bottom: 16px;
      }

      .empty-title {
        font-size: 16px;
        font-weight: 700;
        color: var(--text);
        margin-bottom: 6px;
      }

      .empty-subtitle {
        font-size: 13px;
        color: var(--text-secondary);
      }

      @media (max-width: 760px) {
        .card-title {
          padding: 14px 16px;
        }

        .content {
          padding: 14px;
          gap: 14px;
        }

        .top-widget {
          grid-template-columns: repeat(2, 1fr);
        }

        .entry-header {
          flex-direction: column;
        }

        .entry-badges {
          width: 100%;
        }

        .entry-meta {
          font-size: 11px;
        }
      }
    `;

    const content = this._loading
      ? '<div class="loading-state"><div class="loading-spinner"></div></div>'
      : this._error
      ? `<div class="error-state"><strong>⚠ Error</strong>${this._escapeHtml(this._error)}</div>`
      : this._renderTopWidget() + this._renderQueueList();

    const html = `
      <style>${css}</style>
      <div class="shell">
        <div class="card-title">
          <h2>Print Queue</h2>
          <button class="refresh-btn ${this._loading ? 'loading' : ''}" ${this._loading ? 'disabled' : ''}>
            ${this._loading ? 'Loading...' : '🔄'}
          </button>
        </div>
        <div class="content">
          ${content}
        </div>
      </div>
    `;

    this.shadowRoot.innerHTML = html;

    const refreshBtn = this.shadowRoot.querySelector('.refresh-btn');
    if (refreshBtn && !this._loading) {
      refreshBtn.addEventListener('click', () => this._loadQueueData());
    }
  }

  getCardSize() {
    return 10;
  }
}

customElements.define('unified-queue-board-card', UnifiedQueueBoardCard);
