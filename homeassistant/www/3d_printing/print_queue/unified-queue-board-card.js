/**
 * Unified Production Queue Board Card
 * 
 * Displays the unified print queue with:
 * - Compact top widget showing overnight-fit count, AMS-ready count, in-progress count
 * - Main area with queue entries grouped by state
 * - State chips (up_next, preparing, ready, in progress, blocked, done)
 * - Empty, loading, and error states
 * - Responsive layout for desktop and mobile
 */

import { addUnifiedQueueEntry } from '../common/unified-queue-api-client.js?v=1';

const QUEUE_STATE_FILTER_ORDER = ['backlog', 'up_next', 'preparing', 'ready', 'in_progress', 'blocked', 'done'];
const QUEUE_DEFAULT_VISIBLE_STATES = ['up_next', 'preparing', 'ready', 'in_progress', 'blocked'];
const QUEUE_STATE_GROUP_ORDER = ['in_progress', 'ready', 'preparing', 'up_next', 'backlog', 'blocked', 'done'];
const QUEUE_STATE_TRANSITIONS = {
  backlog: ['up_next', 'preparing', 'ready', 'in_progress'],
  up_next: ['backlog', 'preparing', 'ready', 'in_progress', 'blocked'],
  preparing: ['up_next', 'ready', 'in_progress', 'blocked'],
  ready: ['up_next', 'backlog', 'in_progress', 'blocked'],
  in_progress: ['blocked', 'done'],
  blocked: ['preparing', 'ready', 'in_progress', 'done'],
  done: ['in_progress'],
};
const VALID_QUEUE_SOURCES = ['catalog_model', 'working_group', 'working_file', 'idea'];
const VALID_QUEUE_SORTS = new Set(['rank', 'rank-desc', 'duration', 'duration-desc', 'recently-added']);
const VALID_QUEUE_VIEWS = new Set(['list', 'kanban']);
// Per-state palette — drives card wash, kanban column accent, list group dot,
// filter swatches. Single source of truth across both views.
const QUEUE_STATE_PALETTE = {
  backlog:     '#7a6a57',  // muted gray-brown (parked / someday items)
  up_next:     '#a07cff',  // bright purple (next to print)
  preparing:   '#ff9a3c',
  ready:       '#e6d84a',
  in_progress: '#3aa9ff',
  blocked:     '#ff6b6b',
  done:        '#4fcf75',
};

class UnifiedQueueBoardCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = null;
    this._hass = null;
    this.printerId = 'p1';
    this._entries = [];
    this._loading = false;
    this._error = null;
    this._refreshTimer = null;
    this._flashTimer = null;
    this._flashMessage = null;
    
    // Filter state
    this._filters = {
      states: [...QUEUE_DEFAULT_VISIBLE_STATES],
      sources: [],  // Empty = all sources
      sort: 'rank',  // Default: sort by rank
      search: '',  // Free-text search across title + source
    };
    // View state (list | kanban). Persisted per printer.
    this._view = 'list';
    // Transient drag state used for list reorder + kanban state moves.
    this._dragEntryId = null;
    this._dragBusy = false;

    // Pending entry-delete confirmation (entry id whose Delete button was
    // clicked but not yet confirmed). null = no confirm modal showing.
    this._pendingDeleteEntryId = null;

    // Idea-create dialog (shared with Model Catalog)
    this._ideaCreateDialogOpen = false;
    this._ideaCreateSubmitting = false;
    this._ideaCreateError = '';
    this._ideaCreateDraft = { title: '', notes: '', links: '', sketchUrl: '' };

    this._addModalOpen = false;
    this._addTab = 'quick';
    this._addSourceKind = 'catalog_model';
    this._addSourceId = '';
    this._addIdeaTitle = '';
    this._addIdeaNotes = '';
    this._addSourceOptions = {
      catalog_model: [],
      working_group: [],
    };
    this._addLoadingSources = false;
    this._addLoadingDetail = false;
    this._addSubmitting = false;
    this._addDetailError = null;
    this._addDetailFiles = [];
    this._rowActionBusy = false;
    this._editModalOpen = false;
    this._editEntryId = null;
    this._editTitle = '';
    this._editCopies = 1;
    this._editSubmitting = false;
    this._editError = null;
    this._detailEntry = null;
    this._detailLoading = false;
    this._detailError = null;
    this._detailFiles = [];
    this._detailTab = 'plates';
    this._detailSubmitting = false;
    this._detailDirty = false;
    this._ideaGraduateBusy = false;
    this._detailForm = {
      title: '',
      copies: 1,
      state: 'preparing',
      queueNotes: '',
    };
    this._suggestions = [];
    this._suggestionsError = null;
    this._suggestionBusy = {};

    // Planner state
    this._plannerOpen = false;
    this._plannerStrategy = 'balanced';
    this._plannerPreview = [];
    this._plannerHistory = [];
    this._plannerLocalHistory = [];
    this._plannerFallbackMode = false;
    this._plannerLoading = false;
    this._plannerError = null;
    this._plannerBusy = false;

    // Tracks whether this card currently holds a global body scroll lock.
    this._bodyScrollLocked = false;

    this._loadFilterState();
    this._loadViewState();
  }

  setConfig(config) {
    if (!config.printer_id) {
      throw new Error('unified-queue-board-card: printer_id required in config');
    }
    this._config = config;
    this.printerId = config.printer_id || 'p1';
  }

  _loadFilterState() {
    try {
      const stored = localStorage.getItem(`uq-filters-${this.printerId}`);
      if (stored) {
        const parsed = JSON.parse(stored);
        this._filters = { ...this._filters, ...parsed };
      }
    } catch (e) {
      console.warn('Failed to load filter state:', e);
    }
    this._normalizeFilterState();
  }

  _saveFilterState() {
    try {
      localStorage.setItem(`uq-filters-${this.printerId}`, JSON.stringify(this._filters));
    } catch (e) {
      console.warn('Failed to save filter state:', e);
    }
  }

  _normalizeFilterState() {
    const hasStateArray = Array.isArray(this._filters.states);
    const normalizedStates = Array.isArray(this._filters.states)
      ? [...new Set(this._filters.states
          .map(state => String(state || '').trim())
          .filter(state => QUEUE_STATE_FILTER_ORDER.includes(state)))]
      : [];
    const normalizedSources = Array.isArray(this._filters.sources)
      ? [...new Set(this._filters.sources
          .map(source => String(source || '').trim())
          .filter(source => VALID_QUEUE_SOURCES.includes(source)))]
      : [];
    const normalizedSort = String(this._filters.sort || '').trim();
    const normalizedSearch = String(this._filters.search || '').slice(0, 200);

    // Preserve an intentionally empty selection ("show none") from the States filter.
    this._filters.states = hasStateArray ? normalizedStates : [...QUEUE_DEFAULT_VISIBLE_STATES];
    this._filters.sources = normalizedSources;
    this._filters.sort = VALID_QUEUE_SORTS.has(normalizedSort) ? normalizedSort : 'rank';
    this._filters.search = normalizedSearch;
  }

  _hasDefaultStateFilter() {
    return this._filters.states.length === QUEUE_DEFAULT_VISIBLE_STATES.length
      && QUEUE_DEFAULT_VISIBLE_STATES.every(state => this._filters.states.includes(state));
  }

  _toggleStateFilter(state) {
    if (this._filters.states.includes(state)) {
      this._filters.states = this._filters.states.filter(s => s !== state);
    } else {
      this._filters.states.push(state);
    }
    this._saveFilterState();
    this._render();
  }

  _toggleSourceFilter(source) {
    if (source === 'working_files') {
      const workingKinds = ['working_group', 'working_file'];
      const anyActive = workingKinds.some(k => this._filters.sources.includes(k));
      if (anyActive) {
        this._filters.sources = this._filters.sources.filter(s => !workingKinds.includes(s));
      } else {
        workingKinds.forEach(k => {
          if (!this._filters.sources.includes(k)) this._filters.sources.push(k);
        });
      }
    } else {
      if (this._filters.sources.includes(source)) {
        this._filters.sources = this._filters.sources.filter(s => s !== source);
      } else {
        this._filters.sources.push(source);
      }
    }
    this._saveFilterState();
    this._render();
  }

  _setSortOrder(sort) {
    this._filters.sort = sort;
    this._saveFilterState();
    this._render();
  }

  _setSearchQuery(query) {
    const next = String(query || '').slice(0, 200);
    if (next === this._filters.search) return;
    this._filters.search = next;
    // Mark that we want to keep focus on the search input after the next render.
    this._restoreSearchFocus = true;
    this._saveFilterState();
    this._render();
  }

  _clearAllFilters() {
    // Preserve current sort order — clear only resets state, source, and search filters.
    const preservedSort = this._filters.sort;
    this._filters = {
      states: [...QUEUE_DEFAULT_VISIBLE_STATES],
      sources: [],
      sort: preservedSort,
      search: '',
    };
    this._saveFilterState();
    this._render();
  }

  _loadViewState() {
    try {
      const stored = localStorage.getItem(`uq-view-${this.printerId}`);
      if (stored && VALID_QUEUE_VIEWS.has(stored)) {
        this._view = stored;
      }
    } catch (e) {
      console.warn('Failed to load view state:', e);
    }
  }

  _saveViewState() {
    try {
      localStorage.setItem(`uq-view-${this.printerId}`, this._view);
    } catch (e) {
      console.warn('Failed to save view state:', e);
    }
  }

  _setView(view) {
    if (!VALID_QUEUE_VIEWS.has(view) || view === this._view) return;
    this._view = view;
    this._saveViewState();
    this._render();
  }

  // KPI hero stats: total remaining minutes (excluding done plates / done
  // entries), an 'active jobs' count, and a coarse skipped-plate count for
  // the visible meta line.
  _getEtaStats() {
    let remainingMinutes = 0;
    let activeJobs = 0;
    let skippedPlates = 0;
    let doneCopies = 0;
    let totalCopies = 0;

    for (const entry of this._entries) {
      const state = String(entry.state || '').trim();
      const copiesRequested = Number.isFinite(entry.copies_requested) ? entry.copies_requested : 1;
      const copiesCompleted = Number.isFinite(entry.copies_completed) ? entry.copies_completed : 0;
      totalCopies += copiesRequested;
      doneCopies += copiesCompleted;
      if (copiesCompleted > 0) skippedPlates += copiesCompleted;

      if (state === 'done') continue;
      const totalMinutes = Number(entry.estimated_total_minutes || 0);
      // Skip minutes attributable to copies already completed.
      const remainingShare = copiesRequested > 0
        ? totalMinutes * Math.max(0, copiesRequested - copiesCompleted) / copiesRequested
        : totalMinutes;
      remainingMinutes += Math.max(0, Math.round(remainingShare));
      if (['preparing', 'ready', 'in_progress', 'blocked'].includes(state)) {
        activeJobs++;
      }
    }

    const pctComplete = totalCopies > 0
      ? Math.min(100, Math.max(2, Math.round((doneCopies / totalCopies) * 100)))
      : 0;

    return { remainingMinutes, activeJobs, skippedPlates, pctComplete };
  }

  _isValidStateTransition(fromState, toState) {
    if (!fromState || !toState) return false;
    if (fromState === toState) return true;
    const allowed = QUEUE_STATE_TRANSITIONS[fromState] || [];
    return allowed.includes(toState);
  }

  // Briefly highlight a card with a red border + shake when a kanban drop
  // is rejected (invalid state transition). Survives re-renders triggered by
  // the flash banner via state-backed class on the rendered card.
  // Note: does NOT call _render() itself — the caller is expected to render
  // (typically via _setFlashMessage) so the toast and card highlight appear
  // together in a single paint, avoiding a double-render flash. The cleanup
  // also avoids _render() (which would replay the toast entrance animation
  // while the flash message is still active) and instead just strips the
  // class from the existing card DOM in place.
  _flashInvalidDrop(queueEntryId) {
    this._invalidDropEntryId = queueEntryId;
    if (this._invalidDropTimer) {
      clearTimeout(this._invalidDropTimer);
    }
    this._invalidDropTimer = setTimeout(() => {
      this._invalidDropEntryId = null;
      this._invalidDropTimer = null;
      const card = this.shadowRoot?.querySelector(
        `.qcard.invalid-drop[data-entry-id="${CSS.escape(String(queueEntryId))}"]`
      );
      if (card) card.classList.remove('invalid-drop');
    }, 750);
  }

  async _changeEntryState(queueEntryId, newState, opts = null) {
    const source = String(opts?.source || '').trim();
    // Defense-in-depth: state transitions via drag/drop are only valid in kanban mode.
    if (source === 'kanban-dnd' && this._view !== 'kanban') return;
    const entry = this._getEntryById(queueEntryId);
    if (!entry) return;
    const fromState = String(entry.state || '').trim();
    const toState = String(newState || '').trim();
    if (fromState === toState) return;

    if (!this._isValidStateTransition(fromState, toState)) {
      this._flashInvalidDrop(queueEntryId);
      this._setFlashMessage(
        `Cannot move from ${this._getStateLabel(fromState)} to ${this._getStateLabel(toState)}.`,
        'error'
      );
      return;
    }

    // Optimistic update so the card visually lands in the new column.
    entry.state = toState;
    this._dragBusy = true;
    this._render();
    try {
      const response = await fetch(
        `${this._getCatalogApiBase()}/unified-queue/entries/${encodeURIComponent(queueEntryId)}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ state: toState }),
        }
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(payload.message || payload.error || `State change failed (${response.status})`));
      }
      this._setFlashMessage(`Moved to ${this._getStateLabel(toState)}.`, 'success');
      await this._loadQueueData();
    } catch (err) {
      // Roll back optimistic update.
      entry.state = fromState;
      this._setFlashMessage(err.message || 'State change failed.', 'error');
      this._render();
    } finally {
      this._dragBusy = false;
    }
  }

  // Drag-to-reorder for the list view. Visible IDs is the new client-side
  // order; we compute moves relative to current ranks so the backend gets a
  // minimal patch.
  async _commitListReorder(visibleEntryIds) {
    if (!Array.isArray(visibleEntryIds) || visibleEntryIds.length === 0) return;
    // Build the full ranked list, replacing the visible slice in-place so
    // hidden entries (filtered out) keep their relative order.
    const visibleSet = new Set(visibleEntryIds);
    const ranked = this._getAllEntriesRanked();
    const visibleSlots = [];
    const newOrder = ranked.map(entry => {
      if (visibleSet.has(entry.queue_entry_id)) {
        const slotIndex = visibleSlots.length;
        visibleSlots.push(slotIndex);
        return null; // placeholder, filled below
      }
      return entry.queue_entry_id;
    });
    let cursor = 0;
    for (let i = 0; i < newOrder.length; i++) {
      if (newOrder[i] === null) {
        newOrder[i] = visibleEntryIds[cursor++];
      }
    }

    const moves = newOrder.map((id, index) => ({ id, new_rank: index + 1 }));
    // Drop no-op moves to keep payload small.
    const currentRanks = new Map(
      ranked.map((entry, idx) => [entry.queue_entry_id, Number.isFinite(entry.rank) ? entry.rank : idx + 1])
    );
    const trimmed = moves.filter(m => currentRanks.get(m.id) !== m.new_rank);
    if (trimmed.length === 0) return;

    this._dragBusy = true;
    this._render();
    try {
      const response = await fetch(
        `${this._getQueueApiBase()}/queues/${encodeURIComponent(this.printerId)}/reorder`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ moves: trimmed }),
        }
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(payload.message || payload.error || `Reorder failed (${response.status})`));
      }
      this._setFlashMessage('Queue order updated.', 'success');
      await this._loadQueueData();
    } catch (err) {
      this._setFlashMessage(err.message || 'Reorder failed.', 'error');
      await this._loadQueueData();
    } finally {
      this._dragBusy = false;
    }
  }

  // ---- DnD: list reorder ----
  _attachListReorderDnD() {
    if (this._view !== 'list') return;
    const body = this.shadowRoot.querySelector('[data-list-body]');
    const flat = this.shadowRoot.querySelector('.flat-list');
    if (!body || !flat) return;
    const dndEnabled = flat.getAttribute('data-flat-dnd') === '1';
    if (!dndEnabled) return;

    body.querySelectorAll('.qcard').forEach(card => {
      card.addEventListener('dragstart', (ev) => {
        this._dragEntryId = card.dataset.entryId;
        card.classList.add('dragging');
        ev.dataTransfer.effectAllowed = 'move';
        try { ev.dataTransfer.setData('text/plain', this._dragEntryId); } catch (_) { /* ignore */ }
      });
      card.addEventListener('dragend', () => {
        card.classList.remove('dragging');
      });
    });

    body.addEventListener('dragover', (ev) => {
      ev.preventDefault();
      const dragging = body.querySelector('.qcard.dragging');
      if (!dragging) return;
      const cards = Array.from(body.querySelectorAll('.qcard:not(.dragging)'));
      const after = cards.find(card => {
        const r = card.getBoundingClientRect();
        return ev.clientY < r.top + r.height / 2;
      });
      if (after) body.insertBefore(dragging, after);
      else body.appendChild(dragging);
    });

    body.addEventListener('drop', (ev) => {
      ev.preventDefault();
      const dragging = body.querySelector('.qcard.dragging');
      if (!dragging) return;
      const ids = Array.from(body.querySelectorAll('.qcard')).map(c => c.dataset.entryId);
      if (ids.length === 0 || ids.some(id => !id)) return;
      this._commitListReorder(ids);
    });
  }

  // ---- DnD: kanban state moves ----
  _attachKanbanDnD() {
    if (this._view !== 'kanban') return;
    const cols = this.shadowRoot.querySelectorAll('.kanban-col-body[data-drop]');
    if (cols.length === 0) return;

    this.shadowRoot.querySelectorAll('.kanban-column .qcard').forEach(card => {
      card.addEventListener('dragstart', (ev) => {
        this._dragEntryId = card.dataset.entryId;
        card.classList.add('dragging');
        ev.dataTransfer.effectAllowed = 'move';
        try { ev.dataTransfer.setData('text/plain', this._dragEntryId); } catch (_) { /* ignore */ }
      });
      card.addEventListener('dragend', () => {
        card.classList.remove('dragging');
        this.shadowRoot.querySelectorAll('.kanban-col-body.drop-target')
          .forEach(z => z.classList.remove('drop-target'));
      });
    });

    cols.forEach(zone => {
      zone.addEventListener('dragover', (ev) => {
        ev.preventDefault();
        zone.classList.add('drop-target');
      });
      zone.addEventListener('dragleave', () => {
        zone.classList.remove('drop-target');
      });
      zone.addEventListener('drop', (ev) => {
        ev.preventDefault();
        zone.classList.remove('drop-target');
        const id = (() => {
          try { return ev.dataTransfer.getData('text/plain') || this._dragEntryId; }
          catch (_) { return this._dragEntryId; }
        })();
        const newState = zone.dataset.drop;
        if (!id || !newState) return;
        this._changeEntryState(id, newState, { source: 'kanban-dnd' });
      });
    });
  }

  set hass(hass) {
    const isFirstHass = !this._hass;
    this._hass = hass;

    // This card fetches its own queue data and does not depend on the HA state bus
    // for its main view model. Re-rendering on every hass update causes visible
    // flashing because the full shadow DOM is replaced each time.
    if (isFirstHass && this._config && !this.shadowRoot.innerHTML) {
      this._render();
    } else {
      // Update DB pill on every hass update (entity state changes)
      this._updateDbPill();
    }
  }

  _update() {
    if (!this._hass || !this._config) return;
    this._render();
  }

  async _fetchAllQueueEntries() {
    const pageSize = 200;
    const maxPages = 25;
    let offset = 0;
    const allEntries = [];

    for (let page = 0; page < maxPages; page++) {
      const response = await fetch(
        `${this._getQueueApiBase()}/queues/${encodeURIComponent(this.printerId)}/entries?limit=${pageSize}&offset=${offset}`,
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
      const pageEntries = Array.isArray(data?.entries)
        ? data.entries
        : (Array.isArray(data) ? data : []);
      allEntries.push(...pageEntries);

      const hasMore = Boolean(data?.pagination?.has_more);
      if (!hasMore || pageEntries.length === 0) {
        break;
      }

      offset += pageEntries.length;
    }

    return allEntries;
  }

  async _loadQueueData() {
    if (!this._hass) return;
    const isInitialLoad = this._entries.length === 0 && !this._error;
    
    this._loading = true;
    this._error = null;
    if (isInitialLoad) {
      this._render();
    }
    
    try {
      this._entries = await this._fetchAllQueueEntries();
      this._error = null;
      await this._loadMediumConfidenceSuggestions();
    } catch (err) {
      console.error('Failed to load queue:', err);
      this._error = `Failed to load queue: ${err.message}`;

      // Preserve the last successful snapshot during background refresh failures.
      // Clearing the entire board causes a visible flash and throws away useful state.
      if (isInitialLoad) {
        this._entries = [];
        this._suggestions = [];
        this._suggestionsError = null;
      }
    } finally {
      this._loading = false;
      if (isInitialLoad || !this._hasOpenOverlay()) {
        this._render();
      }
    }
  }

  _hasOpenOverlay() {
    return this._addModalOpen || !!this._detailEntry || this._plannerOpen;
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

    if (this._flashTimer) {
      clearTimeout(this._flashTimer);
      this._flashTimer = null;
    }

    this._syncBodyScrollLock(false);
  }

  _shouldLockBodyScroll() {
    return this._addModalOpen || !!this._detailEntry || this._plannerOpen || !!this._pendingDeleteEntryId;
  }

  _syncBodyScrollLock(forceLocked = null) {
    const body = document && document.body;
    if (!body) return;

    const shouldLock = forceLocked === null ? this._shouldLockBodyScroll() : !!forceLocked;
    if (shouldLock === this._bodyScrollLocked) return;

    const rawCount = Number.parseInt(body.dataset.uqScrollLockCount || '0', 10);
    const currentCount = Number.isFinite(rawCount) ? Math.max(0, rawCount) : 0;

    if (shouldLock) {
      if (currentCount === 0) {
        body.dataset.uqScrollLockPrevOverflow = body.style.overflow || '';
        body.dataset.uqScrollLockPrevOverscroll = body.style.overscrollBehavior || '';
        body.style.overflow = 'hidden';
        body.style.overscrollBehavior = 'none';
      }
      body.dataset.uqScrollLockCount = String(currentCount + 1);
      this._bodyScrollLocked = true;
      return;
    }

    const nextCount = Math.max(0, currentCount - 1);
    body.dataset.uqScrollLockCount = String(nextCount);
    if (nextCount === 0) {
      body.style.overflow = body.dataset.uqScrollLockPrevOverflow || '';
      body.style.overscrollBehavior = body.dataset.uqScrollLockPrevOverscroll || '';
      delete body.dataset.uqScrollLockPrevOverflow;
      delete body.dataset.uqScrollLockPrevOverscroll;
      delete body.dataset.uqScrollLockCount;
    }
    this._bodyScrollLocked = false;
  }

  _getQueueApiBase() {
    return 'http://model-catalog.socko.us/api/v1';
  }

  _getCatalogApiBase() {
    return 'http://model-catalog.socko.us/api';
  }

  _updateDbPill() {
    if (!this._hass) return;

    const dbStateEl = this.shadowRoot?.querySelector('#db-profile-state');
    const dbPillEl = this.shadowRoot?.querySelector('.db-pill');
    if (!dbStateEl) return;

    try {
      // Source of truth = actual sidecar profile (sensor polls /config).
      // input_select holds the user's *target* and may drift from the sidecar
      // across HA restarts or out-of-band switches.
      const actualState = this._hass.states['sensor.model_catalog_sidecar_db_profile'];
      const targetState = this._hass.states['input_select.model_catalog_db_profile_target'];

      const actualRaw = actualState && actualState.state ? String(actualState.state) : '';
      const targetRaw = targetState && targetState.state ? String(targetState.state) : '';
      const actual = actualRaw.toLowerCase();
      const target = targetRaw.toLowerCase();
      const unavailable = !actualRaw || ['unknown', 'unavailable', 'none', '-'].includes(actual);

      if (unavailable) {
        dbStateEl.textContent = target ? `${target.toUpperCase()}?` : '-';
      } else if (target && target !== actual) {
        dbStateEl.textContent = `${actual.toUpperCase()} ≠ ${target.toUpperCase()}`;
      } else {
        dbStateEl.textContent = actual.toUpperCase();
      }

      if (dbPillEl) {
        dbPillEl.classList.toggle('db-pill-mismatch', !unavailable && !!target && target !== actual);
        dbPillEl.classList.toggle('db-pill-unavailable', unavailable);
        const tip = unavailable
          ? 'Sidecar DB profile sensor unavailable; showing target helper value'
          : (target && target !== actual)
            ? `Sidecar is on ${actual.toUpperCase()}, but target helper is ${target.toUpperCase()} (restart or out-of-band switch)`
            : 'Model catalog DB profile (sidecar)';
        dbPillEl.setAttribute('title', tip);
      }
    } catch (_err) {
      dbStateEl.textContent = '-';
    }
  }

  _getStats() {
    const stats = {
      overnightFit: 0,
      amsReady: 0,
      inProgress: 0,
      total: this._entries.length,
    };

    for (const entry of this._entries) {
      if (entry.state === 'in_progress') stats.inProgress++;
      if ((entry.overnight_fit_score || 0) >= 50) stats.overnightFit++;
      if ((entry.ams_ready_score || 0) >= 50) stats.amsReady++;
    }

    return stats;
  }

  _setFlashMessage(message, type = 'success') {
    this._flashMessage = { message, type };
    if (this._flashTimer) {
      clearTimeout(this._flashTimer);
    }
    if (this._flashRemoveTimer) {
      clearTimeout(this._flashRemoveTimer);
      this._flashRemoveTimer = null;
    }
    // After visible duration: fade the toast out in place (no full re-render,
    // which would destroy/recreate the DOM and cause a brief replay flash).
    this._flashTimer = setTimeout(() => {
      this._flashTimer = null;
      const el = this.shadowRoot?.querySelector('.flash-banner');
      if (el) {
        el.classList.add('flash-banner--leaving');
        this._flashRemoveTimer = setTimeout(() => {
          this._flashMessage = null;
          this._flashRemoveTimer = null;
          // Only re-render if no new flash arrived in the meantime.
          if (!this._flashTimer) this._render();
        }, 220);
      } else {
        this._flashMessage = null;
        this._render();
      }
    }, 2500);
    this._render();
  }

  _openAddModal() {
    const hasCachedSources = Array.isArray(this._addSourceOptions.catalog_model) && this._addSourceOptions.catalog_model.length > 0
      && Array.isArray(this._addSourceOptions.working_group) && this._addSourceOptions.working_group.length > 0;

    this._addModalOpen = true;
    this._addTab = 'quick';
    this._addSourceKind = 'catalog_model';
    this._addSourceId = '';
    this._addIdeaTitle = '';
    this._addIdeaNotes = '';
    this._addLoadingSources = !hasCachedSources;
    this._addLoadingDetail = false;
    this._addSubmitting = false;
    this._addDetailError = null;
    this._addDetailFiles = [];
    this._render();

    if (!hasCachedSources) {
      this._loadAddSourceOptions({ renderLoadingState: false });
    }
  }

  _closeAddModal() {
    this._addModalOpen = false;
    this._addSubmitting = false;
    this._addLoadingDetail = false;
    this._addDetailError = null;
    this._render();
  }

  async _loadAddSourceOptions({ renderLoadingState = true } = {}) {
    if (!this._addLoadingSources) {
      this._addLoadingSources = true;
      if (renderLoadingState) {
        this._render();
      }
    }

    try {
      const [modelsRes, groupsRes] = await Promise.all([
        fetch(`${this._getCatalogApiBase()}/models?sort=name`),
        fetch(`${this._getCatalogApiBase()}/working-groups?limit=250`),
      ]);

      const modelsPayload = modelsRes.ok ? await modelsRes.json() : {};
      const groupsPayload = groupsRes.ok ? await groupsRes.json() : {};

      const modelOptions = Array.isArray(modelsPayload.models)
        ? modelsPayload.models
            .map((model, index) => {
              const value = String(model.public_id || model.model_id || model.model_url || model.id || '').trim();
              if (!value) return null;
              return {
                value,
                label: String(model.name || value || `Model ${index + 1}`).trim(),
              };
            })
            .filter(Boolean)
        : [];

      const workingOptions = Array.isArray(groupsPayload.groups)
        ? groupsPayload.groups
            .map((group, index) => {
              const groupId = Number(group.id);
              if (!Number.isFinite(groupId)) return null;
              const slug = String(group.slug || '').trim();
              const value = slug || String(groupId);
              return {
                value,
                label: String(group.title || slug || `Working Group ${index + 1}`).trim(),
                groupId,
              };
            })
            .filter(Boolean)
        : [];

      this._addSourceOptions = {
        catalog_model: modelOptions,
        working_group: workingOptions,
      };
    } catch (err) {
      this._addDetailError = `Failed to load add sources: ${err.message}`;
    } finally {
      this._addLoadingSources = false;
      this._render();
    }
  }

  _getActiveAddOptions() {
    if (this._addSourceKind === 'idea') {
      return [];
    }
    return this._addSourceOptions[this._addSourceKind] || [];
  }

  _getAddSourceOption(value) {
    const normalized = String(value || '').trim();
    if (!normalized) return null;
    return this._getActiveAddOptions().find(option => option.value === normalized) || null;
  }

  async _loadAddSourceDetail() {
    if (this._addSourceKind === 'idea') {
      this._addDetailError = 'Ideas do not include files or plates until they are graduated.';
      this._addDetailFiles = [];
      this._render();
      return;
    }

    const sourceId = String(this._addSourceId || '').trim();
    if (!sourceId) {
      this._addDetailError = 'Choose a source first.';
      this._render();
      return;
    }

    this._addLoadingDetail = true;
    this._addDetailError = null;
    this._addDetailFiles = [];
    this._render();

    try {
      if (this._addSourceKind === 'catalog_model') {
        this._addDetailFiles = await this._loadCatalogSourceDetail(sourceId);
      } else {
        this._addDetailFiles = await this._loadWorkingGroupSourceDetail(sourceId);
      }
    } catch (err) {
      this._addDetailError = err.message;
      this._addDetailFiles = [];
    } finally {
      this._addLoadingDetail = false;
      this._render();
    }
  }

  async _loadCatalogSourceDetail(sourceId) {
    const detailRes = await fetch(`${this._getCatalogApiBase()}/models/${encodeURIComponent(sourceId)}/detail`);
    if (!detailRes.ok) {
      throw new Error(`Failed to load model detail (${detailRes.status})`);
    }

    const detailPayload = await detailRes.json();
    const model = detailPayload && typeof detailPayload.model === 'object' ? detailPayload.model : {};
    const files = Array.isArray(model.files) ? model.files : [];
    if (!files.length) {
      throw new Error('Selected model has no queueable files.');
    }

    const normalized = await Promise.all(
      files.map(async (file, index) => {
        const fileId = String(file.id || file.file_id || '').trim() || `catalog-file-${index + 1}`;
        const fileName = String(file.filename || file.name || fileId).trim();
        const fileType = String(file.file_type || file.content_type || file.asset_type || '').toLowerCase();
        const is3mf = fileName.toLowerCase().endsWith('.3mf') || fileType.includes('3mf');

        let plates = [{ plate_id: 'default', plate_name: 'Default Plate', selected: true }];
        if (is3mf) {
          try {
            const platesRes = await fetch(
              `${this._getCatalogApiBase()}/models/${encodeURIComponent(sourceId)}/files/${encodeURIComponent(fileId)}/plates`
            );
            if (platesRes.ok) {
              const platesPayload = await platesRes.json();
              const rawPlates = Array.isArray(platesPayload.plates) ? platesPayload.plates : [];
              if (rawPlates.length > 0) {
                plates = rawPlates.map((plate, plateIndex) => ({
                  plate_id: String(plate.plate_key || plate.plate_id || plate.id || `plate-${plateIndex + 1}`).trim(),
                  plate_name: String(plate.plate_name || plate.name || `Plate ${plateIndex + 1}`).trim(),
                  selected: true,
                }));
              }
            }
          } catch (_err) {
            // Keep default plate fallback if metadata fetch fails.
          }
        }

        return {
          file_id: fileId,
          file_name: fileName,
          selected: true,
          thumbnail_url: String(file.thumbnail_url || file.preview_url || '').trim(),
          plates,
        };
      })
    );

    return normalized;
  }

  async _resolveWorkingGroupId(sourceId) {
    const option = this._getAddSourceOption(sourceId);
    if (option && Number.isFinite(option.groupId)) {
      return option.groupId;
    }

    if (/^\d+$/.test(sourceId)) {
      return Number(sourceId);
    }

    const lookupRes = await fetch(
      `${this._getCatalogApiBase()}/working-groups?limit=50&q=${encodeURIComponent(sourceId)}`
    );
    if (!lookupRes.ok) {
      throw new Error(`Failed to resolve working group (${lookupRes.status})`);
    }

    const lookupPayload = await lookupRes.json();
    const groups = Array.isArray(lookupPayload.groups) ? lookupPayload.groups : [];
    const matched = groups.find(group => String(group.slug || '').trim() === sourceId) || groups[0];
    const groupId = matched ? Number(matched.id) : NaN;
    if (!Number.isFinite(groupId)) {
      throw new Error('Working group was not found.');
    }

    return groupId;
  }

  async _loadWorkingGroupSourceDetail(sourceId) {
    const groupId = await this._resolveWorkingGroupId(sourceId);
    const groupRes = await fetch(`${this._getCatalogApiBase()}/working-groups/${groupId}`);
    if (!groupRes.ok) {
      throw new Error(`Failed to load working group detail (${groupRes.status})`);
    }

    const groupPayload = await groupRes.json();
    const group = groupPayload && typeof groupPayload.group === 'object' ? groupPayload.group : {};
    const items = Array.isArray(group.items) ? group.items : [];
    if (!items.length) {
      throw new Error('Selected working group has no files.');
    }

    return items.map((item, index) => {
      const itemId = Number(item.id);
      const filePath = String(item.file_path || '').trim();
      const fileName = filePath ? filePath.split(/[\\/]/).pop() : `working-item-${index + 1}`;

      return {
        file_id: Number.isFinite(itemId) ? `working-item-${itemId}` : `working-item-${index + 1}`,
        file_name: fileName,
        selected: true,
        thumbnail_url: String(item.thumbnail_url || item.preview_url || item.image_url || '').trim(),
        plates: [{
          plate_id: 'default',
          plate_name: 'Default Plate',
          selected: true,
        }],
      };
    });
  }

  _setAddSourceKind(sourceKind) {
    if (sourceKind !== 'catalog_model' && sourceKind !== 'working_group' && sourceKind !== 'idea') {
      return;
    }

    this._addSourceKind = sourceKind;
    this._addSourceId = '';
    this._addDetailError = null;
    this._addDetailFiles = [];
    this._render();
  }

  _setAddIdeaTitle(value) {
    this._addIdeaTitle = String(value || '').slice(0, 120);
  }

  _setAddIdeaNotes(value) {
    this._addIdeaNotes = String(value || '').slice(0, 1200);
  }

  _setAddSourceId(sourceId) {
    const shouldRender = !!this._addDetailError || this._addDetailFiles.length > 0;
    this._addSourceId = String(sourceId || '').trim();
    this._addDetailError = null;
    this._addDetailFiles = [];
    if (shouldRender) {
      this._render();
    }
  }

  _setAddTab(tab) {
    if (tab !== 'quick' && tab !== 'advanced') {
      return;
    }

    this._addTab = tab;
    this._render();
  }

  _toggleAddFileSelection(fileId) {
    this._addDetailFiles = this._addDetailFiles.map(file => {
      if (file.file_id !== fileId) return file;
      const nextSelected = !file.selected;
      return {
        ...file,
        selected: nextSelected,
        plates: Array.isArray(file.plates)
          ? file.plates.map(plate => ({ ...plate, selected: nextSelected ? plate.selected : false }))
          : [],
      };
    });
    this._render();
  }

  _toggleAddPlateSelection(fileId, plateId) {
    this._addDetailFiles = this._addDetailFiles.map(file => {
      if (file.file_id !== fileId) return file;

      const nextPlates = (file.plates || []).map(plate => {
        if (plate.plate_id !== plateId) return plate;
        return { ...plate, selected: !plate.selected };
      });

      const hasSelectedPlates = nextPlates.some(plate => plate.selected);
      return {
        ...file,
        selected: hasSelectedPlates,
        plates: nextPlates,
      };
    });
    this._render();
  }

  _getAddSelectionMetrics() {
    const fileCount = this._addDetailFiles.length;
    const plateCount = this._addDetailFiles.reduce((sum, file) => sum + (Array.isArray(file.plates) ? file.plates.length : 0), 0);

    const selectedFiles = this._addDetailFiles.filter(file => file.selected);
    const selectedFileCount = selectedFiles.length;
    const selectedPlateCount = selectedFiles.reduce(
      (sum, file) => sum + (Array.isArray(file.plates) ? file.plates.filter(plate => plate.selected).length : 0),
      0
    );

    return {
      fileCount,
      plateCount,
      selectedFileCount,
      selectedPlateCount,
    };
  }

  _buildAdvancedSelectedFilesPayload() {
    return this._addDetailFiles.map(file => ({
      file_id: file.file_id,
      file_name: file.file_name,
      selected: !!file.selected,
      plates: (file.plates || []).map(plate => ({
        plate_id: plate.plate_id,
        selected: !!plate.selected,
      })),
    }));
  }

  _getSelectedAddSourceLabel() {
    const sourceKind = String(this._addSourceKind || '').trim();
    const sourceId = String(this._addSourceId || '').trim();
    if (!sourceKind || !sourceId) return '';
    const options = Array.isArray(this._addSourceOptions[sourceKind]) ? this._addSourceOptions[sourceKind] : [];
    const selected = options.find(option => String(option?.value || '').trim() === sourceId);
    return String(selected?.label || '').trim();
  }

  async _submitAddToQueue() {
    if (this._addSourceKind === 'idea') {
      const ideaTitle = this._stripTitlePrefix(this._addIdeaTitle || '').trim();
      if (!ideaTitle) {
        this._addDetailError = 'Idea title is required.';
        this._render();
        return;
      }

      this._addSubmitting = true;
      this._addDetailError = null;
      this._render();

      try {
        const payload = {
          source_kind: 'idea',
          title: `Idea: ${ideaTitle}`,
          state: 'up_next',
          queue_notes: String(this._addIdeaNotes || '').trim() || null,
        };

        await addUnifiedQueueEntry({
          queueApiBase: this._getQueueApiBase(),
          printerId: this.printerId,
          payload,
        });

        this._closeAddModal();
        await this._loadQueueData();

        this._setFlashMessage('Idea added successfully.', 'success');
      } catch (err) {
        this._addDetailError = err.message;
        this._render();
      } finally {
        this._addSubmitting = false;
        this._render();
      }
      return;
    }

    const sourceId = String(this._addSourceId || '').trim();
    if (!sourceId) {
      this._addDetailError = 'Choose a source first.';
      this._render();
      return;
    }

    if (this._addTab === 'advanced' && this._addDetailFiles.length === 0) {
      this._addDetailError = 'Load source details before advanced add.';
      this._render();
      return;
    }

    if (this._addSourceKind === 'catalog_model' || this._addSourceKind === 'working_group') {
      const existingEntries = this._entries.filter(entry => {
        const entrySourceId = String(entry.source_id || entry.source_ref || '').trim();
        return String(entry.source_kind || '').trim() === this._addSourceKind && entrySourceId === sourceId;
      });
      if (existingEntries.length > 0) {
        const entryLabel = existingEntries.length === 1 ? 'entry' : 'entries';
        const confirmed = window.confirm(
          `This source already has ${existingEntries.length} queue ${entryLabel}. Re-adding will create another independent entry. Continue?`
        );
        if (!confirmed) {
          return;
        }
      }
    }

    this._addSubmitting = true;
    this._addDetailError = null;
    this._render();

    try {
      const payload = {
        source_kind: this._addSourceKind,
        source_id: sourceId,
      };
      const sourceLabel = this._getSelectedAddSourceLabel();
      if (sourceLabel) {
        if (this._addSourceKind === 'catalog_model') {
          payload.title = `Catalog Model: ${sourceLabel}`;
        } else if (this._addSourceKind === 'working_group') {
          payload.title = `Working Group: ${sourceLabel}`;
        }
      }

      if (this._addTab === 'quick') {
        payload.quick_add = true;
      } else {
        payload.selection_mode = 'selected_plates';
        payload.selected_files = this._buildAdvancedSelectedFilesPayload();
      }

      await addUnifiedQueueEntry({
        queueApiBase: this._getQueueApiBase(),
        printerId: this.printerId,
        payload,
      });

      this._closeAddModal();
      this._setFlashMessage('Queue entry created successfully.', 'success');
      await this._loadQueueData();
    } catch (err) {
      this._addDetailError = err.message;
      this._render();
    } finally {
      this._addSubmitting = false;
      this._render();
    }
  }

  _getEntryById(queueEntryId) {
    return this._entries.find(entry => entry.queue_entry_id === queueEntryId) || null;
  }

  _buildLocalModelIdSeed(title) {
    const normalized = String(title || '').toLowerCase();
    const slug = normalized
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 48) || 'idea-model';
    const random = Math.random().toString(16).slice(2, 10).padEnd(8, '0');
    return `${slug}--${random}`;
  }

  _parseIdeaExternalLinks(rawValue) {
    var raw = String(rawValue || '').trim();
    if (!raw) return [];
    var lines = raw.split(/[\n,]+/).map(function(s) { return s.trim(); }).filter(Boolean);
    var results = [];
    for (var i = 0; i < lines.length; i++) {
      var parts = lines[i].split('|');
      var url = String(parts[0] || '').trim();
      var label = parts.length > 1 ? String(parts[1] || '').trim() : '';
      if (url) {
        results.push({ url: url, label: label || url });
      }
    }
    return results;
  }

  async _createIdeaEntity(ideaDraft) {
    var sidecarUrl = this._getCatalogApiBase();
    var localModelId = this._buildLocalModelIdSeed(ideaDraft.title);
    var payload = {
      local_model_id: localModelId,
      model_name: String(ideaDraft.title || '').trim(),
      entity_type: 'idea',
      tags: [],
    };
    var notes = String(ideaDraft.notes || '').trim();
    if (notes) payload.notes = notes;
    var links = this._parseIdeaExternalLinks(ideaDraft.links);
    if (links.length) payload.external_links = links;
    var sketch = String(ideaDraft.sketchUrl || '').trim();
    if (sketch) payload.sketch_image = sketch;

    var response = await fetch(sidecarUrl + '/local/models', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    var body = await response.json().catch(function() { return {}; });
    if (!response.ok) {
      throw new Error(String(body.message || body.error || 'Failed to create idea (' + response.status + ')'));
    }
    return body;
  }

  _openIdeaCreateDialog() {
    this._ideaCreateDraft = { title: '', notes: '', links: '', sketchUrl: '' };
    this._ideaCreateError = '';
    this._ideaCreateSubmitting = false;
    this._ideaCreateDialogOpen = true;
    this._render();
  }

  _closeIdeaCreateDialog() {
    if (this._ideaCreateSubmitting) return;
    this._ideaCreateDialogOpen = false;
    this._render();
  }

  async _submitIdeaCreateDialog() {
    var title = String(this._ideaCreateDraft.title || '').trim();
    if (!title) {
      this._ideaCreateError = 'Title is required.';
      this._render();
      return;
    }
    this._ideaCreateSubmitting = true;
    this._ideaCreateError = '';
    this._render();
    try {
      await this._createIdeaEntity(this._ideaCreateDraft);

      // Also add a queue entry so the idea appears on the board
      var notes = String(this._ideaCreateDraft.notes || '').trim() || null;
      await addUnifiedQueueEntry({
        queueApiBase: this._getQueueApiBase(),
        printerId: this.printerId,
        payload: {
          source_kind: 'idea',
          title: 'Idea: ' + title,
          state: 'up_next',
          queue_notes: notes,
        },
      });

      this._ideaCreateDialogOpen = false;
      this._ideaCreateSubmitting = false;
      await this._loadQueueData();
      this._setFlashMessage('Idea created successfully.', 'success');
      this._render();
    } catch (err) {
      this._ideaCreateError = String(err && err.message ? err.message : 'Unknown error');
      this._ideaCreateSubmitting = false;
      this._render();
    }
  }

  _renderIdeaCreateDialog() {
    if (!this._ideaCreateDialogOpen) return '';
    var draft = this._ideaCreateDraft || {};
    var errorHtml = this._ideaCreateError
      ? '<div class="idea-create-error">' + this._escapeHtml(this._ideaCreateError) + '</div>'
      : '';
    return '<div class="idea-create-backdrop" data-action="close-idea-create-dialog">'
      + '<div class="idea-create-dialog">'
      + '<div class="idea-create-header">'
      + '<h3>New Idea</h3>'
      + '<span class="idea-create-subtitle">Capture a quick idea for something to print</span>'
      + '</div>'
      + '<div class="idea-create-body">'
      + '<label class="idea-create-field"><strong>Title <span style="color:var(--error-color,#e53935)">*</span></strong>'
      + '<input class="idea-create-input" data-idea-field="title" type="text" maxlength="120" value="' + this._escapeHtml(draft.title || '') + '" placeholder="What should we print?" /></label>'
      + '<label class="idea-create-field"><span>Notes</span>'
      + '<textarea class="idea-create-input" data-idea-field="notes" maxlength="2000" rows="3" placeholder="Context, requirements, color/material hints...">' + this._escapeHtml(draft.notes || '') + '</textarea></label>'
      + '<label class="idea-create-field"><span>External Links</span>'
      + '<textarea class="idea-create-input" data-idea-field="links" rows="2" placeholder="One URL per line (optionally: url|label)">' + this._escapeHtml(draft.links || '') + '</textarea></label>'
      + '<label class="idea-create-field"><span>Sketch / Reference Image URL</span>'
      + '<input class="idea-create-input" data-idea-field="sketchUrl" type="url" value="' + this._escapeHtml(draft.sketchUrl || '') + '" placeholder="https://..." /></label>'
      + errorHtml
      + '</div>'
      + '<div class="idea-create-footer">'
      + '<button class="ghost-btn" data-action="close-idea-create-dialog">Cancel</button>'
      + '<button class="idea-create-submit" data-action="submit-idea-create-dialog"' + (this._ideaCreateSubmitting ? ' disabled' : '') + '>'
      + (this._ideaCreateSubmitting ? 'Creating...' : 'Create Idea') + '</button>'
      + '</div>'
      + '</div>'
      + '</div>';
  }

  _appendQueueNoteLine(existingNotes, nextLine) {
    const existing = String(existingNotes || '').trim();
    const line = String(nextLine || '').trim();
    if (!line) return existing || null;
    if (!existing) return line;
    return `${existing}\n${line}`;
  }

  _getAllEntriesRanked() {
    return [...this._entries].sort((a, b) => {
      const aRank = Number.isFinite(a.rank) ? a.rank : 999999;
      const bRank = Number.isFinite(b.rank) ? b.rank : 999999;
      if (aRank !== bRank) return aRank - bRank;
      return new Date(a.created_at || 0) - new Date(b.created_at || 0);
    });
  }

  _getSourceMeta(entry) {
    const sourceKind = String(entry.source_kind || '').trim();
    const sourceId = String(entry.source_id || entry.source_ref || '').trim() || 'n/a';
    const sourceMap = {
      catalog_model: { icon: 'CAT', label: 'Catalog' },
      working_group: { icon: 'WRK', label: 'Working Files' },
      working_file: { icon: 'WRK', label: 'Working Files' },
      idea: { icon: 'IDE', label: 'Idea' },
    };
    const mapped = sourceMap[sourceKind] || { icon: 'SRC', label: 'Source' };
    return {
      ...mapped,
      sourceKind,
      sourceId,
      fullLabel: `${mapped.label}: ${sourceId}`,
    };
  }

  async _moveEntry(queueEntryId, direction) {
    const delta = direction === 'up' ? -1 : 1;
    const ordered = this._getAllEntriesRanked();
    const index = ordered.findIndex(entry => entry.queue_entry_id === queueEntryId);
    if (index < 0) return;

    const targetIndex = index + delta;
    if (targetIndex < 0 || targetIndex >= ordered.length) return;

    const current = ordered[index];
    const target = ordered[targetIndex];
    const currentRank = Number.isFinite(current.rank) ? current.rank : index;
    const targetRank = Number.isFinite(target.rank) ? target.rank : targetIndex;

    this._rowActionBusy = true;
    this._render();
    try {
      const response = await fetch(
        `${this._getQueueApiBase()}/queues/${encodeURIComponent(this.printerId)}/reorder`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            moves: [
              { id: current.queue_entry_id, new_rank: targetRank },
              { id: target.queue_entry_id, new_rank: currentRank },
            ],
          }),
        }
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(payload.message || payload.error || `Reorder failed (${response.status})`));
      }
      this._setFlashMessage('Queue order updated.', 'success');
      await this._loadQueueData();
    } catch (err) {
      this._setFlashMessage(err.message, 'error');
    } finally {
      this._rowActionBusy = false;
      this._render();
    }
  }

  // Open the in-card delete-confirm modal for the given entry. The actual
  // delete request is dispatched only when the user confirms via
  // `_confirmPendingDelete`.
  _requestEntryDelete(queueEntryId) {
    if (!queueEntryId) return;
    this._pendingDeleteEntryId = queueEntryId;
    this._render();
  }

  _dismissPendingDelete() {
    if (!this._pendingDeleteEntryId) return;
    this._pendingDeleteEntryId = null;
    this._render();
  }

  async _confirmPendingDelete() {
    const entryId = this._pendingDeleteEntryId;
    if (!entryId) return;
    this._pendingDeleteEntryId = null;
    await this._deleteEntry(entryId);
  }

  async _deleteEntry(queueEntryId) {
    this._rowActionBusy = true;
    this._render();
    try {
      const response = await fetch(
        `${this._getQueueApiBase()}/queues/${encodeURIComponent(this.printerId)}/entries/${encodeURIComponent(queueEntryId)}`,
        { method: 'DELETE' }
      );
      if (!response.ok && response.status !== 204) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(String(payload.message || payload.error || `Delete failed (${response.status})`));
      }
      this._setFlashMessage('Queue entry deleted.', 'success');
      await this._loadQueueData();
    } catch (err) {
      this._setFlashMessage(err.message, 'error');
    } finally {
      this._rowActionBusy = false;
      this._render();
    }
  }

  _openEditModal(queueEntryId) {
    this._openEntryDetail(queueEntryId, 'info');
  }

  _closeEditModal() {
    this._editModalOpen = false;
    this._editEntryId = null;
    this._editTitle = '';
    this._editCopies = 1;
    this._editSubmitting = false;
    this._editError = null;
    this._render();
  }

  _setEditTitle(value) {
    this._editTitle = String(value || '');
    this._render();
  }

  _setEditCopies(value) {
    const parsed = Number.parseInt(value, 10);
    this._editCopies = Number.isFinite(parsed) ? parsed : value;
    this._render();
  }

  async _submitEditModal() {
    const queueEntryId = String(this._editEntryId || '').trim();
    const entry = this._getEntryById(queueEntryId);
    if (!queueEntryId || !entry) {
      this._editError = 'Entry no longer exists.';
      this._render();
      return;
    }

    const currentTitle = String(entry.title || '').trim();
    const newTitle = String(this._editTitle || '').trim() || currentTitle;
    const parsedCopies = Number.parseInt(this._editCopies, 10);
    if (!Number.isFinite(parsedCopies) || parsedCopies < 1) {
      this._editError = 'Copies must be an integer >= 1.';
      this._render();
      return;
    }

    this._editSubmitting = true;
    this._editError = null;
    this._render();
    try {
      const response = await fetch(
        `${this._getCatalogApiBase()}/unified-queue/entries/${encodeURIComponent(queueEntryId)}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: newTitle,
            copies_requested: parsedCopies,
          }),
        }
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(payload.message || payload.error || `Update failed (${response.status})`));
      }

      this._closeEditModal();
      this._setFlashMessage('Queue entry updated.', 'success');
      await this._loadQueueData();
    } catch (err) {
      this._editError = err.message;
      this._editSubmitting = false;
      this._render();
    }
  }

  async _editEntry(queueEntryId) {
    this._openEntryDetail(queueEntryId, 'info');
  }

  _openEntryDetail(queueEntryId, tab = 'plates') {
    const entry = this._getEntryById(queueEntryId);
    if (!entry) return;
    this._detailEntry = entry;
    this._detailLoading = true;
    this._detailError = null;
    this._detailFiles = [];
    this._detailTab = tab === 'info' ? 'info' : 'plates';
    this._detailSubmitting = false;
    this._detailDirty = false;
    this._ideaGraduateBusy = false;
    this._detailForm = {
      title: String(entry.title || '').trim(),
      copies: Number.isFinite(entry.copies_requested) ? entry.copies_requested : 1,
      state: String(entry.state || 'preparing').trim() || 'preparing',
      queueNotes: String(entry.queue_notes || '').trim(),
    };
    this._render();
    this._loadEntryDetailFiles(entry);
  }

  _closeEntryDetail() {
    this._detailEntry = null;
    this._detailLoading = false;
    this._detailError = null;
    this._detailFiles = [];
    this._detailTab = 'plates';
    this._detailSubmitting = false;
    this._detailDirty = false;
    this._ideaGraduateBusy = false;
    this._detailForm = {
      title: '',
      copies: 1,
      state: 'preparing',
      queueNotes: '',
    };
    this._render();
  }

  _setDetailTab(tab) {
    this._detailTab = tab === 'info' ? 'info' : 'plates';
    this._render();
  }

  _setDetailTitle(value) {
    this._detailForm.title = String(value || '');
    this._detailDirty = true;
  }

  _setDetailCopies(value) {
    this._detailForm.copies = String(value || '');
    this._detailDirty = true;
  }

  _setDetailState(value) {
    this._detailForm.state = String(value || '').trim() || 'preparing';
    this._detailDirty = true;
    this._render();
  }

  _setDetailNotes(value) {
    this._detailForm.queueNotes = String(value || '');
    this._detailDirty = true;
  }

  _toggleDetailFileSelection(fileUnitId) {
    this._detailFiles = this._detailFiles.map(file => {
      if (file.file_unit_id !== fileUnitId) return file;
      const nextSelected = !file.selected;
      const nextPlates = Array.isArray(file.plates)
        ? file.plates.map(plate => {
            const isDone = String(plate.state || '').trim() === 'done';
            if (nextSelected) {
              return { ...plate, selected: true };
            }
            // Keep completed plates selected; users must change completion state first.
            return { ...plate, selected: isDone ? true : false };
          })
        : [];
      return {
        ...file,
        selected: nextPlates.some(plate => plate.selected),
        plates: nextPlates,
      };
    });
    this._detailDirty = true;
    this._render();
  }

  _toggleDetailPlateSelection(fileUnitId, plateUnitId) {
    this._detailFiles = this._detailFiles.map(file => {
      if (file.file_unit_id !== fileUnitId) return file;
      const nextPlates = Array.isArray(file.plates)
        ? file.plates.map(plate => {
            if (plate.plate_unit_id !== plateUnitId) return plate;
          if (String(plate.state || '').trim() === 'done') return plate;
            return { ...plate, selected: !plate.selected };
          })
        : [];
      return {
        ...file,
        selected: nextPlates.some(plate => plate.selected),
        plates: nextPlates,
      };
    });
    this._detailDirty = true;
    this._render();
  }

  _selectAllDetailFilePlates(fileUnitId) {
    this._detailFiles = this._detailFiles.map(file => {
      if (file.file_unit_id !== fileUnitId) return file;
      const nextPlates = Array.isArray(file.plates)
        ? file.plates.map(plate => ({ ...plate, selected: true }))
        : [];
      return {
        ...file,
        selected: nextPlates.some(plate => plate.selected),
        plates: nextPlates,
      };
    });
    this._detailDirty = true;
    this._render();
  }

  _clearDetailFilePendingSelections(fileUnitId) {
    this._detailFiles = this._detailFiles.map(file => {
      if (file.file_unit_id !== fileUnitId) return file;
      const nextPlates = Array.isArray(file.plates)
        ? file.plates.map(plate => {
            const isDone = String(plate.state || '').trim() === 'done';
            return { ...plate, selected: isDone ? true : false };
          })
        : [];
      return {
        ...file,
        selected: nextPlates.some(plate => plate.selected),
        plates: nextPlates,
      };
    });
    this._detailDirty = true;
    this._render();
  }

  _markDetailPlateDone(fileUnitId, plateUnitId) {
    this._detailFiles = this._detailFiles.map(file => {
      if (file.file_unit_id !== fileUnitId) return file;
      return {
        ...file,
        plates: Array.isArray(file.plates)
          ? file.plates.map(plate => {
              if (plate.plate_unit_id !== plateUnitId || plate.state === 'done') return plate;
              return { ...plate, selected: true, state: 'done', last_attempt_outcome: 'success', completion_confidence: 'high' };
            })
          : [],
      };
    });
    this._detailDirty = true;
    this._render();
  }

  _buildDetailSelectionPayload() {
    return this._detailFiles.map(file => ({
      file_unit_id: file.file_unit_id,
      selected: file.selected !== false,
      plates: Array.isArray(file.plates)
        ? file.plates.map(plate => ({
            plate_unit_id: plate.plate_unit_id,
            selected: plate.selected !== false,
            state: plate.state || 'pending',
          }))
        : [],
    }));
  }

  _getDetailStateOptions() {
    const currentState = String(this._detailForm.state || this._detailEntry?.state || 'preparing').trim() || 'preparing';
    const allowed = QUEUE_STATE_TRANSITIONS[currentState] || [];
    const ordered = [currentState, ...QUEUE_STATE_FILTER_ORDER.filter(state => state !== currentState && allowed.includes(state))];
    return ordered.length > 0 ? ordered : [currentState];
  }

  _getDetailStateToneClass(state) {
    const normalized = String(state || '').trim();
    if (!normalized) return 'preparing';
    return normalized.replace(/_/g, '-');
  }

  async _submitDetailModal() {
    const queueEntryId = String(this._detailEntry?.queue_entry_id || '').trim();
    if (!queueEntryId || !this._detailEntry) {
      this._detailError = 'Entry no longer exists.';
      this._render();
      return;
    }

    const title = String(this._detailForm.title || '').trim();
    if (!title) {
      this._detailError = 'Title cannot be empty.';
      this._render();
      return;
    }

    const copies = Number.parseInt(this._detailForm.copies, 10);
    if (!Number.isFinite(copies) || copies < 1) {
      this._detailError = 'Copies must be an integer >= 1.';
      this._render();
      return;
    }

    this._detailSubmitting = true;
    this._detailError = null;
    this._render();

    try {
      const entryResponse = await fetch(
        `${this._getCatalogApiBase()}/unified-queue/entries/${encodeURIComponent(queueEntryId)}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title,
            copies_requested: copies,
            state: this._detailForm.state,
            queue_notes: String(this._detailForm.queueNotes || '').trim() || null,
          }),
        }
      );
      const entryPayload = await entryResponse.json().catch(() => ({}));
      if (!entryResponse.ok) {
        throw new Error(String(entryPayload.message || entryPayload.error || `Update failed (${entryResponse.status})`));
      }

      if (Array.isArray(this._detailFiles) && this._detailFiles.length > 0) {
        const selectionResponse = await fetch(
          `${this._getCatalogApiBase()}/unified-queue/entries/${encodeURIComponent(queueEntryId)}/selection`,
          {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ files: this._buildDetailSelectionPayload() }),
          }
        );
        const selectionPayload = await selectionResponse.json().catch(() => ({}));
        if (!selectionResponse.ok) {
          throw new Error(String(selectionPayload.message || selectionPayload.error || `Selection update failed (${selectionResponse.status})`));
        }
      }

      await this._loadQueueData();
      this._closeEntryDetail();
      this._setFlashMessage('Queue entry updated.', 'success');
    } catch (err) {
      this._detailError = err.message;
      this._detailSubmitting = false;
      this._render();
    }
  }

  async _graduateIdeaToWorkingGroup() {
    const entry = this._detailEntry;
    const queueEntryId = String(entry?.queue_entry_id || '').trim();
    if (!entry || !queueEntryId || String(entry.source_kind || '').trim() !== 'idea') return;

    const ideaTitle = this._stripTitlePrefix(this._detailForm.title || entry.title || '').trim();
    if (!ideaTitle) {
      this._detailError = 'Idea title is required before graduating.';
      this._render();
      return;
    }

    this._detailSubmitting = true;
    this._ideaGraduateBusy = true;
    this._detailError = null;
    this._render();

    try {
      const groupResponse = await fetch(`${this._getCatalogApiBase()}/working-groups`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: ideaTitle,
          notes: String(this._detailForm.queueNotes || '').trim() || null,
          stage: 'draft',
        }),
      });
      const groupPayload = await groupResponse.json().catch(() => ({}));
      if (!groupResponse.ok || !groupPayload.group) {
        throw new Error(String(groupPayload.message || groupPayload.error || `Working group create failed (${groupResponse.status})`));
      }

      const group = groupPayload.group;
      const groupRef = String(group.slug || group.id || '').trim();
      if (!groupRef) {
        throw new Error('Working group created without a usable reference.');
      }

      await addUnifiedQueueEntry({
        queueApiBase: this._getQueueApiBase(),
        printerId: this.printerId,
        payload: {
          source_kind: 'working_group',
          source_id: groupRef,
          title: `Working Group: ${ideaTitle}`,
          state: 'preparing',
          queue_notes: 'Created from queue idea graduation',
        },
      });

      const now = new Date().toISOString().slice(0, 16).replace('T', ' ');
      const note = this._appendQueueNoteLine(
        this._detailForm.queueNotes,
        `[${now}] Graduated to Working Group ${groupRef}`
      );

      const completeResponse = await fetch(
        `${this._getCatalogApiBase()}/unified-queue/entries/${encodeURIComponent(queueEntryId)}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ state: 'done', queue_notes: note }),
        }
      );
      const completePayload = await completeResponse.json().catch(() => ({}));
      if (!completeResponse.ok) {
        throw new Error(String(completePayload.message || completePayload.error || `Idea completion failed (${completeResponse.status})`));
      }

      await this._loadQueueData();
      this._closeEntryDetail();
      this._setFlashMessage(`Idea graduated to Working Group ${groupRef}.`, 'success');
    } catch (err) {
      this._detailError = err.message;
      this._detailSubmitting = false;
      this._render();
    } finally {
      this._ideaGraduateBusy = false;
    }
  }

  async _graduateIdeaToCatalog() {
    const entry = this._detailEntry;
    const queueEntryId = String(entry?.queue_entry_id || '').trim();
    if (!entry || !queueEntryId || String(entry.source_kind || '').trim() !== 'idea') return;

    const ideaTitle = this._stripTitlePrefix(this._detailForm.title || entry.title || '').trim();
    if (!ideaTitle) {
      this._detailError = 'Idea title is required before graduating.';
      this._render();
      return;
    }

    this._detailSubmitting = true;
    this._ideaGraduateBusy = true;
    this._detailError = null;
    this._render();

    try {
      const localModelId = this._buildLocalModelIdSeed(ideaTitle);
      const createResponse = await fetch(`${this._getCatalogApiBase()}/local/models`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          local_model_id: localModelId,
          model_name: ideaTitle,
          model_description: String(this._detailForm.queueNotes || '').trim() || null,
          source_origin: 'queue_idea',
        }),
      });
      const createPayload = await createResponse.json().catch(() => ({}));
      if (!createResponse.ok) {
        throw new Error(String(createPayload.message || createPayload.error || `Catalog entry create failed (${createResponse.status})`));
      }

      const modelRef = String(createPayload.local_model_id || localModelId).trim();
      await addUnifiedQueueEntry({
        queueApiBase: this._getQueueApiBase(),
        printerId: this.printerId,
        payload: {
          source_kind: 'catalog_model',
          source_id: modelRef,
          title: `Catalog Model: ${ideaTitle}`,
          state: 'preparing',
          queue_notes: 'Created from queue idea graduation',
        },
      });

      const now = new Date().toISOString().slice(0, 16).replace('T', ' ');
      const note = this._appendQueueNoteLine(
        this._detailForm.queueNotes,
        `[${now}] Graduated to Catalog ${modelRef}`
      );

      const completeResponse = await fetch(
        `${this._getCatalogApiBase()}/unified-queue/entries/${encodeURIComponent(queueEntryId)}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ state: 'done', queue_notes: note }),
        }
      );
      const completePayload = await completeResponse.json().catch(() => ({}));
      if (!completeResponse.ok) {
        throw new Error(String(completePayload.message || completePayload.error || `Idea completion failed (${completeResponse.status})`));
      }

      await this._loadQueueData();
      this._closeEntryDetail();
      this._setFlashMessage(`Idea graduated to Catalog ${modelRef}.`, 'success');
    } catch (err) {
      this._detailError = err.message;
      this._detailSubmitting = false;
      this._render();
    } finally {
      this._ideaGraduateBusy = false;
    }
  }

  _buildPrintHistoryHref(archiveId = null) {
    if (archiveId !== null && archiveId !== undefined && String(archiveId).trim()) {
      return `/3d-printing/print-history?archive_id=${encodeURIComponent(String(archiveId).trim())}`;
    }
    return '/3d-printing/print-history';
  }

  async _loadMediumConfidenceSuggestions() {
    try {
      const response = await fetch(
        `${this._getQueueApiBase()}/queues/${encodeURIComponent(this.printerId)}/suggestions?status=suggested`
      );
      if (!response.ok) {
        this._suggestions = [];
        this._suggestionsError = null;
        return;
      }

      const payload = await response.json().catch(() => ({}));
      const suggestions = Array.isArray(payload.suggestions) ? payload.suggestions : [];
      const mediumOnly = suggestions.filter(item => String(item.confidence || '').toLowerCase() === 'medium');

      const byEntry = new Map();
      mediumOnly.forEach(item => {
        const entryId = String(item.queue_entry_id || '').trim();
        if (!entryId) return;

        const existing = byEntry.get(entryId);
        const existingTs = Date.parse(existing && existing.created_at ? existing.created_at : '') || 0;
        const currentTs = Date.parse(item && item.created_at ? item.created_at : '') || 0;
        if (!existing || currentTs >= existingTs) {
          byEntry.set(entryId, item);
        }
      });

      this._suggestions = Array.from(byEntry.values());
      this._suggestionsError = null;
    } catch (_err) {
      this._suggestions = [];
      this._suggestionsError = null;
    }
  }

  async _acceptSuggestion(suggestionId, queueEntryId) {
    const sid = String(suggestionId || '').trim();
    const entryId = String(queueEntryId || '').trim();
    if (!sid || !entryId) return;

    this._suggestionBusy[sid] = true;
    this._render();
    try {
      const response = await fetch(
        `${this._getQueueApiBase()}/queues/${encodeURIComponent(this.printerId)}/suggestions/${encodeURIComponent(sid)}/remap`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ queue_entry_id: entryId }),
        }
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(payload.message || payload.error || `Accept failed (${response.status})`));
      }

      this._setFlashMessage('Suggestion accepted and queue entry marked done.', 'success');
      await this._loadQueueData();
    } catch (err) {
      this._setFlashMessage(err.message, 'error');
    } finally {
      delete this._suggestionBusy[sid];
      this._render();
    }
  }

  async _rejectSuggestion(suggestionId) {
    const sid = String(suggestionId || '').trim();
    if (!sid) return;

    this._suggestionBusy[sid] = true;
    this._render();
    try {
      const response = await fetch(
        `${this._getQueueApiBase()}/queues/${encodeURIComponent(this.printerId)}/suggestions/${encodeURIComponent(sid)}/reject`,
        { method: 'POST' }
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(payload.message || payload.error || `Reject failed (${response.status})`));
      }

      this._setFlashMessage('Suggestion rejected.', 'success');
      await this._loadQueueData();
    } catch (err) {
      this._setFlashMessage(err.message, 'error');
    } finally {
      delete this._suggestionBusy[sid];
      this._render();
    }
  }

  async _openPlannerDrawer() {
    this._plannerOpen = true;
    this._plannerStrategy = 'balanced';
    this._plannerPreview = [];
    this._plannerLoading = true;
    this._plannerError = null;
    this._plannerBusy = false;
    this._render();
    await this._loadPlannerHistory();
    await this._loadPlannerPreview();
  }

  _closePlannerDrawer() {
    this._plannerOpen = false;
    this._plannerPreview = [];
    this._render();
  }

  _buildLocalPlannerPreview(strategy) {
    const ordered = this._getAllEntriesRanked();
    const scored = ordered.map((entry, index) => {
      const duration = Number(entry.estimated_total_minutes || 0);
      const ams = Number(entry.ams_score_pct || 0);
      const overnight = Number(entry.overnight_fit_minutes || 0);

      let score = 0;
      let reason = 'Balanced queue score';
      if (strategy === 'aggressive') {
        score = (overnight * 10) + (ams * 2) - duration;
        reason = overnight > 0 ? 'Prioritized for overnight fit' : 'Lower overnight priority';
      } else if (strategy === 'lazy') {
        score = (ams * 10) + (overnight * 0.5) - (duration * 0.25);
        reason = ams >= 70 ? 'High AMS readiness' : 'Lower AMS readiness';
      } else {
        score = (ams * 6) + (overnight * 3) - (duration * 0.5);
        reason = 'Balanced AMS readiness and overnight fit';
      }

      return {
        queue_entry_id: entry.queue_entry_id,
        title: entry.title || entry.queue_entry_id,
        reason,
        current_rank: Number.isFinite(entry.rank) ? entry.rank : index + 1,
        _score: score,
      };
    });

    scored.sort((a, b) => {
      if (b._score !== a._score) return b._score - a._score;
      return a.current_rank - b.current_rank;
    });

    return scored.map((item, index) => ({
      queue_entry_id: item.queue_entry_id,
      title: item.title,
      reason: item.reason,
      new_rank: index + 1,
      current_rank: item.current_rank,
    }));
  }

  async _applyPlannerReorderMoves(moves) {
    const response = await fetch(
      `${this._getQueueApiBase()}/queues/${encodeURIComponent(this.printerId)}/reorder`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ moves }),
      }
    );
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(String(payload.message || payload.error || `Reorder failed (${response.status})`));
    }
  }

  async _loadPlannerHistory() {
    try {
      const response = await fetch(
        `${this._getQueueApiBase()}/queues/${encodeURIComponent(this.printerId)}/plan/history`,
        { method: 'GET' }
      );
      if (response.status === 404) {
        this._plannerFallbackMode = true;
        this._plannerHistory = this._plannerLocalHistory.map(item => ({
          timestamp: item.timestamp,
          strategy: item.strategy,
          entries_reordered: item.entries_reordered,
        }));
        this._plannerError = null;
        return;
      }

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(payload.message || payload.error || `Failed to load planner history (${response.status})`));
      }
      this._plannerHistory = Array.isArray(payload.history) ? payload.history.slice(0, 10) : [];
      this._plannerFallbackMode = false;
      this._plannerError = null;
    } catch (err) {
      this._plannerError = err.message;
      this._plannerHistory = [];
    } finally {
      this._plannerLoading = false;
      this._render();
    }
  }

  async _loadPlannerPreview() {
    try {
      const strategy = String(this._plannerStrategy || 'balanced').trim();
      const response = await fetch(
        `${this._getQueueApiBase()}/queues/${encodeURIComponent(this.printerId)}/plan/preview?strategy=${encodeURIComponent(strategy)}`,
        { method: 'GET' }
      );

      if (response.status === 404) {
        this._plannerFallbackMode = true;
        this._plannerPreview = this._buildLocalPlannerPreview(strategy);
        this._plannerError = null;
        return;
      }

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(payload.message || payload.error || `Failed to load preview (${response.status})`));
      }
      this._plannerPreview = Array.isArray(payload.planned_order) ? payload.planned_order : [];
      this._plannerFallbackMode = false;
      this._plannerError = null;
    } catch (err) {
      this._plannerError = err.message;
      this._plannerPreview = [];
    } finally {
      this._render();
    }
  }

  async _setPlannerStrategy(strategy) {
    this._plannerStrategy = String(strategy || 'balanced').trim();
    await this._loadPlannerPreview();
  }

  async _applyPlannedOrder() {
    if (!Array.isArray(this._plannerPreview) || this._plannerPreview.length === 0) {
      this._setFlashMessage('No planner preview to apply.', 'error');
      return;
    }

    this._plannerBusy = true;
    this._render();
    try {
      const strategy = String(this._plannerStrategy || 'balanced').trim();
      if (this._plannerFallbackMode) {
        const current = this._getAllEntriesRanked().map((entry, index) => ({
          id: entry.queue_entry_id,
          rank: Number.isFinite(entry.rank) ? entry.rank : index + 1,
        }));
        const rankById = new Map(current.map(item => [item.id, item.rank]));

        const moves = this._plannerPreview
          .map((item, index) => {
            const id = String(item.queue_entry_id || '').trim();
            if (!id) return null;
            const newRank = Number.isFinite(item.new_rank) ? item.new_rank : index + 1;
            const oldRank = rankById.get(id);
            if (!Number.isFinite(oldRank) || oldRank === newRank) return null;
            return { id, new_rank: newRank };
          })
          .filter(Boolean);

        if (moves.length > 0) {
          await this._applyPlannerReorderMoves(moves);
        }

        const previousRanks = current.map(item => ({ id: item.id, rank: item.rank }));
        this._plannerLocalHistory.unshift({
          timestamp: new Date().toISOString(),
          strategy,
          entries_reordered: moves.length,
          previous_ranks: previousRanks,
        });
        this._plannerLocalHistory = this._plannerLocalHistory.slice(0, 10);
        this._plannerHistory = this._plannerLocalHistory.map(item => ({
          timestamp: item.timestamp,
          strategy: item.strategy,
          entries_reordered: item.entries_reordered,
        }));
      } else {
        const response = await fetch(
          `${this._getQueueApiBase()}/queues/${encodeURIComponent(this.printerId)}/plan/apply`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ strategy, planned_order: this._plannerPreview }),
          }
        );
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(payload.message || payload.error || `Apply failed (${response.status})`));
        }
      }

      this._setFlashMessage(`Planner applied (${strategy} strategy).`, 'success');
      this._plannerBusy = false;
      this._plannerPreview = [];
      this._render();
      await this._loadQueueData();
      await this._loadPlannerPreview();
    } catch (err) {
      this._setFlashMessage(err.message, 'error');
      this._plannerBusy = false;
      this._render();
    }
  }

  async _undoLastPlannerOp() {
    this._plannerBusy = true;
    this._render();
    try {
      if (this._plannerFallbackMode) {
        const last = this._plannerLocalHistory.shift();
        if (!last || !Array.isArray(last.previous_ranks) || last.previous_ranks.length === 0) {
          throw new Error('No local planner operation to undo.');
        }
        const moves = last.previous_ranks
          .filter(item => item && item.id && Number.isFinite(item.rank))
          .map(item => ({ id: item.id, new_rank: item.rank }));
        if (moves.length > 0) {
          await this._applyPlannerReorderMoves(moves);
        }
        this._plannerHistory = this._plannerLocalHistory.map(item => ({
          timestamp: item.timestamp,
          strategy: item.strategy,
          entries_reordered: item.entries_reordered,
        }));
      } else {
        const response = await fetch(
          `${this._getQueueApiBase()}/queues/${encodeURIComponent(this.printerId)}/plan/undo`,
          { method: 'POST' }
        );
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(payload.message || payload.error || `Undo failed (${response.status})`));
        }
      }

      this._setFlashMessage('Planner operation undone.', 'success');
      this._plannerBusy = false;
      this._plannerPreview = [];
      this._render();
      await this._loadQueueData();
      await this._loadPlannerPreview();
    } catch (err) {
      this._setFlashMessage(err.message, 'error');
      this._plannerBusy = false;
      this._render();
    }
  }

  _toSafePositiveInt(value, fallback = 0) {
    const parsed = Number.parseInt(value, 10);
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
  }

  _extractSelectionMap(entry) {
    const selectionMap = new Map();
    const selectedFiles = Array.isArray(entry.selected_files) ? entry.selected_files : [];
    selectedFiles.forEach(file => {
      const fileId = String(file.file_id || file.id || '').trim();
      if (!fileId) return;

      const selected = file.selected !== false;
      const plates = Array.isArray(file.plates)
        ? file.plates.map(plate => ({
            plate_id: String(plate.plate_id || plate.plate_key || plate.id || '').trim(),
            selected: plate.selected !== false,
          }))
        : [];

      selectionMap.set(fileId, { selected, plates });
    });

    return selectionMap;
  }

  _normalizeDetailFiles(rawFiles, entry) {
    const sourceSelection = this._extractSelectionMap(entry);
    const copiesRequested = this._toSafePositiveInt(entry.copies_requested, 1);
    const copiesCompleted = this._toSafePositiveInt(entry.copies_completed, 0);

    return rawFiles.map((file, index) => {
      const fileId = String(file.file_id || file.id || `detail-file-${index + 1}`).trim();
      const defaultSelected = entry.selection_mode === 'all_files_all_plates' ? true : false;
      const selectedConfig = sourceSelection.get(fileId);
      const selected = selectedConfig ? selectedConfig.selected : defaultSelected;
      const rawPlates = Array.isArray(file.plates) ? file.plates : [];
      const plateSelectionMap = new Map(
        (selectedConfig && Array.isArray(selectedConfig.plates) ? selectedConfig.plates : [])
          .filter(plate => plate.plate_id)
          .map(plate => [plate.plate_id, plate.selected])
      );

      const normalizedPlates = rawPlates.map((plate, plateIndex) => {
        const plateId = String(plate.plate_id || plate.plate_key || plate.id || `plate-${plateIndex + 1}`).trim();
        const defaultPlateSelected = entry.selection_mode === 'selected_plates' ? false : selected;
        const selectedPlate = plateSelectionMap.has(plateId) ? !!plateSelectionMap.get(plateId) : defaultPlateSelected;

        return {
          plate_id: plateId,
          plate_name: String(plate.plate_name || plate.name || `Plate ${plateIndex + 1}`).trim(),
          selected: selectedPlate,
          completion_count: this._toSafePositiveInt(plate.completion_count, copiesCompleted),
          completion_target: this._toSafePositiveInt(plate.completion_target, copiesRequested),
        };
      });

      return {
        file_id: fileId,
        file_name: String(file.file_name || file.filename || file.name || fileId).trim(),
        selected,
        thumbnail_url: String(file.thumbnail_url || file.preview_url || file.image_url || file.thumb_url || '').trim(),
        plates: normalizedPlates,
      };
    });
  }

  async _loadEntryDetailFiles(entry) {
    if (!entry) return;

    const activeEntryId = String(entry.queue_entry_id || '').trim();
    if (!activeEntryId) return;

    try {
      const response = await fetch(
        `${this._getCatalogApiBase()}/unified-queue/entries/${encodeURIComponent(activeEntryId)}/detail`
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(payload.message || payload.error || `Failed to load entry detail (${response.status})`));
      }

      this._detailFiles = Array.isArray(payload.files) ? payload.files.map(file => ({
        ...file,
        plates: Array.isArray(file.plates) ? file.plates.map(plate => ({ ...plate })) : [],
      })) : [];
      this._detailError = null;
    } catch (err) {
      this._detailFiles = [];
      this._detailError = err && err.message ? err.message : 'Failed to load entry details.';
    } finally {
      if (this._detailEntry && String(this._detailEntry.queue_entry_id || '').trim() === activeEntryId) {
        this._detailLoading = false;
        this._render();
      }
    }
  }

  _getFilteredAndSortedEntries() {
    const searchTerm = String(this._filters.search || '').trim().toLowerCase();
    // Apply filters
    let filtered = this._entries.filter(entry => {
      // State filter
      if (this._filters.states.length === 0) {
        return false;
      }
      if (!this._filters.states.includes(entry.state)) {
        return false;
      }
      // Source filter
      if (this._filters.sources.length > 0 && !this._filters.sources.includes(entry.source_kind)) {
        return false;
      }
      // Search filter (title + source kind + source id, case-insensitive)
      if (searchTerm) {
        const haystack = [
          entry.title || '',
          entry.source_kind || '',
          entry.source_id || entry.source_ref || '',
          entry.block_reason || '',
        ].join(' ').toLowerCase();
        if (!haystack.includes(searchTerm)) return false;
      }
      return true;
    });

    // Apply sorting
    const sorted = [...filtered].sort((a, b) => {
      const aRank = Number.isFinite(a.rank) ? a.rank : 999;
      const bRank = Number.isFinite(b.rank) ? b.rank : 999;
      switch (this._filters.sort) {
        case 'rank':
          return aRank - bRank;
        case 'rank-desc':
          return bRank - aRank;
        case 'duration':
          return (a.estimated_total_minutes || 0) - (b.estimated_total_minutes || 0);
        case 'duration-desc':
          return (b.estimated_total_minutes || 0) - (a.estimated_total_minutes || 0);
        case 'recently-added':
          return new Date(b.created_at || 0) - new Date(a.created_at || 0);
        default:
          return 0;
      }
    });

    return sorted;
  }

  _getStateColor(state) {
    return QUEUE_STATE_PALETTE[state] || '#9eacba';
  }

  _getSourceBadgeStyles(sourceKind) {
    const styles = {
      'catalog_model': { bg: 'rgba(58,169,255,0.14)', color: '#3aa9ff' },
      'working_group': { bg: 'rgba(46,224,184,0.14)', color: '#2ee0b8' },
      'working_file': { bg: 'rgba(46,224,184,0.14)', color: '#2ee0b8' },
      'idea': { bg: 'rgba(255,181,71,0.14)', color: '#ffb547' },
    };
    return styles[sourceKind] || { bg: 'rgba(255,255,255,0.05)', color: '#9eacba' };
  }

  _renderTopWidget() {
    const stats = this._getStats();
    const eta = this._getEtaStats();
    const remainStr = this._formatDuration(eta.remainingMinutes);
    const readyCount = this._entries.filter(entry => entry.state === 'ready').length;
    const blockedCount = this._entries.filter(entry => entry.state === 'blocked' || String(entry.block_reason || '').trim()).length;
    const suggestionCount = Array.isArray(this._suggestions) ? this._suggestions.length : 0;
    const reviewCount = blockedCount + suggestionCount;
    const activeCount = this._entries.filter(entry => entry.state !== 'done').length;
    const completedCount = this._entries.filter(entry => entry.state === 'done').length;

    return `
      <div class="top-widget">
        <div class="stat-card stat-card-primary" aria-label="Active queue summary">
          <div class="stat-label">Active Queue</div>
          <div class="stat-value">${activeCount}</div>
          <div class="stat-sub">${stats.total} total entries · ${stats.inProgress} printing now</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Ready Now</div>
          <div class="stat-value">${readyCount}</div>
          <div class="stat-sub">${stats.amsReady} AMS-ready · ${stats.overnightFit} overnight-fit</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Review Required</div>
          <div class="stat-value">${reviewCount}</div>
          <div class="stat-sub">${suggestionCount} completion suggestion${suggestionCount === 1 ? '' : 's'} · ${blockedCount} blocked</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Time Remaining</div>
          <div class="stat-value stat-value-duration">${this._escapeHtml(remainStr)}</div>
          <div class="stat-sub">${eta.activeJobs} active job${eta.activeJobs === 1 ? '' : 's'} · ${eta.skippedPlates} done copies skipped</div>
          <div class="eta-bar"><span style="width: ${eta.pctComplete}%"></span></div>
        </div>
      </div>
    `;
  }

  _renderFilterControls() {
    const hasActiveFilters =
      !this._hasDefaultStateFilter() ||
      this._filters.sources.length > 0 ||
      (this._filters.search && this._filters.search.trim().length > 0);

    const searchValue = this._escapeHtml(this._filters.search || '');

    return `
      <div class="toolbar">
        <div class="view-switch" role="tablist" aria-label="Queue view">
          <button type="button" data-view="list" class="${this._view === 'list' ? 'active' : ''}" aria-pressed="${this._view === 'list'}">▤ List</button>
          <button type="button" data-view="kanban" class="${this._view === 'kanban' ? 'active' : ''}" aria-pressed="${this._view === 'kanban'}">▦ Kanban</button>
        </div>

        <div class="toolbar-divider"></div>

        <details class="dropdown" data-dropdown="states">
          <summary><span class="dd-label">States</span> <span class="dd-summary">${this._escapeHtml(this._stateFilterSummary())}</span></summary>
          <div class="dropdown-menu">
            <div class="menu-actions">
              <button type="button" data-action="states-all">Select all</button>
              <button type="button" data-action="states-none">Clear</button>
            </div>
            <div class="dd-divider"></div>
            ${this._renderStateFilterCheckboxes()}
          </div>
        </details>

        <details class="dropdown" data-dropdown="sources">
          <summary><span class="dd-label">Source</span> <span class="dd-summary">${this._escapeHtml(this._sourceFilterSummary())}</span></summary>
          <div class="dropdown-menu">
            ${this._renderSourceFilterRadios()}
          </div>
        </details>

        <div class="search-box">
          <span class="search-icon" aria-hidden="true">⌕</span>
          <input type="search" class="search-input" data-action="search"
                 placeholder="Search title, source…"
                 value="${searchValue}"
                 aria-label="Search queue entries" />
          ${this._filters.search ? `<button type="button" class="search-clear" data-action="search-clear" title="Clear search" aria-label="Clear search">×</button>` : ''}
        </div>

        ${hasActiveFilters ? `<button class="clear-filters-btn" data-action="clear" title="Reset state, source, and search filters (sort unchanged)">Clear filters</button>` : ''}

        <div class="toolbar-spacer"></div>

        <select class="sort-dropdown" data-action="sort" title="Sort order">
          <option value="rank" ${this._filters.sort === 'rank' ? 'selected' : ''}>Rank ↑</option>
          <option value="rank-desc" ${this._filters.sort === 'rank-desc' ? 'selected' : ''}>Rank ↓</option>
          <option value="duration" ${this._filters.sort === 'duration' ? 'selected' : ''}>Duration ↑</option>
          <option value="duration-desc" ${this._filters.sort === 'duration-desc' ? 'selected' : ''}>Duration ↓</option>
          <option value="recently-added" ${this._filters.sort === 'recently-added' ? 'selected' : ''}>Recently added</option>
        </select>
      </div>
    `;
  }

  _stateFilterSummary() {
    const all = QUEUE_STATE_FILTER_ORDER.length;
    const selected = this._filters.states.length;
    if (selected === 0) return 'None';
    if (selected === all) return 'All';
    if (selected <= 2) {
      return this._filters.states.map(s => this._getStateLabel(s)).join(', ');
    }
    return `${selected} of ${all}`;
  }

  _sourceFilterSummary() {
    if (this._filters.sources.length === 0) return 'All';
    const isWorking = this._filters.sources.includes('working_group') || this._filters.sources.includes('working_file');
    const isCatalog = this._filters.sources.includes('catalog_model');
    const isIdea = this._filters.sources.includes('idea');
    const labels = [];
    if (isCatalog) labels.push('Catalog');
    if (isWorking) labels.push('Working');
    if (isIdea) labels.push('Ideas');
    return labels.join(', ') || 'All';
  }

  _renderStateFilterCheckboxes() {
    return QUEUE_STATE_FILTER_ORDER.map(state => `
      <label class="dd-row" data-state="${state}">
        <input type="checkbox" data-action="toggle-state" data-state="${state}" ${this._filters.states.includes(state) ? 'checked' : ''} />
        <span class="dd-swatch" style="background: ${QUEUE_STATE_PALETTE[state]}"></span>
        <span>${this._escapeHtml(this._getStateLabel(state))}</span>
      </label>
    `).join('');
  }

  _renderSourceFilterRadios() {
    const isWorking = this._filters.sources.includes('working_group') || this._filters.sources.includes('working_file');
    const isCatalog = this._filters.sources.includes('catalog_model');
    const isIdea = this._filters.sources.includes('idea');
    const isAll = !isCatalog && !isWorking && !isIdea;
    const radios = [
      { value: 'all', label: 'All sources', checked: isAll, swatch: null },
      { value: 'catalog_model', label: 'Catalog', checked: isCatalog && !isWorking && !isIdea, swatch: '#3aa9ff' },
      { value: 'working_files', label: 'Working Files', checked: isWorking && !isCatalog && !isIdea, swatch: '#2ee0b8' },
      { value: 'idea', label: 'Ideas', checked: isIdea && !isCatalog && !isWorking, swatch: '#ffb547' },
    ];
    return radios.map(r => `
      <label class="dd-row">
        <input type="radio" name="uq-source" data-action="set-source" data-source="${r.value}" ${r.checked ? 'checked' : ''} />
        ${r.swatch ? `<span class="dd-swatch" style="background: ${r.swatch}"></span>` : '<span class="dd-swatch ghost"></span>'}
        <span>${this._escapeHtml(r.label)}</span>
      </label>
    `).join('');
  }

  _getStateLabel(state) {
    const labels = {
      'backlog': 'Backlog',
      'up_next': 'Up Next',
      'preparing': 'Preparing',
      'ready': 'Ready',
      'in_progress': 'In Progress',
      'done': 'Done',
      'blocked': 'Blocked',
    };
    return labels[state] || state;
  }

  _renderQueueList() {
    const entries = this._getFilteredAndSortedEntries();

    if (entries.length === 0) {
      const hasFilters = !this._hasDefaultStateFilter() || this._filters.sources.length > 0;
      const message = hasFilters
        ? 'No entries match your filters'
        : 'Queue is Empty';
      const subtitle = hasFilters
        ? 'Try adjusting your filter selection'
        : 'Add items to start planning your prints';

      return `
        <div class="empty-state">
          <div class="empty-icon">📋</div>
          <div class="empty-title">${message}</div>
          <div class="empty-subtitle">${subtitle}</div>
        </div>
      `;
    }

    if (this._view === 'kanban') {
      return this._renderKanbanView(entries);
    }
    return this._renderListView(entries);
  }

  _renderListView(entries) {
    const dnd = (this._filters.sort === 'rank');
    const hint = dnd
      ? 'Sorted by <strong>Rank</strong> · drag cards to reorder.'
      : (this._filters.sort.startsWith('duration')
          ? 'Sorted by <strong>Duration</strong> · drag-to-reorder is disabled.'
          : (this._filters.sort === 'recently-added'
              ? 'Sorted by <strong>Recently added</strong> · drag-to-reorder is disabled.'
              : 'Drag-to-reorder is disabled while a non-rank sort is active.'));
    const cards = entries.map(entry => this._renderQueueEntry(entry, { draggable: dnd, showStatePill: true })).join('');
    return `
      <div class="flat-list" data-flat-dnd="${dnd ? '1' : '0'}">
        <div class="flat-list-hint">${hint}</div>
        <div class="flat-list-body" data-list-body>
          ${cards}
        </div>
      </div>
    `;
  }

  _renderKanbanView(entries) {
    const visibleStates = QUEUE_STATE_FILTER_ORDER.filter(s => this._filters.states.includes(s));
    const grouped = this._groupEntriesByState(entries);
    const columns = visibleStates.map(stateKey => {
      const items = grouped[stateKey] || [];
      const colMinutes = items.reduce((sum, e) => sum + Number(e.estimated_total_minutes || 0), 0);
      const colTime = colMinutes > 0 ? `${this._formatDuration(colMinutes)} of work` : '—';
      const swatch = QUEUE_STATE_PALETTE[stateKey];
      const cards = items.length === 0
        ? `<div class="col-empty">Drop here to mark ${this._escapeHtml(this._getStateLabel(stateKey).toLowerCase())}</div>`
        : items.map(entry => this._renderQueueEntry(entry, { draggable: true, showStatePill: false })).join('');
      return `
        <div class="kanban-column" data-state="${stateKey}" style="--state: ${swatch}">
          <div class="kanban-column-header">
            <span class="kanban-ttl"><span class="kanban-dot"></span>${this._escapeHtml(this._getStateLabel(stateKey))}</span>
            <span class="kanban-count">${items.length}</span>
          </div>
          <div class="kanban-column-time">${this._escapeHtml(colTime)}</div>
          <div class="kanban-col-body" data-drop="${stateKey}">
            ${cards}
          </div>
        </div>
      `;
    }).join('');

    return `<div class="kanban-columns">${columns || '<div class="empty-state"><div class="empty-icon">📋</div><div class="empty-title">No states selected</div><div class="empty-subtitle">Use the States filter to show columns.</div></div>'}</div>`;
  }

  _groupEntriesByState(entries = this._entries) {
    const grouped = {};
    for (const entry of entries) {
      if (!grouped[entry.state]) grouped[entry.state] = [];
      grouped[entry.state].push(entry);
    }
    return grouped;
  }

  _formatStateLabel(state) {
    return this._getStateLabel(state);
  }

  _renderQueueEntry(entry, opts) {
    opts = opts || {};
    const draggable = opts.draggable !== false;
    const showStatePill = !!opts.showStatePill;
    const sourceMeta = this._getSourceMeta(entry);
    const sourceClass = entry.source_kind === 'idea'
      ? 'idea'
      : entry.source_kind === 'catalog_model'
        ? 'catalog'
        : 'working';
    // Card source chip shows just the source kind label (Catalog / Working
    // File / Idea) without the source id, per UX feedback.
    const sourceLabel = sourceMeta.label;
    // Strip any leading "Catalog Model: " / "Working File: " / "Idea: " /
    // "Working Group: " prefix the backend may have stamped onto the title.
    const displayTitle = this._stripTitlePrefix(entry.title || 'Untitled');
    const stateColor = QUEUE_STATE_PALETTE[entry.state] || '#9eacba';
    const stateLabel = this._getStateLabel(entry.state);
    const durationMinutes = Number(entry.estimated_total_minutes || 0);
    const copiesRequested = Number.isFinite(entry.copies_requested) ? entry.copies_requested : 1;
    const copiesCompleted = Number.isFinite(entry.copies_completed) ? entry.copies_completed : 0;
    const remainingCopies = Math.max(0, copiesRequested - copiesCompleted);
    const remainingMinutes = copiesRequested > 0
      ? Math.round(durationMinutes * remainingCopies / copiesRequested)
      : durationMinutes;
    const hasDuration = durationMinutes > 0;
    const remainStr = this._formatDuration(remainingMinutes);
    const totalStr = this._formatDuration(durationMinutes);
    const timeSummary = hasDuration
      ? `<span><span class="qcard-meta-key">Time</span> <span class="qcard-remain">${this._escapeHtml(remainStr)}</span> <span class="qcard-total">/ ${this._escapeHtml(totalStr)}</span></span>`
      : '';
    const segs = Array.from({ length: Math.max(1, copiesRequested) }).map((_, i) => {
      const done = i < copiesCompleted;
      return `<div class="qcard-seg ${done ? 'done' : ''}"></div>`;
    }).join('');
    const blockReason = String(entry.block_reason || '').trim();

    const fullInfo = [
      `Title: ${displayTitle}`,
      `Source: ${sourceMeta.fullLabel}`,
      `State: ${stateLabel}`,
      `Rank: ${Number.isFinite(entry.rank) ? entry.rank : 'n/a'}`,
      `Copies: ${copiesCompleted}/${copiesRequested}`,
      `Duration: ${hasDuration ? totalStr : 'no estimate'}`,
    ].join(' | ');

    const invalidDrop = this._invalidDropEntryId === entry.queue_entry_id;
    return `
      <article class="qcard${invalidDrop ? ' invalid-drop' : ''}"
               draggable="${draggable}"
               data-entry-id="${this._escapeHtml(entry.queue_entry_id)}"
               data-state="${this._escapeHtml(entry.state)}"
               style="--state: ${stateColor}"
               title="${this._escapeHtml(fullInfo)}">
        <div class="qcard-row1">
          ${draggable ? '<span class="qcard-drag" aria-hidden="true">⋮⋮</span>' : ''}
          <span class="qcard-rank">${Number.isFinite(entry.rank) ? entry.rank : '—'}</span>
          <span class="qcard-title">${this._escapeHtml(displayTitle)}</span>
          <span class="qcard-source-badge ${sourceClass}">${this._escapeHtml(sourceLabel)}</span>
          ${showStatePill ? `<span class="qcard-state-pill">${this._escapeHtml(stateLabel)}</span>` : ''}
        </div>
        <div class="qcard-row2">
          <div class="qcard-meta">
            <span><span class="qcard-meta-key">Copies</span> ${copiesCompleted}/${copiesRequested}</span>
            ${timeSummary}
            ${entry.ams_ready_score !== undefined ? `<span><span class="qcard-meta-key">AMS</span> ${entry.ams_ready_score}%</span>` : ''}
            ${entry.overnight_fit_score !== undefined ? `<span><span class="qcard-meta-key">Overnight</span> ${entry.overnight_fit_score}%</span>` : ''}
            ${blockReason ? `<span class="qcard-block-reason">⚠ ${this._escapeHtml(blockReason)}</span>` : ''}
          </div>
        </div>
        <div class="qcard-row3">
          <div class="qcard-progress" title="${copiesCompleted} of ${copiesRequested} copies done">
            <div class="qcard-plate-bar">${segs}</div>
            ${copiesCompleted > 0 ? `<span class="qcard-total">${this._escapeHtml(this._formatDuration(durationMinutes - remainingMinutes))} already done</span>` : '<span class="qcard-total">No completed copies yet</span>'}
          </div>
          <div class="qcard-actions" role="group" aria-label="Queue entry actions">
            <button class="entry-action-btn" data-action="entry-detail" data-entry-id="${this._escapeHtml(entry.queue_entry_id)}" title="View &amp; edit details">Details</button>
            <button class="entry-action-btn danger" data-action="entry-delete" data-entry-id="${this._escapeHtml(entry.queue_entry_id)}" title="Delete">Delete</button>
          </div>
        </div>
      </article>
    `;
  }

  _stripTitlePrefix(title) {
    return String(title || '').replace(/^(?:Catalog Model|Working File|Working Group|Idea)\s*:\s*/i, '').trim() || 'Untitled';
  }

  _formatDuration(minutes) {
    if (!minutes || minutes === 0) return '—';
    if (minutes < 60) return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
  }

  _escapeHtml(text) {
    const value = String(text ?? '');
    const map = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#039;',
    };
    return value.replace(/[&<>"']/g, (m) => map[m]);
  }

  _renderFlashBanner() {
    if (!this._flashMessage || !this._flashMessage.message) {
      return '';
    }

    const toneClass = this._flashMessage.type === 'error' ? 'error' : 'success';
    const icon = toneClass === 'error' ? '\u26A0' : '\u2713';
    return `
      <div class="flash-banner ${toneClass}" role="status" aria-live="polite">
        <span class="flash-banner-icon" aria-hidden="true">${icon}</span>
        ${this._escapeHtml(this._flashMessage.message)}
      </div>
    `;
  }

  _renderDeleteConfirm() {
    if (!this._pendingDeleteEntryId) return '';
    const entry = this._getEntryById(this._pendingDeleteEntryId);
    const label = entry ? this._stripTitlePrefix(entry.title || this._pendingDeleteEntryId) : this._pendingDeleteEntryId;
    const state = String(entry && entry.state ? entry.state : '').trim();
    const guardedStates = new Set(['preparing', 'ready', 'in_progress', 'blocked', 'done']);
    const stateWarning = state && guardedStates.has(state)
      ? `<div class="delete-confirm-message" style="margin-top:10px;color:#fca5a5;">
            This entry is currently in <strong>${this._escapeHtml(state)}</strong> state. Deleting it will discard the current progress and cannot be undone.
         </div>`
      : '';
    return `
      <div class="delete-confirm" role="dialog" aria-modal="true" aria-label="Delete queue entry">
        <div class="delete-confirm-backdrop"></div>
        <div class="delete-confirm-dialog">
          <div class="delete-confirm-title">Delete queue entry?</div>
          <div class="delete-confirm-message">
            This removes <strong>${this._escapeHtml(label)}</strong> from the queue. This cannot be undone.
          </div>
          ${stateWarning}
          <div class="delete-confirm-actions">
            <button class="delete-confirm-btn" data-action="delete-confirm-cancel">Keep Entry</button>
            <button class="delete-confirm-btn danger" data-action="delete-confirm-accept">Delete Entry</button>
          </div>
        </div>
      </div>
    `;
  }

  _renderSuggestionCards() {
    if (!Array.isArray(this._suggestions) || this._suggestions.length === 0) {
      return '';
    }

    const suggestionCount = this._suggestions.length;
    const cards = this._suggestions.map(suggestion => {
      const suggestionId = String(suggestion.suggestion_id || '').trim();
      const entryId = String(suggestion.queue_entry_id || '').trim();
      if (!suggestionId || !entryId) return '';

      const entry = this._getEntryById(entryId);
      if (!entry) return '';

      const busy = !!this._suggestionBusy[suggestionId];
      const archiveId = String(suggestion.archive_id || '').trim();
      const title = String(entry.title || 'this queue entry').trim();
      const reasons = Array.isArray(suggestion.reasons) ? suggestion.reasons : [];
      const reasonLabel = reasons.length > 0 ? reasons.join(', ') : 'medium confidence match';

      return `
        <article class="suggestion-card" data-suggestion-id="${this._escapeHtml(suggestionId)}" data-entry-id="${this._escapeHtml(entryId)}">
          <div class="suggestion-copy">
            <div class="suggestion-title">${this._escapeHtml(title)}</div>
            <div class="suggestion-meta">Archive ${this._escapeHtml(archiveId || 'unknown')} · ${this._escapeHtml(reasonLabel)}</div>
          </div>
          <div class="suggestion-actions">
            <button class="suggestion-btn accept" data-action="suggestion-accept" data-suggestion-id="${this._escapeHtml(suggestionId)}" data-entry-id="${this._escapeHtml(entryId)}" ${busy ? 'disabled' : ''}>${busy ? 'Working...' : 'Accept'}</button>
            <button class="suggestion-btn reject" data-action="suggestion-reject" data-suggestion-id="${this._escapeHtml(suggestionId)}" ${busy ? 'disabled' : ''}>Reject</button>
          </div>
        </article>
      `;
    }).join('');

    return cards ? `
      <section class="suggestions-block">
        <div class="suggestions-head">
          <div>
            <div class="suggestions-kicker">Review Required</div>
            <div class="suggestions-title-row">${suggestionCount} completion suggestion${suggestionCount === 1 ? '' : 's'}</div>
          </div>
          <div class="suggestions-summary">Medium-confidence archive matches waiting for operator confirmation</div>
        </div>
        ${cards}
      </section>
    ` : '';
  }

  _renderAddModal() {
    if (!this._addModalOpen) {
      return '';
    }

    const isIdeaSource = this._addSourceKind === 'idea';
    const activeOptions = this._getActiveAddOptions();
    const metrics = this._getAddSelectionMetrics();
    const ideaTitle = this._stripTitlePrefix(this._addIdeaTitle || '');
    const quickPreview = `${metrics.fileCount} files x ${metrics.plateCount} plates = ${metrics.plateCount} queue copies`;
    const advancedPreview = `${metrics.selectedFileCount} files x ${metrics.selectedPlateCount} selected plates = ${metrics.selectedPlateCount} queue copies`;

    return `
      <div class="modal-backdrop add-backdrop" data-action="close-add">
        <div class="add-modal" role="dialog" aria-modal="true" aria-label="Add To Queue">
          <div class="add-modal-header">
            <h3>Add To Queue</h3>
            <button class="modal-close-btn" data-action="close-add" title="Close">✕</button>
          </div>

          <div class="add-modal-body">
            <div class="add-controls">
              <label class="field">
                <span class="field-label">Source Type</span>
                <select class="add-source-kind">
                  <option value="catalog_model" ${this._addSourceKind === 'catalog_model' ? 'selected' : ''}>Catalog Model</option>
                  <option value="working_group" ${this._addSourceKind === 'working_group' ? 'selected' : ''}>Working Group</option>
                </select>
              </label>

              ${isIdeaSource ? `
              <label class="field">
                <span class="field-label">Idea Title</span>
                <input class="add-idea-title" type="text" maxlength="120" value="${this._escapeHtml(ideaTitle)}" placeholder="What should we print?" />
              </label>
              <div class="idea-add-panel">
                <div class="inline-note">Ideas are captured as up_next entries and can later graduate to Working Group or Catalog from details.</div>
              </div>
              ` : `
              <label class="field">
                <span class="field-label">Source</span>
                <select class="add-source-select">
                  <option value="">Choose a source...</option>
                  ${activeOptions.map(option => `
                    <option value="${this._escapeHtml(option.value)}" ${this._addSourceId === option.value ? 'selected' : ''}>
                      ${this._escapeHtml(option.label)}
                    </option>
                  `).join('')}
                </select>
              </label>

              <button class="load-detail-btn" data-action="load-add-detail" ${this._addLoadingSources || this._addLoadingDetail ? 'disabled' : ''}>
                ${this._addLoadingDetail ? 'Loading...' : 'Load Files'}
              </button>
              `}
            </div>

            ${isIdeaSource ? `
            <label class="field">
              <span class="field-label">Idea Notes (Optional)</span>
              <textarea class="add-idea-notes" maxlength="1200" placeholder="Context, requirements, color/material hints...">${this._escapeHtml(this._addIdeaNotes || '')}</textarea>
            </label>
            ` : ''}

            <div class="tab-row" ${isIdeaSource ? 'style="display:none"' : ''}>
              <button class="tab-btn ${this._addTab === 'quick' ? 'active' : ''}" data-action="add-tab" data-tab="quick">Quick Add</button>
              <button class="tab-btn ${this._addTab === 'advanced' ? 'active' : ''}" data-action="add-tab" data-tab="advanced">Advanced Add</button>
            </div>

            <div class="tab-panels">
              <section class="tab-panel ${this._addTab === 'quick' ? 'active' : ''}">
                <p class="tab-copy">${isIdeaSource ? 'Creates an idea entry in up_next.' : 'Adds all files and all plates from the selected source.'}</p>
                <div class="copy-preview">${this._escapeHtml(isIdeaSource ? 'Idea entry will be created with source kind = idea and state = up_next.' : quickPreview)}</div>
              </section>

              <section class="tab-panel ${this._addTab === 'advanced' && !isIdeaSource ? 'active' : ''}">
                <p class="tab-copy">Choose exactly which files and plates should be queued.</p>
                <div class="copy-preview">${this._escapeHtml(advancedPreview)}</div>
                <div class="selection-grid">
                  ${this._renderAdvancedSelectionGrid()}
                </div>
              </section>
            </div>

            ${this._addLoadingSources && !isIdeaSource ? '<div class="inline-note">Loading source options...</div>' : ''}
            ${this._addDetailError ? `<div class="inline-error">${this._escapeHtml(this._addDetailError)}</div>` : ''}
          </div>

          <div class="add-modal-footer">
            <button class="ghost-btn" data-action="close-add">Cancel</button>
            <button class="primary-btn" data-action="submit-add" ${this._addSubmitting ? 'disabled' : ''}>
              ${this._addSubmitting ? 'Adding...' : 'Add To Queue'}
            </button>
          </div>
        </div>
      </div>
    `;
  }

  _renderAdvancedSelectionGrid() {
    if (this._addDetailFiles.length === 0) {
      return '<div class="inline-note">Load a source to configure file and plate checkboxes.</div>';
    }

    return this._addDetailFiles.map(file => `
      <div class="file-block">
        <label class="check-row file-row">
          <input
            type="checkbox"
            class="file-checkbox"
            data-file-id="${this._escapeHtml(file.file_id)}"
            ${file.selected ? 'checked' : ''}
          />
          <span>${this._escapeHtml(file.file_name)}</span>
        </label>
        <div class="plate-list">
          ${(file.plates || []).map(plate => `
            <label class="check-row plate-row">
              <input
                type="checkbox"
                class="plate-checkbox"
                data-file-id="${this._escapeHtml(file.file_id)}"
                data-plate-id="${this._escapeHtml(plate.plate_id)}"
                ${plate.selected ? 'checked' : ''}
              />
              <span>${this._escapeHtml(plate.plate_name)}</span>
            </label>
          `).join('')}
        </div>
      </div>
    `).join('');
  }
  
  _renderEditModal() {
    return '';
  }

  _renderEntryDetailModal() {
    if (!this._detailEntry) {
      return '';
    }

    const entry = this._detailEntry;
    const sourceMeta = this._getSourceMeta(entry);
    const archiveId = String(entry.last_archive_id || '').trim();
    const printHistoryHref = this._buildPrintHistoryHref(archiveId || null);

    const title = this._escapeHtml(String(this._detailForm.title || entry.title || ''));
    const copies = this._escapeHtml(String(this._detailForm.copies || entry.copies_requested || 1));
    const notes = this._escapeHtml(String(this._detailForm.queueNotes || ''));
    const detailStateClass = this._getDetailStateToneClass(this._detailForm.state);
    const stateOptions = this._getDetailStateOptions().map(state => `
      <option value="${state}" ${this._detailForm.state === state ? 'selected' : ''}>● ${this._getStateLabel(state)}</option>
    `).join('');

    const fileGrid = this._detailLoading
      ? '<div class="inline-note">Loading files and plate states...</div>'
      : this._detailError
      ? `<div class="inline-error">${this._escapeHtml(this._detailError)}</div>`
      : this._detailFiles.length === 0
      ? '<div class="inline-note">No file-level detail is available for this entry yet.</div>'
      : `
        <div class="entry-detail-file-grid">
          ${this._detailFiles.map(file => {
            const plates = Array.isArray(file.plates) ? file.plates : [];
            const selectedCount = plates.filter(plate => plate.selected !== false).length;
            const completedCount = plates.filter(plate => String(plate.state || '').trim() === 'done').length;
            const totalCount = plates.length;
            const allSelected = totalCount > 0 && selectedCount === totalCount;
            const pendingSelected = Math.max(0, selectedCount - completedCount);
            const thumbnailUrl = String(file.thumbnail_url || file.preview_url || file.image_url || file.thumb_url || '').trim();
            return `
              <article class="entry-detail-file-card ${file.selected ? 'selected' : 'unselected'}">
                <div class="entry-detail-file-header">
                  <div class="entry-detail-file-main">
                    <div class="entry-detail-file-thumb">
                      ${thumbnailUrl
                        ? `<img src="${this._escapeHtml(thumbnailUrl)}" alt="${this._escapeHtml(file.file_name || 'Model preview')}" loading="lazy" />`
                        : '<span>3MF</span>'}
                    </div>
                    <div>
                      <div class="entry-detail-file-name" title="${this._escapeHtml(file.file_name || '')}">${this._escapeHtml(file.file_name || 'Untitled File')}</div>
                      <div class="entry-detail-file-summary">${selectedCount}/${totalCount} plates selected · ${completedCount} done</div>
                    </div>
                  </div>
                  <div class="entry-detail-file-actions">
                    <button class="entry-detail-toggle-btn" type="button" data-action="detail-file-select-all" data-file-unit-id="${this._escapeHtml(file.file_unit_id || '')}" ${allSelected ? 'disabled' : ''}>Select all</button>
                    <button class="entry-detail-toggle-btn danger" type="button" data-action="detail-file-clear-pending" data-file-unit-id="${this._escapeHtml(file.file_unit_id || '')}" ${pendingSelected === 0 ? 'disabled' : ''}>Remove model</button>
                  </div>
                </div>
                <div class="entry-detail-plate-list">
                  ${plates.map(plate => {
                    const isDone = String(plate.state || '').trim() === 'done';
                    const isSelected = plate.selected !== false;
                    const checkboxDisabled = isDone && isSelected;
                    return `
                    <label class="entry-detail-plate-row ${isSelected ? 'selected' : 'unselected'}">
                      <input type="checkbox" class="entry-detail-plate-checkbox" data-file-unit-id="${this._escapeHtml(file.file_unit_id || '')}" data-plate-unit-id="${this._escapeHtml(plate.plate_unit_id || '')}" ${isSelected ? 'checked' : ''} ${checkboxDisabled ? 'disabled' : ''} />
                      <span class="entry-detail-plate-name">${this._escapeHtml(plate.plate_name || plate.plate_key || 'Plate')}</span>
                      ${isDone
                        ? '<span class="entry-detail-plate-state done">Done</span>'
                        : (isSelected
                            ? '<span class="entry-detail-plate-state pending">Pending</span>'
                            : '<span class="entry-detail-plate-state skipped">Not selected</span>')}
                      ${(!isSelected || isDone)
                        ? '<span class="entry-detail-mark-placeholder"></span>'
                        : `<button class="entry-detail-mark-btn" type="button" data-action="mark-detail-plate-done" data-file-unit-id="${this._escapeHtml(file.file_unit_id || '')}" data-plate-unit-id="${this._escapeHtml(plate.plate_unit_id || '')}">Mark done</button>`}
                    </label>
                  `;
                  }).join('')}
                </div>
              </article>
            `;
          }).join('')}
        </div>
      `;

    const details = [
      ['Queue ID', entry.queue_entry_id],
      ['Title', entry.title],
      ['Source Kind', entry.source_kind],
      ['Source ID', sourceMeta.sourceId],
      ['State', this._detailForm.state],
      ['Rank', String(entry.rank)],
      ['Copies', String(this._detailForm.copies || entry.copies_requested || 1)],
      ['Duration', this._formatDuration(entry.estimated_total_minutes || 0)],
      ['Selection Mode', entry.selection_mode || 'all_files_all_plates'],
      ['Added', entry.created_at || ''],
    ];

    return `
      <div class="modal-backdrop detail-backdrop" data-action="close-detail">
        <section class="add-modal entry-detail-modal" role="dialog" aria-modal="true" aria-label="Queue Entry Details">
          <div class="add-modal-header">
            <h3>Queue Entry</h3>
            <button class="modal-close-btn" data-action="close-detail" title="Close">✕</button>
          </div>

          <div class="add-modal-body entry-detail-body">
            <div class="entry-detail-title-row">
              <label class="field entry-detail-main-field">
                <span class="field-label">Title</span>
                <input type="text" class="entry-detail-title-input" value="${title}" placeholder="Queue entry title" />
              </label>
              <label class="field entry-detail-copies-field">
                <span class="field-label">Copies</span>
                <input type="number" class="entry-detail-copies-input" min="1" step="1" value="${copies}" />
              </label>
            </div>

            <div class="entry-detail-meta-row">
              <div class="field entry-detail-source-field">
                <span class="field-label">Source</span>
                <div class="entry-detail-source-line">
                  <span class="entry-detail-source ${sourceMeta.sourceKind === 'idea' ? 'idea' : sourceMeta.sourceKind === 'catalog_model' ? 'catalog' : 'working'}">${this._escapeHtml(sourceMeta.label)}</span>
                  <span class="entry-detail-source-id" title="${this._escapeHtml(sourceMeta.sourceId)}">${this._escapeHtml(sourceMeta.sourceId)}</span>
                </div>
              </div>
              <label class="field entry-detail-state-field">
                <span class="field-label">State</span>
                <select class="entry-detail-state-select ${this._escapeHtml(detailStateClass)}" data-action="detail-state">
                  ${stateOptions}
                </select>
              </label>
            </div>

            <div class="entry-detail-tab-row">
              <button class="tab-btn ${this._detailTab === 'plates' ? 'active' : ''}" data-action="detail-tab" data-tab="plates">Files & Plates</button>
              <button class="tab-btn ${this._detailTab === 'info' ? 'active' : ''}" data-action="detail-tab" data-tab="info">Info & Notes</button>
            </div>

            <div class="tab-panels entry-detail-tab-panels">
              <section class="tab-panel ${this._detailTab === 'plates' ? 'active' : ''}">
                ${fileGrid}
              </section>

              <section class="tab-panel ${this._detailTab === 'info' ? 'active' : ''}">
                <div class="detail-grid entry-detail-info-grid">
              ${details.map(([label, value]) => `
                <div class="detail-row">
                  <div class="detail-key">${this._escapeHtml(label)}</div>
                  <div class="detail-value" title="${this._escapeHtml(String(value || ''))}">${this._escapeHtml(String(value || ''))}</div>
                </div>
              `).join('')}
                </div>

                <section class="detail-section">
                  <h4>Archive Linkage</h4>
                  ${archiveId
                    ? `<div class="archive-chip">Archive ${this._escapeHtml(archiveId)} linked</div>`
                    : '<div class="inline-note">No linked archive yet (entry not completed or matched).</div>'}
                </section>

                <section class="detail-section">
                  <h4>Print History</h4>
                  <a class="history-link" href="${this._escapeHtml(printHistoryHref)}" target="_blank" rel="noopener noreferrer">
                    ${archiveId ? 'Open linked archive in Print History' : 'Open Print History'}
                  </a>
                </section>

                <section class="detail-section">
                  <h4>Queue Notes</h4>
                  <textarea class="entry-detail-notes" data-action="detail-notes" placeholder="Queue-only notes visible in this board">${notes}</textarea>
                </section>

                ${sourceMeta.sourceKind === 'idea' ? `
                <section class="detail-section">
                  <h4>Graduate Idea</h4>
                  <div class="idea-graduate-row">
                    <button class="ghost-btn" data-action="graduate-idea-working" ${this._detailSubmitting ? 'disabled' : ''}>Graduate To Working Group</button>
                    <button class="primary-btn" data-action="graduate-idea-catalog" ${this._detailSubmitting ? 'disabled' : ''}>Graduate To Catalog</button>
                  </div>
                  <div class="inline-note">Graduation creates a new queue entry for the target source and marks this idea as done.</div>
                </section>
                ` : ''}
              </section>
            </div>

            ${this._detailError ? `<div class="inline-error">${this._escapeHtml(this._detailError)}</div>` : ''}
          </div>

          <div class="add-modal-footer">
            <div class="entry-detail-footer-left">
              <button class="ghost-btn" data-action="entry-delete" data-entry-id="${this._escapeHtml(entry.queue_entry_id || '')}" ${this._detailSubmitting ? 'disabled' : ''}>Remove</button>
            </div>
            <button class="ghost-btn" data-action="close-detail" ${this._detailSubmitting ? 'disabled' : ''}>Cancel</button>
            <button class="primary-btn" data-action="submit-detail" ${this._detailSubmitting ? 'disabled' : ''}>${this._detailSubmitting ? 'Saving...' : 'Save changes'}</button>
          </div>
        </section>
      </div>
    `;
  }

  _renderPlannerDrawer() {
    if (!this._plannerOpen) {
      return '';
    }

    const strategyOptions = [
      { value: 'aggressive', label: 'Aggressive - Prioritize overtime' },
      { value: 'balanced', label: 'Balanced - Mix AMS & overnight' },
      { value: 'lazy', label: 'Lazy - Prioritize AMS' },
    ];

    const previewList = this._plannerLoading
      ? '<div class="inline-note">Loading planner preview...</div>'
      : this._plannerError
      ? `<div class="inline-error">${this._escapeHtml(this._plannerError)}</div>`
      : Array.isArray(this._plannerPreview) && this._plannerPreview.length > 0
      ? `
        <ol class="planner-preview-list">
          ${this._plannerPreview.map((item, idx) => {
            const entryId = String(item.queue_entry_id || '').trim();
            const title = String(item.title || 'Untitled').trim();
            const reason = String(item.reason || '').trim();
            return `
              <li class="planner-preview-item">
                <span class="planner-rank">${idx + 1}</span>
                <div class="planner-item-main">
                  <div class="planner-item-title">${this._escapeHtml(title)}</div>
                  ${reason ? `<div class="planner-item-reason">${this._escapeHtml(reason)}</div>` : ''}
                </div>
              </li>
            `;
          }).join('')}
        </ol>
      `
      : '<div class="inline-note">No preview available.</div>';

    const historyList = Array.isArray(this._plannerHistory) && this._plannerHistory.length > 0
      ? `
        <ul class="planner-history-list">
          ${this._plannerHistory.map(op => {
            const timestamp = String(op.timestamp || '').trim();
            const strategy = String(op.strategy || 'unknown').trim();
            const entriesCount = Number(op.entries_reordered) || 0;
            return `
              <li class="planner-history-item">
                <div class="planner-history-time">${this._escapeHtml(timestamp)}</div>
                <div class="planner-history-details">
                  <span class="planner-history-strategy">${this._escapeHtml(strategy)}</span>
                  <span class="planner-history-count">${entriesCount} entries reordered</span>
                </div>
              </li>
            `;
          }).join('')}
        </ul>
      `
      : '<div class="inline-note">No planner history yet.</div>';

    const canUndo = Array.isArray(this._plannerHistory) && this._plannerHistory.length > 0;

    return `
      <div class="modal-backdrop planner-backdrop" data-action="close-planner">
        <aside class="planner-drawer" role="dialog" aria-modal="true" aria-label="Queue Planner">
          <div class="planner-drawer-header">
            <div>
              <h3>Queue Planner</h3>
              <div class="planner-drawer-subtitle">Optimize queue order with intelligent strategies</div>
            </div>
            <button class="modal-close-btn" data-action="close-planner" title="Close">✕</button>
          </div>

          <div class="planner-drawer-body">
            <section class="planner-section">
              <h4>Strategy</h4>
              <div class="strategy-selector">
                ${strategyOptions.map(opt => `
                  <label class="strategy-radio">
                    <input
                      type="radio"
                      name="planner-strategy"
                      value="${this._escapeHtml(opt.value)}"
                      ${this._plannerStrategy === opt.value ? 'checked' : ''}
                      data-action="set-strategy"
                    />
                    <span>${this._escapeHtml(opt.label)}</span>
                  </label>
                `).join('')}
              </div>
            </section>

            <section class="planner-section">
              <h4>Preview</h4>
              ${previewList}
            </section>

            <section class="planner-section">
              <h4>History</h4>
              ${historyList}
            </section>
          </div>

          <div class="planner-drawer-footer">
            <button class="ghost-btn" data-action="close-planner" ${this._plannerBusy ? 'disabled' : ''}>Cancel</button>
            <button class="ghost-btn ${canUndo ? 'warning' : 'disabled'}" data-action="undo-plan" ${!canUndo || this._plannerBusy ? 'disabled' : ''}>↶ Undo</button>
            <button class="primary-btn" data-action="apply-plan" ${this._plannerBusy ? 'disabled' : ''}>
              ${this._plannerBusy ? 'Applying...' : 'Apply Plan'}
            </button>
          </div>
        </aside>
      </div>
    `;
  }

  _render() {
    this._syncBodyScrollLock();

    const css = `
      :host {
        display: block;
        width: 100%;
        /* Theme-aware palette: align with other 3D Printing views (Print History, etc.)
           by deriving surfaces, text, and borders from the active HA theme rather than
           hardcoded slate-blue values. Accent colors remain shared with the queue
           state palette for visual continuity. */
        --bg-page: var(--primary-background-color);
        --bg-panel: var(--ha-card-background, var(--card-background-color));
        --bg-card: var(--ha-card-background, var(--card-background-color));
        --bg-card-alt: color-mix(in srgb, var(--ha-card-background, var(--card-background-color)) 92%, var(--primary-text-color) 8%);
        --border: var(--divider-color);
        --border-strong: color-mix(in srgb, var(--divider-color) 60%, var(--primary-text-color) 40%);
        --text: var(--primary-text-color);
        --text-secondary: var(--secondary-text-color);
        --text-muted: color-mix(in srgb, var(--secondary-text-color) 70%, transparent);
        --state-backlog: #7a6a57;
        --state-up-next: #a07cff;
        --state-preparing: #ff9a3c;
        --state-ready: #58e0b8;
        --state-in-progress: #3aa9ff;
        --state-blocked: #ff6b6b;
        --state-done: #4fcf75;
        --accent: var(--state-ready);
        --accent-blue: var(--state-in-progress);
        --accent-amber: var(--state-preparing);
        --accent-red: var(--state-blocked);
        --accent-green: var(--state-done);
        --shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0, 0, 0, 0.12));
      }

      :host {
        display: flex;
        flex-direction: column;
        height: 100%;
        width: 100%;
      }

      * {
        box-sizing: border-box;
      }

      .shell {
        width: 100%;
        height: 100%;
        background: transparent;
        border: 0;
        border-radius: 0;
        box-shadow: none;
        overflow: visible;
        display: flex;
        flex-direction: column;
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

      .title-actions {
        display: inline-flex;
        align-items: center;
        gap: 8px;
      }

      .add-btn {
        padding: 6px 12px;
        border: 1px solid rgba(110, 231, 200, 0.35);
        border-radius: 8px;
        background: rgba(110, 231, 200, 0.12);
        color: var(--accent);
        font-size: 12px;
        font-weight: 700;
        cursor: pointer;
        transition: all 0.2s;
      }

      .add-btn:hover {
        background: rgba(110, 231, 200, 0.2);
        border-color: rgba(110, 231, 200, 0.5);
      }

      .planner-btn {
        padding: 6px 12px;
        border: 1px solid rgba(124, 199, 255, 0.35);
        border-radius: 8px;
        background: rgba(124, 199, 255, 0.12);
        color: var(--accent-blue);
        font-size: 12px;
        font-weight: 700;
        cursor: pointer;
        transition: all 0.2s;
      }

      .planner-btn:hover {
        background: rgba(124, 199, 255, 0.2);
        border-color: rgba(124, 199, 255, 0.5);
      }

      .db-pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 8px 10px;
        border-radius: 999px;
        border: 1px solid rgba(125, 125, 125, 0.35);
        background: rgba(96, 165, 250, 0.12);
        box-shadow: none;
        height: 36px;
      }

      .db-icon {
        width: 16px;
        height: 16px;
        flex-shrink: 0;
        color: var(--primary-color, #60a5fa);
        opacity: 1;
        display: flex;
        align-items: center;
        justify-content: center;
      }

      .db-label {
        font-size: 11px;
        font-weight: 700;
        color: var(--secondary-text-color, #9ca3af);
        white-space: nowrap;
      }

      .db-state {
        font-size: 12px;
        font-weight: 700;
        text-transform: uppercase;
        color: var(--primary-text-color, #f3f4f6);
        white-space: nowrap;
      }

      .db-pill:hover {
        background: rgba(96, 165, 250, 0.18);
        border-color: rgba(96, 165, 250, 0.5);
        cursor: pointer;
      }

      .db-pill.db-pill-mismatch {
        background: rgba(251, 191, 36, 0.18);
        border-color: rgba(251, 191, 36, 0.6);
      }

      .db-pill.db-pill-mismatch .db-state {
        color: #fde68a;
      }

      .db-pill.db-pill-mismatch .db-icon {
        color: #fbbf24;
      }

      .db-pill.db-pill-unavailable {
        background: rgba(125, 125, 125, 0.18);
        border-color: rgba(125, 125, 125, 0.5);
      }

      .db-pill.db-pill-unavailable .db-state {
        color: var(--secondary-text-color, #9ca3af);
      }

      .flash-banner {
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        z-index: 9999;
        padding: 16px 28px;
        border-radius: 12px;
        font-size: 15px;
        font-weight: 700;
        border: 1px solid transparent;
        box-shadow: 0 12px 32px rgba(0, 0, 0, 0.5),
                    0 4px 10px rgba(0, 0, 0, 0.35);
        backdrop-filter: blur(10px);
        max-width: min(90vw, 560px);
        text-align: center;
        pointer-events: none;
        animation: flash-toast-in 0.22s ease-out;
      }
      @keyframes flash-toast-in {
        from { opacity: 0; transform: translate(-50%, calc(-50% - 12px)) scale(0.96); }
        to   { opacity: 1; transform: translate(-50%, -50%) scale(1); }
      }
      .flash-banner--leaving {
        animation: flash-toast-out 0.22s ease-in forwards;
      }
      @keyframes flash-toast-out {
        from { opacity: 1; transform: translate(-50%, -50%) scale(1); }
        to   { opacity: 0; transform: translate(-50%, calc(-50% - 8px)) scale(0.97); }
      }

      .flash-banner.success {
        background: rgba(20, 40, 28, 0.92);
        border-color: rgba(125, 220, 151, 0.55);
        color: var(--accent-green);
      }

      .flash-banner.error {
        background: rgba(50, 18, 18, 0.94);
        border-color: rgba(245, 144, 144, 0.7);
        color: var(--accent-red);
      }
      .flash-banner-icon {
        display: inline-block;
        margin-right: 8px;
        font-size: 14px;
        font-weight: 700;
      }

      /* ---------- Delete confirm modal ---------- */
      .delete-confirm {
        position: fixed;
        inset: 0;
        z-index: 9998;
        display: grid;
        place-items: center;
        padding: 16px;
        box-sizing: border-box;
      }
      .delete-confirm-backdrop {
        position: absolute;
        inset: 0;
        background: rgba(15, 23, 42, 0.55);
        backdrop-filter: blur(4px);
      }
      .delete-confirm-dialog {
        position: relative;
        display: grid;
        gap: 12px;
        width: min(440px, 100%);
        padding: 20px 22px;
        border-radius: 14px;
        border: 1px solid rgba(245, 144, 144, 0.45);
        background: var(--bg-card, rgba(15, 23, 42, 0.98));
        box-shadow: 0 18px 42px rgba(2, 6, 23, 0.55),
                    0 0 0 1px rgba(245, 144, 144, 0.18);
        animation: flash-toast-in 0.18s ease-out;
      }
      .delete-confirm-title {
        font-size: 16px;
        font-weight: 700;
        color: var(--text);
      }
      .delete-confirm-message {
        font-size: 13px;
        line-height: 1.5;
        color: var(--text-secondary);
      }
      .delete-confirm-message strong {
        color: var(--text);
      }
      .delete-confirm-actions {
        display: flex;
        justify-content: flex-end;
        gap: 8px;
        margin-top: 4px;
      }
      .delete-confirm-btn {
        padding: 8px 14px;
        font-size: 13px;
        font-weight: 600;
        border-radius: 8px;
        border: 1px solid var(--border);
        background: rgba(255, 255, 255, 0.04);
        color: var(--text);
        cursor: pointer;
        transition: background 0.15s, border-color 0.15s;
      }
      .delete-confirm-btn:hover {
        background: rgba(255, 255, 255, 0.08);
        border-color: var(--border-strong);
      }
      .delete-confirm-btn.danger {
        background: rgba(245, 144, 144, 0.16);
        border-color: rgba(245, 144, 144, 0.55);
        color: #ff9b9b;
      }
      .delete-confirm-btn.danger:hover {
        background: rgba(245, 144, 144, 0.28);
        border-color: rgba(245, 144, 144, 0.85);
        color: #ffb0b0;
      }

      .suggestions-block {
        display: grid;
        gap: 8px;
        margin-bottom: 2px;
        padding: 10px 12px;
        border: 1px solid rgba(242, 195, 91, 0.24);
        border-radius: 14px;
        background: linear-gradient(180deg, rgba(242, 195, 91, 0.08), rgba(242, 195, 91, 0.03));
      }

      .suggestions-head {
        display: flex;
        justify-content: space-between;
        align-items: end;
        gap: 10px;
        flex-wrap: wrap;
      }

      .suggestions-kicker {
        font-size: 10px;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--text-muted);
      }

      .suggestions-title-row {
        color: var(--text);
        font-size: 14px;
        font-weight: 700;
        margin-top: 2px;
      }

      .suggestions-summary {
        color: var(--text-secondary);
        font-size: 11px;
      }

      .suggestion-card {
        border: 1px solid rgba(242, 195, 91, 0.24);
        border-radius: 10px;
        background: rgba(255,255,255,0.02);
        padding: 8px 10px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
      }

      .suggestion-title {
        color: var(--text);
        font-size: 13px;
        font-weight: 700;
      }

      .suggestion-meta {
        color: var(--text-secondary);
        font-size: 11px;
        margin-top: 3px;
      }

      .suggestion-actions {
        display: inline-flex;
        gap: 6px;
        flex-wrap: wrap;
      }

      .suggestion-btn {
        border-radius: 8px;
        border: 1px solid var(--border);
        min-height: 30px;
        padding: 0 10px;
        font-size: 12px;
        font-weight: 700;
        cursor: pointer;
      }

      .suggestion-btn.accept {
        border-color: rgba(110, 231, 200, 0.35);
        background: rgba(110, 231, 200, 0.14);
        color: var(--accent);
      }

      .suggestion-btn.reject {
        border-color: rgba(245, 144, 144, 0.3);
        background: rgba(245, 144, 144, 0.12);
        color: var(--accent-red);
      }

      .suggestion-btn:disabled {
        opacity: 0.7;
        cursor: not-allowed;
      }

      .content {
        padding: 18px;
        display: flex;
        flex-direction: column;
        gap: 18px;
        flex: 1;
        min-height: 0;
      }

      .filter-bar {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 12px;
        padding: 14px;
        background: rgba(255,255,255,0.02);
        border: 1px solid var(--border);
        border-radius: 14px;
        align-items: center;
      }

      .filter-section {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }

      .filter-label {
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.07em;
        text-transform: uppercase;
        color: var(--text-muted);
      }

      .filter-buttons {
        display: flex;
        gap: 6px;
        flex-wrap: wrap;
      }

      .filter-btn {
        padding: 6px 10px;
        border: 1px solid var(--border);
        border-radius: 10px;
        background: rgba(255,255,255,0.03);
        color: var(--text-secondary);
        font-size: 12px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s;
        white-space: nowrap;
      }

      .filter-btn:hover {
        background: rgba(255,255,255,0.06);
        color: var(--text);
      }

      .filter-btn.active {
        background: rgba(110, 231, 200, 0.12);
        border-color: rgba(110, 231, 200, 0.30);
        color: var(--accent);
      }

      .sort-dropdown {
        padding: 6px 10px;
        border: 1px solid var(--border);
        border-radius: 10px;
        background: rgba(255,255,255,0.03);
        color: var(--text);
        font-size: 12px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s;
        width: auto;
        min-width: 0;
        max-width: 180px;
        margin-left: auto;
      }

      .sort-dropdown:hover {
        background: rgba(255,255,255,0.06);
        border-color: var(--border-strong);
      }

      .sort-dropdown option {
        background: var(--bg-card);
        color: var(--text);
      }

      .clear-filters-btn {
        padding: 6px 10px;
        border: 1px solid rgba(245, 144, 144, 0.3);
        border-radius: 10px;
        background: rgba(245, 144, 144, 0.08);
        color: #f59090;
        font-size: 12px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s;
        white-space: nowrap;
      }

      .clear-filters-btn:hover {
        background: rgba(245, 144, 144, 0.12);
        border-color: rgba(245, 144, 144, 0.5);
        color: #ff7f7f;
      }

      .search-box {
        position: relative;
        display: inline-flex;
        align-items: center;
        flex: 0 1 240px;
        min-width: 160px;
      }
      .search-icon {
        position: absolute;
        left: 10px;
        color: var(--text-muted);
        font-size: 13px;
        pointer-events: none;
      }
      .search-input {
        width: 100%;
        padding: 6px 28px 6px 28px;
        border: 1px solid var(--border);
        border-radius: 10px;
        background: rgba(255,255,255,0.03);
        color: var(--text);
        font-size: 12px;
        font-weight: 500;
        transition: all 0.2s;
      }
      .search-input::placeholder {
        color: var(--text-muted);
      }
      .search-input:focus {
        outline: none;
        border-color: var(--accent);
        background: rgba(255,255,255,0.06);
      }
      .search-input::-webkit-search-cancel-button {
        display: none;
      }
      .search-clear {
        position: absolute;
        right: 6px;
        background: transparent;
        border: none;
        color: var(--text-muted);
        cursor: pointer;
        font-size: 16px;
        line-height: 1;
        padding: 2px 6px;
        border-radius: 6px;
      }
      .search-clear:hover {
        color: var(--text);
        background: rgba(255,255,255,0.08);
      }

      .top-widget {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 10px;
      }

      .stat-card {
        background: var(--bg-card-alt);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 12px 14px;
        display: grid;
        gap: 4px;
        text-align: left;
      }

      .stat-card-primary {
        border-color: rgba(124,199,255,0.3);
        background: linear-gradient(135deg, rgba(124,199,255,0.14), rgba(110,231,200,0.08));
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
        font-size: 26px;
        font-weight: 800;
        letter-spacing: -0.04em;
        color: var(--text);
      }

      .stat-value-duration {
        font-size: 22px;
        letter-spacing: -0.02em;
      }

      .stat-sub {
        font-size: 11px;
        color: var(--text-secondary);
        line-height: 1.4;
      }

      .queue-list {
        display: flex;
        flex-direction: column;
        gap: 16px;
        flex: 1;
        min-height: 0;
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

      .entry-title-block {
        display: flex;
        flex-direction: column;
        gap: 4px;
        min-width: 0;
        flex: 1;
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
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .source-ref {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        max-width: 100%;
      }

      .source-icon-pill {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 28px;
        height: 18px;
        padding: 0 6px;
        border: 1px solid var(--border);
        border-radius: 999px;
        background: rgba(255,255,255,0.04);
        color: var(--text-secondary);
        font-size: 9px;
        font-weight: 700;
        letter-spacing: 0.05em;
      }

      .source-ref-text {
        color: var(--text-secondary);
        font-size: 11px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        max-width: 240px;
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

      .entry-actions {
        margin-top: 10px;
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
      }

      .entry-action-btn {
        height: 28px;
        padding: 0 10px;
        border: 1px solid var(--border);
        border-radius: 8px;
        background: rgba(255,255,255,0.03);
        color: var(--text-secondary);
        font-size: 11px;
        font-weight: 700;
        cursor: pointer;
        transition: all 0.15s;
      }

      .entry-action-btn:hover,
      .entry-action-btn:focus-visible {
        background: rgba(255,255,255,0.07);
        color: var(--text);
        outline: none;
      }

      .entry-action-btn.danger {
        border-color: rgba(245, 144, 144, 0.35);
        color: var(--accent-red);
      }

      .entry-action-btn.danger:hover,
      .entry-action-btn.danger:focus-visible {
        background: rgba(245, 144, 144, 0.12);
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

      .modal-backdrop {
        position: fixed;
        inset: 0;
        z-index: 50;
        background: rgba(3, 8, 14, 0.7);
        backdrop-filter: blur(3px);
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 18px;
      }

      .add-modal {
        width: min(900px, 100%);
        max-height: calc(100vh - 40px);
        overflow: hidden;
        background:
          linear-gradient(180deg,
            color-mix(in srgb, var(--bg-card-alt) 88%, var(--state-in-progress) 12%),
            color-mix(in srgb, var(--bg-card) 92%, transparent));
        border: 1px solid var(--border-strong);
        border-radius: 18px;
        box-shadow: var(--shadow);
        animation: fadeInUp 0.18s ease-out;
        display: grid;
        grid-template-rows: auto 1fr auto;
      }

      @keyframes fadeInUp {
        from {
          opacity: 0;
          transform: translateY(8px);
        }
        to {
          opacity: 1;
          transform: translateY(0);
        }
      }

      .add-modal-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 14px 16px;
        border-bottom: 1px solid var(--border);
        background: color-mix(in srgb, var(--bg-card-alt) 94%, var(--state-in-progress) 6%);
      }

      .add-modal-header h3 {
        margin: 0;
        color: var(--text);
        font-size: 16px;
      }

      .modal-close-btn {
        border: 1px solid var(--border);
        background: rgba(255,255,255,0.03);
        color: var(--text-secondary);
        border-radius: 8px;
        padding: 4px 8px;
        cursor: pointer;
      }

      .add-modal-body {
        padding: 16px;
        display: flex;
        flex-direction: column;
        gap: 14px;
        min-height: 0;
        overflow: auto;
      }

      .add-controls {
        display: grid;
        grid-template-columns: 1fr 1fr auto;
        gap: 10px;
      }

      .field {
        display: flex;
        flex-direction: column;
        gap: 5px;
      }

      .field-label {
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.07em;
        text-transform: uppercase;
        color: var(--text-muted);
      }

      .field select {
        height: 34px;
        border: 1px solid var(--border);
        border-radius: 10px;
        background: rgba(255,255,255,0.03);
        color: var(--text);
        padding: 0 10px;
        font-size: 12px;
        color-scheme: dark light;
      }

      .field input {
        height: 34px;
        border: 1px solid var(--border);
        border-radius: 10px;
        background: rgba(255,255,255,0.03);
        color: var(--text);
        padding: 0 10px;
        font-size: 12px;
      }

      .field textarea {
        min-height: 72px;
        border: 1px solid var(--border);
        border-radius: 10px;
        background: rgba(255,255,255,0.03);
        color: var(--text);
        padding: 8px 10px;
        font-size: 12px;
        resize: vertical;
      }

      .idea-add-panel {
        align-self: end;
      }

      .field select option {
        background: var(--bg-card);
        color: var(--text);
      }

      .load-detail-btn {
        align-self: end;
        height: 34px;
        padding: 0 12px;
        border: 1px solid var(--border);
        border-radius: 10px;
        background: rgba(255,255,255,0.05);
        color: var(--text-secondary);
        font-size: 12px;
        font-weight: 600;
        cursor: pointer;
      }

      .load-detail-btn:disabled {
        opacity: 0.6;
        cursor: not-allowed;
      }

      .tab-row {
        display: inline-flex;
        border: 1px solid var(--border);
        border-radius: 10px;
        overflow: hidden;
        width: fit-content;
      }

      .tab-btn {
        border: 0;
        background: rgba(255,255,255,0.03);
        color: var(--text-secondary);
        padding: 8px 12px;
        font-size: 12px;
        font-weight: 700;
        cursor: pointer;
        transition: all 0.2s;
      }

      .tab-btn.active {
        background: rgba(110, 231, 200, 0.16);
        color: var(--accent);
      }

      .tab-panels {
        border: 1px solid var(--border);
        border-radius: 12px;
        overflow: hidden;
      }

      .tab-panel {
        display: none;
        padding: 12px;
        background: rgba(255,255,255,0.02);
      }

      .tab-panel.active {
        display: block;
      }

      .tab-copy {
        margin: 0 0 10px;
        font-size: 12px;
        color: var(--text-secondary);
      }

      .copy-preview {
        margin-bottom: 12px;
        border-radius: 10px;
        border: 1px solid color-mix(in srgb, var(--state-in-progress) 32%, transparent);
        background: color-mix(in srgb, var(--state-in-progress) 12%, transparent);
        padding: 8px 10px;
        font-size: 12px;
        color: var(--state-in-progress);
      }

      .selection-grid {
        display: grid;
        gap: 10px;
        max-height: min(46vh, 420px);
        overflow-y: auto;
        overflow-x: hidden;
        padding-right: 4px;
        scrollbar-gutter: stable;
      }

      .file-block {
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 10px;
        background: rgba(255,255,255,0.02);
      }

      .check-row {
        display: flex;
        align-items: center;
        gap: 8px;
        color: var(--text);
        font-size: 12px;
      }

      .file-row {
        font-weight: 700;
      }

      .plate-list {
        margin-top: 8px;
        margin-left: 22px;
        display: grid;
        gap: 6px;
      }

      .plate-row {
        color: var(--text-secondary);
      }

      .inline-note {
        font-size: 12px;
        color: var(--text-secondary);
      }

      .idea-graduate-row {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 8px;
      }

      .inline-error {
        border-radius: 10px;
        border: 1px solid rgba(245, 144, 144, 0.25);
        background: rgba(245, 144, 144, 0.1);
        color: var(--accent-red);
        font-size: 12px;
        padding: 8px 10px;
      }

      .detail-grid {
        display: grid;
        gap: 8px;
      }

      .detail-backdrop {
        justify-content: center;
        align-items: center;
        padding: 18px;
      }

      .detail-drawer {
        width: min(720px, 96vw);
        height: 100vh;
        background: rgba(22, 29, 40, 0.99);
        border-left: 1px solid var(--border-strong);
        box-shadow: -16px 0 48px rgba(0, 0, 0, 0.35);
        display: grid;
        grid-template-rows: auto 1fr auto;
        animation: slideInRight 180ms ease-out;
      }

      .detail-drawer-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 10px;
        padding: 14px 16px;
        border-bottom: 1px solid var(--border);
      }

      .detail-drawer-header h3 {
        margin: 0;
        color: var(--text);
        font-size: 16px;
      }

      .detail-drawer-subtitle {
        margin-top: 4px;
        color: var(--text-secondary);
        font-size: 12px;
      }

      .detail-drawer-body {
        padding: 14px 16px 16px;
        overflow-y: auto;
        display: grid;
        gap: 14px;
      }

      .detail-section {
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 12px;
        background: rgba(255,255,255,0.02);
      }

      .detail-section h4 {
        margin: 0 0 10px;
        color: var(--text);
        font-size: 13px;
      }

      .detail-file-grid {
        display: grid;
        gap: 10px;
      }

      .entry-detail-modal {
        width: min(1024px, 100%);
      }

      .entry-detail-header-meta {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }

      .entry-detail-source {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        width: fit-content;
        padding: 4px 9px;
        border-radius: 999px;
        font-size: 10px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        border: 1px solid var(--border);
        color: var(--text-secondary);
        background: rgba(255,255,255,0.04);
      }

      .entry-detail-source.catalog {
        color: var(--state-in-progress);
        border-color: color-mix(in srgb, var(--state-in-progress) 36%, transparent);
        background: color-mix(in srgb, var(--state-in-progress) 14%, transparent);
      }

      .entry-detail-source.working {
        color: var(--state-ready);
        border-color: color-mix(in srgb, var(--state-ready) 36%, transparent);
        background: color-mix(in srgb, var(--state-ready) 14%, transparent);
      }

      .entry-detail-source.idea {
        color: var(--state-preparing);
        border-color: color-mix(in srgb, var(--state-preparing) 36%, transparent);
        background: color-mix(in srgb, var(--state-preparing) 14%, transparent);
      }

      .entry-detail-body {
        min-height: 0;
        overflow: hidden;
      }

      .entry-detail-state-select,
      .entry-detail-title-input,
      .entry-detail-copies-input,
      .entry-detail-notes {
        border: 1px solid var(--border);
        border-radius: 10px;
        background: rgba(255,255,255,0.04);
        color: var(--text);
      }

      .entry-detail-state-select {
        height: 36px;
        padding: 0 10px;
        font-size: 12px;
        font-weight: 700;
        min-width: 180px;
        color-scheme: dark light;
      }

      .entry-detail-state-select option {
        background: var(--bg-card);
        color: var(--text);
      }

      .entry-detail-state-select.backlog {
        color: var(--state-backlog);
        border-color: color-mix(in srgb, var(--state-backlog) 44%, transparent);
        background: color-mix(in srgb, var(--state-backlog) 16%, transparent);
      }
      .entry-detail-state-select.up_next {
        color: var(--state-up-next);
        border-color: color-mix(in srgb, var(--state-up-next) 44%, transparent);
        background: color-mix(in srgb, var(--state-up-next) 16%, transparent);
      }

      .entry-detail-state-select.preparing {
        color: var(--state-preparing);
        border-color: color-mix(in srgb, var(--state-preparing) 44%, transparent);
        background: color-mix(in srgb, var(--state-preparing) 16%, transparent);
      }

      .entry-detail-state-select.ready {
        color: var(--state-ready);
        border-color: color-mix(in srgb, var(--state-ready) 44%, transparent);
        background: color-mix(in srgb, var(--state-ready) 16%, transparent);
      }

      .entry-detail-state-select.in-progress {
        color: var(--state-in-progress);
        border-color: color-mix(in srgb, var(--state-in-progress) 44%, transparent);
        background: color-mix(in srgb, var(--state-in-progress) 16%, transparent);
      }

      .entry-detail-state-select.blocked {
        color: var(--state-blocked);
        border-color: color-mix(in srgb, var(--state-blocked) 44%, transparent);
        background: color-mix(in srgb, var(--state-blocked) 16%, transparent);
      }

      .entry-detail-state-select.done {
        color: var(--state-done);
        border-color: color-mix(in srgb, var(--state-done) 48%, transparent);
        background: color-mix(in srgb, var(--state-done) 18%, transparent);
      }

      .entry-detail-state-select option[value="backlog"] { color: var(--state-backlog); background: var(--bg-card); }
      .entry-detail-state-select option[value="up_next"] { color: var(--state-up-next); background: var(--bg-card); }
      .entry-detail-state-select option[value="preparing"] { color: var(--state-preparing); background: var(--bg-card); }
      .entry-detail-state-select option[value="ready"] { color: var(--state-ready); background: var(--bg-card); }
      .entry-detail-state-select option[value="in_progress"] { color: var(--state-in-progress); background: var(--bg-card); }
      .entry-detail-state-select option[value="blocked"] { color: var(--state-blocked); background: var(--bg-card); }
      .entry-detail-state-select option[value="done"] { color: var(--state-done); background: var(--bg-card); }

      .entry-detail-meta-row {
        display: grid;
        grid-template-columns: 1fr auto;
        gap: 10px;
        align-items: end;
      }

      .entry-detail-source-line {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
      }

      .entry-detail-source-id {
        color: var(--text-secondary);
        font-size: 12px;
        max-width: 220px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .entry-detail-title-row {
        display: grid;
        grid-template-columns: 1fr 120px;
        gap: 10px;
      }

      .entry-detail-main-field {
        min-width: 0;
      }

      .entry-detail-title-input,
      .entry-detail-copies-input {
        height: 40px;
        padding: 0 10px;
        font-size: 14px;
      }

      .entry-detail-title-input {
        font-size: 28px;
        font-weight: 800;
        letter-spacing: -0.03em;
        padding: 0 14px;
      }

      .entry-detail-copies-input {
        text-align: center;
      }

      .entry-detail-tab-row {
        display: inline-flex;
        border: 1px solid var(--border);
        border-radius: 10px;
        overflow: hidden;
        width: fit-content;
      }

      .entry-detail-tab-panels {
        width: 100%;
        flex: 1 1 auto;
        min-height: 0;
        overflow: auto;
      }

      .entry-detail-tab-panels > .tab-panel {
        min-height: 100%;
      }

      .entry-detail-file-grid {
        display: grid;
        gap: 10px;
      }

      .entry-detail-file-card {
        border: 1px solid var(--border);
        border-radius: 12px;
        background: rgba(255,255,255,0.02);
        overflow: hidden;
      }

      .entry-detail-file-card.unselected {
        opacity: 0.78;
      }

      .entry-detail-file-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 10px;
        padding: 10px 12px;
        border-bottom: 1px solid rgba(148, 163, 184, 0.08);
      }

      .entry-detail-file-main {
        display: grid;
        grid-template-columns: 44px 1fr;
        gap: 10px;
        align-items: center;
        min-width: 0;
      }

      .entry-detail-file-thumb {
        width: 44px;
        height: 36px;
        border-radius: 8px;
        border: 1px solid var(--border);
        overflow: hidden;
        display: flex;
        align-items: center;
        justify-content: center;
        background: linear-gradient(135deg,
          color-mix(in srgb, var(--state-in-progress) 20%, transparent),
          color-mix(in srgb, var(--state-ready) 16%, transparent));
        color: var(--text-muted);
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.04em;
      }

      .entry-detail-file-thumb img {
        width: 100%;
        height: 100%;
        object-fit: cover;
      }

      .entry-detail-file-name {
        color: var(--text);
        font-size: 14px;
        font-weight: 700;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .entry-detail-file-summary {
        margin-top: 4px;
        color: var(--text-secondary);
        font-size: 11px;
      }

      .entry-detail-file-actions {
        display: flex;
        gap: 8px;
        align-items: center;
      }

      .entry-detail-toggle-btn,
      .entry-detail-mark-btn {
        height: 30px;
        padding: 0 10px;
        border-radius: 8px;
        border: 1px solid var(--border);
        background: rgba(255,255,255,0.04);
        color: var(--text-secondary);
        font-size: 11px;
        font-weight: 700;
        cursor: pointer;
      }

      .entry-detail-toggle-btn.selected {
        color: var(--accent);
        border-color: rgba(110, 231, 200, 0.35);
        background: rgba(110, 231, 200, 0.12);
      }

      .entry-detail-toggle-btn.danger {
        color: #ffb0b0;
        border-color: rgba(245, 144, 144, 0.35);
        background: rgba(245, 144, 144, 0.12);
      }

      .entry-detail-toggle-btn:disabled {
        opacity: 0.45;
        cursor: not-allowed;
      }

      .entry-detail-mark-btn {
        color: var(--state-done);
        border-color: color-mix(in srgb, var(--state-done) 38%, transparent);
        background: color-mix(in srgb, var(--state-done) 16%, transparent);
      }

      .entry-detail-mark-btn.disabled {
        opacity: 0.45;
        cursor: not-allowed;
      }

      .entry-detail-plate-list {
        display: grid;
      }

      .entry-detail-plate-row {
        display: grid;
        grid-template-columns: auto 1fr auto auto;
        gap: 10px;
        align-items: center;
        padding: 8px 12px;
        border-top: 1px solid rgba(148, 163, 184, 0.08);
      }

      .entry-detail-plate-row.selected {
        background: rgba(110, 231, 200, 0.05);
      }

      .entry-detail-plate-checkbox {
        width: 14px;
        height: 14px;
        accent-color: var(--accent);
      }

      .entry-detail-plate-name {
        color: var(--text);
        font-size: 12px;
      }

      .entry-detail-plate-state {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 3px 8px;
        border-radius: 999px;
        border: 1px solid var(--border);
        font-size: 10px;
        font-weight: 700;
        text-transform: uppercase;
      }

      .entry-detail-plate-state.done {
        color: var(--state-done);
        border-color: color-mix(in srgb, var(--state-done) 38%, transparent);
        background: color-mix(in srgb, var(--state-done) 16%, transparent);
      }

      .entry-detail-plate-state.pending {
        color: var(--state-in-progress);
        border-color: color-mix(in srgb, var(--state-in-progress) 38%, transparent);
        background: color-mix(in srgb, var(--state-in-progress) 14%, transparent);
      }

      .entry-detail-plate-state.skipped {
        color: var(--text-muted);
        border-color: rgba(148, 163, 184, 0.2);
        background: rgba(255,255,255,0.03);
      }

      .entry-detail-mark-placeholder {
        display: block;
        width: 74px;
        height: 1px;
      }

      .entry-detail-info-grid {
        margin-bottom: 2px;
      }

      .entry-detail-notes {
        width: 100%;
        min-height: 96px;
        padding: 10px 12px;
        resize: vertical;
        font: inherit;
      }

      .entry-detail-footer-left {
        margin-right: auto;
      }

      .detail-file-card {
        border: 1px solid var(--border);
        border-radius: 10px;
        background: rgba(255,255,255,0.015);
        display: grid;
        grid-template-columns: 88px 1fr;
        gap: 10px;
        padding: 8px;
      }

      .detail-file-thumb {
        width: 88px;
        height: 88px;
        border-radius: 8px;
        border: 1px solid var(--border);
        overflow: hidden;
        background: rgba(255,255,255,0.03);
        display: grid;
        place-items: center;
      }

      .detail-file-thumb img {
        width: 100%;
        height: 100%;
        object-fit: cover;
      }

      .detail-file-thumb.empty {
        color: var(--text-muted);
        font-size: 11px;
      }

      .detail-file-main {
        min-width: 0;
      }

      .detail-file-header {
        display: flex;
        justify-content: space-between;
        gap: 8px;
        align-items: center;
      }

      .detail-file-name {
        color: var(--text);
        font-size: 12px;
        font-weight: 700;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .detail-file-state {
        border-radius: 999px;
        border: 1px solid var(--border);
        padding: 2px 8px;
        font-size: 10px;
        font-weight: 700;
        text-transform: uppercase;
      }

      .detail-file-state.selected {
        color: var(--accent);
        border-color: rgba(110, 231, 200, 0.35);
        background: rgba(110, 231, 200, 0.12);
      }

      .detail-file-state.unselected {
        color: var(--text-muted);
      }

      .detail-file-summary {
        margin-top: 4px;
        color: var(--text-secondary);
        font-size: 11px;
      }

      .detail-plate-list {
        margin-top: 8px;
        display: grid;
        gap: 6px;
      }

      .detail-plate-row {
        display: flex;
        justify-content: space-between;
        gap: 8px;
        border-radius: 8px;
        padding: 6px 8px;
        border: 1px solid var(--border);
        font-size: 11px;
      }

      .detail-plate-row.selected {
        background: rgba(110, 231, 200, 0.08);
        border-color: rgba(110, 231, 200, 0.25);
      }

      .detail-plate-row.unselected {
        background: rgba(255,255,255,0.01);
        opacity: 0.75;
      }

      .detail-plate-name {
        color: var(--text);
      }

      .detail-plate-count {
        color: var(--text-secondary);
        font-weight: 700;
      }

      .archive-chip {
        border-radius: 999px;
        border: 1px solid rgba(124, 199, 255, 0.3);
        background: rgba(124, 199, 255, 0.12);
        color: var(--accent-blue);
        display: inline-flex;
        align-items: center;
        padding: 4px 10px;
        font-size: 12px;
        font-weight: 700;
      }

      .history-link {
        color: var(--accent-blue);
        font-size: 12px;
        font-weight: 700;
        text-decoration: none;
      }

      .history-link:hover,
      .history-link:focus-visible {
        text-decoration: underline;
      }

      @keyframes slideInRight {
        from {
          transform: translateX(28px);
          opacity: 0;
        }
        to {
          transform: translateX(0);
          opacity: 1;
        }
      }

      .planner-drawer {
        width: min(640px, 96vw);
        height: 100vh;
        background: rgba(22, 29, 40, 0.99);
        border-left: 1px solid var(--border-strong);
        box-shadow: -16px 0 48px rgba(0, 0, 0, 0.35);
        display: grid;
        grid-template-rows: auto 1fr auto;
        animation: slideInRight 180ms ease-out;
      }

      .planner-drawer-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 10px;
        padding: 14px 16px;
        border-bottom: 1px solid var(--border);
      }

      .planner-drawer-header h3 {
        margin: 0;
        color: var(--text);
        font-size: 16px;
      }

      .planner-drawer-subtitle {
        margin-top: 4px;
        color: var(--text-secondary);
        font-size: 12px;
      }

      .planner-drawer-body {
        padding: 14px 16px 16px;
        overflow-y: auto;
        display: grid;
        gap: 14px;
      }

      .planner-section {
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 12px;
        background: rgba(255,255,255,0.02);
      }

      .planner-section h4 {
        margin: 0 0 10px;
        color: var(--text);
        font-size: 13px;
      }

      .strategy-selector {
        display: grid;
        gap: 8px;
      }

      .strategy-radio {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px;
        border-radius: 8px;
        border: 1px solid var(--border);
        background: rgba(255,255,255,0.01);
        cursor: pointer;
        transition: all 0.15s;
      }

      .strategy-radio:hover {
        background: rgba(255,255,255,0.05);
        border-color: var(--border-strong);
      }

      .strategy-radio input[type="radio"] {
        cursor: pointer;
      }

      .strategy-radio input[type="radio"]:checked ~ span {
        color: var(--accent-blue);
        font-weight: 700;
      }

      .strategy-radio span {
        color: var(--text);
        font-size: 12px;
      }

      .planner-preview-list {
        list-style: decimal inside;
        display: grid;
        gap: 8px;
        margin: 0;
        padding: 0;
      }

      .planner-preview-item {
        display: flex;
        gap: 10px;
        align-items: flex-start;
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 8px;
        background: rgba(255,255,255,0.01);
      }

      .planner-rank {
        color: var(--text-muted);
        font-weight: 700;
        font-size: 11px;
        min-width: 20px;
        text-align: center;
      }

      .planner-item-main {
        flex: 1;
        min-width: 0;
      }

      .planner-item-title {
        color: var(--text);
        font-size: 12px;
        font-weight: 600;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .planner-item-reason {
        color: var(--text-secondary);
        font-size: 11px;
        margin-top: 4px;
      }

      .planner-history-list {
        list-style: none;
        display: grid;
        gap: 8px;
        margin: 0;
        padding: 0;
      }

      .planner-history-item {
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 8px;
        background: rgba(255,255,255,0.01);
      }

      .planner-history-time {
        color: var(--text-secondary);
        font-size: 10px;
        font-weight: 700;
        text-transform: uppercase;
      }

      .planner-history-details {
        display: flex;
        gap: 10px;
        margin-top: 4px;
        align-items: center;
      }

      .planner-history-strategy {
        color: var(--accent-blue);
        font-size: 11px;
        font-weight: 700;
      }

      .planner-history-count {
        color: var(--text-muted);
        font-size: 11px;
      }

      .planner-drawer-footer {
        display: flex;
        justify-content: space-between;
        gap: 8px;
        padding: 14px 16px;
        border-top: 1px solid var(--border);
      }

      .planner-drawer-footer .primary-btn {
        flex: 1;
      }

      .detail-row {
        display: grid;
        grid-template-columns: 120px 1fr;
        gap: 10px;
        align-items: start;
      }

      .detail-key {
        color: var(--text-muted);
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-weight: 700;
      }

      .detail-value {
        color: var(--text);
        font-size: 12px;
        word-break: break-word;
      }

      .add-modal-footer {
        display: flex;
        justify-content: flex-end;
        gap: 8px;
        padding: 14px 16px;
        border-top: 1px solid var(--border);
      }

      .ghost-btn,
      .primary-btn {
        height: 34px;
        padding: 0 12px;
        border-radius: 9px;
        border: 1px solid var(--border);
        font-size: 12px;
        font-weight: 700;
        cursor: pointer;
      }

      .ghost-btn {
        background: rgba(255,255,255,0.03);
        color: var(--text-secondary);
      }

      .primary-btn {
        background: rgba(110, 231, 200, 0.16);
        color: var(--accent);
        border-color: rgba(110, 231, 200, 0.35);
      }

      .primary-btn:disabled {
        opacity: 0.7;
        cursor: not-allowed;
      }

      /* ---------- New Toolbar (view switch + dropdown filters) ---------- */
      .toolbar {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 10px;
        padding: 10px 12px;
        background: var(--bg-card-alt);
        border: 1px solid var(--border);
        border-radius: 14px;
      }
      .toolbar-divider {
        width: 1px;
        align-self: stretch;
        background: var(--border);
        margin: 2px 2px;
      }
      .toolbar-spacer {
        flex: 1 1 auto;
        min-width: 8px;
      }
      .view-switch {
        display: inline-flex;
        background: rgba(255,255,255,0.04);
        border: 1px solid var(--border);
        border-radius: 999px;
        padding: 2px;
      }
      .view-switch button {
        appearance: none;
        background: transparent;
        border: 0;
        color: var(--text-secondary);
        padding: 6px 14px;
        font-size: 12px;
        font-weight: 700;
        border-radius: 999px;
        cursor: pointer;
        transition: background 0.15s, color 0.15s;
      }
      .view-switch button.active {
        background: rgba(124, 199, 255, 0.18);
        color: var(--accent-blue);
        box-shadow: inset 0 0 0 1px rgba(124, 199, 255, 0.35);
      }
      .dropdown {
        position: relative;
        font-size: 12px;
      }
      .dropdown > summary {
        list-style: none;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 7px 12px;
        border: 1px solid var(--border);
        border-radius: 10px;
        background: rgba(255,255,255,0.02);
        color: var(--text);
        user-select: none;
      }
      .dropdown > summary::-webkit-details-marker { display: none; }
      .dropdown > summary::after {
        content: '▾';
        margin-left: 4px;
        color: var(--text-muted);
      }
      .dropdown[open] > summary {
        border-color: var(--border-strong);
        background: rgba(124, 199, 255, 0.08);
      }
      .dropdown .dd-label {
        font-weight: 700;
        color: var(--text-secondary);
        text-transform: uppercase;
        font-size: 10px;
        letter-spacing: 0.06em;
      }
      .dropdown .dd-summary {
        color: var(--text);
        font-weight: 600;
      }
      .dropdown-menu {
        position: absolute;
        top: calc(100% + 6px);
        left: 0;
        z-index: 30;
        min-width: 220px;
        background: var(--bg-panel);
        border: 1px solid var(--border-strong);
        border-radius: 12px;
        box-shadow: 0 14px 40px rgba(0,0,0,0.45);
        padding: 8px;
        display: flex;
        flex-direction: column;
        gap: 2px;
      }
      .dropdown-menu .menu-actions {
        display: flex;
        gap: 6px;
        padding: 2px 4px 6px;
      }
      .dropdown-menu .menu-actions button {
        flex: 1;
        appearance: none;
        background: rgba(255,255,255,0.03);
        border: 1px solid var(--border);
        color: var(--text-secondary);
        font-size: 11px;
        font-weight: 700;
        padding: 5px 0;
        border-radius: 7px;
        cursor: pointer;
      }
      .dropdown-menu .menu-actions button:hover {
        color: var(--accent-blue);
        border-color: rgba(124,199,255,0.35);
      }
      .dropdown-menu .dd-divider {
        height: 1px;
        background: var(--border);
        margin: 4px 0;
      }
      .dropdown-menu .dd-row {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 6px 8px;
        border-radius: 7px;
        cursor: pointer;
        color: var(--text);
      }
      .dropdown-menu .dd-row:hover {
        background: rgba(255,255,255,0.04);
      }
      .dropdown-menu .dd-row input {
        accent-color: var(--accent-blue);
        margin: 0;
      }
      .dropdown-menu .dd-swatch {
        width: 12px;
        height: 12px;
        border-radius: 3px;
        flex: 0 0 auto;
        box-shadow: inset 0 0 0 1px rgba(0,0,0,0.25);
      }
      .dropdown-menu .dd-swatch.ghost {
        background: transparent;
        box-shadow: inset 0 0 0 1px var(--border);
      }

      /* ---------- ETA Hero KPI ---------- */
      .top-widget {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 10px;
      }
      .eta-bar {
        position: relative;
        height: 6px;
        border-radius: 999px;
        background: rgba(255,255,255,0.08);
        overflow: hidden;
        margin-top: 2px;
      }
      .eta-bar > span {
        display: block;
        height: 100%;
        background: linear-gradient(90deg, var(--accent-blue), var(--accent));
        border-radius: 999px;
        transition: width 0.4s ease;
      }

      /* ---------- Per-state palette + new card ---------- */
      .qcard {
        position: relative;
        background: var(--bg-card-alt);
        background-image:
          linear-gradient(180deg,
            color-mix(in srgb, var(--state, #9eacba) 11%, transparent),
            transparent 62%),
          linear-gradient(160deg,
            rgba(255,255,255,0.035),
            rgba(255,255,255,0.012) 44%,
            rgba(0,0,0,0.08)),
          linear-gradient(var(--bg-card-alt), var(--bg-card-alt));
        border: 1px solid var(--border);
        border-left: 3px solid var(--state, #9eacba);
        border-radius: 12px;
        padding: 10px 12px;
        display: flex;
        flex-direction: column;
        gap: 6px;
        cursor: default;
        box-shadow: 0 4px 14px rgba(0,0,0,0.20);
        transition: border-color 0.15s, transform 0.12s;
        contain: layout paint style;
      }
      .qcard[draggable="true"] {
        cursor: grab;
      }
      .qcard[draggable="true"]:active {
        cursor: grabbing;
      }
      .qcard:hover {
        border-color: var(--border-strong);
      }
      .qcard.dragging {
        opacity: 0.5;
        transform: scale(0.98);
      }
      .qcard.invalid-drop {
        border: 2px solid var(--accent-red, #f59090) !important;
        border-left: 4px solid var(--accent-red, #f59090) !important;
        background: linear-gradient(180deg,
          rgba(245, 144, 144, 0.22),
          rgba(245, 144, 144, 0.08)) !important;
        box-shadow: 0 0 0 3px rgba(245, 144, 144, 0.35),
                    0 0 18px rgba(245, 144, 144, 0.55);
        animation: qcard-shake 0.55s cubic-bezier(0.36, 0.07, 0.19, 0.97);
      }
      @keyframes qcard-shake {
        10%, 90% { transform: translateX(-2px); }
        20%, 80% { transform: translateX(4px); }
        30%, 50%, 70% { transform: translateX(-6px); }
        40%, 60% { transform: translateX(6px); }
      }
      .qcard-row1 {
        display: flex;
        align-items: center;
        gap: 6px;
        flex-wrap: wrap;
      }
      .qcard-drag {
        color: var(--text-muted);
        cursor: grab;
        font-size: 14px;
        line-height: 1;
        user-select: none;
        letter-spacing: -2px;
      }
      .qcard-rank {
        background: color-mix(in srgb, var(--state, #9eacba) 14%, transparent);
        color: var(--text);
        border: 1px solid color-mix(in srgb, var(--state, #9eacba) 30%, transparent);
        font-weight: 800;
        font-size: 11px;
        padding: 2px 7px;
        border-radius: 6px;
        min-width: 22px;
        text-align: center;
      }
      .qcard-title {
        font-weight: 700;
        font-size: 13px;
        color: var(--text);
        flex: 1;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .qcard-state-pill {
        background: color-mix(in srgb, var(--state) 14%, transparent);
        color: var(--state);
        border: 1px solid color-mix(in srgb, var(--state) 50%, transparent);
        font-size: 10px;
        font-weight: 800;
        text-transform: uppercase;
        padding: 2px 7px;
        border-radius: 999px;
        letter-spacing: 0.05em;
      }
      .qcard-row2 {
        display: flex;
        align-items: center;
        gap: 8px;
        min-width: 0;
      }
      .qcard-meta {
        display: flex;
        flex-wrap: wrap;
        gap: 4px 10px;
        font-size: 11px;
        color: color-mix(in srgb, var(--text) 72%, var(--text-secondary));
      }
      .qcard-meta-key {
        color: color-mix(in srgb, var(--text) 52%, var(--text-muted));
        font-weight: 700;
        text-transform: uppercase;
        font-size: 9px;
        letter-spacing: 0.05em;
      }
      .qcard-source-badge {
        font-size: 9px;
        font-weight: 800;
        letter-spacing: 0.06em;
        padding: 2px 7px;
        border-radius: 6px;
        text-transform: uppercase;
        flex: 0 0 auto;
      }
      .qcard-source-badge.catalog { background: rgba(124,199,255,0.18); color: #7cc7ff; }
      .qcard-source-badge.working { background: rgba(110,231,200,0.18); color: #6ee7c8; }
      .qcard-source-badge.idea    { background: rgba(242,195,91,0.18);  color: #f2c35b; }
      .qcard-block-reason {
        color: var(--accent-amber);
      }
      .qcard-plate-bar {
        display: flex;
        gap: 3px;
        flex: 1 1 auto;
      }
      .qcard-seg {
        flex: 1;
        height: 4px;
        border-radius: 2px;
        background: rgba(255,255,255,0.10);
      }
      .qcard-seg.done {
        background: var(--state, #9eacba);
      }
      .qcard-progress {
        display: flex;
        flex: 1 1 auto;
        align-items: center;
        gap: 8px;
        min-width: 0;
      }
      .qcard-remain {
        color: var(--text);
        font-weight: 700;
      }
      .qcard-total {
        color: color-mix(in srgb, var(--text) 46%, var(--text-muted));
        font-size: 11px;
      }
      .qcard-row3 {
        display: flex;
        align-items: center;
        gap: 10px;
        justify-content: space-between;
        flex-wrap: wrap;
      }
      .qcard-actions {
        display: flex;
        gap: 6px;
        align-items: center;
        margin-left: auto;
        flex: 0 0 auto;
      }
      .qcard-actions .entry-action-btn {
        flex: 0 0 auto;
        padding: 4px 9px;
        font-size: 11px;
        font-weight: 700;
        border-radius: 6px;
        border: 1px solid var(--border);
        background: rgba(255,255,255,0.03);
        color: var(--text-secondary);
        cursor: pointer;
      }
      .qcard-actions .entry-action-btn:hover {
        color: var(--text);
        border-color: var(--border-strong);
      }
      .qcard-actions .entry-action-btn.danger:hover {
        color: var(--accent-red);
        border-color: rgba(245,144,144,0.45);
      }

      /* ---------- Flat list view ---------- */
      .flat-list {
        display: flex;
        flex-direction: column;
        gap: 8px;
        flex: 1;
        min-height: 0;
      }
      .flat-list-hint {
        font-size: 11px;
        color: var(--text-secondary);
        padding: 4px 2px;
      }
      .flat-list-hint strong {
        color: var(--text);
      }
      .flat-list-body {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }

      /* ---------- Kanban view ---------- */
      .kanban-columns {
        display: grid;
        grid-auto-flow: column;
        grid-auto-columns: 280px;
        gap: 12px;
        overflow-x: auto;
        align-items: stretch;
        padding-bottom: 10px;
        scrollbar-gutter: stable;
        height: 100%;
      }
      .kanban-column {
        background: var(--bg-card-alt);
        background-image:
          linear-gradient(180deg,
            color-mix(in srgb, var(--state, #9eacba) 15%, transparent),
            transparent 72px),
          linear-gradient(var(--bg-card-alt), var(--bg-card-alt));
        border: 1px solid var(--border);
        border-top: 4px solid var(--state, #9eacba);
        border-radius: 12px;
        padding: 10px;
        display: flex;
        flex-direction: column;
        gap: 8px;
        min-height: 120px;
        flex: 1;
      }
      .kanban-column-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      .kanban-ttl {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        font-size: 13px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--text);
      }
      .kanban-dot {
        width: 11px;
        height: 11px;
        border-radius: 50%;
        background: var(--state, #9eacba);
        box-shadow:
          0 0 0 2px color-mix(in srgb, var(--state, #9eacba) 26%, rgba(0,0,0,0.14)),
          0 0 12px color-mix(in srgb, var(--state, #9eacba) 44%, transparent);
      }
      .kanban-count {
        background: rgba(255,255,255,0.06);
        color: color-mix(in srgb, var(--text) 64%, var(--text-secondary));
        padding: 2px 8px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 700;
      }
      .kanban-column-time {
        font-size: 11px;
        color: color-mix(in srgb, var(--text) 52%, var(--text-muted));
        text-transform: uppercase;
        letter-spacing: 0.05em;
      }
      .kanban-col-body {
        display: flex;
        flex-direction: column;
        gap: 8px;
        min-height: 50px;
        padding: 4px;
        border-radius: 8px;
        transition: background 0.15s;
        flex: 1;
      }
      .kanban-col-body.drop-target {
        background: color-mix(in srgb, var(--state, #9eacba) 18%, transparent);
        outline: 2px dashed color-mix(in srgb, var(--state, #9eacba) 60%, transparent);
        outline-offset: -3px;
      }
      .col-empty {
        text-align: center;
        font-size: 11px;
        color: var(--text-muted);
        padding: 18px 8px;
        border: 1px dashed var(--border);
        border-radius: 8px;
        background: rgba(255,255,255,0.02);
      }

      @media (max-width: 960px) {
        .filter-bar {
          grid-template-columns: 1fr;
        }

        .filter-buttons {
          width: 100%;
        }
      }

      @media (max-width: 760px) {
        .card-title {
          padding: 14px 16px;
        }

        .title-actions {
          gap: 6px;
        }

        .add-btn,
        .refresh-btn {
          padding: 6px 8px;
        }

        .content {
          padding: 14px;
          gap: 14px;
        }

        .add-controls {
          grid-template-columns: 1fr;
        }

        .load-detail-btn {
          width: 100%;
        }

        .modal-backdrop {
          padding: 8px;
        }

        .add-modal {
          max-height: calc(100vh - 16px);
        }

        .selection-grid {
          max-height: min(40vh, 320px);
        }

        .entry-detail-title-row,
        .entry-detail-meta-row {
          grid-template-columns: 1fr;
        }

        .entry-detail-state-select {
          min-width: 0;
          width: 100%;
        }

        .entry-detail-title-input {
          font-size: 20px;
        }

        .entry-detail-file-header {
          flex-direction: column;
          align-items: stretch;
        }

        .entry-detail-file-actions {
          justify-content: flex-end;
        }

        .entry-detail-plate-row {
          grid-template-columns: auto 1fr;
          gap: 8px;
        }

        .entry-detail-plate-state,
        .entry-detail-mark-btn,
        .entry-detail-mark-placeholder {
          justify-self: start;
          margin-left: 22px;
        }

        .filter-bar {
          grid-template-columns: 1fr;
          gap: 10px;
          padding: 10px;
        }

        .filter-buttons {
          width: 100%;
        }

        .top-widget {
          grid-template-columns: repeat(2, 1fr);
        }

        .entry-header {
          flex-direction: column;
        }

        .suggestion-card {
          flex-direction: column;
          align-items: flex-start;
        }

        .suggestion-actions {
          width: 100%;
        }

        .suggestion-btn {
          flex: 1;
        }

        .entry-badges {
          width: 100%;
        }

        .entry-meta {
          font-size: 11px;
        }

        .entry-actions {
          width: 100%;
          justify-content: space-between;
        }

        .entry-action-btn {
          flex: 1;
        }

        .source-ref-text {
          max-width: 150px;
        }

        .detail-row {
          grid-template-columns: 1fr;
          gap: 4px;
        }

        .detail-drawer {
          width: 100vw;
        }

        .detail-file-card {
          grid-template-columns: 1fr;
        }

        .detail-file-thumb {
          width: 100%;
          height: 140px;
        }
      }

      /* ---- Idea Create Dialog ---- */
      .idea-create-backdrop {
        position: fixed; inset: 0; z-index: 1000;
        background: rgba(0,0,0,0.55);
        display: flex; align-items: center; justify-content: center;
      }
      .idea-create-dialog {
        background: var(--card-background-color, #1e1e1e);
        border-radius: 12px; width: 440px; max-width: 94vw;
        box-shadow: 0 8px 32px rgba(0,0,0,0.5);
        display: flex; flex-direction: column; overflow: hidden;
      }
      .idea-create-header {
        padding: 20px 24px 8px; border-bottom: 1px solid var(--divider-color, #333);
      }
      .idea-create-header h3 { margin: 0 0 2px; font-size: 18px; }
      .idea-create-subtitle { font-size: 13px; color: var(--secondary-text-color, #aaa); }
      .idea-create-body { padding: 16px 24px; display: flex; flex-direction: column; gap: 14px; }
      .idea-create-field { display: flex; flex-direction: column; gap: 4px; }
      .idea-create-field span, .idea-create-field strong { font-size: 13px; color: var(--primary-text-color, #e0e0e0); }
      .idea-create-input {
        font-size: 14px; padding: 8px 10px; border-radius: 6px;
        border: 1px solid var(--divider-color, #444);
        background: var(--primary-background-color, #111);
        color: var(--primary-text-color, #e0e0e0);
        font-family: inherit; resize: vertical;
      }
      .idea-create-input:focus { outline: none; border-color: var(--primary-color, #03a9f4); }
      .idea-create-error { color: var(--error-color, #e53935); font-size: 13px; margin-top: 4px; }
      .idea-create-footer {
        padding: 12px 24px; border-top: 1px solid var(--divider-color, #333);
        display: flex; justify-content: flex-end; gap: 10px;
      }
      .idea-create-submit {
        background: var(--primary-color, #03a9f4); color: #fff; border: none;
        padding: 8px 18px; border-radius: 6px; cursor: pointer; font-size: 14px;
      }
      .idea-create-submit:disabled { opacity: 0.6; cursor: not-allowed; }
    `;

    const shouldShowBlockingLoading = this._loading && this._entries.length === 0;
    const shouldShowBlockingError = !!this._error && this._entries.length === 0;
    const content = shouldShowBlockingLoading
      ? '<div class="loading-state"><div class="loading-spinner"></div></div>'
      : shouldShowBlockingError
      ? `<div class="error-state"><strong>⚠ Error</strong>${this._escapeHtml(this._error)}</div>`
      : this._renderFlashBanner() + this._renderSuggestionCards() + this._renderTopWidget() + this._renderFilterControls() + this._renderQueueList();

    const html = `
      <style>${css}</style>
      <div class="shell">
        <div class="card-title">
          <h2>Print Queue</h2>
          <div class="title-actions">
            <div class="db-pill" title="Model catalog DB profile">
              <svg class="db-icon" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="currentColor" d="M12,3C7.58,3 4,4.79 4,7C4,9.21 7.58,11 12,11C16.42,11 20,9.21 20,7C20,4.79 16.42,3 12,3M4,9V12C4,14.21 7.58,16 12,16C16.42,16 20,14.21 20,12V9C20,11.21 16.42,13 12,13C7.58,13 4,11.21 4,9M4,14V17C4,19.21 7.58,21 12,21C16.42,21 20,19.21 20,17V14C20,16.21 16.42,18 12,18C7.58,18 4,16.21 4,14Z"/></svg>
              <span class="db-label">DB</span>
              <span class="db-state" id="db-profile-state">-</span>
            </div>
            <button class="planner-btn" data-action="open-planner" title="Open Queue Planner">📊 Planner</button>
            <button class="add-btn idea-add-btn" data-action="open-idea-create-dialog" title="Add a new idea">💡 Add Idea</button>
            <button class="add-btn" data-action="open-add">+ Add</button>
            <button class="refresh-btn ${this._loading ? 'loading' : ''}" data-action="refresh" ${this._loading ? 'disabled' : ''}>
              ${this._loading ? 'Loading...' : '🔄'}
            </button>
          </div>
        </div>
        <div class="content">
          ${content}
        </div>
      </div>
      ${this._renderAddModal()}
      ${this._renderIdeaCreateDialog()}
      ${this._renderEntryDetailModal()}
      ${this._renderPlannerDrawer()}
      ${this._renderDeleteConfirm()}
    `;

    this.shadowRoot.innerHTML = html;

    const refreshBtn = this.shadowRoot.querySelector('.refresh-btn');
    if (refreshBtn && !this._loading) {
      refreshBtn.addEventListener('click', () => this._loadQueueData());
    }

    // ---- View switch ----
    const viewBtns = this.shadowRoot.querySelectorAll('.view-switch button[data-view]');
    viewBtns.forEach(btn => {
      btn.addEventListener('click', () => this._setView(btn.dataset.view));
    });

    // ---- State multi-select dropdown (checkboxes) ----
    const stateChecks = this.shadowRoot.querySelectorAll('input[data-action="toggle-state"]');
    stateChecks.forEach(cb => {
      cb.addEventListener('change', () => this._toggleStateFilter(cb.dataset.state));
    });

    // Select all / Clear actions inside the states dropdown.
    const statesAllBtn = this.shadowRoot.querySelector('button[data-action="states-all"]');
    if (statesAllBtn) {
      statesAllBtn.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        this._filters.states = [...QUEUE_STATE_FILTER_ORDER];
        this._saveFilterState();
        this._render();
      });
    }
    const statesNoneBtn = this.shadowRoot.querySelector('button[data-action="states-none"]');
    if (statesNoneBtn) {
      statesNoneBtn.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        this._filters.states = [];
        this._saveFilterState();
        this._render();
      });
    }

    // ---- Source single-select dropdown (radios) ----
    const sourceRadios = this.shadowRoot.querySelectorAll('input[data-action="set-source"]');
    sourceRadios.forEach(r => {
      r.addEventListener('change', () => {
        const value = r.dataset.source;
        if (value === 'all') {
          this._filters.sources = [];
        } else if (value === 'working_files') {
          this._filters.sources = ['working_group', 'working_file'];
        } else {
          this._filters.sources = [value];
        }
        this._saveFilterState();
        this._render();
      });
    });

    // ---- Outside-click closes open dropdowns (within shadow root) ----
    this.shadowRoot.addEventListener('click', (ev) => {
      const path = ev.composedPath();
      this.shadowRoot.querySelectorAll('details.dropdown[open]').forEach(d => {
        if (!path.includes(d)) d.open = false;
      });
    });

    // ---- Sort select ----
    const sortDropdown = this.shadowRoot.querySelector('.sort-dropdown');
    if (sortDropdown) {
      sortDropdown.addEventListener('change', (e) => {
        this._setSortOrder(e.target.value);
      });
    }

    const clearBtn = this.shadowRoot.querySelector('.clear-filters-btn');
    if (clearBtn) {
      clearBtn.addEventListener('click', () => this._clearAllFilters());
    }

    const searchInput = this.shadowRoot.querySelector('.search-input');
    if (searchInput) {
      // Restore focus + caret after re-render triggered by typing.
      if (this._restoreSearchFocus) {
        this._restoreSearchFocus = false;
        searchInput.focus();
        const len = searchInput.value.length;
        try { searchInput.setSelectionRange(len, len); } catch (_) { /* ignore */ }
      }
      let searchDebounce = null;
      searchInput.addEventListener('input', (ev) => {
        const value = ev.target.value;
        if (searchDebounce) clearTimeout(searchDebounce);
        searchDebounce = setTimeout(() => {
          this._setSearchQuery(value);
        }, 200);
      });
      searchInput.addEventListener('keydown', (ev) => {
        if (ev.key === 'Escape') {
          ev.target.value = '';
          this._setSearchQuery('');
        }
      });
    }

    const searchClearBtn = this.shadowRoot.querySelector('.search-clear');
    if (searchClearBtn) {
      searchClearBtn.addEventListener('click', () => this._setSearchQuery(''));
    }

    // ---- DnD wiring (list reorder + kanban state moves) ----
    this._attachListReorderDnD();
    this._attachKanbanDnD();

    // ---- DB pill update ----
    this._updateDbPill();

    const dbPill = this.shadowRoot.querySelector('.db-pill');
    if (dbPill) {
      dbPill.addEventListener('click', () => {
        if (this._hass) {
          this._hass.callService('input_select', 'open_help', {
            entity_id: 'input_select.model_catalog_db_profile_target'
          }).catch(() => {
            // Fallback: just open more-info
            this._hass.callService('frontend', 'set_state', {
              state: 'more-info/input_select.model_catalog_db_profile_target'
            });
          });
        }
      });
    }

    const addBtn = this.shadowRoot.querySelector('.add-btn:not(.idea-add-btn)');
    if (addBtn) {
      addBtn.addEventListener('click', () => this._openAddModal());
    }

    // ---- Idea Create Dialog listeners ----
    const ideaAddBtn = this.shadowRoot.querySelector('.idea-add-btn');
    if (ideaAddBtn) {
      ideaAddBtn.addEventListener('click', () => this._openIdeaCreateDialog());
    }

    const ideaBackdrop = this.shadowRoot.querySelector('.idea-create-backdrop');
    if (ideaBackdrop) {
      ideaBackdrop.addEventListener('click', (event) => {
        if (event.target === ideaBackdrop) {
          this._closeIdeaCreateDialog();
        }
      });
    }

    const ideaCloseBtn = this.shadowRoot.querySelector('.idea-create-dialog [data-action="close-idea-create-dialog"]');
    if (ideaCloseBtn) {
      ideaCloseBtn.addEventListener('click', () => this._closeIdeaCreateDialog());
    }

    const ideaSubmitBtn = this.shadowRoot.querySelector('[data-action="submit-idea-create-dialog"]');
    if (ideaSubmitBtn) {
      ideaSubmitBtn.addEventListener('click', () => this._submitIdeaCreateDialog());
    }

    const ideaInputs = this.shadowRoot.querySelectorAll('.idea-create-input');
    ideaInputs.forEach(input => {
      input.addEventListener('input', (event) => {
        const field = String(event.target.getAttribute('data-idea-field') || '').trim();
        if (field && Object.prototype.hasOwnProperty.call(this._ideaCreateDraft, field)) {
          this._ideaCreateDraft[field] = String(event.target.value || '');
        }
        if (this._ideaCreateError) {
          this._ideaCreateError = '';
        }
      });
      const tag = String(input.tagName || '').toUpperCase();
      if (tag !== 'TEXTAREA') {
        input.addEventListener('keydown', (event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            this._submitIdeaCreateDialog();
          }
        });
      }
    });

    const modalBackdrop = this.shadowRoot.querySelector('.add-backdrop');
    if (modalBackdrop) {
      modalBackdrop.addEventListener('click', (event) => {
        if (event.target === modalBackdrop) {
          this._closeAddModal();
        }
      });
    }

    const addModal = this.shadowRoot.querySelector('.add-modal');
    if (addModal) {
      addModal.addEventListener('click', (event) => {
        event.stopPropagation();
      });
    }

    const modalCloseBtns = this.shadowRoot.querySelectorAll('[data-action="close-add"]');
    modalCloseBtns.forEach(button => {
      button.addEventListener('click', () => this._closeAddModal());
    });

    const editBackdrop = this.shadowRoot.querySelector('[data-action="close-edit"].modal-backdrop');
    if (editBackdrop) {
      editBackdrop.addEventListener('click', (event) => {
        if (event.target === editBackdrop) {
          this._closeEditModal();
        }
      });
    }

    const editCloseBtns = this.shadowRoot.querySelectorAll('[data-action="close-edit"]:not(.modal-backdrop)');
    editCloseBtns.forEach(button => {
      button.addEventListener('click', () => this._closeEditModal());
    });

    const editTitleInput = this.shadowRoot.querySelector('.edit-title-input');
    if (editTitleInput) {
      editTitleInput.addEventListener('input', (event) => {
        this._setEditTitle(event.target.value);
      });
    }

    const editCopiesInput = this.shadowRoot.querySelector('.edit-copies-input');
    if (editCopiesInput) {
      editCopiesInput.addEventListener('input', (event) => {
        this._setEditCopies(event.target.value);
      });
    }

    const submitEditBtn = this.shadowRoot.querySelector('[data-action="submit-edit"]');
    if (submitEditBtn) {
      submitEditBtn.addEventListener('click', () => this._submitEditModal());
    }

    const addTabBtns = this.shadowRoot.querySelectorAll('[data-action="add-tab"]');
    addTabBtns.forEach(button => {
      button.addEventListener('click', () => {
        this._setAddTab(button.dataset.tab);
      });
    });

    const sourceKindSelect = this.shadowRoot.querySelector('.add-source-kind');
    if (sourceKindSelect) {
      sourceKindSelect.addEventListener('change', (event) => {
        this._setAddSourceKind(event.target.value);
      });
    }

    const sourceSelect = this.shadowRoot.querySelector('.add-source-select');
    if (sourceSelect) {
      sourceSelect.addEventListener('change', (event) => {
        this._setAddSourceId(event.target.value);
      });
    }

    const addIdeaTitle = this.shadowRoot.querySelector('.add-idea-title');
    if (addIdeaTitle) {
      addIdeaTitle.addEventListener('input', (event) => {
        this._setAddIdeaTitle(event.target.value);
      });
    }

    const addIdeaNotes = this.shadowRoot.querySelector('.add-idea-notes');
    if (addIdeaNotes) {
      addIdeaNotes.addEventListener('input', (event) => {
        this._setAddIdeaNotes(event.target.value);
      });
    }

    const loadDetailBtn = this.shadowRoot.querySelector('[data-action="load-add-detail"]');
    if (loadDetailBtn) {
      loadDetailBtn.addEventListener('click', () => this._loadAddSourceDetail());
    }

    const submitAddBtn = this.shadowRoot.querySelector('[data-action="submit-add"]');
    if (submitAddBtn) {
      submitAddBtn.addEventListener('click', () => this._submitAddToQueue());
    }

    const fileCheckboxes = this.shadowRoot.querySelectorAll('.file-checkbox');
    fileCheckboxes.forEach(checkbox => {
      checkbox.addEventListener('change', (event) => {
        this._toggleAddFileSelection(event.target.dataset.fileId);
      });
    });

    const plateCheckboxes = this.shadowRoot.querySelectorAll('.plate-checkbox');
    plateCheckboxes.forEach(checkbox => {
      checkbox.addEventListener('change', (event) => {
        this._toggleAddPlateSelection(event.target.dataset.fileId, event.target.dataset.plateId);
      });
    });

    const detailBackdrop = this.shadowRoot.querySelector('[data-action="close-detail"].modal-backdrop');
    if (detailBackdrop) {
      detailBackdrop.addEventListener('click', (event) => {
        if (event.target === detailBackdrop) {
          this._closeEntryDetail();
        }
      });
    }

    const detailCloseBtns = this.shadowRoot.querySelectorAll('[data-action="close-detail"]:not(.modal-backdrop)');
    detailCloseBtns.forEach(button => {
      button.addEventListener('click', () => this._closeEntryDetail());
    });

    const detailTabBtns = this.shadowRoot.querySelectorAll('[data-action="detail-tab"]');
    detailTabBtns.forEach(button => {
      button.addEventListener('click', () => {
        this._setDetailTab(button.dataset.tab);
      });
    });

    const detailTitleInput = this.shadowRoot.querySelector('.entry-detail-title-input');
    if (detailTitleInput) {
      detailTitleInput.addEventListener('input', (event) => {
        this._setDetailTitle(event.target.value);
      });
    }

    const detailCopiesInput = this.shadowRoot.querySelector('.entry-detail-copies-input');
    if (detailCopiesInput) {
      detailCopiesInput.addEventListener('input', (event) => {
        this._setDetailCopies(event.target.value);
      });
    }

    const detailStateSelect = this.shadowRoot.querySelector('[data-action="detail-state"]');
    if (detailStateSelect) {
      detailStateSelect.addEventListener('change', (event) => {
        this._setDetailState(event.target.value);
      });
    }

    const detailNotes = this.shadowRoot.querySelector('[data-action="detail-notes"]');
    if (detailNotes) {
      detailNotes.addEventListener('input', (event) => {
        this._setDetailNotes(event.target.value);
      });
    }

    const detailFileSelectAllButtons = this.shadowRoot.querySelectorAll('[data-action="detail-file-select-all"]');
    detailFileSelectAllButtons.forEach(button => {
      button.addEventListener('click', () => {
        this._selectAllDetailFilePlates(button.dataset.fileUnitId);
      });
    });

    const detailFileClearPendingButtons = this.shadowRoot.querySelectorAll('[data-action="detail-file-clear-pending"]');
    detailFileClearPendingButtons.forEach(button => {
      button.addEventListener('click', () => {
        this._clearDetailFilePendingSelections(button.dataset.fileUnitId);
      });
    });

    const detailPlateCheckboxes = this.shadowRoot.querySelectorAll('.entry-detail-plate-checkbox');
    detailPlateCheckboxes.forEach(checkbox => {
      checkbox.addEventListener('change', (event) => {
        this._toggleDetailPlateSelection(event.target.dataset.fileUnitId, event.target.dataset.plateUnitId);
      });
    });

    const detailMarkBtns = this.shadowRoot.querySelectorAll('[data-action="mark-detail-plate-done"]');
    detailMarkBtns.forEach(button => {
      button.addEventListener('click', () => {
        this._markDetailPlateDone(button.dataset.fileUnitId, button.dataset.plateUnitId);
      });
    });

    const submitDetailBtn = this.shadowRoot.querySelector('[data-action="submit-detail"]');
    if (submitDetailBtn) {
      submitDetailBtn.addEventListener('click', () => this._submitDetailModal());
    }

    const graduateWorkingBtn = this.shadowRoot.querySelector('[data-action="graduate-idea-working"]');
    if (graduateWorkingBtn) {
      graduateWorkingBtn.addEventListener('click', () => this._graduateIdeaToWorkingGroup());
    }

    const graduateCatalogBtn = this.shadowRoot.querySelector('[data-action="graduate-idea-catalog"]');
    if (graduateCatalogBtn) {
      graduateCatalogBtn.addEventListener('click', () => this._graduateIdeaToCatalog());
    }

    const plannerBtn = this.shadowRoot.querySelector('.planner-btn');
    if (plannerBtn) {
      plannerBtn.addEventListener('click', () => this._openPlannerDrawer());
    }

    const plannerBackdrop = this.shadowRoot.querySelector('[data-action="close-planner"].modal-backdrop');
    if (plannerBackdrop) {
      plannerBackdrop.addEventListener('click', (event) => {
        if (event.target === plannerBackdrop) {
          this._closePlannerDrawer();
        }
      });
    }

    const plannerCloseBtns = this.shadowRoot.querySelectorAll('[data-action="close-planner"]:not(.modal-backdrop)');
    plannerCloseBtns.forEach(button => {
      button.addEventListener('click', () => this._closePlannerDrawer());
    });

    const strategyRadios = this.shadowRoot.querySelectorAll('input[name="planner-strategy"]');
    strategyRadios.forEach(radio => {
      radio.addEventListener('change', (e) => {
        this._setPlannerStrategy(e.target.value);
      });
    });

    const applyPlanBtn = this.shadowRoot.querySelector('[data-action="apply-plan"]');
    if (applyPlanBtn) {
      applyPlanBtn.addEventListener('click', () => this._applyPlannedOrder());
    }

    const undoPlanBtn = this.shadowRoot.querySelector('[data-action="undo-plan"]');
    if (undoPlanBtn) {
      undoPlanBtn.addEventListener('click', () => this._undoLastPlannerOp());
    }

    const suggestionActionBtns = this.shadowRoot.querySelectorAll('.suggestion-btn');
    suggestionActionBtns.forEach(button => {
      button.addEventListener('click', async (event) => {
        const action = event.currentTarget.dataset.action;
        const suggestionId = event.currentTarget.dataset.suggestionId;
        if (!action || !suggestionId) return;

        if (action === 'suggestion-accept') {
          await this._acceptSuggestion(suggestionId, event.currentTarget.dataset.entryId);
        } else if (action === 'suggestion-reject') {
          await this._rejectSuggestion(suggestionId);
        }
      });
    });

    const entryActionButtons = this.shadowRoot.querySelectorAll('.entry-action-btn');
    entryActionButtons.forEach(button => {
      button.disabled = this._rowActionBusy;
      button.addEventListener('click', async (event) => {
        const action = event.currentTarget.dataset.action;
        const entryId = event.currentTarget.dataset.entryId;
        if (!entryId || !action) return;
        if (this._rowActionBusy) return;

        if (action === 'entry-detail') {
          const entry = this._getEntryById(entryId);
          const tab = entry && entry.source_kind === 'idea' ? 'info' : 'plates';
          this._openEntryDetail(entryId, tab);
        } else if (action === 'entry-edit') {
          await this._editEntry(entryId);
        } else if (action === 'entry-delete') {
          this._requestEntryDelete(entryId);
        }
      });
    });

    // Delete-confirm modal wiring.
    const delConfirmBackdrop = this.shadowRoot.querySelector('.delete-confirm-backdrop');
    if (delConfirmBackdrop) {
      delConfirmBackdrop.addEventListener('click', () => this._dismissPendingDelete());
    }
    const delCancelBtn = this.shadowRoot.querySelector('[data-action="delete-confirm-cancel"]');
    if (delCancelBtn) {
      delCancelBtn.addEventListener('click', () => this._dismissPendingDelete());
    }
    const delAcceptBtn = this.shadowRoot.querySelector('[data-action="delete-confirm-accept"]');
    if (delAcceptBtn) {
      delAcceptBtn.addEventListener('click', () => this._confirmPendingDelete());
    }
  }

  getCardSize() {
    return 10;
  }
}

customElements.define('unified-queue-board-card', UnifiedQueueBoardCard);
