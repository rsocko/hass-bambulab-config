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
    this.printerId = 'p1';
    this._entries = [];
    this._loading = false;
    this._error = null;
    this._refreshTimer = null;
    this._flashTimer = null;
    this._flashMessage = null;
    
    // Filter state
    this._filters = {
      states: ['todo', 'ready', 'started', 'blocked'],  // Default: exclude idea, done
      sources: [],  // Empty = all sources
      sort: 'rank',  // Default: sort by rank
    };

    this._addModalOpen = false;
    this._addTab = 'quick';
    this._addSourceKind = 'catalog_model';
    this._addSourceId = '';
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

    this._loadFilterState();
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
  }

  _saveFilterState() {
    try {
      localStorage.setItem(`uq-filters-${this.printerId}`, JSON.stringify(this._filters));
    } catch (e) {
      console.warn('Failed to save filter state:', e);
    }
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
    if (this._filters.sources.includes(source)) {
      this._filters.sources = this._filters.sources.filter(s => s !== source);
    } else {
      this._filters.sources.push(source);
    }
    this._saveFilterState();
    this._render();
  }

  _setSortOrder(sort) {
    this._filters.sort = sort;
    this._saveFilterState();
    this._render();
  }

  _clearAllFilters() {
    this._filters = {
      states: ['todo', 'ready', 'started', 'blocked'],
      sources: [],
      sort: 'rank',
    };
    this._saveFilterState();
    this._render();
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
        `${this._getQueueApiBase()}/queues/${this.printerId}/entries`,
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
      await this._loadMediumConfidenceSuggestions();
    } catch (err) {
      console.error('Failed to load queue:', err);
      this._error = `Failed to load queue: ${err.message}`;
      this._entries = [];
      this._suggestions = [];
      this._suggestionsError = null;
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

    if (this._flashTimer) {
      clearTimeout(this._flashTimer);
      this._flashTimer = null;
    }
  }

  _getQueueApiBase() {
    return 'http://model-catalog.socko.us/api/v1';
  }

  _getCatalogApiBase() {
    return 'http://model-catalog.socko.us/api';
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

  _setFlashMessage(message, type = 'success') {
    this._flashMessage = { message, type };
    if (this._flashTimer) {
      clearTimeout(this._flashTimer);
    }
    this._flashTimer = setTimeout(() => {
      this._flashMessage = null;
      this._flashTimer = null;
      this._render();
    }, 4000);
    this._render();
  }

  _openAddModal() {
    this._addModalOpen = true;
    this._addTab = 'quick';
    this._addSourceKind = 'catalog_model';
    this._addSourceId = '';
    this._addDetailError = null;
    this._addDetailFiles = [];
    this._render();
    this._loadAddSourceOptions();
  }

  _closeAddModal() {
    this._addModalOpen = false;
    this._addSubmitting = false;
    this._addLoadingDetail = false;
    this._addDetailError = null;
    this._render();
  }

  async _loadAddSourceOptions() {
    this._addLoadingSources = true;
    this._render();

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
    return this._addSourceOptions[this._addSourceKind] || [];
  }

  _getAddSourceOption(value) {
    const normalized = String(value || '').trim();
    if (!normalized) return null;
    return this._getActiveAddOptions().find(option => option.value === normalized) || null;
  }

  async _loadAddSourceDetail() {
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
    if (sourceKind !== 'catalog_model' && sourceKind !== 'working_group') {
      return;
    }

    this._addSourceKind = sourceKind;
    this._addSourceId = '';
    this._addDetailError = null;
    this._addDetailFiles = [];
    this._render();
  }

  _setAddSourceId(sourceId) {
    this._addSourceId = String(sourceId || '').trim();
    this._addDetailError = null;
    this._addDetailFiles = [];
    this._render();
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

  async _submitAddToQueue() {
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

    this._addSubmitting = true;
    this._addDetailError = null;
    this._render();

    try {
      const payload = {
        source_kind: this._addSourceKind,
        source_id: sourceId,
      };

      if (this._addTab === 'quick') {
        payload.quick_add = true;
      } else {
        payload.selection_mode = 'selected_plates';
        payload.selected_files = this._buildAdvancedSelectedFilesPayload();
      }

      const response = await fetch(
        `${this._getQueueApiBase()}/queues/${encodeURIComponent(this.printerId)}/add`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
        }
      );

      const responseBody = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(responseBody.message || responseBody.error || `Queue add failed (${response.status})`));
      }

      this._closeAddModal();
      this._setFlashMessage('Queue entry created successfully.', 'success');
      await this._loadQueueData();
      // Reveal any entry states that are now in the queue but not in the active filter,
      // so the newly-added entry is immediately visible.
      const knownStates = new Set(this._entries.map(e => String(e.state || '').trim()).filter(Boolean));
      let filterChanged = false;
      for (const s of knownStates) {
        if (!this._filters.states.includes(s)) {
          this._filters.states = [...this._filters.states, s];
          filterChanged = true;
        }
      }
      if (filterChanged) {
        this._saveFilterState();
        this._render();
      }
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
      working_group: { icon: 'WRK', label: 'Working Group' },
      working_file: { icon: 'FIL', label: 'Working File' },
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

  async _deleteEntry(queueEntryId) {
    const entry = this._getEntryById(queueEntryId);
    const label = entry ? (entry.title || queueEntryId) : queueEntryId;
    if (!window.confirm(`Delete queue entry '${label}'?`)) {
      return;
    }

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
    const entry = this._getEntryById(queueEntryId);
    if (!entry) return;

    this._editModalOpen = true;
    this._editEntryId = queueEntryId;
    this._editTitle = String(entry.title || '').trim();
    this._editCopies = Number.isFinite(entry.copies_requested) ? entry.copies_requested : 1;
    this._editSubmitting = false;
    this._editError = null;
    this._render();
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
    this._openEditModal(queueEntryId);
  }

  _openEntryDetail(queueEntryId) {
    const entry = this._getEntryById(queueEntryId);
    if (!entry) return;
    this._detailEntry = entry;
    this._detailLoading = true;
    this._detailError = null;
    this._detailFiles = [];
    this._render();
    this._loadEntryDetailFiles(entry);
  }

  _closeEntryDetail() {
    this._detailEntry = null;
    this._detailLoading = false;
    this._detailError = null;
    this._detailFiles = [];
    this._render();
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
      const sourceId = String(entry.source_id || entry.source_ref || '').trim();
      if (!sourceId || (entry.source_kind !== 'catalog_model' && entry.source_kind !== 'working_group')) {
        this._detailFiles = [];
        this._detailError = null;
      } else {
        const rawFiles = entry.source_kind === 'catalog_model'
          ? await this._loadCatalogSourceDetail(sourceId)
          : await this._loadWorkingGroupSourceDetail(sourceId);
        this._detailFiles = this._normalizeDetailFiles(rawFiles, entry);
        this._detailError = null;
      }
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
    // Apply filters
    let filtered = this._entries.filter(entry => {
      // State filter
      if (this._filters.states.length > 0 && !this._filters.states.includes(entry.state)) {
        return false;
      }
      // Source filter
      if (this._filters.sources.length > 0 && !this._filters.sources.includes(entry.source_kind)) {
        return false;
      }
      return true;
    });

    // Apply sorting
    const sorted = [...filtered].sort((a, b) => {
      switch (this._filters.sort) {
        case 'rank':
          return (a.rank || 999) - (b.rank || 999);
        case 'rank-desc':
          return (b.rank || 999) - (a.rank || 999);
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

  _renderFilterControls() {
    const hasActiveFilters = 
      this._filters.states.length !== 4 || 
      this._filters.sources.length > 0 || 
      this._filters.sort !== 'rank';

    return `
      <div class="filter-bar">
        <div class="filter-section">
          <div class="filter-label">State</div>
          <div class="filter-buttons">
            ${this._renderStateFilterButtons()}
          </div>
        </div>
        
        <div class="filter-section">
          <div class="filter-label">Source</div>
          <div class="filter-buttons">
            ${this._renderSourceFilterButtons()}
          </div>
        </div>
        
        <div class="filter-section">
          <div class="filter-label">Sort By</div>
          <select class="sort-dropdown" data-action="sort">
            <option value="rank" ${this._filters.sort === 'rank' ? 'selected' : ''}>Rank (A-Z)</option>
            <option value="rank-desc" ${this._filters.sort === 'rank-desc' ? 'selected' : ''}>Rank (Z-A)</option>
            <option value="duration" ${this._filters.sort === 'duration' ? 'selected' : ''}>Duration (Short→Long)</option>
            <option value="duration-desc" ${this._filters.sort === 'duration-desc' ? 'selected' : ''}>Duration (Long→Short)</option>
            <option value="recently-added" ${this._filters.sort === 'recently-added' ? 'selected' : ''}>Recently Added</option>
          </select>
        </div>
        
        ${hasActiveFilters ? `<button class="clear-filters-btn" data-action="clear">Clear All</button>` : ''}
      </div>
    `;
  }

  _renderStateFilterButtons() {
    const states = ['todo', 'ready', 'started', 'blocked', 'done', 'idea'];
    return states.map(state => `
      <button 
        class="filter-btn ${this._filters.states.includes(state) ? 'active' : ''}"
        data-action="toggle-state"
        data-state="${state}"
        title="Toggle ${state} filter"
      >
        ${this._getStateLabel(state)}
      </button>
    `).join('');
  }

  _renderSourceFilterButtons() {
    const sources = ['catalog_model', 'working_group', 'working_file', 'idea'];
    const labels = {
      'catalog_model': 'Catalog',
      'working_group': 'Working',
      'working_file': 'File',
      'idea': 'Ideas',
    };
    return sources.map(source => `
      <button 
        class="filter-btn ${this._filters.sources.includes(source) ? 'active' : ''}"
        data-action="toggle-source"
        data-source="${source}"
        title="Toggle ${labels[source]} filter"
      >
        ${labels[source]}
      </button>
    `).join('');
  }

  _getStateLabel(state) {
    const labels = {
      'idea': 'Ideas',
      'todo': 'To Do',
      'ready': 'Ready',
      'started': 'Started',
      'done': 'Done',
      'blocked': 'Blocked',
    };
    return labels[state] || state;
  }

  _renderQueueList() {
    const entries = this._getFilteredAndSortedEntries();

    if (entries.length === 0) {
      const hasFilters = this._filters.states.length !== 4 || this._filters.sources.length > 0;
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

    const grouped = this._groupEntriesByState(entries);
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

  _groupEntriesByState(entries = this._entries) {
    const grouped = {};
    for (const entry of entries) {
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
    const sourceMeta = this._getSourceMeta(entry);
    const sourceLabel = entry.source_kind.replace(/_/g, ' ').toUpperCase();
    const copiesRequested = Number.isFinite(entry.copies_requested) ? entry.copies_requested : 1;
    const fullInfo = [
      `Title: ${entry.title || 'Untitled'}`,
      `Source: ${sourceMeta.fullLabel}`,
      `State: ${entry.state || 'unknown'}`,
      `Rank: ${Number.isFinite(entry.rank) ? entry.rank : 'n/a'}`,
      `Copies: ${copiesRequested}`,
      `Duration: ${durationStr}`,
    ].join(' | ');

    return `
      <div class="queue-entry" data-entry-id="${entry.queue_entry_id}" title="${this._escapeHtml(fullInfo)}">
        <div class="entry-header">
          <div class="entry-title">
            <span class="entry-rank">${entry.rank || '—'}</span>
            <div class="entry-title-block">
              <span class="entry-name">${this._escapeHtml(entry.title)}</span>
              <span class="source-ref" title="${this._escapeHtml(sourceMeta.fullLabel)}">
                <span class="source-icon-pill">${sourceMeta.icon}</span>
                <span class="source-ref-text">${this._escapeHtml(sourceMeta.sourceId)}</span>
              </span>
            </div>
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
          <span class="meta-item"># ${copiesRequested} copies</span>
          <span class="meta-item">⏱ ${durationStr}</span>
          ${entry.ams_ready_score !== undefined ? `<span class="meta-item">🔌 AMS ${entry.ams_ready_score}%</span>` : ''}
          ${entry.overnight_fit_score !== undefined ? `<span class="meta-item">🌙 Overnight ${entry.overnight_fit_score}%</span>` : ''}
          ${entry.last_attempt_outcome ? `<span class="meta-item outcome-${entry.last_attempt_outcome}">Latest: ${entry.last_attempt_outcome}</span>` : ''}
        </div>

        <div class="entry-actions" role="group" aria-label="Queue entry actions">
          <button class="entry-action-btn" data-action="entry-detail" data-entry-id="${entry.queue_entry_id}" aria-label="Open details for ${this._escapeHtml(entry.title)}" title="Details">
            Detail
          </button>
          <button class="entry-action-btn" data-action="entry-edit" data-entry-id="${entry.queue_entry_id}" aria-label="Edit ${this._escapeHtml(entry.title)}" title="Edit">
            Edit
          </button>
          <button class="entry-action-btn" data-action="entry-up" data-entry-id="${entry.queue_entry_id}" aria-label="Move up ${this._escapeHtml(entry.title)}" title="Move up">
            Up
          </button>
          <button class="entry-action-btn" data-action="entry-down" data-entry-id="${entry.queue_entry_id}" aria-label="Move down ${this._escapeHtml(entry.title)}" title="Move down">
            Down
          </button>
          <button class="entry-action-btn danger" data-action="entry-delete" data-entry-id="${entry.queue_entry_id}" aria-label="Delete ${this._escapeHtml(entry.title)}" title="Delete">
            Delete
          </button>
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
    return `
      <div class="flash-banner ${toneClass}">
        ${this._escapeHtml(this._flashMessage.message)}
      </div>
    `;
  }

  _renderSuggestionCards() {
    if (!Array.isArray(this._suggestions) || this._suggestions.length === 0) {
      return '';
    }

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
            <div class="suggestion-title">Did you mean to mark ${this._escapeHtml(title)} as done?</div>
            <div class="suggestion-meta">Archive ${this._escapeHtml(archiveId || 'unknown')} · ${this._escapeHtml(reasonLabel)}</div>
          </div>
          <div class="suggestion-actions">
            <button class="suggestion-btn accept" data-action="suggestion-accept" data-suggestion-id="${this._escapeHtml(suggestionId)}" data-entry-id="${this._escapeHtml(entryId)}" ${busy ? 'disabled' : ''}>${busy ? 'Working...' : 'Accept'}</button>
            <button class="suggestion-btn reject" data-action="suggestion-reject" data-suggestion-id="${this._escapeHtml(suggestionId)}" ${busy ? 'disabled' : ''}>Reject</button>
          </div>
        </article>
      `;
    }).join('');

    return cards ? `<section class="suggestions-block">${cards}</section>` : '';
  }

  _renderAddModal() {
    if (!this._addModalOpen) {
      return '';
    }

    const activeOptions = this._getActiveAddOptions();
    const metrics = this._getAddSelectionMetrics();
    const quickPreview = `${metrics.fileCount} files x ${metrics.plateCount} plates = ${metrics.plateCount} queue copies`;
    const advancedPreview = `${metrics.selectedFileCount} files x ${metrics.selectedPlateCount} selected plates = ${metrics.selectedPlateCount} queue copies`;

    return `
      <div class="modal-backdrop" data-action="close-add">
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
            </div>

            <div class="tab-row">
              <button class="tab-btn ${this._addTab === 'quick' ? 'active' : ''}" data-action="add-tab" data-tab="quick">Quick Add</button>
              <button class="tab-btn ${this._addTab === 'advanced' ? 'active' : ''}" data-action="add-tab" data-tab="advanced">Advanced Add</button>
            </div>

            <div class="tab-panels">
              <section class="tab-panel ${this._addTab === 'quick' ? 'active' : ''}">
                <p class="tab-copy">Adds all files and all plates from the selected source.</p>
                <div class="copy-preview">${this._escapeHtml(quickPreview)}</div>
              </section>

              <section class="tab-panel ${this._addTab === 'advanced' ? 'active' : ''}">
                <p class="tab-copy">Choose exactly which files and plates should be queued.</p>
                <div class="copy-preview">${this._escapeHtml(advancedPreview)}</div>
                <div class="selection-grid">
                  ${this._renderAdvancedSelectionGrid()}
                </div>
              </section>
            </div>

            ${this._addLoadingSources ? '<div class="inline-note">Loading source options...</div>' : ''}
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
    if (!this._editModalOpen) {
      return '';
    }

    const title = this._escapeHtml(String(this._editTitle || ''));
    const copies = this._escapeHtml(String(this._editCopies || 1));

    return `
      <div class="modal-backdrop edit-backdrop" data-action="close-edit">
        <section class="add-modal edit-modal" role="dialog" aria-modal="true" aria-label="Edit Queue Entry">
          <div class="add-modal-header">
            <div>
              <h3>Edit Queue Entry</h3>
              <div class="add-modal-subtitle">Update title and requested copies</div>
            </div>
            <button class="modal-close-btn" data-action="close-edit" title="Close">✕</button>
          </div>

          <div class="add-modal-body">
            <div class="add-grid">
              <label class="form-label">Title
                <input
                  type="text"
                  class="edit-title-input"
                  value="${title}"
                  placeholder="Queue entry title"
                />
              </label>

              <label class="form-label">Copies
                <input
                  type="number"
                  class="edit-copies-input"
                  min="1"
                  step="1"
                  value="${copies}"
                />
              </label>
            </div>

            ${this._editError ? `<div class="inline-error">${this._escapeHtml(this._editError)}</div>` : ''}
          </div>

          <div class="add-modal-footer">
            <button class="ghost-btn" data-action="close-edit" ${this._editSubmitting ? 'disabled' : ''}>Cancel</button>
            <button class="primary-btn" data-action="submit-edit" ${this._editSubmitting ? 'disabled' : ''}>
              ${this._editSubmitting ? 'Saving...' : 'Save'}
            </button>
          </div>
        </section>
      </div>
    `;
  }

  _renderEntryDetailModal() {
    if (!this._detailEntry) {
      return '';
    }

    const entry = this._detailEntry;
    const sourceMeta = this._getSourceMeta(entry);
    const archiveId = String(entry.last_archive_id || '').trim();
    const printHistoryHref = this._buildPrintHistoryHref(archiveId || null);

    const fileGrid = this._detailLoading
      ? '<div class="inline-note">Loading files and plate states...</div>'
      : this._detailError
      ? `<div class="inline-error">${this._escapeHtml(this._detailError)}</div>`
      : this._detailFiles.length === 0
      ? '<div class="inline-note">No file-level detail is available for this source yet.</div>'
      : `
        <div class="detail-file-grid">
          ${this._detailFiles.map(file => {
            const selectedCount = file.plates.filter(plate => plate.selected).length;
            return `
              <article class="detail-file-card">
                <div class="detail-file-thumb ${file.thumbnail_url ? '' : 'empty'}">
                  ${file.thumbnail_url
                    ? `<img src="${this._escapeHtml(file.thumbnail_url)}" alt="${this._escapeHtml(file.file_name)} thumbnail" loading="lazy" decoding="async" />`
                    : '<span>No Preview</span>'}
                </div>
                <div class="detail-file-main">
                  <div class="detail-file-header">
                    <div class="detail-file-name" title="${this._escapeHtml(file.file_name)}">${this._escapeHtml(file.file_name)}</div>
                    <div class="detail-file-state ${file.selected ? 'selected' : 'unselected'}">${file.selected ? 'Selected' : 'Not selected'}</div>
                  </div>
                  <div class="detail-file-summary">${selectedCount}/${file.plates.length} plates selected</div>
                  <div class="detail-plate-list">
                    ${file.plates.map(plate => `
                      <div class="detail-plate-row ${plate.selected ? 'selected' : 'unselected'}">
                        <span class="detail-plate-name">${this._escapeHtml(plate.plate_name)}</span>
                        <span class="detail-plate-count">${this._escapeHtml(String(plate.completion_count))}/${this._escapeHtml(String(plate.completion_target))}</span>
                      </div>
                    `).join('')}
                  </div>
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
      ['State', entry.state],
      ['Rank', String(entry.rank)],
      ['Copies', String(entry.copies_requested || 1)],
      ['Duration', this._formatDuration(entry.estimated_total_minutes || 0)],
      ['Selection Mode', entry.selection_mode || 'all_files_all_plates'],
      ['Queue Notes', entry.queue_notes || ''],
    ];

    return `
      <div class="modal-backdrop detail-backdrop" data-action="close-detail">
        <aside class="detail-drawer" role="dialog" aria-modal="true" aria-label="Queue Entry Details">
          <div class="detail-drawer-header">
            <div>
              <h3>Queue Entry Details</h3>
              <div class="detail-drawer-subtitle">Files, plates, archive linkage, and history path</div>
            </div>
            <button class="modal-close-btn" data-action="close-detail" title="Close">✕</button>
          </div>

          <div class="detail-drawer-body">
            <div class="detail-grid">
              ${details.map(([label, value]) => `
                <div class="detail-row">
                  <div class="detail-key">${this._escapeHtml(label)}</div>
                  <div class="detail-value" title="${this._escapeHtml(String(value || ''))}">${this._escapeHtml(String(value || ''))}</div>
                </div>
              `).join('')}
            </div>

            <section class="detail-section">
              <h4>Files And Plates</h4>
              ${fileGrid}
            </section>

            <section class="detail-section">
              <h4>Archive Linkage</h4>
              ${archiveId
                ? `<div class="archive-chip">Archive ${this._escapeHtml(archiveId)} linked</div>`
                : '<div class="inline-note">No linked archive yet (entry not completed/matched).</div>'}
            </section>

            <section class="detail-section">
              <h4>Print History</h4>
              <a class="history-link" href="${this._escapeHtml(printHistoryHref)}" target="_blank" rel="noopener noreferrer">
                ${archiveId ? 'Open linked archive in Print History' : 'Open Print History'}
              </a>
            </section>
          </div>

          <div class="add-modal-footer">
            <button class="ghost-btn" data-action="close-detail">Close</button>
          </div>
        </aside>
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
    const css = `
      :host {
        display: block;
        width: 100%;
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
        width: 100%;
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

      .flash-banner {
        padding: 10px 12px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 600;
        border: 1px solid transparent;
      }

      .flash-banner.success {
        background: rgba(125, 220, 151, 0.12);
        border-color: rgba(125, 220, 151, 0.28);
        color: var(--accent-green);
      }

      .flash-banner.error {
        background: rgba(245, 144, 144, 0.12);
        border-color: rgba(245, 144, 144, 0.28);
        color: var(--accent-red);
      }

      .suggestions-block {
        display: grid;
        gap: 8px;
        margin-bottom: 4px;
      }

      .suggestion-card {
        border: 1px solid rgba(242, 195, 91, 0.35);
        border-radius: 12px;
        background: rgba(242, 195, 91, 0.1);
        padding: 10px 12px;
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
        width: 100%;
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
        backdrop-filter: blur(2px);
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 18px;
      }

      .add-modal {
        width: min(900px, 100%);
        max-height: calc(100vh - 40px);
        overflow: auto;
        background: linear-gradient(180deg, rgba(28, 36, 47, 0.98), rgba(18, 24, 33, 0.98));
        border: 1px solid var(--border-strong);
        border-radius: 18px;
        box-shadow: var(--shadow);
        animation: fadeInUp 0.18s ease-out;
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
        border: 1px solid rgba(124, 199, 255, 0.2);
        background: rgba(124, 199, 255, 0.1);
        padding: 8px 10px;
        font-size: 12px;
        color: var(--accent-blue);
      }

      .selection-grid {
        display: grid;
        gap: 10px;
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
        justify-content: flex-end;
        align-items: stretch;
        padding: 0;
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

      @media (max-width: 960px) {
        .filter-bar {
          grid-template-columns: 1fr;
        }

        .filter-buttons {
          width: 100%;
        }

        .sort-dropdown {
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

        .filter-bar {
          grid-template-columns: 1fr;
          gap: 10px;
          padding: 10px;
        }

        .filter-buttons {
          width: 100%;
        }

        .sort-dropdown {
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
    `;

    const content = this._loading
      ? '<div class="loading-state"><div class="loading-spinner"></div></div>'
      : this._error
      ? `<div class="error-state"><strong>⚠ Error</strong>${this._escapeHtml(this._error)}</div>`
      : this._renderFlashBanner() + this._renderSuggestionCards() + this._renderTopWidget() + this._renderFilterControls() + this._renderQueueList();

    const html = `
      <style>${css}</style>
      <div class="shell">
        <div class="card-title">
          <h2>Print Queue</h2>
          <div class="title-actions">
            <button class="planner-btn" data-action="open-planner" title="Open Queue Planner">📊 Planner</button>
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
      ${this._renderEditModal()}
      ${this._renderEntryDetailModal()}
      ${this._renderPlannerDrawer()}
    `;

    this.shadowRoot.innerHTML = html;

    const refreshBtn = this.shadowRoot.querySelector('.refresh-btn');
    if (refreshBtn && !this._loading) {
      refreshBtn.addEventListener('click', () => this._loadQueueData());
    }

    // Attach filter event listeners
    const filterBtns = this.shadowRoot.querySelectorAll('.filter-btn');
    filterBtns.forEach(btn => {
      btn.addEventListener('click', (e) => {
        const action = e.target.dataset.action;
        if (action === 'toggle-state') {
          this._toggleStateFilter(e.target.dataset.state);
        } else if (action === 'toggle-source') {
          this._toggleSourceFilter(e.target.dataset.source);
        }
      });
    });

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

    const addBtn = this.shadowRoot.querySelector('.add-btn');
    if (addBtn) {
      addBtn.addEventListener('click', () => this._openAddModal());
    }

    const modalBackdrop = this.shadowRoot.querySelector('.modal-backdrop');
    if (modalBackdrop) {
      modalBackdrop.addEventListener('click', (event) => {
        if (event.target === modalBackdrop) {
          this._closeAddModal();
        }
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
          this._openEntryDetail(entryId);
        } else if (action === 'entry-edit') {
          await this._editEntry(entryId);
        } else if (action === 'entry-delete') {
          await this._deleteEntry(entryId);
        } else if (action === 'entry-up') {
          await this._moveEntry(entryId, 'up');
        } else if (action === 'entry-down') {
          await this._moveEntry(entryId, 'down');
        }
      });
    });
  }

  getCardSize() {
    return 10;
  }
}

customElements.define('unified-queue-board-card', UnifiedQueueBoardCard);
