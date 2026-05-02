var inboxShared = window.ModelCatalogIntakeShared;
if (!inboxShared) {
  throw new Error("model-catalog-intake-shared.js must load before model-catalog-inbox-review-card.js");
}

var escapeHtml = inboxShared.escapeHtml;
var basename = inboxShared.basename;
var formatLabel = inboxShared.formatLabel;
var parseDecisionWarnings = inboxShared.parseDecisionWarnings;
var warningMessages = inboxShared.warningMessages;
var duplicateWarnings = inboxShared.duplicateWarnings;
var batchActionLabel = inboxShared.batchActionLabel;
var callServiceWithResponse = inboxShared.callServiceWithResponse;
var sharedStyles = inboxShared.sharedStyles;

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
    this._workingGroups = [];
    this._stateFilter = '';
    this._selectMode = false;
    this._selectedIds = {};
    this._batchResult = null;
    this._currentView = 'active_queue'; // 'active_queue' or 'job_history'
  }

  setConfig(config) {
    this._config = Object.assign({ title: 'Inbox Review' }, config || {});
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
      var groupsResponse = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_list_working_groups', {
        limit: 200,
        offset: 0,
      });
      this._workingGroups = Array.isArray(groupsResponse.groups) ? groupsResponse.groups : [];
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
    return normalized === 'queued' || normalized === 'failed';
  }

  _canDeleteItem(item) {
    return this._canDeleteStatus(item && item.status);
  }

  async _deleteItem(itemId, status) {
    if (!this._canDeleteStatus(status)) {
      this._error = 'Delete is only allowed for queued or failed items.';
      this._render();
      return;
    }
    if (!window.confirm('Delete this intake item from the queue? This cannot be undone.')) {
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

  async _createGroup(itemId, sourcePath) {
    var title = window.prompt('Working group title', basename(sourcePath || '') || 'Working Group');
    if (!title) {
      return;
    }
    this._loading = true;
    this._error = '';
    this._status = '';
    this._render();
    try {
      await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_group_intake_item', {
        item_id: itemId,
        action: 'create_working_group',
        title: title,
        stage: 'draft',
      });
      this._status = 'Item sent to working files.';
      this._loading = false;
      await this._refresh();
    } catch (error) {
      this._error = error && error.message ? String(error.message) : 'Could not send intake item to working files.';
      this._loading = false;
      this._render();
    }
  }

  async _attachExisting(itemId) {
    var options = this._workingGroups.map(function (group) {
      return String(group.id) + ': ' + (group.title || 'Untitled Group');
    }).join('\n');
    var answer = window.prompt('Attach to existing working group. Enter the numeric group ID.\n\n' + options, this._workingGroups.length ? String(this._workingGroups[0].id) : '');
    if (!answer) {
      return;
    }
    var groupId = Number(answer);
    if (!Number.isFinite(groupId) || groupId <= 0) {
      this._error = 'A valid working group ID is required.';
      this._render();
      return;
    }
    this._loading = true;
    this._error = '';
    this._status = '';
    this._render();
    try {
      await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_group_intake_item', {
        item_id: itemId,
        action: 'attach_existing_working_group',
        working_group_id: groupId,
      });
      this._status = 'Intake item attached to existing working group.';
      this._loading = false;
      await this._refresh();
    } catch (error) {
      this._error = error && error.message ? String(error.message) : 'Could not attach intake item to working group.';
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
    var terminalStates = ['grouped_new', 'grouped_existing', 'published_to_catalog', 'rejected'];
    return this._items.filter(function (item) {
      var state = String(item.state || item.status || '').toLowerCase();
      return terminalStates.indexOf(state) >= 0;
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
      var deleteMessage = 'Delete ' + String(selectedItems.length) + ' selected intake item(s) from the queue? This cannot be undone.\n\nOnly queued/failed items can be deleted; others will be reported as skipped.';
      if (!window.confirm(deleteMessage)) {
        return;
      }
    }

    this._loading = true;
    this._error = '';
    this._status = '';
    this._batchResult = null;
    this._render();

    var results = [];
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
          results.push({
            item_id: item.item_id,
            label: basename(sourceEntry.path || item.item_id),
            outcome: 'succeeded',
            message: 'published to curated local catalog',
          });
          continue;
        }

        if (action === 'create-group') {
          var title = basename(sourceEntry.path || '') || 'Working Group';
          await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_group_intake_item', {
            item_id: item.item_id,
            action: 'create_working_group',
            title: title,
            stage: 'draft',
          });
          results.push({
            item_id: item.item_id,
            label: basename(sourceEntry.path || item.item_id),
            outcome: 'succeeded',
            message: 'sent to working files as ' + title,
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
    if (action === 'switch-view') {
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
    if (action === 'batch-validate') {
      this._runBatchAction('validate');
      return;
    }
    if (action === 'batch-publish-curated') {
      this._runBatchAction('publish-curated');
      return;
    }
    if (action === 'batch-create-group') {
      this._runBatchAction('create-group');
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
    if (action === 'create-group') {
      this._createGroup(itemId, sourcePath);
      return;
    }
    if (action === 'attach-existing') {
      this._attachExisting(itemId);
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

    this.shadowRoot.innerHTML = ''
      + '<style>' + sharedStyles + '</style>'
      + '<ha-card>'
      + '  <div class="shell">'
      + '    <div class="header"><div class="title-row"><div><div class="title">' + escapeHtml(this._config.title) + '</div><div class="subtitle">Review intake items, then publish curated, send to working files, or attach them to existing work.</div></div><div class="button-row"><button class="button" data-action="refresh-inbox">Refresh</button><button class="button ' + (this._selectMode ? 'warn' : '') + '" data-action="toggle-select-mode">' + (this._selectMode ? 'Cancel Select' : 'Select Items') + '</button></div></div>'
      + '    ' + (this._error ? '<div class="status error">' + escapeHtml(this._error) + '</div>' : '')
      + '    ' + (this._status ? '<div class="status">' + escapeHtml(this._status) + '</div>' : '')
      + '    </div>'
      + '    <section class="section"><div class="toolbar-row"><div class="button-row"><button class="button' + (this._currentView === 'active_queue' ? ' primary' : '') + '" data-action="switch-view" data-view="active_queue">Active Queue (' + String(activeQueueCount) + ')</button><button class="button' + (this._currentView === 'job_history' ? ' primary' : '') + '" data-action="switch-view" data-view="job_history">Job History (' + String(jobHistoryCount) + ')</button></div></div></section>'
      + '    ' + (this._currentView === 'active_queue' ? '<section class="toolbar-row"><div class="field"><label for="inbox-state-filter">State Filter</label><select id="inbox-state-filter" class="select"><option value="">All</option><option value="submitted"' + (this._stateFilter === 'submitted' ? ' selected' : '') + '>Submitted</option><option value="validated_ready"' + (this._stateFilter === 'validated_ready' ? ' selected' : '') + '>Validated Ready</option><option value="validated_warning"' + (this._stateFilter === 'validated_warning' ? ' selected' : '') + '>Validated Warning</option><option value="deferred"' + (this._stateFilter === 'deferred' ? ' selected' : '') + '>Deferred</option></select></div></div></section>' : '')
      + '    <section class="toolbar-row"><div class="status">Items: ' + String(visibleItems.length) + (this._selectMode ? ' / Selected: ' + String(selectedCount) : '') + '</div></section>'
      + '    ' + (this._selectMode ? '<section class="batch-toolbar"><div class="title-row"><div><div class="title">' + String(selectedCount) + ' selected</div><div class="subtitle">Batch review keeps curated publish and working-file handoff as distinct destination actions.</div></div></div><div class="button-row"><button class="button primary" data-action="batch-validate"' + (!selectedCount ? ' disabled' : '') + '>Validate</button><button class="button primary" data-action="batch-publish-curated"' + (!selectedCount ? ' disabled' : '') + '>Publish Curated</button><button class="button primary" data-action="batch-create-group"' + (!selectedCount ? ' disabled' : '') + '>Send To Working Files</button><button class="button warn" data-action="batch-defer"' + (!selectedCount ? ' disabled' : '') + '>Defer</button><button class="button danger" data-action="batch-reject"' + (!selectedCount ? ' disabled' : '') + '>Reject</button><button class="button danger" data-action="batch-delete"' + (!selectedCount ? ' disabled' : '') + '>Delete</button><button class="button" data-action="toggle-select-mode">Cancel</button></div></section>' : '')
      + '    ' + (this._batchResult ? '<section class="result-summary"><div class="title-row"><div><div class="title">Batch Result Summary</div><div class="subtitle">' + escapeHtml(batchActionLabel(this._batchResult.action)) + ' across ' + String(this._batchResult.total) + ' item(s).</div></div><button class="button" data-action="clear-batch-result">Dismiss</button></div><div class="button-row"><span class="chip ok">Succeeded ' + String(this._batchResult.succeeded) + '</span><span class="chip warn">Partial ' + String(this._batchResult.partial) + '</span><span class="chip error">Failed ' + String(this._batchResult.failed) + '</span></div><div class="entries">' + this._batchResult.results.map(function (result) { return '<div class="result-line"><span>' + escapeHtml(result.label || result.item_id) + '</span><span>' + escapeHtml(result.message || result.outcome) + '</span></div>'; }).join('') + '</div></section>' : '')
      + '    ' + (this._loading && !visibleItems.length ? '<div class="state-row">Loading inbox items...</div>' : '')
      + '    ' + (!this._loading && !visibleItems.length ? '<div class="state-row">No intake items match the current view.</div>' : '')
      + '    ' + (visibleItems.length ? '<div class="items">' + visibleItems.map(function (item) {
          var sourceEntry = item.source_entry || {};
          var warnings = parseDecisionWarnings(item);
          var warningsText = warningMessages(warnings).join('; ');
          if (!warningsText) {
            warningsText = item.decision_note || '';
          }
          var duplicateSignals = duplicateWarnings(item);
          var isSelected = !!this._selectedIds[item.item_id];
          var deleteDisabled = this._canDeleteItem(item) ? '' : ' disabled title="Only queued/failed items can be deleted"';
          var isTerminal = this._currentView === 'job_history';
          var actionButtons = isTerminal 
            ? '<button class="button" data-action="view-item" data-item-id="' + escapeHtml(item.item_id) + '">View</button><button class="button danger" data-action="delete-item" data-item-id="' + escapeHtml(item.item_id) + '" data-item-status="' + escapeHtml(item.status || '') + '"' + deleteDisabled + '>Delete</button>'
            : '<button class="button" data-action="validate-item" data-item-id="' + escapeHtml(item.item_id) + '">Validate</button><button class="button primary" data-action="publish-curated-item" data-item-id="' + escapeHtml(item.item_id) + '">Publish Curated</button><button class="button primary" data-action="create-group" data-item-id="' + escapeHtml(item.item_id) + '" data-source-path="' + escapeHtml(sourceEntry.path || '') + '">Send To Working Files</button><button class="button" data-action="attach-existing" data-item-id="' + escapeHtml(item.item_id) + '">Attach Existing</button><button class="button warn" data-action="defer-item" data-item-id="' + escapeHtml(item.item_id) + '">Defer</button><button class="button danger" data-action="reject-item" data-item-id="' + escapeHtml(item.item_id) + '">Reject</button><button class="button danger" data-action="delete-item" data-item-id="' + escapeHtml(item.item_id) + '" data-item-status="' + escapeHtml(item.status || '') + '"' + deleteDisabled + '>Delete</button>';
          return ''
            + '<article class="entry-row' + (isSelected ? ' selected' : '') + '">'
            + '  <div class="entry-top"><div><div class="entry-name">' + escapeHtml(basename(sourceEntry.path || item.item_id)) + '</div><div class="entry-path">' + escapeHtml(sourceEntry.path || item.item_id) + '</div></div><div class="button-row">' + (this._selectMode ? '<label class="selector"><input type="checkbox" data-action="toggle-item-selection" data-item-id="' + escapeHtml(item.item_id) + '"' + (isSelected ? ' checked' : '') + '> Select</label>' : '') + '<span class="chip ' + ((item.state || '').indexOf('warning') >= 0 ? 'warn' : '') + '">' + escapeHtml(formatLabel(item.state || item.status)) + '</span><span class="chip ' + (duplicateSignals.length ? 'warn' : (String(item.verification_status || '').toLowerCase() === 'pass' ? 'ok' : '')) + '">' + escapeHtml(item.verification_status || item.status || 'unknown') + '</span></div></div>'
            + '  <div class="item-grid"><div class="summary-card"><div class="summary-label">Cleanup Policy</div><div class="summary-value">' + escapeHtml(item.cleanup_policy || 'keep') + '</div></div><div class="summary-card"><div class="summary-label">Queue Status</div><div class="summary-value">' + escapeHtml(item.status || 'queued') + '</div></div></div>'
            + (duplicateSignals.length ? '<div class="warning-box"><div class="warning-title">Duplicate Candidate</div><div class="muted">' + escapeHtml(warningMessages(duplicateSignals).join('; ')) + '</div></div>' : '')
            + (warningsText ? '<div class="muted">Validation / note: ' + escapeHtml(warningsText) + '</div>' : '')
            + (this._selectMode ? '<div class="muted">Row actions are replaced by the shared batch toolbar while selection mode is active.</div>' : '<div class="entry-actions">' + actionButtons + '</div>')
            + '</article>';
        }, this).join('') + '</div>' : '')
      + '  </div>'
      + '</ha-card>';

    var filterNode = this.shadowRoot.querySelector('#inbox-state-filter');
    if (filterNode) {
      filterNode.onchange = this._handleFilterChange.bind(this);
    }
  }
}

if (!customElements.get('model-catalog-inbox-review-card')) {
  customElements.define('model-catalog-inbox-review-card', ModelCatalogInboxReviewCard);
}
