var inboxShared = window.ModelCatalogIntakeShared;
if (!inboxShared) {
  throw new Error("model-catalog-intake-shared.js must load before model-catalog-inbox-review-card.js");
}

var escapeHtml = inboxShared.escapeHtml;
var basename = inboxShared.basename;
var formatLabel = inboxShared.formatLabel;
var parseValidationActions = inboxShared.parseValidationActions;
var parseDecisionWarnings = inboxShared.parseDecisionWarnings;
var warningMessages = inboxShared.warningMessages;
var duplicateWarnings = inboxShared.duplicateWarnings;
var batchActionLabel = inboxShared.batchActionLabel;
var callServiceWithResponse = inboxShared.callServiceWithResponse;
var fireModelCatalogDataChanged = inboxShared.fireModelCatalogDataChanged;
var sharedStyles = inboxShared.sharedStyles;
var selectInputOption = inboxShared.selectInputOption;

function pathStem(path) {
  var name = basename(path || '');
  if (!name) {
    return '';
  }
  var dotIndex = name.lastIndexOf('.');
  return dotIndex > 0 ? name.slice(0, dotIndex) : name;
}

function suggestedGroupTitle(sourceEntry) {
  var hintedTitle = String(sourceEntry && sourceEntry.group_title || '').trim();
  if (hintedTitle) {
    return hintedTitle;
  }
  if (String(sourceEntry && sourceEntry.type || '').toLowerCase() === 'folder') {
    return basename(sourceEntry && sourceEntry.path || '') || 'Untitled';
  }
  return pathStem(sourceEntry && sourceEntry.path || '') || basename(sourceEntry && sourceEntry.path || '') || 'Untitled';
}

function validationActionSummary(actions) {
  if (!Array.isArray(actions) || !actions.length) {
    return '';
  }
  var counts = {
    allow_duplicate: 0,
    exclude_source: 0,
  };
  actions.forEach(function (entry) {
    var decision = String(entry && entry.decision || '').trim().toLowerCase();
    if (decision === 'allow_duplicate' || decision === 'exclude_source') {
      counts[decision] += 1;
    }
  });
  var parts = [];
  if (counts.allow_duplicate) {
    parts.push(String(counts.allow_duplicate) + ' allow duplicate');
  }
  if (counts.exclude_source) {
    parts.push(String(counts.exclude_source) + ' excluded source');
  }
  if (!parts.length) {
    return '';
  }
  return parts.join('; ');
}

function summarizeCleanupCandidateStates(items) {
  var counts = {};
  (items || []).forEach(function (item) {
    var state = String(item && (item.state || item.status) || 'unknown').trim().toLowerCase();
    if (!state) {
      state = 'unknown';
    }
    counts[state] = Number(counts[state] || 0) + 1;
  });
  return Object.keys(counts).sort().map(function (state) {
    return formatLabel(state) + ' ' + String(counts[state]);
  }).join(', ');
}

function normalizedTerminalResult(item) {
  var value = item && item.terminal_result;
  if (value && typeof value === 'object') {
    return value;
  }
  return {
    kind: 'none',
    primary_result_id: null,
    local_model_ids: [],
    group_results: [],
    raw: item && item.terminal_result_id,
  };
}

function splitTerminalResultIds(item) {
  var terminalResult = normalizedTerminalResult(item);
  if (Array.isArray(terminalResult.local_model_ids) && terminalResult.local_model_ids.length) {
    return terminalResult.local_model_ids.slice();
  }
  return String(item && item.terminal_result_id || '')
    .split(',')
    .map(function (value) { return String(value || '').trim(); })
    .filter(Boolean);
}

function terminalDisplayAction(item) {
  return String(item && (item.terminal_display_action || item.terminal_action || item.state) || '').trim();
}

function terminalResultSummary(item) {
  var terminalResult = normalizedTerminalResult(item);
  var curatedCount = Array.isArray(terminalResult.local_model_ids) ? terminalResult.local_model_ids.length : 0;
  if (curatedCount) {
    return curatedCount === 1 ? terminalResult.local_model_ids[0] : 'Curated ' + String(curatedCount);
  }
  return 'Not recorded';
}

function formatTimestamp(value) {
  var raw = String(value || '').trim();
  if (!raw) {
    return 'Not recorded';
  }
  var parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) {
    return raw;
  }
  return parsed.toLocaleString();
}

class ModelCatalogInboxReviewCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._hass = null;
    this._config = null;
    this._loading = false;
    this._error = '';
    this._status = '';
    this._items = [];
    this._stateFilter = '';
    this._selectMode = false;
    this._selectedIds = {};
    this._batchResult = null;
    this._currentView = 'active_queue'; // 'active_queue' or 'job_history'
    this._confirmDialog = null;
  }

  setConfig(config) {
    this._config = Object.assign({
      title: 'Inbox Review',
      defaultView: 'active_queue',
      historyOnly: false,
      sectionEntity: '',
      curatedSection: 'curated',
      modelEntity: 'input_text.model_catalog_sidecar_base_url',
      modelSidecarUrl: '',
    }, config || {});
    this._currentView = this._historyOnly()
      ? 'job_history'
      : (String(this._config.defaultView || '').trim() === 'job_history' ? 'job_history' : 'active_queue');
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this.isConnected && !this._loading && !this._items.length) {
      this._refresh();
    }
  }

  connectedCallback() {
    if (this._hass && !this._loading && !this._items.length) {
      this._refresh();
    }
    if (this.shadowRoot) {
      this.shadowRoot.addEventListener('click', this._handleClick.bind(this));
    }
  }

  disconnectedCallback() {
    if (this.shadowRoot) {
      this.shadowRoot.removeEventListener('click', this._handleClick.bind(this));
    }
  }

  getCardSize() {
    return 16;
  }

  _historyOnly() {
    return !!(this._config && this._config.historyOnly);
  }

  _showActiveQueue() {
    return !this._historyOnly();
  }

  async _navigateToSection(option, statusMessage) {
    if (!option || !this._config || !this._config.sectionEntity) {
      return;
    }
    await selectInputOption(this._hass, this._config.sectionEntity, option);
    if (statusMessage) {
      this._status = statusMessage;
      this._render();
    }
  }

  _fireBrowserModEvent(service, data) {
    var event = new CustomEvent('ll-custom', {
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

  _openModelDetailPopup(modelRef, modelName) {
    if (!modelRef) {
      return;
    }
    this._fireBrowserModEvent('browser_mod.popup', {
      title: modelName || 'Model Details',
      size: 'wide',
      content: {
        type: 'custom:model-detail-popup-card',
        model_ref: modelRef,
        model_entity: this._config.modelEntity,
        model_sidecar_url: this._config.modelSidecarUrl || '',
      },
    });
  }

  _terminalSummaryMarkup(item, proposedTitle) {
    var terminalAction = terminalDisplayAction(item);
    var resultLabel = terminalAction === 'rejected' ? 'Outcome' : 'Local Model';
    var resultValue = terminalResultSummary(item);
    var actorValue = String(item.terminal_actor || 'queue_processed').trim();

    return ''
      + '<div class="item-grid"><div class="summary-card"><div class="summary-label">Outcome</div><div class="summary-value">' + escapeHtml(formatLabel(terminalAction || item.state || 'completed')) + '</div></div><div class="summary-card"><div class="summary-label">Completed</div><div class="summary-value">' + escapeHtml(formatTimestamp(item.terminal_at || item.updated_at || item.cleanup_done_at || item.verified_at || item.created_at)) + '</div></div><div class="summary-card"><div class="summary-label">Actor</div><div class="summary-value">' + escapeHtml(formatLabel(actorValue)) + '</div></div><div class="summary-card"><div class="summary-label">' + escapeHtml(resultLabel) + '</div><div class="summary-value">' + escapeHtml(resultValue) + '</div></div></div>'
      + (proposedTitle ? '<div class="muted">Planned title: ' + escapeHtml(proposedTitle) + '</div>' : '');
  }

  _historyActionButtons(item, deleteDisabled, proposedTitle) {
    var terminalAction = terminalDisplayAction(item);
    var terminalResult = normalizedTerminalResult(item);
    var localModelIds = Array.isArray(terminalResult.local_model_ids) ? terminalResult.local_model_ids : [];
    var buttons = [];

    if (terminalAction === 'published_to_catalog' && localModelIds.length === 1) {
      buttons.push('<button class="button primary" data-action="view-local-model" data-local-model-id="' + escapeHtml(localModelIds[0]) + '" data-model-name="' + escapeHtml(proposedTitle || localModelIds[0]) + '">View Model</button>');
    }
    if (localModelIds.length) {
      buttons.push('<button class="button' + (!buttons.length ? ' primary' : '') + '" data-action="open-curated-section" data-local-model-id="' + escapeHtml(localModelIds[0]) + '">Open Curated</button>');
    }
    buttons.push('<button class="button danger" data-action="delete-item" data-item-id="' + escapeHtml(item.item_id) + '" data-item-status="' + escapeHtml(item.status || '') + '"' + deleteDisabled + '>Delete</button>');
    return buttons.join('');
  }

  async _refresh() {
    if (!this._hass || this._loading) {
      return;
    }
    this._loading = true;
    this._error = '';
    this._render();
    try {
      var itemsResponse = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_list_intake_items', {
        limit: 100,
        offset: 0,
        state_filter: this._stateFilter || undefined,
      });
      this._items = Array.isArray(itemsResponse.items) ? itemsResponse.items : [];
    } catch (error) {
      this._error = error && error.message ? String(error.message) : 'Could not load inbox review state.';
    } finally {
      this._loading = false;
      this._render();
    }
  }

  async _validateItem(itemId) {
    this._loading = true;
    this._error = '';
    this._status = '';
    this._render();
    try {
      var response = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_validate_intake_item', { item_id: itemId });
      this._status = 'Validation complete: ' + (response.validation ? response.validation.validation_state : 'done');
      this._loading = false;
      await this._refresh();
    } catch (error) {
      this._error = error && error.message ? String(error.message) : 'Could not validate intake item.';
      this._loading = false;
      this._render();
    }
  }

  async _publishCurated(itemId) {
    this._loading = true;
    this._error = '';
    this._status = '';
    this._render();
    try {
      await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_publish_to_local', { upload_id: itemId });
      this._status = 'Item published to curated local catalog.';
      fireModelCatalogDataChanged(['curated'], { reason: 'publish-curated', itemId: itemId });
      this._loading = false;
      await this._refresh();
    } catch (error) {
      this._error = error && error.message ? String(error.message) : 'Could not publish intake item to curated local catalog.';
      this._loading = false;
      this._render();
    }
  }

  async _deferItem(itemId) {
    var note = window.prompt('Deferral note', 'Deferred by operator');
    if (note == null) {
      return;
    }
    this._loading = true;
    this._error = '';
    this._status = '';
    this._render();
    try {
      await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_defer_intake_item', { item_id: itemId, note: note });
      this._status = 'Item deferred.';
      this._loading = false;
      await this._refresh();
    } catch (error) {
      this._error = error && error.message ? String(error.message) : 'Could not defer intake item.';
      this._loading = false;
      this._render();
    }
  }

  async _rejectItem(itemId) {
    var note = window.prompt('Rejection note', 'Rejected by operator');
    if (note == null) {
      return;
    }
    this._loading = true;
    this._error = '';
    this._status = '';
    this._render();
    try {
      await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_reject_intake_item', { item_id: itemId, note: note });
      this._status = 'Item rejected.';
      this._loading = false;
      await this._refresh();
    } catch (error) {
      this._error = error && error.message ? String(error.message) : 'Could not reject intake item.';
      this._loading = false;
      this._render();
    }
  }

  _canDeleteStatus(status) {
    var normalized = String(status || '').trim().toLowerCase();
    var deletable = { queued: true, failed: true, submitted: true, validated_ready: true, validated_warning: true, deferred: true };
    return deletable[normalized] === true;
  }

  _canDeleteItem(item) {
    return this._canDeleteStatus(item && item.status);
  }

  _showConfirmDialog(options) {
    var config = options && typeof options === 'object' ? options : {};
    var card = this;
    return new Promise(function (resolve) {
      card._confirmDialog = {
        title: String(config.title || 'Confirm Action'),
        message: String(config.message || 'Are you sure you want to continue?'),
        confirmLabel: String(config.confirmLabel || 'Confirm'),
        cancelLabel: String(config.cancelLabel || 'Cancel'),
        danger: config.danger !== false,
        resolve: resolve,
      };
      card._render();
    });
  }

  _resolveConfirmDialog(accepted) {
    if (!this._confirmDialog) {
      return;
    }
    var resolver = this._confirmDialog.resolve;
    this._confirmDialog = null;
    this._render();
    if (typeof resolver === 'function') {
      resolver(!!accepted);
    }
  }

  _renderConfirmDialog() {
    if (!this._confirmDialog) {
      return '';
    }
    return ''
      + '<div class="confirm-overlay" role="dialog" aria-modal="true" aria-label="' + escapeHtml(this._confirmDialog.title) + '">'
      + '  <div class="confirm-backdrop" data-action="confirm-dialog-cancel"></div>'
      + '  <div class="confirm-dialog">'
      + '    <div class="title">' + escapeHtml(this._confirmDialog.title) + '</div>'
      + '    <div class="muted">' + escapeHtml(this._confirmDialog.message) + '</div>'
      + '    <div class="button-row confirm-actions">'
      + '      <button class="button" data-action="confirm-dialog-cancel">' + escapeHtml(this._confirmDialog.cancelLabel) + '</button>'
      + '      <button class="button' + (this._confirmDialog.danger ? ' danger' : ' primary') + '" data-action="confirm-dialog-accept">' + escapeHtml(this._confirmDialog.confirmLabel) + '</button>'
      + '    </div>'
      + '  </div>'
      + '</div>';
  }

  async _deleteItem(itemId, status) {
    if (!this._canDeleteStatus(status)) {
      this._error = 'Delete is only allowed for non-terminal intake items.';
      this._render();
      return;
    }
    var confirmed = await this._showConfirmDialog({
      title: 'Delete Intake Item?',
      message: 'This removes the selected intake item from the queue and cannot be undone.',
      confirmLabel: 'Delete Item',
      cancelLabel: 'Keep Item',
      danger: true,
    });
    if (!confirmed) {
      return;
    }
    this._loading = true;
    this._error = '';
    this._status = '';
    this._render();
    try {
      await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_delete_intake_upload', { upload_id: itemId });
      this._status = 'Item deleted from intake queue.';
      this._loading = false;
      await this._refresh();
    } catch (error) {
      this._error = error && error.message ? String(error.message) : 'Could not delete intake item.';
      this._loading = false;
      this._render();
    }
  }

  _getActiveQueueItems() {
    var activeStates = ['submitted', 'validated_ready', 'validated_warning', 'deferred'];
    return this._items.filter(function (item) {
      var state = String(item.state || item.status || '').toLowerCase();
      return activeStates.indexOf(state) >= 0;
    });
  }

  _getJobHistoryItems() {
    return this._items.filter(function (item) {
      var terminalAction = String(item.terminal_action || '').trim().toLowerCase();
      if (terminalAction) {
        return true;
      }
      var state = String(item.state || item.status || '').toLowerCase();
      return ['grouped_new', 'grouped_existing', 'published_to_catalog', 'published_by_destination', 'rejected'].indexOf(state) >= 0;
    });
  }

  _getVisibleItems() {
    if (this._currentView === 'job_history') {
      return this._getJobHistoryItems();
    }
    return this._getActiveQueueItems();
  }

  _selectedItems() {
    return this._getVisibleItems().filter(function (item) {
      return !!this._selectedIds[item.item_id];
    }, this);
  }

  _toggleSelectMode(forceValue) {
    this._selectMode = typeof forceValue === 'boolean' ? forceValue : !this._selectMode;
    if (!this._selectMode) {
      this._selectedIds = {};
    }
    this._render();
  }

  _toggleItemSelection(itemId) {
    if (!itemId) {
      return;
    }
    if (this._selectedIds[itemId]) {
      delete this._selectedIds[itemId];
    } else {
      this._selectedIds[itemId] = true;
    }
    this._render();
  }

  _cleanupCandidates() {
    return this._getActiveQueueItems().filter(function (item) {
      return this._canDeleteItem(item);
    }, this);
  }

  async _cleanupStaleQueueItems() {
    var candidates = this._cleanupCandidates();
    if (!candidates.length) {
      this._status = 'No active queue items are eligible for cleanup.';
      this._render();
      return;
    }
    var confirmed = await this._showConfirmDialog({
      title: 'Delete Active Queue Items?',
      message: 'This will delete ' + String(candidates.length) + ' non-terminal intake item(s): ' + summarizeCleanupCandidateStates(candidates) + '. Use this only to clean up stale queue records from canceled or abandoned work.',
      confirmLabel: 'Delete Queue Items',
      cancelLabel: 'Keep Items',
      danger: true,
    });
    if (!confirmed) {
      return;
    }
    this._loading = true;
    this._error = '';
    this._status = '';
    this._render();
    var deletedCount = 0;
    try {
      for (var index = 0; index < candidates.length; index += 1) {
        await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_delete_intake_upload', {
          upload_id: candidates[index].item_id,
        });
        deletedCount += 1;
      }
      this._status = 'Deleted ' + String(deletedCount) + ' active queue item(s).';
      this._loading = false;
      await this._refresh();
    } catch (error) {
      this._error = error && error.message ? String(error.message) : 'Could not clean up active queue items.';
      this._loading = false;
      this._render();
    }
  }

  async _runBatchAction(action) {
    var selectedItems = this._selectedItems();
    if (!selectedItems.length) {
      this._error = 'Select one or more inbox items first.';
      this._render();
      return;
    }

    var note = '';
    if (action === 'defer') {
      note = window.prompt('Batch deferral note', 'Deferred by operator (batch)');
      if (note == null) {
        return;
      }
    }
    if (action === 'reject') {
      note = window.prompt('Batch rejection note', 'Rejected by operator (batch)');
      if (note == null) {
        return;
      }
    }
    if (action === 'delete') {
      var deleteMessage = 'Delete ' + String(selectedItems.length) + ' selected intake item(s) from the queue? This cannot be undone.\n\nOnly non-terminal items can be deleted; others will be reported as skipped.';
      var confirmedBatchDelete = await this._showConfirmDialog({
        title: 'Delete Selected Intake Items?',
        message: deleteMessage,
        confirmLabel: 'Delete Selected',
        cancelLabel: 'Keep Items',
        danger: true,
      });
      if (!confirmedBatchDelete) {
        return;
      }
    }

    this._loading = true;
    this._error = '';
    this._status = '';
    this._batchResult = null;
    this._render();

    var results = [];
        var changedScopes = {};
    for (var index = 0; index < selectedItems.length; index += 1) {
      var item = selectedItems[index];
      var sourceEntry = item.source_entry || {};
      try {
        if (action === 'validate') {
          var validationResponse = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_validate_intake_item', { item_id: item.item_id });
          var validationState = validationResponse.validation ? validationResponse.validation.validation_state : 'done';
          var validationWarnings = validationResponse.validation ? validationResponse.validation.warnings || [] : [];
          results.push({
            item_id: item.item_id,
            label: basename(sourceEntry.path || item.item_id),
            outcome: validationState === 'ready' ? 'succeeded' : 'partial',
            message: validationState === 'ready'
              ? 'validated ready'
              : 'validated ' + validationState + (validationWarnings.length ? ': ' + warningMessages(validationWarnings).join('; ') : ''),
          });
          continue;
        }

        if (action === 'publish-curated') {
          await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_publish_to_local', { upload_id: item.item_id });
              changedScopes.curated = true;
          results.push({
            item_id: item.item_id,
            label: basename(sourceEntry.path || item.item_id),
            outcome: 'succeeded',
            message: 'published to curated local catalog',
          });
          continue;
        }

        if (action === 'defer') {
          await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_defer_intake_item', { item_id: item.item_id, note: note || 'Deferred by operator (batch)' });
          results.push({
            item_id: item.item_id,
            label: basename(sourceEntry.path || item.item_id),
            outcome: 'succeeded',
            message: 'deferred',
          });
          continue;
        }

        if (action === 'reject') {
          await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_reject_intake_item', { item_id: item.item_id, note: note || 'Rejected by operator (batch)' });
          results.push({
            item_id: item.item_id,
            label: basename(sourceEntry.path || item.item_id),
            outcome: 'succeeded',
            message: 'rejected',
          });
          continue;
        }

        if (action === 'delete') {
          if (!this._canDeleteItem(item)) {
            results.push({
              item_id: item.item_id,
              label: basename(sourceEntry.path || item.item_id),
              outcome: 'partial',
              message: 'not deleted: status ' + String(item.status || 'unknown') + ' is not deletable',
            });
            continue;
          }
          await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_delete_intake_upload', { upload_id: item.item_id });
          results.push({
            item_id: item.item_id,
            label: basename(sourceEntry.path || item.item_id),
            outcome: 'succeeded',
            message: 'deleted from intake queue',
          });
        }
      } catch (error) {
        results.push({
          item_id: item.item_id,
          label: basename(sourceEntry.path || item.item_id),
          outcome: 'failed',
          message: error && error.message ? String(error.message) : 'action failed',
        });
      }
    }

    this._batchResult = {
      action: action,
      total: results.length,
      succeeded: results.filter(function (result) { return result.outcome === 'succeeded'; }).length,
      partial: results.filter(function (result) { return result.outcome === 'partial'; }).length,
      failed: results.filter(function (result) { return result.outcome === 'failed'; }).length,
      results: results,
    };
    this._status = 'Batch ' + batchActionLabel(action).toLowerCase() + ' complete.';
    this._selectedIds = {};
    this._selectMode = false;
    this._loading = false;
        if (changedScopes.curated || changedScopes.working) {
          fireModelCatalogDataChanged(Object.keys(changedScopes), { reason: 'batch-' + action, total: results.length });
        }
    await this._refresh();
  }

  _handleClick(event) {
    var target = event.target instanceof Element ? event.target.closest('[data-action]') : null;
    if (!target) {
      return;
    }
    var action = String(target.getAttribute('data-action') || '');
    var itemId = String(target.getAttribute('data-item-id') || '');
    var sourcePath = String(target.getAttribute('data-source-path') || '');
    if (action === 'refresh-inbox') {
      this._refresh();
      return;
    }
    if (action === 'cleanup-stale-queue') {
      this._cleanupStaleQueueItems();
      return;
    }
    if (action === 'switch-view') {
      if (!this._showActiveQueue()) {
        return;
      }
      this._currentView = String(target.getAttribute('data-view') || 'active_queue');
      this._stateFilter = '';
      this._selectedIds = {};
      this._render();
      return;
    }
    if (action === 'toggle-select-mode') {
      this._toggleSelectMode();
      return;
    }
    if (action === 'toggle-item-selection') {
      this._toggleItemSelection(itemId);
      return;
    }
    if (action === 'clear-batch-result') {
      this._batchResult = null;
      this._render();
      return;
    }
    if (action === 'confirm-dialog-cancel') {
      this._resolveConfirmDialog(false);
      return;
    }
    if (action === 'confirm-dialog-accept') {
      this._resolveConfirmDialog(true);
      return;
    }
    if (action === 'batch-validate') {
      this._runBatchAction('validate');
      return;
    }
    if (action === 'batch-publish-curated') {
      this._runBatchAction('publish-curated');
      return;
    }
    if (action === 'batch-defer') {
      this._runBatchAction('defer');
      return;
    }
    if (action === 'batch-reject') {
      this._runBatchAction('reject');
      return;
    }
    if (action === 'batch-delete') {
      this._runBatchAction('delete');
      return;
    }
    if (action === 'validate-item') {
      this._validateItem(itemId);
      return;
    }
    if (action === 'publish-curated-item') {
      this._publishCurated(itemId);
      return;
    }
    if (action === 'defer-item') {
      this._deferItem(itemId);
      return;
    }
    if (action === 'reject-item') {
      this._rejectItem(itemId);
      return;
    }
    if (action === 'delete-item') {
      this._deleteItem(itemId, String(target.getAttribute('data-item-status') || ''));
      return;
    }
    if (action === 'view-local-model') {
      this._openModelDetailPopup(
        String(target.getAttribute('data-local-model-id') || ''),
        String(target.getAttribute('data-model-name') || '')
      );
      return;
    }
    if (action === 'open-curated-section') {
      this._navigateToSection(
        this._config.curatedSection,
        'Opened Curated for model ' + String(target.getAttribute('data-local-model-id') || '') + '.'
      );
      return;
    }
  }

  _handleFilterChange(event) {
    var target = event.target instanceof Element ? event.target : null;
    if (!target) {
      return;
    }
    this._stateFilter = String(target.value || '').trim();
    this._refresh();
  }

  _render() {
    if (!this.shadowRoot || !this._config) {
      return;
    }
    var visibleItems = this._getVisibleItems();
    var selectedCount = this._selectedItems().length;
    var activeQueueCount = this._getActiveQueueItems().length;
    var jobHistoryCount = this._getJobHistoryItems().length;
    var isActiveQueueView = this._currentView === 'active_queue' && this._showActiveQueue();
    var canSelect = isActiveQueueView;
    var cleanupCandidateCount = this._cleanupCandidates().length;
    var subtitle = this._historyOnly() || this._currentView === 'job_history'
      ? 'Completed intake outcomes from wizard-direct and queued execution paths.'
      : 'Review queued intake items, with Job History kept as the primary completed-work surface.';
    var viewToolbar = this._showActiveQueue()
      ? '<section class="section"><div class="toolbar-row"><div class="button-row"><button class="button' + (isActiveQueueView ? ' primary' : '') + '" data-action="switch-view" data-view="active_queue">Active Queue (' + String(activeQueueCount) + ')</button><button class="button' + (this._currentView === 'job_history' ? ' primary' : '') + '" data-action="switch-view" data-view="job_history">Job History (' + String(jobHistoryCount) + ')</button></div></div></section>'
      : '<section class="section"><div class="toolbar-row"><div class="status">Showing completed Job History only. Active Queue remains available through background/admin paths.</div></div></section>';
    var confirmStyles = ''
      + 'ha-card{border-radius:0 !important;border:none !important;background:transparent !important;box-shadow:none !important;}'
      + '.confirm-overlay{position:fixed;inset:0;z-index:40;display:grid;place-items:center;padding:16px;box-sizing:border-box;}'
      + '.confirm-backdrop{position:absolute;inset:0;background:rgba(15,23,42,0.55);backdrop-filter:blur(4px);}'
      + '.confirm-dialog{position:relative;display:grid;gap:10px;width:min(460px,100%);max-height:calc(100% - 16px);overflow:auto;padding:16px;border-radius:14px;border:1px solid rgba(148,163,184,0.28);background:var(--card-background-color,rgba(15,23,42,0.98));box-shadow:0 18px 42px rgba(2,6,23,0.45);}'
      + '.confirm-dialog .muted{white-space:pre-line;}'
      + '.confirm-actions{justify-content:flex-end;}';

    this.shadowRoot.innerHTML = ''
      + '<style>' + sharedStyles + confirmStyles + '</style>'
      + '<ha-card>'
      + '  <div class="shell">'
      + '    <div class="header"><div class="title-row"><div><div class="title">' + escapeHtml(this._config.title) + '</div><div class="subtitle">' + escapeHtml(subtitle) + '</div></div><div class="button-row"><button class="button" data-action="refresh-inbox">Refresh</button>' + ((!isActiveQueueView && cleanupCandidateCount > 0) ? '<button class="button warn" data-action="cleanup-stale-queue">Clean Active Queue (' + String(cleanupCandidateCount) + ')</button>' : '') + (canSelect ? '<button class="button ' + (this._selectMode ? 'warn' : '') + '" data-action="toggle-select-mode">' + (this._selectMode ? 'Cancel Select' : 'Select Items') + '</button>' : '') + '</div></div>'
      + '    ' + (this._error ? '<div class="status error">' + escapeHtml(this._error) + '</div>' : '')
      + '    ' + (this._status ? '<div class="status">' + escapeHtml(this._status) + '</div>' : '')
      + '    </div>'
      + '    ' + viewToolbar
      + '    ' + (isActiveQueueView ? '<section class="toolbar-row"><div class="field"><label for="inbox-state-filter">State Filter</label><select id="inbox-state-filter" class="select"><option value="">All</option><option value="submitted"' + (this._stateFilter === 'submitted' ? ' selected' : '') + '>Submitted</option><option value="validated_ready"' + (this._stateFilter === 'validated_ready' ? ' selected' : '') + '>Validated Ready</option><option value="validated_warning"' + (this._stateFilter === 'validated_warning' ? ' selected' : '') + '>Validated Warning</option><option value="deferred"' + (this._stateFilter === 'deferred' ? ' selected' : '') + '>Deferred</option></select></div></div></section>' : '')
      + '    <section class="toolbar-row"><div class="status">Items: ' + String(visibleItems.length) + (this._selectMode && canSelect ? ' / Selected: ' + String(selectedCount) : '') + '</div></section>'
      + '    ' + (this._selectMode && canSelect ? '<section class="batch-toolbar"><div class="title-row"><div><div class="title">' + String(selectedCount) + ' selected</div><div class="subtitle">Batch review actions for queued intake items.</div></div></div><div class="button-row"><button class="button primary" data-action="batch-validate"' + (!selectedCount ? ' disabled' : '') + '>Validate</button><button class="button primary" data-action="batch-publish-curated"' + (!selectedCount ? ' disabled' : '') + '>Publish Curated</button><button class="button warn" data-action="batch-defer"' + (!selectedCount ? ' disabled' : '') + '>Defer</button><button class="button danger" data-action="batch-reject"' + (!selectedCount ? ' disabled' : '') + '>Reject</button><button class="button danger" data-action="batch-delete"' + (!selectedCount ? ' disabled' : '') + '>Delete</button><button class="button" data-action="toggle-select-mode">Cancel</button></div></section>' : '')
      + '    ' + (this._batchResult ? '<section class="result-summary"><div class="title-row"><div><div class="title">Batch Result Summary</div><div class="subtitle">' + escapeHtml(batchActionLabel(this._batchResult.action)) + ' across ' + String(this._batchResult.total) + ' item(s).</div></div><button class="button" data-action="clear-batch-result">Dismiss</button></div><div class="button-row"><span class="chip ok">Succeeded ' + String(this._batchResult.succeeded) + '</span><span class="chip warn">Partial ' + String(this._batchResult.partial) + '</span><span class="chip error">Failed ' + String(this._batchResult.failed) + '</span></div><div class="entries">' + this._batchResult.results.map(function (result) { return '<div class="result-line"><span>' + escapeHtml(result.label || result.item_id) + '</span><span>' + escapeHtml(result.message || result.outcome) + '</span></div>'; }).join('') + '</div></section>' : '')
      + '    ' + (this._loading && !visibleItems.length ? '<div class="state-row">Loading intake items...</div>' : '')
      + '    ' + (!this._loading && !visibleItems.length ? '<div class="state-row">No intake items match the current view.</div>' : '')
      + '    ' + (visibleItems.length ? '<div class="items">' + visibleItems.map(function (item) {
          var sourceEntry = item.source_entry || {};
          var proposedTitle = suggestedGroupTitle(sourceEntry);
          var warnings = parseDecisionWarnings(item);
          var validationActions = parseValidationActions(item);
          var warningsText = warningMessages(warnings).join('; ');
          if (!warningsText) {
            warningsText = item.decision_note || '';
          }
          var validationActionText = validationActionSummary(validationActions);
          var duplicateSignals = duplicateWarnings(item);
          var isSelected = !!this._selectedIds[item.item_id];
          var deleteDisabled = this._canDeleteItem(item) ? '' : ' disabled title="Only queued/failed items can be deleted"';
          var isTerminal = this._currentView === 'job_history';
          var actionButtons = isTerminal 
            ? this._historyActionButtons(item, deleteDisabled, proposedTitle)
            : '<button class="button" data-action="validate-item" data-item-id="' + escapeHtml(item.item_id) + '">Validate</button><button class="button primary" data-action="publish-curated-item" data-item-id="' + escapeHtml(item.item_id) + '">Publish Curated</button><button class="button warn" data-action="defer-item" data-item-id="' + escapeHtml(item.item_id) + '">Defer</button><button class="button danger" data-action="reject-item" data-item-id="' + escapeHtml(item.item_id) + '">Reject</button><button class="button danger" data-action="delete-item" data-item-id="' + escapeHtml(item.item_id) + '" data-item-status="' + escapeHtml(item.status || '') + '"' + deleteDisabled + '>Delete</button>';
          return ''
            + '<article class="entry-row' + (isSelected ? ' selected' : '') + '">'
            + '  <div class="entry-top"><div><div class="entry-name">' + escapeHtml(basename(sourceEntry.path || item.item_id)) + '</div><div class="entry-path">' + escapeHtml(sourceEntry.path || item.item_id) + '</div></div><div class="button-row">' + (this._selectMode && canSelect ? '<label class="selector"><input type="checkbox" data-action="toggle-item-selection" data-item-id="' + escapeHtml(item.item_id) + '"' + (isSelected ? ' checked' : '') + '> Select</label>' : '') + '<span class="chip ' + ((item.state || '').indexOf('warning') >= 0 ? 'warn' : '') + '">' + escapeHtml(formatLabel((isTerminal ? terminalDisplayAction(item) : (item.terminal_action || item.state || item.status)) || item.status)) + '</span><span class="chip ' + (duplicateSignals.length ? 'warn' : (String(item.verification_status || '').toLowerCase() === 'pass' ? 'ok' : '')) + '">' + escapeHtml(item.verification_status || item.status || 'unknown') + '</span></div></div>'
            + '  ' + (isTerminal ? this._terminalSummaryMarkup(item, proposedTitle) : '<div class="item-grid"><div class="summary-card"><div class="summary-label">Cleanup Policy</div><div class="summary-value">' + escapeHtml(item.cleanup_policy || 'keep') + '</div></div><div class="summary-card"><div class="summary-label">Queue Status</div><div class="summary-value">' + escapeHtml(item.status || 'queued') + '</div></div><div class="summary-card"><div class="summary-label">Suggested Title</div><div class="summary-value">' + escapeHtml(proposedTitle) + '</div></div></div>')
            + (duplicateSignals.length ? '<div class="warning-box"><div class="warning-title">Duplicate Candidate</div><div class="muted">' + escapeHtml(warningMessages(duplicateSignals).join('; ')) + '</div></div>' : '')
            + (warningsText ? '<div class="muted">Validation / note: ' + escapeHtml(warningsText) + '</div>' : '')
            + (validationActionText ? '<div class="muted">Saved review actions: ' + escapeHtml(validationActionText) + '</div>' : '')
            + (this._selectMode && canSelect ? '<div class="muted">Row actions are replaced by the shared batch toolbar while selection mode is active.</div>' : '<div class="entry-actions">' + actionButtons + '</div>')
            + '</article>';
        }, this).join('') + '</div>' : '')
      + '  </div>'
      + '</ha-card>'
      + this._renderConfirmDialog();

    var filterNode = this.shadowRoot.querySelector('#inbox-state-filter');
    if (filterNode) {
      filterNode.onchange = this._handleFilterChange.bind(this);
    }
  }
}

if (!customElements.get('model-catalog-inbox-review-card')) {
  customElements.define('model-catalog-inbox-review-card', ModelCatalogInboxReviewCard);
}
