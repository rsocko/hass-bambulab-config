/**
 * Model Detail Popup Card
 * 
 * Provides a comprehensive detail view and inline editing interface for models
 * from the local catalog directly in Home Assistant UI.
 * 
 * Phase 3.0 MVP - Detail View (Read-Only)
 * - Details tab with model metadata and enrichment
 * - Media Gallery tab for photos
 * - 3D Viewer action button that opens dedicated popup
 * - Linked Prints tab showing archives linked to this model
 * 
 * Usage in browser_mod popup:
 * ```
 * service: browser_mod.popup
 * data:
 *   title: Model Name
 *   size: wide
 *   content:
 *     type: custom:model-detail-popup-card
 *     model_ref: "gridfinity-bin"
 *     model_entity: "input_text.model_catalog_sidecar_base_url"
 * ```
 */

import { setupThumbnailLazyObserver, addShimmerAnimation, getCachedThumbnailObjectUrl } from './thumbnail-lazy-loader.js?v=5';
import { addUnifiedQueueEntry } from '../common/unified-queue-api-client.js?v=1';
import { UnifiedQueueDialogController, normalizeQueueDialogTargetState, queueDialogTargetStateLabel } from '../common/unified-queue-dialog.js?v=1';

class ModelDetailPopupCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    
    // State
    this._modelRef = "";
    this._modelSidecarUrl = "";
    this._modelDetail = null;
    this._loading = false;
    this._isSaving = false;
    this._error = "";
    this._activeTab = "details";
    this._isEditMode = false;
    this._refreshingCandidates = false;
    this._archiveMetaCache = {};
    this._archiveImagePreview = null; // { archiveId, images[], index }
    this._editAdvancedSectionOpen = false;
    this._lastModifiedTimestamp = null;
    this._conflictDialog = null;
    this._showConflictDialog = false;
    this._photoGallery = [];
    this._activePhotoIndex = null;
    this._heroMediaFilter = 'all';
    this._heroActiveMediaIndex = 0;
    this._heroHiddenMediaFieldKey = 'media_hidden_ids';
    this._overflowOpen = false;
    this._panelMode = 'tabs';
    this._panelActiveTab = 'panel-queue';
    this._collapsedSections = {};
    this._popupExtensions = new Map();
    this._queueDialogController = new UnifiedQueueDialogController(this, {
      loadSourceDetail: this._loadQueueDialogSourceDetail.bind(this),
      addEntry: async ({ queueApiBase, printerId, payload }) => {
        await addUnifiedQueueEntry({ queueApiBase, printerId, payload });
      },
      afterSubmit: async () => {
        await this._loadModelDetail();
      },
      getPrinterId: () => String(this._config && this._config.queue_printer_id ? this._config.queue_printer_id : "p1"),
      getQueueApiBase: () => {
        const resolved = String(this._resolveModelSidecarUrl() || "").trim();
        return resolved ? `${resolved}/api/v1` : "";
      },
    });

    // Unified queue dialog state (#1499)
    this._queueDialogOpen = false;
    this._queueDialogMode = "quick";
    this._queueDialogModelRef = "";
    this._queueDialogModelName = "";
    this._queueDialogIntent = "add";
    this._queueDialogExistingCount = 0;
    this._queueDialogTargetState = "up_next";
    this._queueDialogNotes = "";
    this._queueDialogLoading = false;
    this._queueDialogSubmitting = false;
    this._queueDialogError = "";
    this._queueDialogFiles = [];
    
    // Render stability: prevent re-rendering during interactions
    this._isInteracting = false;
    this._renderScheduled = false;
    this._lastRenderedModelUrl = null;

    // Fullscreen overlay state
    this._overlayRoot = null;
    this._savedBodyOverflow = null;
    
    // Bound handlers
    this._boundClickHandler = this._handleClick.bind(this);
    this._boundChangeHandler = this._handleChange.bind(this);
    this._boundInputHandler = this._handleInput.bind(this);
    this._boundDragOverHandler = this._handleDragOver.bind(this);
    this._boundDragLeaveHandler = this._handleDragLeave.bind(this);
    this._boundDropHandler = this._handleDrop.bind(this);
    this._boundOverlayClickHandler = this._handleOverlayClick.bind(this);
    this._boundOverlayCancelHandler = this._handleOverlayCancel.bind(this);
    this._boundKeydownHandler = this._handleKeydown.bind(this);
  }

  setConfig(config) {
    this._config = config || {};
    this._modelRef = String(this._config.model_ref || "").trim();
    this._modelSidecarUrl = String(this._config.model_sidecar_url || "").trim();
    var requestedInitialTab = String(this._config.initial_tab || "details").trim().toLowerCase();
    if (requestedInitialTab !== "details" && requestedInitialTab !== "gallery" && requestedInitialTab !== "prints") {
      requestedInitialTab = "details";
    }
    this._activeTab = requestedInitialTab;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;

    this._modelSidecarUrl = this._resolveModelSidecarUrl();

    // Perform initial load if we haven't yet
    if (!this._modelDetail && !this._loading && !this._error && this._modelRef && this._modelSidecarUrl) {
      this._loadModelDetail();
    }

    // During edit mode, avoid re-rendering the popup on every HA state tick,
    // which can recreate the form and steal input focus.
    if (this._isEditMode) {
      const editForm = this.shadowRoot.querySelector('model-detail-edit-form');
      if (editForm) {
        editForm.hass = hass;
      }
      return;
    }

    // If we're currently interacting (clicking buttons, etc), defer render
    if (this._isInteracting) {
      this._renderScheduled = true;
      return;
    }

    // Only re-render if model data has changed
    const currentModelUrl = this._modelDetail?.model_url || '';
    if (this._lastRenderedModelUrl === currentModelUrl) {
      // Model data hasn't changed, skip re-render
      return;
    }

    this._lastRenderedModelUrl = currentModelUrl;
    this._render();
  }

  connectedCallback() {
    this.shadowRoot.addEventListener("click", this._boundClickHandler);
    this.shadowRoot.addEventListener("change", this._boundChangeHandler);
    this.shadowRoot.addEventListener("input", this._boundInputHandler);
    this.shadowRoot.addEventListener("dragover", this._boundDragOverHandler);
    this.shadowRoot.addEventListener("dragleave", this._boundDragLeaveHandler);
    this.shadowRoot.addEventListener("drop", this._boundDropHandler);
  }

  disconnectedCallback() {
    this.shadowRoot.removeEventListener("click", this._boundClickHandler);
    this.shadowRoot.removeEventListener("change", this._boundChangeHandler);
    this.shadowRoot.removeEventListener("input", this._boundInputHandler);
    this.shadowRoot.removeEventListener("dragover", this._boundDragOverHandler);
    this.shadowRoot.removeEventListener("dragleave", this._boundDragLeaveHandler);
    this.shadowRoot.removeEventListener("drop", this._boundDropHandler);
    this._destroyOverlayRoot();
  }

  _resolveModelSidecarUrl() {
    if (this._config && this._config.model_entity && this._hass && this._hass.states) {
      const configuredEntity = this._hass.states[this._config.model_entity];
      if (configuredEntity && configuredEntity.state) {
        return String(configuredEntity.state).trim();
      }
    }

    if (this._hass && this._hass.states) {
      const baseUrlEntity = this._hass.states["input_text.model_catalog_sidecar_base_url"];
      if (baseUrlEntity && baseUrlEntity.state) {
        return String(baseUrlEntity.state).trim();
      }
    }

    return String(this._config && this._config.model_sidecar_url || "").trim();
  }

  _handleClick(event) {
    let target = null;
    if (event.target instanceof Element) {
      target = event.target;
    } else if (event.composedPath) {
      target = event.composedPath().find(node => node instanceof Element) || null;
    }

    if (!target) {
      return;
    }

    // Fast path: open the file picker immediately for upload clicks.
    // Keep this before other delegated selector checks to minimize click latency.
    if (this._isEditMode && this._activeTab === 'gallery' && this._getPhotoUploadArea(target)) {
      event.preventDefault();
      this._openPhotoFilePicker();
      return;
    }

    // "+ Add Image" button — always available on the gallery tab (no edit mode required).
    if (this._activeTab === 'gallery' && target.closest('#btn-add-image')) {
      event.preventDefault();
      this._openPhotoFilePicker();
      return;
    }

    // Mark as interacting to prevent DOM re-renders during click handling
    this._isInteracting = true;

    // Use requestAnimationFrame to safely exit interaction mode after click completes
    requestAnimationFrame(() => {
      this._isInteracting = false;

      // If a render was scheduled during interaction, do it now
      if (this._renderScheduled) {
        this._renderScheduled = false;
        this._render();
      }
    });
    
    // Tab navigation
    const tabButton = target.closest('.tab-button');
    if (tabButton) {
      event.preventDefault();
      this._activeTab = tabButton.dataset.tab;
      this._isEditMode = false;
      this._render();
      return;
    }

    const overflowToggle = target.closest('#btn-overflow-toggle');
    if (overflowToggle) {
      event.preventDefault();
      this._overflowOpen = !this._overflowOpen;
      this._render();
      return;
    }

    if (!target.closest('.overflow-wrap') && this._overflowOpen) {
      this._overflowOpen = false;
      this._render();
      return;
    }

    const mediaFilterChip = target.closest('[data-media-filter]');
    if (mediaFilterChip) {
      event.preventDefault();
      this._heroMediaFilter = String(mediaFilterChip.dataset.mediaFilter || 'all');
      this._heroActiveMediaIndex = 0;
      this._render();
      return;
    }

    const mediaThumb = target.closest('[data-media-index]');
    if (mediaThumb) {
      event.preventDefault();
      const idx = Number(mediaThumb.dataset.mediaIndex);
      if (Number.isFinite(idx)) {
        this._heroActiveMediaIndex = idx;
        this._render();
      }
      return;
    }

    if (target.closest('#btn-hero-prev')) {
      event.preventDefault();
      this._stepHeroMedia(-1);
      return;
    }

    if (target.closest('#btn-hero-next')) {
      event.preventDefault();
      this._stepHeroMedia(1);
      return;
    }

    if (target.closest('#btn-hero-set-preview')) {
      event.preventDefault();
      const active = this._heroCurrentMedia(this._heroOrderMediaItems(this._heroFilteredMediaItems(this._galleryItems())));
      if (active) {
        this._handleSetHeroMediaPreview(active);
      }
      return;
    }

    if (target.closest('#btn-hero-hide-image')) {
      event.preventDefault();
      const active = this._heroCurrentMedia(this._heroOrderMediaItems(this._heroFilteredMediaItems(this._galleryItems())));
      if (active) {
        this._toggleHeroMediaHidden(active);
      }
      return;
    }

    if (target.closest('#btn-hero-delete-image')) {
      event.preventDefault();
      const active = this._heroCurrentMedia(this._heroOrderMediaItems(this._heroFilteredMediaItems(this._galleryItems())));
      if (active) {
        this._handleDeleteHeroMedia(active);
      }
      return;
    }

    // "+ Add Image" button in the hero media toolbar
    if (target.closest('#btn-hero-add-image')) {
      event.preventDefault();
      this._openHeroPhotoFilePicker();
      return;
    }

    const panelTab = target.closest('[data-panel-tab]');
    if (panelTab) {
      event.preventDefault();
      this._panelActiveTab = String(panelTab.dataset.panelTab || 'panel-queue');
      this._panelMode = 'tabs';
      this._render();
      return;
    }

    if (target.closest('#btn-panel-mode-tabs')) {
      event.preventDefault();
      this._panelMode = 'tabs';
      this._render();
      return;
    }

    if (target.closest('#btn-panel-mode-stacked')) {
      event.preventDefault();
      this._panelMode = 'stacked';
      this._render();
      return;
    }

    const collapseToggle = target.closest('[data-collapse-toggle]');
    if (collapseToggle) {
      event.preventDefault();
      const sectionId = String(collapseToggle.dataset.collapseToggle || '').trim();
      if (sectionId) {
        this._collapsedSections[sectionId] = !this._collapsedSections[sectionId];
        this._render();
      }
      return;
    }

    // Edit button (Phase 3.1)
    if (target.closest("#btn-edit") || target.closest("#btn-manage-photos")) {
      event.preventDefault();
      if (this._activeTab === "details" || this._activeTab === "gallery") {
        this._toggleEditMode();
      }
      return;
    }

    // Save button (Phase 3.1)
    if (target.closest("#btn-save")) {
      event.preventDefault();
      this._handleSaveEdits();
      return;
    }

    // Cancel button (Phase 3.1)
    if (target.closest("#btn-cancel")) {
      event.preventDefault();
      this._isEditMode = false;
      this._render();
      return;
    }

    if (target.closest("#btn-done")) {
      event.preventDefault();
      this._isEditMode = false;
      this._render();
      return;
    }

    // Download button
    if (target.closest("#btn-download")) {
      event.preventDefault();
      this._handleDownload();
      return;
    }

    // Print button — opens unified queue dialog (#1499)
    if (target.closest("#btn-print")) {
      event.preventDefault();
      this._handlePrint();
      return;
    }

    // Queue dialog actions (#1499)
    if (target.classList && target.classList.contains("queue-dialog-backdrop")) {
      event.preventDefault();
      this._closeQueueDialog();
      return;
    }
    const qdAction = target.getAttribute ? target.getAttribute("data-action") : null;
    if (qdAction === "close-queue-dialog") {
      event.preventDefault();
      this._closeQueueDialog();
      return;
    }
    if (qdAction === "queue-dialog-mode") {
      event.preventDefault();
      this._setQueueDialogMode(target.getAttribute("data-mode") || "quick");
      return;
    }
    if (qdAction === "queue-dialog-submit") {
      event.preventDefault();
      this._submitQueueDialog();
      return;
    }
    if (qdAction === "queue-dialog-select-all") {
      event.preventDefault();
      this._setQueueDialogAllPlatesSelected(true);
      return;
    }
    if (qdAction === "queue-dialog-clear-all") {
      event.preventDefault();
      this._setQueueDialogAllPlatesSelected(false);
      return;
    }
    if (qdAction === "queue-dialog-toggle-file") {
      event.preventDefault();
      this._toggleQueueDialogFileSelection(target.getAttribute("data-file-id") || "");
      return;
    }
    if (qdAction === "queue-dialog-toggle-plate") {
      event.preventDefault();
      this._toggleQueueDialogPlateSelection(target.getAttribute("data-file-id") || "", target.getAttribute("data-plate-id") || "");
      return;
    }

    // Source panel: URL action buttons (add, remove, open)
    const urlActionBtn = target.closest('.url-action-btn[data-action]');
    if (urlActionBtn) {
      event.preventDefault();
      const urlAction = urlActionBtn.getAttribute("data-action");
      const urlIndex = parseInt(urlActionBtn.getAttribute("data-url-index") || "0", 10);
      if (urlAction === "add-source-url") {
        this._addSourceUrl();
      } else if (urlAction === "remove-source-url") {
        this._removeSourceUrl(urlIndex);
      } else if (urlAction === "open-source-url") {
        this._openSourceUrl(urlIndex);
      }
      return;
    }

    // Source panel: custom label blur save
    if (target.classList.contains('source-label-input')) {
      // blur is not a click, but let's capture it in case user tabs away
    }

    // Contribution lifecycle actions (#1494)
    const contributionActionBtn = target.closest('.action-mark[data-action], .action-skip[data-action], .action-open[data-action]');
    if (contributionActionBtn) {
      event.preventDefault();
      const action = contributionActionBtn.getAttribute("data-action");
      const isSkip = contributionActionBtn.classList.contains('action-skip');
      if (action === "rated" || action === "boosted" || action === "photos_shared") {
        this._markContributionAction(action, isSkip ? { skip: true } : undefined);
      } else if (action === "open-gallery") {
        this._openPhotoGallery();
      }
      return;
    }

    // 3D viewer button
    if (target.closest("#btn-viewer")) {
      event.preventDefault();
      this._openViewerPopup();
      return;
    }

    // Fullscreen expand button (hero media)
    if (target.closest('.icon-action.expand')) {
      event.preventDefault();
      const items = this._heroOrderMediaItems(this._heroFilteredMediaItems(this._galleryItems()));
      if (items.length) {
        this._activePhotoIndex = this._heroActiveMediaIndex;
        this._openPhotoOverlay();
      }
      return;
    }

    // Conflict dialog buttons
    if (target.closest("#btn-conflict-cancel")) {
      event.preventDefault();
      this._handleConflictResolution('cancel');
      return;
    }

    if (target.closest("#btn-conflict-reload")) {
      event.preventDefault();
      this._handleConflictResolution('reload');
      return;
    }

    if (target.closest("#btn-conflict-overwrite")) {
      event.preventDefault();
      this._handleConflictResolution('overwrite');
      return;
    }

    // Gallery photo actions
    const photoBtn = target.closest('[data-action]');
    if (photoBtn && this._activeTab === 'gallery') {
      const photoTile = photoBtn.closest('.gallery-thumbnail');
      if (!photoTile) {
        return;
      }
      event.preventDefault();
      const action = photoBtn.dataset.action;
      const photoId = photoTile.dataset.photoId;
      const photoIdx = parseInt(photoTile.dataset.photoIndex, 10);
      
      if (action === 'preview') {
        this._handlePhotoPreview(photoIdx);
      } else if (action === 'set-preview') {
        this._handleSetPhotoPreview(photoId);
      } else if (action === 'delete') {
        this._handleDeletePhoto(photoId);
      }
      return;
    }

  }

  _openPhotoFilePicker() {
    const fileInput = this.shadowRoot.getElementById('photo-file-input');
    if (!fileInput) {
      return;
    }

    if (typeof fileInput.showPicker === 'function') {
      try {
        fileInput.showPicker();
        return;
      } catch (_error) {
        // Fall through to click() for browsers that block showPicker here.
      }
    }

    fileInput.click();
  }

  _openHeroPhotoFilePicker() {
    const fileInput = this.shadowRoot.getElementById('hero-photo-file-input');
    if (!fileInput) {
      return;
    }

    if (typeof fileInput.showPicker === 'function') {
      try {
        fileInput.showPicker();
        return;
      } catch (_error) {
        // Fall through to click() for browsers that block showPicker here.
      }
    }

    fileInput.click();
  }

  _handleChange(event) {
    const target = event.target;
    // Queue dialog: target-state select
    if (target instanceof HTMLSelectElement && target.classList.contains("queue-dialog-target-state")) {
      this._queueDialogTargetState = this._normalizeQueueDialogTargetState(String(target.value || "up_next"));
      return;
    }
    // Source panel: publication source dropdown
    if (target instanceof HTMLSelectElement && target.classList.contains("source-select")) {
      this._saveSourceField("publication_source", target.value);
      return;
    }
    // Queue dialog: notes textarea (also handle input event via _handleInput if present)
    if (target instanceof HTMLTextAreaElement && target.getAttribute("data-queue-dialog-notes")) {
      this._queueDialogNotes = String(target.value || "");
      return;
    }
    if (!(target instanceof HTMLInputElement)) {
      return;
    }
    // Source panel: source URL edit (on blur/change)
    if (target.classList.contains("source-url-input")) {
      const idx = parseInt(target.getAttribute("data-source-url-index") || "0", 10);
      this._updateSourceUrl(idx, target.value);
      return;
    }
    // Source panel: custom label (on blur/change)
    if (target.classList.contains("source-label-input")) {
      this._saveSourceField("source_platform_label", target.value);
      return;
    }
    if (target.id !== 'photo-file-input' && target.id !== 'hero-photo-file-input') {
      return;
    }

    const selectedFiles = Array.from(target.files || []);
    target.value = '';
    this._handlePhotoFileSelect(selectedFiles);
  }

  _handleInput(event) {
    const target = event.target;
    if (target instanceof HTMLTextAreaElement && target.getAttribute("data-queue-dialog-notes")) {
      this._queueDialogNotes = String(target.value || "");
    }
    // Source panel: custom label live update (save on blur via change)
    if (target instanceof HTMLInputElement && target.classList.contains("source-label-input")) {
      // Debounce save — we'll save on change/blur handled above
    }
  }

  _getPhotoUploadArea(target) {
    if (!(target instanceof Element)) {
      return null;
    }
    return target.closest('#photo-upload-area');
  }

  _setPhotoUploadDragState(isActive) {
    const uploadArea = this.shadowRoot.getElementById('photo-upload-area');
    if (!uploadArea) {
      return;
    }
    uploadArea.style.background = isActive ? 'rgba(33, 150, 243, 0.12)' : 'transparent';
    uploadArea.style.borderColor = isActive ? 'var(--primary-color)' : 'var(--divider-color)';
  }

  _handleDragOver(event) {
    const uploadArea = this._getPhotoUploadArea(event.target);
    if (!uploadArea || !this._isEditMode || this._activeTab !== 'gallery') {
      return;
    }

    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'copy';
    }
    this._setPhotoUploadDragState(true);
  }

  _handleDragLeave(event) {
    const uploadArea = this._getPhotoUploadArea(event.target);
    if (!uploadArea) {
      return;
    }

    const relatedTarget = event.relatedTarget;
    if (relatedTarget instanceof Node && uploadArea.contains(relatedTarget)) {
      return;
    }
    this._setPhotoUploadDragState(false);
  }

  _handleDrop(event) {
    const uploadArea = this._getPhotoUploadArea(event.target);
    if (!uploadArea || !this._isEditMode || this._activeTab !== 'gallery') {
      return;
    }

    event.preventDefault();
    this._setPhotoUploadDragState(false);

    const files = event.dataTransfer?.files;
    if (!files || files.length === 0) {
      return;
    }

    this._handlePhotoFileSelect(Array.from(files));
  }

  async _loadModelDetail({ silent = false } = {}) {
    if (this._loading) return;
    
    this._loading = true;
    this._error = "";
    // Only show loading spinner on initial load, not background refreshes
    if (!silent) {
      this._render();
    }
    
    try {
      const url = `${this._modelSidecarUrl}/api/models/${encodeURIComponent(this._modelRef)}/detail`;
      const response = await fetch(url);
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      this._modelDetail = await response.json();
      
      if (!this._modelDetail.success) {
        throw new Error(this._modelDetail.error || "Failed to fetch model detail");
      }
    } catch (error) {
      this._error = String(error || "Unknown error");
      this._modelDetail = null;
    } finally {
      this._loading = false;
      this._render();
    }
  }

  _render() {
    const html = this._loading
      ? this._renderLoading()
      : this._error
      ? this._renderError()
      : this._modelDetail
      ? this._renderPopup()
      : this._renderEmpty();
    
    this.shadowRoot.innerHTML = html;

    addShimmerAnimation();
    // Re-run observer wiring on each render when lazy nodes are present.
    // The popup DOM is rebuilt often; one-time setup can leave new nodes unloaded.
    const hasLazyThumbnailNode = !!(this.shadowRoot && this.shadowRoot.querySelector('img[data-thumbnail-lazy-url]'));
    if (hasLazyThumbnailNode && this.shadowRoot) {
      setupThumbnailLazyObserver({
        rootElement: this.shadowRoot,
        root: null,
        rootMargin: '50px',
        threshold: 0.1,
      });
    }

    // Initialize in-tab edit form after rendering.
    if (this._isEditMode && this._modelDetail && this._modelDetail.model) {
      this._initializeEditForm();
    }
  }

  _isThumbnailLazyEndpoint(url) {
    const value = String(url || '').trim();
    return value.includes('/api/models/') && value.endsWith('/thumbnail');
  }

  _normalizeModelApiUrl(url) {
    const value = String(url || '').trim();
    if (!value) {
      return '';
    }
    if (!value.startsWith('/api/models/')) {
      return value;
    }
    const base = String(this._modelSidecarUrl || '').trim().replace(/\/$/, '');
    if (!base) {
      return value;
    }
    return `${base}${value}`;
  }

  _headerThumbnailUrl(model) {
    const previewUrl = this._normalizeModelApiUrl(String(model && model.preview_url ? model.preview_url : '').trim());
    if (previewUrl) {
      return previewUrl;
    }
    const files = Array.isArray(model && model.files)
      ? model.files
      : (Array.isArray(this._modelDetail && this._modelDetail.files) ? this._modelDetail.files : []);
    for (const file of files) {
      if (!file || typeof file !== 'object') {
        continue;
      }
      const candidate = this._normalizeModelApiUrl(String(file.thumbnail_lazy_url || file.thumbnail_url || file.preview_url || '').trim());
      if (candidate) {
        return candidate;
      }
    }
    return '';
  }

  _renderLoading() {
    return `
      <style>
        .popup { padding: 24px; text-align: center; }
        .spinner { 
          display: inline-block; 
          width: 32px; 
          height: 32px; 
          border: 3px solid #e0e0e0; 
          border-top-color: #2196F3; 
          border-radius: 50%; 
          animation: spin 0.8s linear infinite; 
        }
        @keyframes spin { to { transform: rotate(360deg); } }
      </style>
      <div class="popup">
        <div class="spinner"></div>
        <p>Loading model detail...</p>
      </div>
    `;
  }

  _renderError() {
    return `
      <style>
        .popup { padding: 24px; }
        .error-message { 
          background: #ffebee; 
          border: 1px solid #ef5350; 
          border-radius: 4px; 
          padding: 16px; 
          color: #c62828; 
        }
      </style>
      <div class="popup">
        <div class="error-message">
          <strong>Error loading model detail:</strong><br>
          ${this._error}
        </div>
      </div>
    `;
  }

  _renderEmpty() {
    return `
      <style>
        .popup { padding: 24px; text-align: center; color: #999; }
      </style>
      <div class="popup">
        <p>No model detail available</p>
      </div>
    `;
  }

  _renderPopup() {
    const model = this._modelDetail.model || {};
    const allGalleryItems = this._galleryItems();
    const mediaCounts = {
      all: allGalleryItems.length,
      asset: allGalleryItems.filter(item => String(item && item.type || '').toLowerCase() === 'asset').length,
      embedded: allGalleryItems.filter(item => String(item && item.type || '').toLowerCase() === 'embedded').length,
    };
    const mediaItems = this._heroOrderMediaItems(this._heroFilteredMediaItems(allGalleryItems));
    const activeMedia = this._heroCurrentMedia(mediaItems);
    const creator = this._escapeHtml(String(model.creator_name || 'Unknown'));
    const collections = Array.isArray(model.collection_names) ? model.collection_names : [];
    const collectionText = this._escapeHtml(collections.length ? collections.join(' / ') : 'Uncategorized');
    const entityType = this._getEntityType(model);
    const isIdea = entityType === 'idea';

    return `
      <style>
        * { box-sizing: border-box; }
        .popup-shell {
          display: grid;
          gap: 4px;
          margin-top: -12px;
          color: var(--primary-text-color);
          font-family: var(--mdc-typography-font-family, 'Roboto', sans-serif);
          background: var(--card-background-color);
          overflow-y: auto;
          max-height: calc(100vh - 120px);
        }
        .topbar {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 8px;
          flex-wrap: wrap;
          border-bottom: 1px solid var(--divider-color);
          padding: 0 10px 4px;
        }
        .title { display: flex; align-items: center; }
        .title span { color: var(--secondary-text-color); font-size: 11px; line-height: 1.2; }
        .entity-type-badge {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          border: 1px solid var(--divider-color);
          border-radius: 999px;
          padding: 4px 10px;
          font-size: 11px;
          font-weight: 600;
          background: var(--card-background-color);
          color: var(--secondary-text-color);
        }
        .entity-type-badge.idea {
          border-color: #ffc107;
          color: #ffc107;
        }
        .top-actions { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
        .top-actions .action-button {
          padding: 6px 10px;
          border-radius: 7px;
          font-size: 11px;
        }
        .action-button {
          background: var(--primary-color);
          color: var(--text-primary-color);
          border: none;
          border-radius: 8px;
          padding: 7px 12px;
          font-size: 12px;
          cursor: pointer;
        }
        .action-button.ghost {
          background: var(--secondary-background-color);
          color: var(--primary-text-color);
        }
        .queue-dialog-backdrop{position:fixed;inset:0;z-index:30;display:flex;align-items:center;justify-content:center;padding:20px;background:rgba(2,6,23,0.72);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);}
        .queue-dialog{width:min(680px,calc(100vw - 32px));max-height:calc(100vh - 40px);display:grid;grid-template-rows:auto auto minmax(0,1fr) auto;overflow:hidden;border-radius:20px;border:1px solid var(--line-strong);background:rgba(15,23,42,0.97);box-shadow:0 24px 48px rgba(2,6,23,0.42);}
        .queue-dialog-header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:18px 20px 14px;border-bottom:1px solid rgba(148,163,184,0.18);}
        .queue-dialog-header h3{margin:0;font-size:18px;font-weight:800;}
        .queue-dialog-subtitle{margin-top:4px;font-size:12px;color:var(--secondary-text-color);}
        .queue-dialog-tabs{display:flex;gap:8px;padding:12px 20px;border-bottom:1px solid rgba(148,163,184,0.16);}
        .queue-dialog-tab{min-height:34px;padding:0 14px;border-radius:999px;border:1px solid rgba(148,163,184,0.22);background:rgba(15,23,42,0.16);color:var(--secondary-text-color);font-size:12px;font-weight:800;cursor:pointer;}
        .queue-dialog-tab.active{background:rgba(96,165,250,0.18);border-color:rgba(96,165,250,0.34);color:var(--primary-text-color);}
        .queue-dialog-body{display:grid;gap:12px;padding:18px 20px;overflow:auto;}
        .queue-dialog-summary,.queue-dialog-existing-note,.queue-dialog-note,.queue-dialog-metrics{padding:12px 14px;border-radius:14px;border:1px solid rgba(148,163,184,0.18);background:rgba(148,163,184,0.08);font-size:13px;line-height:1.45;}
        .queue-dialog-existing-note{background:rgba(96,165,250,0.12);border-color:rgba(96,165,250,0.24);color:#dbeafe;}
        .queue-dialog-field{display:grid;gap:6px;}
        .queue-dialog-field span{font-size:11px;font-weight:800;color:var(--secondary-text-color);text-transform:uppercase;letter-spacing:.04em;}
        .queue-dialog-target-state,.queue-dialog-notes{width:100%;box-sizing:border-box;border-radius:12px;border:1px solid rgba(148,163,184,0.26);background:rgba(15,23,42,0.16);color:var(--primary-text-color);padding:10px 12px;font:inherit;}
        .queue-dialog-target-state{appearance:none;-webkit-appearance:none;color-scheme:dark;background-color:rgba(15,23,42,0.92);}
        .queue-dialog-target-state:focus{outline:none;border-color:rgba(96,165,250,0.46);box-shadow:0 0 0 1px rgba(96,165,250,0.26);}
        .queue-dialog-target-state option{background-color:rgba(15,23,42,0.98);color:var(--primary-text-color);}
        .queue-dialog-toolbar{display:flex;gap:8px;flex-wrap:wrap;}
        .queue-dialog-file-list{display:grid;gap:10px;}
        .queue-dialog-file-block{display:grid;gap:8px;padding:12px;border-radius:16px;border:1px solid rgba(148,163,184,0.18);background:rgba(15,23,42,0.12);}
        .queue-dialog-file-toggle,.queue-dialog-plate-toggle{display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:38px;padding:0 12px;border-radius:12px;border:1px solid rgba(148,163,184,0.20);background:rgba(15,23,42,0.14);color:var(--primary-text-color);font-size:12px;font-weight:700;cursor:pointer;text-align:left;}
        .queue-dialog-file-toggle span{font-size:11px;color:var(--secondary-text-color);font-weight:700;}
        .queue-dialog-file-toggle.active,.queue-dialog-plate-toggle.active{background:rgba(96,165,250,0.18);border-color:rgba(96,165,250,0.34);}
        .queue-dialog-plates{display:grid;gap:8px;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));}
        .queue-dialog-error{padding:12px 14px;border-radius:14px;border:1px solid rgba(248,113,113,0.32);background:rgba(127,29,29,0.22);color:#fecaca;font-size:13px;}
        .queue-dialog-footer{display:flex;align-items:center;justify-content:flex-end;gap:10px;padding:14px 20px 18px;border-top:1px solid rgba(148,163,184,0.16);}
        .queue-dialog-submit{background:rgba(96,165,250,0.22);border-color:rgba(96,165,250,0.34);}
        .overflow-wrap { position: relative; }
        .overflow-menu {
          position: absolute;
          right: 0;
          top: calc(100% + 4px);
          min-width: 270px;
          border: 1px solid var(--divider-color);
          border-radius: 10px;
          background: var(--card-background-color);
          box-shadow: 0 8px 24px rgba(0,0,0,0.2);
          padding: 8px;
          z-index: 10;
          display: none;
        }
        .overflow-menu.open { display: grid; gap: 6px; }
        .overflow-row {
          border: 1px solid var(--divider-color);
          border-radius: 8px;
          padding: 8px;
          background: var(--secondary-background-color);
        }
        .overflow-row .label { font-size: 12px; font-weight: 600; }
        .overflow-row .meta { font-size: 10px; color: var(--secondary-text-color); margin-top: 3px; }

        .hero {
          display: grid;
          grid-template-columns: 1fr 1fr;
          align-items: start;
        }
        .left {
          border-right: 1px solid var(--divider-color);
          display: grid;
          grid-template-rows: auto auto auto;
          overflow-y: auto;
        }
        .media-with-thumbs {
          display: flex;
          gap: 0;
          min-height: 0;
        }
        .media-with-thumbs .main-media {
          flex: 1 1 0%;
          min-width: 0;
        }
        .media-toolbar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
          padding: 6px 12px;
          flex-wrap: wrap;
        }
        .media-filters {
          display: flex;
          gap: 6px;
          flex-wrap: wrap;
          align-items: center;
        }
        .chip {
          border: 1px solid var(--divider-color);
          border-radius: 999px;
          padding: 4px 8px;
          font-size: 11px;
          color: var(--secondary-text-color);
          background: var(--card-background-color);
          cursor: pointer;
        }
        .chip.active {
          border-color: var(--primary-color);
          color: var(--primary-text-color);
        }
        .main-media {
          margin: 12px;
          border: 1px solid var(--divider-color);
          border-radius: 12px;
          overflow: hidden;
          position: relative;
          min-height: 180px;
          max-height: 320px;
          background: var(--secondary-background-color);
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .main-media img {
          width: 100%;
          max-height: 420px;
          object-fit: contain;
          display: block;
        }
        .main-media .badge {
          position: absolute;
          top: 10px;
          left: 10px;
          border-radius: 999px;
          border: 1px solid var(--divider-color);
          background: rgba(0, 0, 0, 0.55);
          color: #fff;
          font-size: 10px;
          padding: 4px 9px;
          font-weight: 600;
        }
        .main-overlay-tools {
          position: absolute;
          right: 10px;
          top: 10px;
          display: flex;
          gap: 6px;
        }
        .icon-action {
          position: static;
          width: 32px;
          height: 32px;
          border: 1px solid rgba(148,163,184,0.28);
          border-radius: 999px;
          background: rgba(15,23,42,0.78);
          color: var(--primary-text-color);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 2;
          flex: 0 0 auto;
          transition: background .16s ease,color .16s ease,box-shadow .16s ease,border-color .16s ease,transform .16s ease;
        }
        .icon-action:hover,
        .icon-action:focus-visible {
          background: rgba(30,41,59,0.96);
          color: var(--primary-text-color);
          border-color: rgba(148,163,184,0.54);
          box-shadow: 0 0 0 1px rgba(255,255,255,0.16),0 8px 20px rgba(15,23,42,0.22);
          transform: translateY(-1px);
          outline: none;
        }
        .icon-action:active { transform: translateY(0); }
        .icon-action.viewer {
          background: rgba(20,83,45,0.22);
          border-color: rgba(34,197,94,0.28);
          color: var(--primary-text-color);
        }
        .icon-action.viewer:hover,
        .icon-action.viewer:focus-visible {
          background: rgba(20,83,45,0.34);
          color: var(--primary-text-color);
          border-color: rgba(34,197,94,0.46);
          box-shadow: 0 0 0 1px rgba(34,197,94,0.18),0 8px 20px rgba(20,83,45,0.22);
          transform: translateY(-1px);
          outline: none;
        }
        .icon-action.viewer:active { transform: translateY(0); }
        .icon-action.expand {
          background: rgba(30,64,175,0.24);
          border-color: rgba(96,165,250,0.3);
          color: var(--primary-text-color);
        }
        .icon-action.expand:hover,
        .icon-action.expand:focus-visible {
          background: rgba(30,64,175,0.36);
          color: var(--primary-text-color);
          border-color: rgba(96,165,250,0.48);
          box-shadow: 0 0 0 1px rgba(96,165,250,0.18),0 8px 20px rgba(30,64,175,0.22);
          transform: translateY(-1px);
          outline: none;
        }
        .icon-action.expand:active { transform: translateY(0); }
        .icon-action ha-icon { --mdc-icon-size: 18px; }
        .main-nav-btn {
          position: absolute;
          top: 50%;
          transform: translateY(-50%);
          width: 42px;
          height: 42px;
          border-radius: 999px;
          border: 1px solid var(--divider-color);
          background: rgba(0, 0, 0, 0.55);
          color: #fff;
          font-size: 22px;
          line-height: 1;
          padding: 0;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          backdrop-filter: blur(10px);
        }
        .main-nav-btn[disabled] {
          opacity: 0.45;
          cursor: default;
        }
        .main-nav-btn.prev { left: 10px; }
        .main-nav-btn.next { right: 10px; }
        .media-actions {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
          align-items: center;
        }
        .media-actions .action-button {
          appearance: none;
          border: 1px solid rgba(148,163,184,0.32);
          border-radius: 999px;
          padding: 8px 12px;
          background: rgba(255,255,255,0.04);
          color: var(--primary-text-color);
          font-size: 12px;
          font-weight: 700;
          cursor: pointer;
          white-space: nowrap;
          transition: background .16s ease,color .16s ease,box-shadow .16s ease,border-color .16s ease;
        }
        .media-actions .action-button:hover,
        .media-actions .action-button:focus-visible {
          background: rgba(255,255,255,0.10);
          border-color: rgba(148,163,184,0.6);
          box-shadow: 0 0 0 1px rgba(255,255,255,0.14),0 4px 10px rgba(15,23,42,0.12);
          outline: none;
        }
        .media-actions .action-button.danger {
          background: rgba(239,68,68,0.08);
          border-color: rgba(239,68,68,0.28);
        }
        .media-actions .action-button[disabled] {
          opacity: 0.55;
          cursor: not-allowed;
          box-shadow: none;
        }
        .thumbs {
          flex: 0 0 88px;
          padding: 12px 6px;
          display: flex;
          flex-direction: column;
          gap: 7px;
          overflow-y: auto;
          overflow-x: hidden;
          scrollbar-width: thin;
          max-height: 400px;
          border-left: 1px solid var(--divider-color);
        }
        .thumb {
          flex: 0 0 72px;
          width: 72px;
          height: 72px;
          border: 1px solid var(--divider-color);
          border-radius: 9px;
          overflow: hidden;
          background: var(--secondary-background-color);
          cursor: pointer;
          position: relative;
        }
        .thumb img { width: 100%; height: 100%; object-fit: cover; }
        .thumb.active { border-color: var(--primary-color); }
        .thumb .src {
          position: absolute;
          left: 3px;
          bottom: 3px;
          font-size: 9px;
          padding: 2px 5px;
          border-radius: 999px;
          background: rgba(0,0,0,0.62);
          color: #fff;
        }
        .thumb.media-hidden {
          opacity: 0.72;
          order: 999;
        }
        .thumb .hidden-mark {
          position: absolute;
          top: 3px;
          right: 3px;
          width: 16px;
          height: 16px;
          border-radius: 999px;
          background: rgba(127,29,29,0.92);
          color: #fff;
          font-size: 10px;
          font-weight: 700;
          line-height: 16px;
          text-align: center;
        }

        .panel-shell {
          margin: 0 12px 12px;
          border: 1px solid var(--divider-color);
          border-radius: 12px;
          overflow: hidden;
          background: var(--secondary-background-color);
        }
        .panel-toolbar {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 8px;
          flex-wrap: wrap;
          border-bottom: 1px solid var(--divider-color);
          padding: 8px 10px;
        }
        .view-mode {
          display: inline-flex;
          border: 1px solid var(--divider-color);
          border-radius: 999px;
          overflow: hidden;
        }
        .view-mode button {
          border: 0;
          background: transparent;
          color: var(--secondary-text-color);
          padding: 5px 10px;
          font-size: 11px;
          cursor: pointer;
        }
        .view-mode button.active {
          background: var(--card-background-color);
          color: var(--primary-text-color);
        }
        .tabs {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          border-bottom: 1px solid var(--divider-color);
          padding: 9px 10px 0;
        }
        .tabs button {
          border: 1px solid transparent;
          border-bottom: 0;
          border-radius: 10px 10px 0 0;
          padding: 7px 10px;
          background: var(--card-background-color);
          color: var(--secondary-text-color);
          cursor: pointer;
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }
        .tabs button.active {
          color: var(--primary-text-color);
          border-color: var(--divider-color);
          box-shadow: inset 0 -2px 0 var(--primary-color);
        }
        .count {
          border: 1px solid var(--divider-color);
          border-radius: 999px;
          padding: 1px 6px;
          font-size: 10px;
        }
        .tab-panel {
          display: none;
          padding: 10px;
        }
        .tab-panel.active { display: block; }
        .stacked .tabs { display: none; }
        .stacked .tab-panel {
          display: block;
          border-bottom: 1px solid var(--divider-color);
        }
        .stacked .tab-panel:last-child { border-bottom: 0; }

        .queue-list, .related-list, .support-list { display: grid; gap: 7px; }
        .queue-row, .related, .support {
          border: 1px solid var(--divider-color);
          border-radius: 9px;
          background: var(--card-background-color);
          padding: 8px;
          font-size: 12px;
        }
        .detail { color: var(--secondary-text-color); font-size: 11px; margin-top: 3px; }

        .right {
          padding: 12px;
          display: grid;
          grid-template-rows: auto auto 1fr;
          gap: 10px;
          overflow: visible;
        }
        .card {
          border: 1px solid var(--divider-color);
          border-radius: 12px;
          overflow: hidden;
          background: var(--secondary-background-color);
        }
        .card .h {
          border-bottom: 1px solid var(--divider-color);
          background: var(--card-background-color);
          padding: 8px 10px;
          font-size: 12px;
          text-transform: uppercase;
          letter-spacing: 0.03em;
          color: var(--secondary-text-color);
          font-weight: 700;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .refresh-candidates-btn {
          background: none;
          border: 1px solid transparent;
          border-radius: 6px;
          cursor: pointer;
          padding: 4px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          color: var(--secondary-text-color);
          transition: background 0.2s, border-color 0.2s, color 0.2s;
          --mdc-icon-size: 20px;
        }
        .refresh-candidates-btn:hover:not([disabled]) {
          background: var(--secondary-background-color, rgba(255,255,255,0.08));
          border-color: var(--divider-color);
          color: var(--primary-text-color);
        }
        .refresh-candidates-btn:active:not([disabled]) {
          background: var(--divider-color);
        }
        .refresh-candidates-btn[disabled] {
          cursor: default;
          opacity: 0.7;
        }
        .refresh-candidates-btn ha-icon {
          display: block;
        }
        .refresh-candidates-btn.spinning ha-icon {
          animation: spin 1s linear infinite;
        }
        .refresh-candidates-btn.done ha-icon {
          color: var(--success-color, #4CAF50);
        }
        .summary { padding: 10px; display: grid; gap: 8px; }
        .summary .name { font-size: 15px; font-weight: 700; }
        .summary .meta { color: var(--secondary-text-color); font-size: 12px; }
        .status { display: flex; gap: 6px; flex-wrap: wrap; }
        .status span {
          border: 1px solid var(--divider-color);
          border-radius: 999px;
          padding: 4px 8px;
          font-size: 10px;
          color: var(--secondary-text-color);
          background: var(--card-background-color);
        }
        .files { padding: 8px; display: grid; gap: 7px; }
        .card[data-slot="sections:archive-linkage"] > .files {
          max-height: 420px;
          overflow-y: auto;
          scrollbar-width: thin;
        }
        .file-preview { width: 40px; height: 40px; border-radius: 6px; border: 1px solid var(--divider-color); object-fit: cover; flex-shrink: 0; }
        .file-ext-badge { width: 40px; height: 40px; border-radius: 6px; border: 1px solid rgba(148,163,184,0.25); display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 800; color: var(--secondary-text-color); background: rgba(255,255,255,0.04); flex-shrink: 0; }
        .file-ext-badge.x-3mf { color: #5eead4; border-color: rgba(94,234,212,0.3); background: rgba(94,234,212,0.12); }
        .file-ext-badge.x-stl, .file-ext-badge.x-step, .file-ext-badge.x-stp, .file-ext-badge.x-obj { color: #93c5fd; border-color: rgba(96,165,250,0.32); background: rgba(96,165,250,0.12); }
        .collapsible-group {
          border: 1px solid var(--divider-color);
          border-radius: 9px;
          overflow: hidden;
          background: var(--card-background-color);
        }
        .collapse-toggle {
          width: 100%;
          border: 0;
          background: transparent;
          padding: 8px;
          display: grid;
          grid-template-columns: minmax(0, 1fr) auto;
          text-align: left;
          cursor: pointer;
          gap: 8px;
        }
        .collapse-body {
          padding: 8px;
          border-top: 1px solid var(--divider-color);
          font-size: 11px;
          color: var(--secondary-text-color);
        }
        .hidden { display: none !important; }
        .state {
          font-size: 10px;
          border: 1px solid var(--divider-color);
          border-radius: 999px;
          padding: 3px 7px;
          margin-right: 4px;
        }

        @media (max-width: 980px) {
          .hero { grid-template-columns: 1fr; align-items: stretch; }
          .card[data-slot="sections:archive-linkage"] > .files { max-height: none; }
          .left { border-right: 0; border-bottom: 1px solid var(--divider-color); }
          .media-with-thumbs { flex-direction: column; }
          .thumbs {
            flex: 0 0 auto;
            flex-direction: row;
            max-height: none;
            overflow-x: auto;
            overflow-y: hidden;
            border-left: 0;
            border-top: 1px solid var(--divider-color);
            padding: 6px 12px;
          }
          .thumb { flex: 0 0 72px; }
          .panel-shell { margin-bottom: 0; }
          .main-media { max-height: 260px; }
        }
      </style>

      <div class="popup-shell">
        <div class="topbar">
          <div class="title">
            <span>Creator ${creator} | Collection ${collectionText}</span>
          </div>
          <div class="top-actions">
            ${isIdea ? `<span class="entity-type-badge idea">💡 Idea</span>` : ''}
            ${this._renderExtensionSlot('actions:top-bar', '')}
            ${isIdea ? '' : '<button class="action-button ghost" id="btn-viewer">3D View</button>'}
            ${isIdea ? '' : '<button class="action-button ghost" id="btn-download">Download</button>'}
            ${isIdea ? '' : '<button class="action-button" id="btn-print">Print</button>'}
            <div class="overflow-wrap">
              <button class="action-button ghost" id="btn-overflow-toggle">More</button>
              <div class="overflow-menu ${this._overflowOpen ? 'open' : ''}">
                ${this._renderExtensionSlot('actions:overflow', `
                  <div class="overflow-row">
                    <div class="label">Recover Print History wizard</div>
                    <div class="meta">Extension host for #1483 backfill flow</div>
                  </div>
                  <div class="overflow-row">
                    <div class="label">Contribution lifecycle shortcut</div>
                    <div class="meta">Extension host for #1494</div>
                  </div>
                  <div class="overflow-row">
                    <div class="label">Publication pipeline shortcut</div>
                    <div class="meta">Extension host for #1495</div>
                  </div>
                `)}
              </div>
            </div>
          </div>
        </div>

        <div class="hero">
          <div class="left">
            ${this._renderExtensionSlot('hero-left:media', `
              <div class="media-with-thumbs">
                <div class="main-media">
                  ${activeMedia && activeMedia.url ? `<img src="${this._escapeHtml(activeMedia.url)}" alt="Model media" loading="lazy">` : '<span>No preview</span>'}
                  ${activeMedia && activeMedia.type_label ? `<span class="badge">${this._escapeHtml(activeMedia.type_label)}</span>` : ''}
                  <div class="main-overlay-tools">
                    <button class="icon-action viewer" id="btn-viewer" type="button" aria-label="Open 3D viewer" title="Open 3D Viewer"><ha-icon icon="mdi:cube-scan"></ha-icon></button>
                    <button class="icon-action expand" type="button" aria-label="Open full screen" title="Open Full Screen"><ha-icon icon="mdi:fullscreen"></ha-icon></button>
                  </div>
                  <button class="main-nav-btn prev" id="btn-hero-prev" title="Previous" ${mediaItems.filter(i => !i.is_hidden).length > 1 ? '' : 'disabled'}>&#8249;</button>
                  <button class="main-nav-btn next" id="btn-hero-next" title="Next" ${mediaItems.filter(i => !i.is_hidden).length > 1 ? '' : 'disabled'}>&#8250;</button>
                </div>
                <div class="thumbs">
                  ${mediaItems.map((item, idx) => `
                    <button class="thumb ${idx === this._heroActiveMediaIndex ? 'active' : ''} ${item.is_hidden ? 'media-hidden' : ''}" data-media-index="${idx}" title="${this._escapeHtml(item.filename || item.type_label || 'Media item')}">
                      ${item.thumbnail_url || item.url ? `<img src="${this._escapeHtml(item.thumbnail_url || item.url)}" alt="${this._escapeHtml(item.filename || 'thumb')}" loading="lazy">` : ''}
                      <span class="src">${this._escapeHtml(item.type_label || item.type || 'Media')}${item.is_hidden ? ' · Hidden' : ''}</span>
                      ${item.is_hidden ? '<span class="hidden-mark">✕</span>' : ''}
                    </button>
                  `).join('')}
                </div>
              </div>
              <div class="media-toolbar">
                <div class="media-filters">
                  <button class="chip ${this._heroMediaFilter === 'all' ? 'active' : ''}" data-media-filter="all">All (${mediaCounts.all})</button>
                  <button class="chip ${this._heroMediaFilter === 'asset' ? 'active' : ''}" data-media-filter="asset">Assets (${mediaCounts.asset})</button>
                  <button class="chip ${this._heroMediaFilter === 'embedded' ? 'active' : ''}" data-media-filter="embedded">Embedded (${mediaCounts.embedded})</button>
                </div>
                <div class="media-actions">
                  <button id="btn-hero-set-preview" class="action-button" type="button" ${activeMedia && activeMedia.can_set_preview && !activeMedia.is_preview && mediaItems.filter(i => !i.is_hidden).length > 1 ? '' : 'disabled'}>${activeMedia && activeMedia.is_preview ? 'Current Preview' : 'Set Preview'}</button>
                  <button id="btn-hero-add-image" class="action-button" type="button" style="background: var(--primary-color);"><ha-icon icon="mdi:plus" style="--mdc-icon-size: 16px; vertical-align: middle;"></ha-icon> Add Image</button>
                  <button id="btn-hero-hide-image" class="action-button" type="button" ${activeMedia && activeMedia.can_hide ? '' : 'disabled'}>${activeMedia && activeMedia.is_hidden ? 'Unhide Image' : 'Hide Image'}</button>
                  <button id="btn-hero-delete-image" class="action-button danger" type="button" ${activeMedia && activeMedia.can_delete ? '' : 'disabled'}>Delete Image</button>
                </div>
              </div>
              <input type="file" id="hero-photo-file-input" multiple accept=".jpg,.jpeg,.png,.webp" style="display: none;">
            `)}

            ${this._renderPanelWorkspace(model)}
          </div>

          <div class="right">
            ${this._renderSummaryCard(model)}
            ${isIdea ? this._renderIdeaMetadataCard(model) : this._renderModelFilesCard(model)}
            ${isIdea ? '' : this._renderArchiveLinkageCard()}
          </div>
        </div>
      </div>

      ${this._renderQueueDialog()}

      ${this._showConflictDialog ? `
        <div class="conflict-dialog">
          <div class="conflict-dialog-content">
            <div class="conflict-dialog-title">Conflict Detected</div>
            <div class="conflict-dialog-message">This model was modified by another user or session.</div>
            <div class="conflict-dialog-actions">
              <button class="btn-cancel-dialog" id="btn-conflict-cancel">Cancel</button>
              <button class="btn-reload" id="btn-conflict-reload">Reload</button>
              <button class="btn-overwrite" id="btn-conflict-overwrite">Overwrite</button>
            </div>
          </div>
        </div>
      ` : ''}

    `;
  }

  registerPopupExtension(slotName, extension, priority = 100) {
    const slot = String(slotName || '').trim();
    if (!slot || !extension) {
      return;
    }
    const list = this._popupExtensions.get(slot) || [];
    list.push({ extension, priority: Number(priority) || 100 });
    list.sort((a, b) => a.priority - b.priority);
    this._popupExtensions.set(slot, list);
    this._render();
  }

  unregisterPopupExtension(slotName, extension) {
    const slot = String(slotName || '').trim();
    if (!slot || !this._popupExtensions.has(slot)) {
      return;
    }
    const next = (this._popupExtensions.get(slot) || []).filter(item => item.extension !== extension);
    if (next.length) {
      this._popupExtensions.set(slot, next);
    } else {
      this._popupExtensions.delete(slot);
    }
    this._render();
  }

  _renderExtensionSlot(slotName, fallbackHtml = '') {
    const entries = this._popupExtensions.get(slotName) || [];
    if (!entries.length) {
      return fallbackHtml;
    }
    return entries.map(({ extension }) => {
      try {
        if (extension && typeof extension.render === 'function') {
          const rendered = extension.render({
            model: (this._modelDetail && this._modelDetail.model) || {},
            detail: this._modelDetail || {},
            card: this,
          });
          return typeof rendered === 'string' ? rendered : '';
        }
      } catch (error) {
        console.warn('Popup extension render failed for slot', slotName, error);
      }
      return '';
    }).join('');
  }

  _heroFilteredMediaItems(items) {
    const list = Array.isArray(items) ? items : [];
    if (!list.length) {
      return [];
    }
    if (this._heroMediaFilter === 'all') {
      return list;
    }
    return list.filter(item => {
      const type = String(item && item.type || '').toLowerCase();
      return type === this._heroMediaFilter;
    });
  }

  _heroOrderMediaItems(items) {
    const list = Array.isArray(items) ? items : [];
    if (!list.length) {
      return [];
    }
    const visible = list.filter(item => !item || !item.is_hidden);
    const hidden = list.filter(item => item && item.is_hidden);
    return [...visible, ...hidden];
  }

  _heroCurrentMedia(items) {
    const list = Array.isArray(items) ? items : [];
    if (!list.length) {
      this._heroActiveMediaIndex = 0;
      return null;
    }
    const clampedIndex = Math.max(0, Math.min(this._heroActiveMediaIndex, list.length - 1));
    if (clampedIndex !== this._heroActiveMediaIndex) {
      this._heroActiveMediaIndex = clampedIndex;
    }
    return list[clampedIndex] || null;
  }

  _stepHeroMedia(direction) {
    const items = this._heroOrderMediaItems(this._heroFilteredMediaItems(this._galleryItems()));
    if (!items.length) {
      return;
    }
    let nextIndex = this._heroActiveMediaIndex;
    for (let i = 0; i < items.length; i++) {
      nextIndex = (nextIndex + direction + items.length) % items.length;
      if (!items[nextIndex] || !items[nextIndex].is_hidden) {
        break;
      }
    }
    this._heroActiveMediaIndex = nextIndex;
    this._render();
  }

  _renderPanelWorkspace(model) {
    const queueCount = Array.isArray(this._modelDetail.queued_items) ? this._modelDetail.queued_items.length : 0;
    const relatedCount = Array.isArray(model.related_models) ? model.related_models.length : 0;
    const supportCount = Array.isArray(model.support_files) ? model.support_files.length : 0;
    const isNarrow = typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia('(max-width: 980px)').matches
      : false;
    const isStacked = this._panelMode === 'stacked' || isNarrow;

    const panel = (id, title, body) => {
      const active = this._panelActiveTab === id;
      return `<div class="tab-panel ${active || isStacked ? 'active' : ''}" data-stack-title="${this._escapeHtml(title)}">${body}</div>`;
    };

    return `
      <section class="panel-shell ${isStacked ? 'stacked' : ''}">
        <div class="panel-toolbar">
          <div>
            <strong style="font-size:12px;">Panel Workspace</strong>
          </div>
          <div class="view-mode">
            <button id="btn-panel-mode-tabs" class="${!isStacked ? 'active' : ''}">Tabs</button>
            <button id="btn-panel-mode-stacked" class="${isStacked ? 'active' : ''}">Stacked</button>
          </div>
        </div>
        <div class="tabs">
          <button data-panel-tab="panel-queue" class="${this._panelActiveTab === 'panel-queue' ? 'active' : ''}">Queue / Prints <span class="count">${queueCount}</span></button>
          <button data-panel-tab="panel-related" class="${this._panelActiveTab === 'panel-related' ? 'active' : ''}">Related Models <span class="count">${relatedCount}</span></button>
          <button data-panel-tab="panel-support" class="${this._panelActiveTab === 'panel-support' ? 'active' : ''}">Supporting Files <span class="count">${supportCount}</span></button>
          <button data-panel-tab="panel-contribution" class="${this._panelActiveTab === 'panel-contribution' ? 'active' : ''}">Source</button>
          <button data-panel-tab="panel-publication" class="${this._panelActiveTab === 'panel-publication' ? 'active' : ''}">Publication</button>
        </div>
        ${panel('panel-queue', 'Queue / Prints', this._renderExtensionSlot('sections:queue-status', this._renderQueueStatusPanel()))}
        ${panel('panel-related', 'Related Models', this._renderExtensionSlot('sections:related-models', this._renderRelatedModelsPanel(model)))}
        ${panel('panel-support', 'Supporting Files', this._renderExtensionSlot('sections:supporting-files', this._renderSupportingFilesPanel(model)))}
        ${panel('panel-contribution', 'Source & Contribution', this._renderExtensionSlot('sections:contribution-lifecycle', this._renderContributionPanel(model)))}
        ${panel('panel-publication', 'Publication Pipeline', '<div class="queue-row"><strong>Extension host for #1495</strong><div class="detail">Mount publication pipeline workflow here.</div></div>')}
      </section>
    `;
  }

  _renderQueueStatusPanel() {
    const queued = Array.isArray(this._modelDetail.queued_items) ? this._modelDetail.queued_items : [];
    const drafts = Array.isArray(this._modelDetail.draft_intents) ? this._modelDetail.draft_intents : [];
    const rows = [
      ...queued.map(item => `
        <article class="queue-row">
          <strong>${this._escapeHtml(String(item.file_name || 'Queued item'))}</strong>
          <div class="detail">State: ${this._escapeHtml(String(item.state || 'ready'))}${item.plate_index != null ? ` | Plate ${this._escapeHtml(String(item.plate_index))}` : ''}</div>
        </article>
      `),
      ...drafts.map(item => `
        <article class="queue-row">
          <strong>${this._escapeHtml(String(item.file_name || 'Draft intent'))}</strong>
          <div class="detail">Tray assignment: ${this._escapeHtml(String(item.tray_assignment_status || 'pending'))}</div>
        </article>
      `),
    ];
    if (!rows.length) {
      rows.push('<article class="queue-row"><strong>No queue activity</strong><div class="detail">Queue items and draft intents appear here.</div></article>');
    }
    return `<div class="queue-list">${rows.join('')}</div>`;
  }

  _renderRelatedModelsPanel(model) {
    const related = Array.isArray(model.related_models) ? model.related_models : [];
    if (!related.length) {
      return '<div class="related-list"><article class="related"><strong>No related models</strong><div class="detail">Related model suggestions will appear here.</div></article></div>';
    }
    return `<div class="related-list">${related.map(item => `
      <article class="related">
        <strong>${this._escapeHtml(String(item.name || item.model_id || 'Related model'))}</strong>
        <div class="detail">${this._escapeHtml(String(item.relation_type || 'relation'))}${item.similarity_score != null ? ` | similarity ${this._escapeHtml(String(item.similarity_score))}` : ''}</div>
      </article>
    `).join('')}</div>`;
  }

  _renderSupportingFilesPanel(model) {
    const files = Array.isArray(model.support_files) ? model.support_files : [];
    if (!files.length) {
      return '<div class="support-list"><article class="support"><strong>No supporting files</strong><div class="detail">Documentation and references appear here.</div></article></div>';
    }
    return `<div class="support-list">${files.map(file => `
      <article class="support">
        <strong>${this._escapeHtml(String(file.name || 'Support file'))}</strong>
        <div class="detail">${this._escapeHtml(String(file.description || file.category || ''))}</div>
      </article>
    `).join('')}</div>`;
  }

  _renderContributionPanel(model) {
    const metadata = model.structured_metadata || this._modelDetail?.enrichment?.structured_metadata || {};
    const publishing = metadata.publishing || {};
    const provenance = metadata.provenance || {};
    const publication_source = publishing.publication_source;
    const contribution = publishing.contribution || {};
    const source_platform_label = publishing.source_platform_label || '';
    // Merge source_urls (user-managed list) with legacy published_urls values and source_download_url
    const explicitUrls = Array.isArray(provenance.source_urls) ? provenance.source_urls : [];
    const published_urls = publishing.published_urls || {};
    const legacyUrls = Object.values(published_urls).filter(u => typeof u === 'string' && u.startsWith('http'));
    const downloadUrl = typeof provenance.source_download_url === 'string' && provenance.source_download_url.startsWith('http') ? provenance.source_download_url : null;
    // Build deduplicated combined list: explicit first, then legacy/download that aren't already present
    const seenUrls = new Set(explicitUrls);
    const mergedUrls = [...explicitUrls];
    if (downloadUrl && !seenUrls.has(downloadUrl)) { mergedUrls.push(downloadUrl); seenUrls.add(downloadUrl); }
    for (const u of legacyUrls) { if (!seenUrls.has(u)) { mergedUrls.push(u); seenUrls.add(u); } }
    const source_urls = mergedUrls;
    const isLocal = !publication_source || publication_source === 'local' || publication_source === 'original';

    // Known source platforms for dropdown
    const knownSources = [
      { id: 'local', label: 'Local' },
      { id: 'original', label: 'Original (My Design)' },
      { id: 'makerworld', label: 'MakerWorld' },
      { id: 'printables', label: 'Printables' },
      { id: 'thingiverse', label: 'Thingiverse' },
      { id: 'cults3d', label: 'Cults3D' },
      { id: 'thangs', label: 'Thangs' },
      { id: 'myminifactory', label: 'MyMiniFactory' },
      { id: 'other', label: 'Other…' },
    ];

    const currentSource = publication_source || 'local';
    const platformName = (knownSources.find(s => s.id === currentSource) || {}).label || currentSource;

    // --- Source picker ---
    const sourceOptions = knownSources.map(s =>
      `<option value="${this._escapeHtml(s.id)}" ${currentSource === s.id ? 'selected' : ''}>${this._escapeHtml(s.label)}</option>`
    ).join('');

    const customLabelRow = (currentSource === 'other')
      ? `<div class="source-custom-label">
          <label>Custom source name</label>
          <input type="text" class="source-label-input" data-source-field="source_platform_label"
            value="${this._escapeHtml(source_platform_label)}" placeholder="e.g. MyMiniFactory, GitHub…" />
        </div>`
      : '';

    const sourcePicker = `
      <div class="source-section">
        <div class="source-picker">
          <label>Source</label>
          <select class="source-select" data-source-field="publication_source">${sourceOptions}</select>
        </div>
        ${customLabelRow}
      </div>`;

    // --- Source URLs editor ---
    const urlRows = source_urls.map((url, idx) => `
      <div class="source-url-row" data-url-index="${idx}">
        <input type="text" class="source-url-input" data-source-url-index="${idx}"
          value="${this._escapeHtml(url)}" placeholder="https://…" />
        <button class="url-action-btn url-open" data-action="open-source-url" data-url-index="${idx}" title="Open URL"
          ${url && url.startsWith('http') ? '' : 'disabled'}>🔗</button>
        <button class="url-action-btn url-remove" data-action="remove-source-url" data-url-index="${idx}" title="Remove URL">✕</button>
      </div>
    `).join('');

    const sourceUrlsEditor = `
      <div class="source-urls-section">
        <div class="source-urls-header">
          <label>Source URLs</label>
          <button class="url-action-btn url-add" data-action="add-source-url" title="Add URL">＋</button>
        </div>
        ${source_urls.length === 0 ? '<div class="source-urls-empty">No source URLs. Click ＋ to add one.</div>' : ''}
        <div class="source-urls-list">${urlRows}</div>
      </div>`;

    // --- Contribution checklist (only for non-local) ---
    let checklistHtml = '';
    if (!isLocal) {
      const ratedAt = contribution.rated_at;
      const boostedAt = contribution.boosted_at;
      const photosSharedAt = contribution.photos_shared_at;
      const ratedSkipped = contribution.rated_skipped_at;
      const boostedSkipped = contribution.boosted_skipped_at;
      const photosSharedSkipped = contribution.photos_shared_skipped_at;
      const photoCaptureCount = model.photo_capture_count || 0;

      const displayName = (currentSource === 'other')
        ? (source_platform_label || platformName)
        : platformName;

      checklistHtml = `
        <div class="source-divider"></div>
        <div class="contribution-heading">Contribution Checklist</div>
        <div class="contribution-checklist">
          <div class="checklist-item">
            <div class="status-badge complete">✓</div>
            <div class="item-content">
              <strong>Downloaded</strong>
              <div class="detail">from ${this._escapeHtml(displayName)}</div>
            </div>
          </div>

          <div class="checklist-item">
            <div class="status-badge ${photoCaptureCount > 0 ? 'complete' : 'pending'}">
              ${photoCaptureCount > 0 ? '✓' : '☐'}
            </div>
            <div class="item-content">
              <strong>Printed</strong>
              <div class="detail">${photoCaptureCount > 0 ? `${photoCaptureCount} print(s) captured` : 'No prints captured yet'}</div>
            </div>
          </div>

          <div class="checklist-item step-row">
            <div class="status-badge ${ratedAt ? 'complete' : ratedSkipped ? 'skipped' : 'pending'}">
              ${ratedAt ? '✓' : ratedSkipped ? '⊗' : '☐'}
            </div>
            <div class="item-content">
              <strong>Rated on ${this._escapeHtml(displayName)}</strong>
              ${ratedAt ? `<div class="detail">Rated at ${new Date(ratedAt).toLocaleDateString()}</div>` : ratedSkipped ? '<div class="detail">Skipped</div>' : ''}
            </div>
            <div class="step-actions">
              ${!ratedAt && !ratedSkipped ? `<button class="action-button action-mark" data-action="rated">Mark Rated</button><button class="action-button action-skip" data-action="rated">Skip</button>` : ''}
            </div>
          </div>

          <div class="checklist-item step-row">
            <div class="status-badge ${boostedAt ? 'complete' : boostedSkipped ? 'skipped' : 'pending'}">
              ${boostedAt ? '✓' : boostedSkipped ? '⊗' : '☐'}
            </div>
            <div class="item-content">
              <strong>Boosted</strong>
              ${boostedAt ? `<div class="detail">Boosted at ${new Date(boostedAt).toLocaleDateString()}</div>` : boostedSkipped ? '<div class="detail">Skipped</div>' : ''}
            </div>
            <div class="step-actions">
              ${!boostedAt && !boostedSkipped ? `<button class="action-button action-mark" data-action="boosted">Mark Boosted</button><button class="action-button action-skip" data-action="boosted">Skip</button>` : ''}
            </div>
          </div>

          <div class="checklist-item">
            <div class="status-badge ${photoCaptureCount > 0 ? 'complete' : 'pending'}">
              ${photoCaptureCount > 0 ? '✓' : '☐'}
            </div>
            <div class="item-content">
              <strong>Photos Captured</strong>
              <div class="detail">${photoCaptureCount} photo(s) available</div>
            </div>
          </div>

          <div class="checklist-item step-row">
            <div class="status-badge ${photosSharedAt ? 'complete' : photosSharedSkipped ? 'skipped' : 'pending'}">
              ${photosSharedAt ? '✓' : photosSharedSkipped ? '⊗' : '☐'}
            </div>
            <div class="item-content">
              <strong>Photos Shared on ${this._escapeHtml(displayName)}</strong>
              ${photosSharedAt ? `<div class="detail">Shared at ${new Date(photosSharedAt).toLocaleDateString()}</div>` : photosSharedSkipped ? '<div class="detail">Skipped</div>' : ''}
            </div>
            <div class="step-actions">
              ${!photosSharedAt && !photosSharedSkipped ? `<button class="action-button action-mark" data-action="photos_shared">Mark Shared</button><button class="action-button action-skip" data-action="photos_shared">Skip</button>` : ''}
              ${photoCaptureCount > 0 ? `<button class="action-button action-open" data-action="open-gallery">View Photos</button>` : ''}
            </div>
          </div>
        </div>`;
    }

    return `
      ${sourcePicker}
      ${sourceUrlsEditor}
      ${checklistHtml}

      <style>
        .source-section {
          display: grid;
          gap: 8px;
          margin-bottom: 16px;
        }
        .source-picker {
          display: grid;
          grid-template-columns: 80px 1fr;
          align-items: center;
          gap: 8px;
        }
        .source-picker label,
        .source-custom-label label {
          font-size: 12px;
          font-weight: 600;
          color: var(--secondary-text-color);
        }
        .source-select {
          padding: 6px 8px;
          border-radius: 6px;
          border: 1px solid var(--divider-color);
          background: var(--secondary-background-color);
          color: var(--primary-text-color);
          font-size: 13px;
          cursor: pointer;
        }
        .source-custom-label {
          display: grid;
          grid-template-columns: 80px 1fr;
          align-items: center;
          gap: 8px;
        }
        .source-label-input {
          padding: 6px 8px;
          border-radius: 6px;
          border: 1px solid var(--divider-color);
          background: var(--secondary-background-color);
          color: var(--primary-text-color);
          font-size: 13px;
        }
        .source-urls-section {
          margin-bottom: 16px;
        }
        .source-urls-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 8px;
        }
        .source-urls-header label {
          font-size: 12px;
          font-weight: 600;
          color: var(--secondary-text-color);
        }
        .source-urls-empty {
          font-size: 12px;
          color: var(--secondary-text-color);
          padding: 8px 0;
        }
        .source-urls-list {
          display: grid;
          gap: 6px;
        }
        .source-url-row {
          display: grid;
          grid-template-columns: 1fr auto auto;
          gap: 4px;
          align-items: center;
        }
        .source-url-input {
          padding: 6px 8px;
          border-radius: 6px;
          border: 1px solid var(--divider-color);
          background: var(--secondary-background-color);
          color: var(--primary-text-color);
          font-size: 13px;
          min-width: 0;
        }
        .url-action-btn {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 30px;
          height: 30px;
          border: 1px solid var(--divider-color);
          border-radius: 6px;
          background: var(--secondary-background-color);
          color: var(--primary-text-color);
          cursor: pointer;
          font-size: 14px;
          padding: 0;
          transition: all 0.15s ease;
        }
        .url-action-btn:hover {
          background: rgba(96, 165, 250, 0.1);
          border-color: var(--primary-color);
        }
        .url-action-btn[disabled] {
          opacity: 0.35;
          cursor: not-allowed;
        }
        .url-action-btn.url-remove:hover {
          background: rgba(239, 68, 68, 0.1);
          border-color: rgb(239, 68, 68);
          color: rgb(239, 68, 68);
        }
        .url-action-btn.url-add {
          width: auto;
          padding: 0 8px;
          font-size: 16px;
          font-weight: bold;
        }
        .source-divider {
          border-top: 1px solid var(--divider-color);
          margin: 8px 0;
        }
        .contribution-heading {
          font-size: 13px;
          font-weight: 600;
          margin-bottom: 10px;
          color: var(--primary-text-color);
        }
        .contribution-message {
          padding: 12px;
          border-radius: 8px;
          background: rgba(96, 165, 250, 0.08);
          border: 1px solid rgba(96, 165, 250, 0.2);
        }
        .contribution-message strong {
          display: block;
          font-size: 14px;
          margin-bottom: 4px;
        }
        .contribution-message .detail {
          font-size: 12px;
          color: var(--secondary-text-color);
        }
        .contribution-checklist {
          display: grid;
          gap: 12px;
        }
        .checklist-item {
          display: grid;
          grid-template-columns: 32px 1fr auto;
          align-items: center;
          gap: 12px;
          padding: 10px;
          border-radius: 8px;
          border: 1px solid var(--divider-color);
          background: var(--secondary-background-color);
        }
        .checklist-item.step-row {
          grid-template-columns: 32px 1fr auto;
          align-items: center;
        }
        .status-badge {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 28px;
          height: 28px;
          border-radius: 50%;
          font-weight: bold;
          font-size: 14px;
        }
        .status-badge.complete {
          background: rgba(74, 222, 128, 0.2);
          border: 1px solid rgba(74, 222, 128, 0.4);
          color: #4ade80;
        }
        .status-badge.pending {
          background: rgba(156, 163, 175, 0.1);
          border: 1px solid rgba(156, 163, 175, 0.2);
          color: var(--secondary-text-color);
          font-size: 16px;
        }
        .status-badge.skipped {
          background: rgba(251, 191, 36, 0.15);
          border: 1px solid rgba(251, 191, 36, 0.3);
          color: #fbbf24;
          font-size: 16px;
        }
        .item-content {
          display: grid;
          gap: 2px;
        }
        .item-content strong {
          font-size: 13px;
          display: block;
        }
        .item-content .detail {
          font-size: 11px;
          color: var(--secondary-text-color);
        }
        .step-actions {
          display: flex;
          gap: 6px;
          align-items: center;
          justify-content: flex-end;
        }
        .action-button {
          background: var(--primary-color);
          color: var(--text-primary-color);
          border: none;
          border-radius: 6px;
          padding: 6px 12px;
          font-size: 12px;
          font-weight: 500;
          cursor: pointer;
          white-space: nowrap;
          transition: all 0.2s ease;
        }
        .action-button:hover {
          opacity: 0.85;
          box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }
        .action-button.action-open {
          background: transparent;
          color: var(--primary-color);
          border: 1px solid var(--primary-color);
          padding: 5px 11px;
        }
        .action-button.action-open:hover {
          background: rgba(96, 165, 250, 0.1);
          box-shadow: none;
        }
        .action-button.action-skip {
          background: rgba(239, 68, 68, 0.1);
          color: rgb(239, 68, 68);
          border: 1px solid rgb(239, 68, 68);
        }
        .action-button.action-skip:hover {
          background: rgba(239, 68, 68, 0.2);
        }
      </style>
    `;
  }

  _renderSummaryCard(model) {
    const linkedCount = Array.isArray(this._modelDetail.linked_archives) ? this._modelDetail.linked_archives.length : Number(this._modelDetail.link_count || 0);
    const candidateCount = Array.isArray(this._modelDetail.candidate_archives) ? this._modelDetail.candidate_archives.length : 0;
    const relatedCount = Array.isArray(model.related_models) ? model.related_models.length : 0;
    const supportCount = Array.isArray(model.support_files) ? model.support_files.length : 0;
    const tags = Array.isArray(model.keywords) ? model.keywords : [];

    return `
      <section class="card" data-slot="hero-right:summary">
        <div class="h">
          <span>Summary</span>
        </div>
        ${this._renderExtensionSlot('hero-right:summary', `
          <div class="summary">
            <div class="name">${this._escapeHtml(String(model.name || 'Untitled Model'))}</div>
            <div class="meta">Tags: ${this._escapeHtml(tags.join(', ') || 'none')} | Collections: ${this._escapeHtml((model.collection_names || []).join(', ') || 'none')}</div>
            <div class="status">
              <span>Linked archives: ${linkedCount}</span>
              <span>Candidates: ${candidateCount}</span>
              <span>Related: ${relatedCount}</span>
              <span>Supporting: ${supportCount}</span>
            </div>
          </div>
        `)}
      </section>
    `;
  }

  _renderModelFilesCard(model) {
    const files = Array.isArray(model.files) ? model.files : [];
    const rows = files.length ? files.map(file => {
      const filename = this._escapeHtml(String(file.filename || file.asset_filename || file.id || 'file'));
      const rawName = String(file.filename || file.asset_filename || file.id || '');
      const extIdx = rawName.lastIndexOf('.');
      const ext = extIdx >= 0 ? rawName.slice(extIdx + 1).toLowerCase() : '';
      const extUpper = ext.toUpperCase() || 'FILE';
      const extClass = ext ? `x-${this._escapeHtml(ext)}` : '';
      const thumbUrl = this._normalizeModelApiUrl(String(file.thumbnail_lazy_url || file.thumbnail_url || file.preview_url || '').trim());
      const meta = [
        file.asset_type ? String(file.asset_type) : '',
        file.file_size_bytes ? `${Math.round(Number(file.file_size_bytes) / (1024 * 1024))} MB` : '',
      ].filter(Boolean).join(' | ');
      const previewHtml = thumbUrl
        ? `<img class="file-preview" src="${this._escapeHtml(thumbUrl)}" alt="${filename}" loading="lazy">`
        : `<span class="file-ext-badge ${extClass}">${this._escapeHtml(extUpper)}</span>`;
      return `
        <article class="collapsible-group">
          <button class="collapse-toggle" data-collapse-toggle="file-${this._escapeHtml(String(file.id || filename))}">
            <div style="display:flex;align-items:center;gap:10px;">${previewHtml}<div><strong>${filename}</strong><div class="detail">${this._escapeHtml(meta || 'Model file')}</div></div></div>
            <div>▾</div>
          </button>
          <div class="collapse-body ${this._collapsedSections[`file-${String(file.id || filename)}`] ? 'hidden' : ''}">
            Plate and file details host (Phase 0). File id: ${this._escapeHtml(String(file.id || 'n/a'))}
          </div>
        </article>
      `;
    }).join('') : '<article class="queue-row"><strong>No files found</strong><div class="detail">Model file inventory is empty.</div></article>';

    return `
      <section class="card" data-slot="panel:files-core">
        <div class="h">
          <span>Model Files</span>
        </div>
        <div class="files">${rows}</div>
      </section>
    `;
  }


  async _handleArchiveCandidateAction(archiveId, linkId, action) {
    if (!this._modelRef || !this._modelSidecarUrl) return;
    try {
      const endpoint = action === 'link' ? 'accept' : 'reject';
      const url = `${this._modelSidecarUrl}/api/archive-links/${encodeURIComponent(archiveId)}/${encodeURIComponent(linkId)}/${endpoint}`;
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await this._loadModelDetail({ silent: true });
    } catch (e) {
      alert('Failed to update archive linkage: ' + e);
    }
  }

  _resolveBambuddyUrl() {
    if (this._config && this._config.bambuddy_url) {
      return String(this._config.bambuddy_url).trim();
    }
    if (this._hass && this._hass.states) {
      const entity = this._hass.states["input_text.bambuddy_api_base_url"];
      if (entity && entity.state) return String(entity.state).trim();
    }
    return "";
  }

  async _authHeaders(forceRefresh) {
    const auth = this._hass && this._hass.auth ? this._hass.auth : null;
    if (!auth) return {};
    if (forceRefresh && typeof auth.refreshAccessToken === 'function') {
      try { await auth.refreshAccessToken(); } catch { /* use last known token */ }
    }
    const accessToken = auth.accessToken || (auth.data ? auth.data.accessToken : '');
    return accessToken ? { Authorization: 'Bearer ' + accessToken } : {};
  }

  _normalizeServiceResponse(payload) {
    if (Array.isArray(payload) && payload.length) {
      const firstItem = payload[0];
      if (firstItem && typeof firstItem === 'object') return this._normalizeServiceResponse(firstItem);
    }
    if (payload && typeof payload === 'object') {
      if (payload.service_response && typeof payload.service_response === 'object') return this._normalizeServiceResponse(payload.service_response);
      if (payload.response && typeof payload.response === 'object') return this._normalizeServiceResponse(payload.response);
      if (payload.content && typeof payload.content === 'object' && (Object.prototype.hasOwnProperty.call(payload, 'status') || Object.prototype.hasOwnProperty.call(payload, 'headers'))) {
        return Object.assign({}, payload.content, { content: payload.content, status: payload.status, headers: payload.headers });
      }
    }
    return payload && typeof payload === 'object' ? payload : {};
  }

  async _callServiceWithResponse(domain, service, data) {
    if (!this._hass) throw new Error('Home Assistant context is unavailable');
    const endpoint = '/api/services/' + encodeURIComponent(String(domain || '')) + '/' + encodeURIComponent(String(service || '')) + '?return_response';
    const requestBody = JSON.stringify(data && typeof data === 'object' ? data : {});
    let response = await fetch(endpoint, {
      method: 'POST',
      headers: Object.assign({ 'Content-Type': 'application/json' }, await this._authHeaders(false)),
      credentials: 'same-origin',
      body: requestBody,
    });
    if (response.status === 401) {
      response = await fetch(endpoint, {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, await this._authHeaders(true)),
        credentials: 'same-origin',
        body: requestBody,
      });
    }
    let payload = {};
    try { payload = await response.json(); } catch { payload = {}; }
    if (!response.ok) {
      throw payload && typeof payload === 'object'
        ? { message: String(payload.message || payload.error || ('Service call failed (HTTP ' + String(response.status) + ')')), body: payload, status: response.status }
        : new Error('Service call failed (HTTP ' + String(response.status) + ')');
    }
    const normalized = this._normalizeServiceResponse(payload);
    if (normalized && typeof normalized === 'object' && Number(normalized.status || 0) >= 400) {
      throw { message: String(normalized.message || normalized.error || ('Service call failed (embedded HTTP ' + String(normalized.status) + ')')), body: normalized, status: Number(normalized.status || 0) };
    }
    return normalized;
  }

  async _fetchArchiveMeta(archiveId) {
    const id = String(archiveId);
    if (this._archiveMetaCache[id]) return this._archiveMetaCache[id];
    if (!this._hass) return null;
    try {
      const result = await this._callServiceWithResponse('bambuddy', 'get_print_history_archive_detail', { archive_id: Number(archiveId) });
      this._archiveMetaCache[id] = result;
      return result;
    } catch { return null; }
  }

  async _loadArchiveMetaForLinks() {
    if (!this._hass) return;
    const linked = Array.isArray(this._modelDetail && this._modelDetail.linked_archives) ? this._modelDetail.linked_archives : [];
    const candidates = Array.isArray(this._modelDetail && this._modelDetail.candidate_archives) ? this._modelDetail.candidate_archives : [];
    const allLinks = [...linked, ...candidates];
    const ids = [...new Set(allLinks.map(l => String(l.archive_id || l.id || '')).filter(Boolean))];
    const uncached = ids.filter(id => !this._archiveMetaCache[id]);
    if (!uncached.length) return;
    await Promise.all(uncached.map(id => this._fetchArchiveMeta(id)));
    this._render();
  }

  _openArchiveImagePreview(archiveId) {
    const bambuddyUrl = this._resolveBambuddyUrl();
    if (!bambuddyUrl) return;
    const id = String(archiveId);
    const meta = this._archiveMetaCache[id];
    const archive = meta && meta.archive ? meta.archive : meta;
    const thumbUrl = `${bambuddyUrl}/api/v1/archives/${encodeURIComponent(id)}/thumbnail`;

    // Build images from cached photo data
    const images = [{ url: thumbUrl, filename: 'Thumbnail' }];
    const photos = archive && Array.isArray(archive.photos) ? archive.photos : [];
    for (const photo of photos) {
      const photoPath = typeof photo === 'string' ? photo : (photo.path || photo.filename || '');
      if (photoPath) {
        images.push({
          url: `${bambuddyUrl}/api/v1/archives/${encodeURIComponent(id)}/photos/${encodeURIComponent(photoPath)}`,
          filename: photoPath,
        });
      }
    }

    this._archiveImagePreview = { archiveId: id, images, index: 0, loading: false };
    this._ensureOverlayRoot();
    this._renderArchiveImageOverlay();
    if (this._overlayRoot && !this._overlayRoot.open) {
      this._overlayRoot.showModal();
    }
    this._applyBodyScrollLock();
    document.addEventListener('keydown', this._boundKeydownHandler);
  }

  async _openArchivePopup(archiveId) {
    const id = String(archiveId);
    if (!this._hass || !id) return;

    // Ensure archive metadata is loaded
    let meta = this._archiveMetaCache[id];
    if (!meta) {
      meta = await this._fetchArchiveMeta(id);
    }
    if (!meta) return;

    const archive = meta.archive || meta;
    const archiveName = String(archive.print_name || `Archive ${id}`);
    const popupTitle = `${archiveName} · #${id}`;

    // --- Tag parsing (matches YAML template logic) ---
    const systemTagPrefixes = ['f:', 's:', 'spoolman:', 'vendor:', 'material:', 'cost:', 'status:', 'ha enrichment:', 'ha_enrichment:'];
    const systemTagValues = ['ha_enriched:true'];
    const isSystemTag = (tag) => {
      const n = String(tag || '').trim().toLowerCase();
      return systemTagValues.includes(n) || systemTagPrefixes.some(p => n.startsWith(p));
    };
    const allTags = String(archive.tags || '').split(',').map(t => t.trim()).filter(Boolean);
    const userTags = allTags.filter(t => !isSystemTag(t));

    // --- Notes parsing ---
    const ENRICHMENT_MARKER = '+>';
    const rawNotes = String(archive.notes || '');
    const markerIndex = rawNotes.indexOf(ENRICHMENT_MARKER);
    const userNotes = markerIndex >= 0 ? rawNotes.slice(0, markerIndex).replace(/\n+$/, '') : rawNotes.trimEnd();

    // --- Status ---
    const normalizeStatus = (s) => {
      const r = String(s || '').toLowerCase().trim();
      if (r === 'success') return 'completed';
      if (r === 'cancelled' || r === 'aborted' || r === 'stopped') return 'cancelled';
      return r;
    };
    const formatStatus = (s) => { const n = normalizeStatus(s); return n ? n.charAt(0).toUpperCase() + n.slice(1) : ''; };
    const archiveStatus = normalizeStatus(archive.status);
    const statusOptions = ['completed', 'failed', 'cancelled', 'printing'].map(formatStatus);
    const archiveStatusOption = formatStatus(archiveStatus || 'completed');
    if (archiveStatusOption && !statusOptions.includes(archiveStatusOption)) statusOptions.push(archiveStatusOption);

    // --- Failure reason ---
    const archiveFailureReason = String(archive.failure_reason || '').trim();
    const failureReasonOptions = ['Unspecified', 'Adhesion failure', 'Spaghetti / Detached', 'Layer shift', 'Clogged nozzle', 'Filament runout', 'Warping', 'Stringing', 'Under-extrusion', 'Power failure', 'User cancelled', 'Other'];
    if (archiveFailureReason && !failureReasonOptions.includes(archiveFailureReason)) failureReasonOptions.push(archiveFailureReason);

    // --- Project picker ---
    const statusEntity = this._hass.states['sensor.bambuddy_print_history_browser_status'];
    const projectCatalog = Array.isArray(statusEntity?.attributes?.project_options) ? statusEntity.attributes.project_options : [];
    const popupProjectLabel = (pid, pname) => {
      const pidText = String(pid || '').trim();
      const pnameText = String(pname || '').trim();
      for (const opt of projectCatalog) {
        if (pidText && String(opt?.id || '').trim() === pidText && String(opt?.label || '').trim()) return String(opt.label).trim();
      }
      if (pnameText) return pidText ? `${pnameText} [${pidText}]` : pnameText;
      if (pidText) return `Project [${pidText}]`;
      return 'No Project';
    };
    const projectLabels = ['No Project'];
    for (const opt of projectCatalog) {
      const label = String(opt?.label || '').trim();
      if (label && !projectLabels.includes(label)) projectLabels.push(label);
    }
    const currentProjectLabel = popupProjectLabel(archive.project_id, archive.project_name);
    if (currentProjectLabel !== 'No Project' && !projectLabels.includes(currentProjectLabel)) projectLabels.push(currentProjectLabel);

    // --- Editable field values ---
    const LIMIT = 255;
    const editablePrintName = String(archive.print_name || '').slice(0, LIMIT);
    const editableTags = userTags.join(', ').slice(0, LIMIT);
    const editableNotes = String(userNotes || '').slice(0, LIMIT);
    const isFavorite = !!archive.is_favorite;
    const archiveJson = JSON.stringify(archive);

    // --- Button-card helper ---
    const buttonCard = (name, icon, background, tapAction) => ({
      type: 'custom:button-card',
      name, icon,
      show_name: true, show_icon: true, show_state: false,
      tap_action: tapAction,
      hold_action: { action: 'none' },
      styles: {
        card: [{ padding: '12px 10px' }, { 'border-radius': '16px' }, { 'box-shadow': 'none' }, { border: '1px solid rgba(255,255,255,0.08)' }, { background }],
        grid: [{ 'grid-template-areas': '"i" "n"' }, { 'grid-template-columns': '1fr' }, { 'justify-items': 'center' }, { gap: '6px' }],
        icon: [{ width: '22px' }, { height: '22px' }, { color: 'var(--primary-text-color)' }],
        name: [{ 'font-size': '12px' }, { 'font-weight': '600' }, { color: 'var(--primary-text-color)' }],
      },
    });

    // --- Build card stack (matches YAML template) ---
    const cards = [
      {
        type: 'custom:print-history-photo-gallery-card',
        archive_json: archiveJson,
        detail_entity: 'sensor.print_history_popup_archive_detail',
        api_base_entity: 'input_text.bambuddy_api_base_url',
        visibility_entity: 'input_boolean.print_history_show_images',
        include_thumbnail: true,
      },
      {
        type: 'custom:button-card',
        template: 'print_history_archive_popup_content',
        entity: 'sensor.print_history_popup_archive_detail',
        triggers_update: ['sensor.print_history_popup_archive_detail', 'input_boolean.print_history_popup_is_favorite'],
        variables: { archive_json: archiveJson },
        tap_action: { action: 'none' },
        hold_action: { action: 'none' },
      },
      {
        type: 'custom:print-history-tag-editor-card',
        entity: 'input_text.print_history_popup_tags',
        suggestions_entity: 'input_select.print_history_filter_tag',
        title: 'Tags',
        placeholder: 'Add a tag and press Enter',
        helper: 'Reuse an existing tag or create a new one. Press Enter or comma to add.',
      },
      {
        type: 'entities',
        show_header_toggle: false,
        entities: [
          { entity: 'input_text.print_history_popup_print_name', name: 'Print Name', icon: 'mdi:printer-3d' },
          { entity: 'input_select.print_history_popup_project', name: 'Project', icon: 'mdi:folder-outline' },
          { entity: 'input_select.print_history_popup_status', name: 'Status', icon: 'mdi:list-status' },
          {
            type: 'conditional',
            conditions: [{ condition: 'or', conditions: [
              { condition: 'state', entity: 'input_select.print_history_popup_status', state: 'Failed' },
              { condition: 'state', entity: 'input_select.print_history_popup_status', state: 'Cancelled' },
            ]}],
            row: { entity: 'input_select.print_history_popup_failure_reason', name: 'Failure Reason', icon: 'mdi:alert-circle-outline' },
          },
          { entity: 'input_text.print_history_popup_notes', name: 'Notes', icon: 'mdi:text-box-outline' },
        ],
      },
      {
        type: 'grid',
        columns: archiveStatus === 'printing' ? 2 : 3,
        square: false,
        cards: [
          ...(archiveStatus === 'printing' ? [] : [buttonCard('Re-Enrich', 'mdi:refresh-circle', 'rgba(46,125,50,0.18)', { action: 'call-service', service: 'script.reenrich_print_history_archive', data: { archive_id: id } })]),
          buttonCard('Save', 'mdi:content-save-outline', 'rgba(21,101,192,0.18)', { action: 'call-service', service: 'script.save_print_history_archive_popup_edits' }),
          buttonCard('Close', 'mdi:close', 'rgba(255,255,255,0.04)', { action: 'fire-dom-event', browser_mod: { service: 'browser_mod.close_popup' } }),
        ],
      },
    ];

    // --- Fire sequence: close current popup → hydrate helpers → open archive popup ---
    this._fireBrowserModEvent('browser_mod.sequence', {
      sequence: [
        { service: 'browser_mod.close_popup' },
        { service: 'input_text.set_value', data: { entity_id: 'input_text.print_history_popup_archive_id', value: id } },
        { service: isFavorite ? 'input_boolean.turn_on' : 'input_boolean.turn_off', data: { entity_id: 'input_boolean.print_history_popup_is_favorite' } },
        { service: 'input_text.set_value', data: { entity_id: 'input_text.print_history_popup_print_name', value: editablePrintName } },
        { service: 'input_text.set_value', data: { entity_id: 'input_text.print_history_popup_tags', value: editableTags } },
        { service: 'input_text.set_value', data: { entity_id: 'input_text.print_history_popup_notes', value: editableNotes } },
        { service: 'input_select.set_options', data: { entity_id: 'input_select.print_history_popup_project', options: projectLabels } },
        { service: 'input_select.select_option', data: { entity_id: 'input_select.print_history_popup_project', option: currentProjectLabel } },
        { service: 'input_select.set_options', data: { entity_id: 'input_select.print_history_popup_status', options: statusOptions } },
        { service: 'input_select.select_option', data: { entity_id: 'input_select.print_history_popup_status', option: archiveStatusOption } },
        { service: 'input_select.set_options', data: { entity_id: 'input_select.print_history_popup_failure_reason', options: failureReasonOptions } },
        { service: 'input_select.select_option', data: { entity_id: 'input_select.print_history_popup_failure_reason', option: archiveFailureReason || 'Unspecified' } },
        { service: 'browser_mod.popup', data: { title: popupTitle, size: 'normal', content: { type: 'vertical-stack', cards } } },
      ],
    });
  }

  _closeArchiveImagePreview() {
    document.removeEventListener('keydown', this._boundKeydownHandler);
    this._restoreBodyScrollLock();
    if (this._overlayRoot && this._overlayRoot.open) {
      this._overlayRoot.close();
    }
    this._archiveImagePreview = null;
  }

  _renderArchiveImageOverlay() {
    if (!this._overlayRoot || !this._archiveImagePreview) return;
    const preview = this._archiveImagePreview;
    const index = Math.max(0, Math.min(preview.index, preview.images.length - 1));
    const item = preview.images[index] || {};
    const imageUrl = String(item.url || '').trim();
    if (!imageUrl) { this._overlayRoot.innerHTML = ''; return; }
    const meta = this._archiveMetaCache[preview.archiveId];
    const archiveData = meta && meta.archive ? meta.archive : meta;
    const title = (archiveData && archiveData.print_name) || `Archive #${preview.archiveId}`;
    const itemName = String(item.filename || `Image ${index + 1}`);

    this._overlayRoot.innerHTML =
      '<style>' +
      '.mdp-frame,.mdp-frame *{box-sizing:border-box;}' +
      '.frame{position:fixed;inset:0;}' +
      '.backdrop{appearance:none;border:none;position:absolute;inset:0;background:rgba(4,8,15,0.94);padding:0;cursor:pointer;}' +
      '.shell{position:relative;z-index:1;display:grid;grid-template-rows:auto minmax(0,1fr) auto;gap:16px;height:100%;box-sizing:border-box;padding:clamp(16px,2.2vw,28px);}' +
      '.header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;color:#fff;}' +
      '.title{font:700 clamp(18px,2.2vw,24px)/1.2 system-ui,sans-serif;}' +
      '.subtitle{margin-top:6px;font:500 clamp(13px,1.4vw,15px)/1.45 system-ui,sans-serif;color:rgba(255,255,255,0.76);}' +
      '.button{appearance:none;border:1px solid rgba(255,255,255,0.24);border-radius:999px;padding:12px 16px;background:rgba(255,255,255,0.10);color:#fff;font:700 13px/1 system-ui,sans-serif;cursor:pointer;backdrop-filter:blur(10px);display:inline-flex;align-items:center;gap:8px;transition:background .16s ease;}' +
      '.button:hover{background:rgba(255,255,255,0.18);}' +
      '.stage{position:relative;display:flex;align-items:center;justify-content:center;min-height:0;border-radius:24px;overflow:hidden;background:linear-gradient(180deg, rgba(15,23,42,0.82), rgba(2,6,23,0.98));box-shadow:0 24px 60px rgba(0,0,0,0.42);}' +
      '.image-wrap{display:flex;align-items:center;justify-content:center;width:100%;height:100%;min-height:0;padding:clamp(10px,1.6vw,22px);box-sizing:border-box;}' +
      '.image{display:block;width:100%;height:100%;max-width:100%;max-height:100%;object-fit:contain;border-radius:18px;}' +
      '.nav{appearance:none;border:none;position:absolute;top:50%;transform:translateY(-50%);width:56px;height:56px;border-radius:999px;background:rgba(255,255,255,0.14);color:#fff;font-size:30px;line-height:1;cursor:pointer;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(12px);}' +
      '.nav.prev{left:16px;}' +
      '.nav.next{right:16px;}' +
      '.filmstrip{display:flex;gap:12px;overflow-x:auto;padding:2px 2px 6px;}' +
      '.thumb{appearance:none;border:2px solid transparent;background:none;padding:0;border-radius:16px;overflow:hidden;cursor:pointer;flex:0 0 auto;opacity:0.82;transition:opacity 120ms ease,border-color 120ms ease;}' +
      '.thumb.active{border-color:#90caf9;opacity:1;}' +
      '.thumb img{display:block;width:108px;height:108px;object-fit:cover;}' +
      "dialog[aria-label='Full-screen gallery']::backdrop{background:transparent;}" +
      '</style>' +
      '<div class="frame mdp-frame">' +
      '<button class="backdrop" type="button" data-action="close-archive-preview" aria-label="Close"></button>' +
      '<div class="shell" role="dialog" aria-modal="true">' +
      '<div class="header">' +
      '<div><div class="title">' + this._escapeHtml(title) + '</div><div class="subtitle">' + this._escapeHtml(itemName) + ' \u00b7 ' + (index + 1) + ' / ' + preview.images.length + (preview.loading ? ' (loading…)' : '') + '</div></div>' +
      '<div><button class="button" type="button" data-action="close-archive-preview">Close</button></div>' +
      '</div>' +
      '<div class="stage">' +
      '<div class="image-wrap"><img class="image" src="' + this._escapeHtml(imageUrl) + '" alt="' + this._escapeHtml(itemName) + '" loading="eager"></div>' +
      (preview.images.length > 1 ? '<button class="nav prev" type="button" data-action="archive-prev" aria-label="Previous">&#8249;</button><button class="nav next" type="button" data-action="archive-next" aria-label="Next">&#8250;</button>' : '') +
      '</div>' +
      (preview.images.length > 1 ? '<div class="filmstrip">' + preview.images.map(function (gi, idx) {
        var thumbUrl = gi.url || '';
        var thumbAlt = gi.filename || 'Image ' + (idx + 1);
        return '<button class="thumb' + (idx === index ? ' active' : '') + '" type="button" data-archive-thumb-index="' + idx + '" aria-label="' + this._escapeHtml(thumbAlt) + '">' +
          (thumbUrl ? '<img src="' + this._escapeHtml(thumbUrl) + '" alt="' + this._escapeHtml(thumbAlt) + '" loading="lazy">' : '') +
          '</button>';
      }.bind(this)).join('') + '</div>' : '') +
      '</div>' +
      '</div>';

    // Wire overlay event handlers
    const self = this;
    this._overlayRoot.querySelectorAll('[data-action="close-archive-preview"]').forEach(btn => {
      btn.onclick = (e) => { e.preventDefault(); self._closeArchiveImagePreview(); };
    });
    this._overlayRoot.querySelectorAll('[data-action="archive-prev"]').forEach(btn => {
      btn.onclick = (e) => { e.preventDefault(); self._archiveImagePreview.index = Math.max(0, self._archiveImagePreview.index - 1); self._renderArchiveImageOverlay(); };
    });
    this._overlayRoot.querySelectorAll('[data-action="archive-next"]').forEach(btn => {
      btn.onclick = (e) => { e.preventDefault(); self._archiveImagePreview.index = Math.min(self._archiveImagePreview.images.length - 1, self._archiveImagePreview.index + 1); self._renderArchiveImageOverlay(); };
    });
    this._overlayRoot.querySelectorAll('[data-archive-thumb-index]').forEach(btn => {
      btn.onclick = (e) => { e.preventDefault(); self._archiveImagePreview.index = parseInt(btn.dataset.archiveThumbIndex, 10); self._renderArchiveImageOverlay(); };
    });
  }

  async _handleRefreshModelCandidates() {
    if (!this._modelRef || !this._modelSidecarUrl) return;
    const bambuddyUrl = this._resolveBambuddyUrl();
    if (!bambuddyUrl) {
      alert('Bambuddy API URL not configured. Set input_text.bambuddy_api_base_url or add bambuddy_url to card config.');
      return;
    }
    this._refreshingCandidates = true;
    this._renderDetail();
    try {
      const url = `${this._modelSidecarUrl}/api/models/${encodeURIComponent(this._modelRef)}/candidates/refresh`;
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bambuddy_url: bambuddyUrl })
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.message || `HTTP ${res.status}`);
      }
      const result = await res.json();
      await this._loadModelDetail({ silent: true });
      // Show brief success state
      this._refreshingCandidates = false;
      this._refreshCandidatesDone = true;
      this._renderDetail();
      setTimeout(() => { this._refreshCandidatesDone = false; this._renderDetail(); }, 2000);
      return;
    } catch (e) {
      alert('Failed to refresh candidates: ' + e);
    } finally {
      this._refreshingCandidates = false;
      this._refreshCandidatesDone = false;
      this._renderDetail();
    }
  }

  _renderArchiveLinkageCard() {
    const linked = Array.isArray(this._modelDetail.linked_archives) ? this._modelDetail.linked_archives : [];
    const candidates = Array.isArray(this._modelDetail.candidate_archives) ? this._modelDetail.candidate_archives : [];
    const bambuddyUrl = this._resolveBambuddyUrl();

    // Trigger background fetch of archive metadata via HA service
    if (this._hass && (linked.length || candidates.length)) {
      this._loadArchiveMetaForLinks();
    }

    const formatDuration = (seconds) => {
      if (!seconds || seconds <= 0) return '';
      const h = Math.floor(seconds / 3600);
      const m = Math.floor((seconds % 3600) / 60);
      return h > 0 ? `${h}h ${m}m` : `${m}m`;
    };

    const renderArchive = (archive, isCandidate) => {
      const archiveId = String(archive.archive_id || '');
      const linkId = String(archive.id || '');
      const meta = this._archiveMetaCache[archiveId];
      const archiveData = meta && meta.archive ? meta.archive : meta;
      const title = this._escapeHtml(
        (archiveData && archiveData.print_name) ? archiveData.print_name
        : (archive.name || archive.archive_name || `Archive ${archiveId || linkId}`)
      );
      const sectionKey = `archive-${archiveId || linkId}`;
      const primaryPhotoPath = archiveData && archiveData.primary_photo_path ? String(archiveData.primary_photo_path).trim() : '';
      const thumb = (primaryPhotoPath && bambuddyUrl && archiveId)
        ? `${bambuddyUrl}/api/v1/archives/${encodeURIComponent(archiveId)}/photos/${encodeURIComponent(primaryPhotoPath)}`
        : archive.preview_image_url || archive.thumbnail_url || (bambuddyUrl && archiveId ? `${bambuddyUrl}/api/v1/archives/${encodeURIComponent(archiveId)}/thumbnail` : '');

      // Build metadata line from enriched archive data
      const metaParts = [];
      if (archiveData && archiveData.started_at) {
        try {
          const d = new Date(archiveData.started_at);
          metaParts.push(d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) + ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }));
        } catch { /* skip */ }
      }
      if (archiveData && (archiveData.print_time_seconds || archiveData.actual_time_seconds)) {
        const dur = formatDuration(archiveData.actual_time_seconds || archiveData.print_time_seconds);
        if (dur) metaParts.push(dur);
      }
      if (archiveId) metaParts.push(archiveId);
      // Show outcome badge for non-successful outcomes
      const status = archiveData && archiveData.status ? String(archiveData.status).toLowerCase() : '';
      const showOutcome = status && status !== 'completed' && status !== 'printing';
      const outcomeBadge = showOutcome
        ? ` <span style="display:inline-block;padding:1px 6px;border-radius:4px;font-size:10px;font-weight:600;background:${status === 'cancelled' ? 'rgba(255,180,60,0.22);color:#ffcc66' : 'rgba(255,80,80,0.22);color:#ff8a8a'};">${this._escapeHtml(status.charAt(0).toUpperCase() + status.slice(1))}</span>`
        : '';

      const metaLine = this._escapeHtml(metaParts.join(' · '));

      return `
        <article class="collapsible-group" data-slot="actions:per-archive">
          <button class="collapse-toggle" data-collapse-toggle="${sectionKey}">
            <div style="display:flex;align-items:center;gap:10px;">
              ${thumb ? `<img src="${this._escapeHtml(thumb)}" alt="Preview" data-archive-thumb-click="${archiveId}" style="width:48px;height:48px;border-radius:6px;border:1px solid #334;object-fit:cover;cursor:pointer;" title="Click to enlarge">` : ''}
              <div><strong>${title}</strong>${outcomeBadge}<div class="detail">${metaLine || (meta ? '' : '<span style="opacity:0.5">Loading metadata…</span>')}</div></div>
            </div>
            <div><span class="state ${isCandidate ? 'candidate' : 'success'}">${isCandidate ? 'Candidate' : 'Linked'}</span> ▾</div>
          </button>
          <div class="collapse-body ${this._collapsedSections[sectionKey] ? 'hidden' : ''}">
            ${isCandidate
              ? `<button class="action-button" data-archive-link="${archiveId}" data-link-id="${linkId}">Link</button> <button class="action-button ghost" data-archive-skip="${archiveId}" data-link-id="${linkId}">Skip</button>`
              : `<button class="action-button ghost" data-archive-open="${archiveId}">Open archive</button>`}
            ${this._renderExtensionSlot('actions:per-archive', '')}
          </div>
        </article>
      `;
    };

    // Candidate banner if any candidates
    const candidateBanner = candidates.length
      ? `<div class="candidate-banner visible" style="border:1px solid #f0be62;background:rgba(240,190,98,0.13);color:#ffe5ba;border-radius:8px;padding:7px 9px;font-size:11px;margin-bottom:8px;">
          ${candidates.length} potential history matches need review to confirm linkage.
        </div>`
      : '';

    // Attach event listeners after render
    setTimeout(() => {
      if (!this.shadowRoot) return;
      // Link/Skip buttons (candidates)
      candidates.forEach(archive => {
        const archiveId = String(archive.archive_id || '');
        const linkId = String(archive.id || '');
        const linkBtn = this.shadowRoot.querySelector(`button[data-archive-link="${archiveId}"]`);
        const skipBtn = this.shadowRoot.querySelector(`button[data-archive-skip="${archiveId}"]`);
        if (linkBtn) linkBtn.onclick = () => this._handleArchiveCandidateAction(archiveId, linkId, 'link');
        if (skipBtn) skipBtn.onclick = () => this._handleArchiveCandidateAction(archiveId, linkId, 'skip');
      });
      // Open archive buttons (linked) → open HA archive popup
      this.shadowRoot.querySelectorAll('button[data-archive-open]').forEach(btn => {
        btn.onclick = () => {
          const aid = btn.dataset.archiveOpen;
          if (aid) this._openArchivePopup(aid);
        };
      });
      // Thumbnail click → image preview
      this.shadowRoot.querySelectorAll('img[data-archive-thumb-click]').forEach(img => {
        img.onclick = (e) => {
          e.stopPropagation();
          e.preventDefault();
          const aid = img.dataset.archiveThumbClick;
          if (aid) this._openArchiveImagePreview(aid);
        };
      });
      const refreshBtn = this.shadowRoot.querySelector('.refresh-candidates-btn');
      if (refreshBtn) refreshBtn.onclick = () => this._handleRefreshModelCandidates();
    }, 0);

    return `
      <section class="card" data-slot="sections:archive-linkage">
        <div class="h">
          <span>Related Archives</span>
          <button class="refresh-candidates-btn${this._refreshingCandidates ? ' spinning' : ''}${this._refreshCandidatesDone ? ' done' : ''}" title="${this._refreshingCandidates ? 'Refreshing candidates…' : this._refreshCandidatesDone ? 'Refresh complete' : 'Refresh candidate matches'}" ${this._refreshingCandidates ? 'disabled' : ''}>
            <ha-icon icon="${this._refreshCandidatesDone ? 'mdi:check-circle' : 'mdi:refresh'}"></ha-icon>
          </button>
        </div>
        <div class="files">
          ${candidateBanner}
          ${linked.map(item => renderArchive(item, false)).join('')}
          ${candidates.map(item => renderArchive(item, true)).join('')}
          ${this._renderExtensionSlot('sections:archive-linkage', '')}
          ${!linked.length && !candidates.length ? '<article class="queue-row"><strong>No linked or candidate archives</strong><div class="detail">Archive linkage review appears here.</div></article>' : ''}
        </div>
      </section>
    `;
  }

  _renderHeader(model) {
    const creator = model.creator_name || "Unknown";
    const collection = model.collection_names && model.collection_names.length 
      ? model.collection_names.join(" / ") 
      : "Uncategorized";
    const keywords = model.keywords || [];
    const headerThumbnailUrl = this._headerThumbnailUrl(model);
    let thumbnailHtml;
    if (headerThumbnailUrl) {
      if (this._isThumbnailLazyEndpoint(headerThumbnailUrl)) {
        // Reuse a previously resolved object URL when available so re-renders do not flash.
        const cachedObjectUrl = getCachedThumbnailObjectUrl(headerThumbnailUrl);
        if (cachedObjectUrl) {
          thumbnailHtml = `<img src="${this._escapeHtml(cachedObjectUrl)}" alt="Model preview" loading="lazy">`;
        } else {
          thumbnailHtml = `<img data-thumbnail-lazy-url="${this._escapeHtml(headerThumbnailUrl)}" alt="Model preview" loading="lazy">`;
        }
      } else {
        thumbnailHtml = `<img src="${this._escapeHtml(headerThumbnailUrl)}" alt="Model preview" loading="lazy">`;
      }
    } else {
      thumbnailHtml = '<ha-icon icon="mdi:cube-outline"></ha-icon>';
    }
    
    return `
      <div class="popup-header">
        <div class="header-thumbnail">${thumbnailHtml}</div>
        <div class="header-content">
          <div class="header-title">${this._escapeHtml(model.name || "Untitled Model")}</div>
          <div class="header-subtitle">by ${this._escapeHtml(creator)}</div>
          <div class="header-subtitle">📁 ${this._escapeHtml(collection)}</div>
          
          ${keywords.length > 0 ? `
            <div class="header-tags">
              ${keywords.slice(0, 5).map(tag => 
                `<span class="tag-chip">${this._escapeHtml(tag)}</span>`
              ).join('')}
            </div>
          ` : ''}
          
          <div class="header-actions">
            ${this._activeTab === 'details' && !this._isEditMode ? `
              <button class="action-button" id="btn-edit">✏️ Edit</button>
            ` : ''}
            ${this._activeTab === 'gallery' && !this._isEditMode ? `
              <button class="action-button" id="btn-manage-photos">📸 Manage Photos</button>
            ` : ''}
            ${this._activeTab === 'gallery' ? `
              <button class="action-button" id="btn-add-image" style="background: var(--primary-color);">
                <ha-icon icon="mdi:plus" style="--mdc-icon-size: 16px; vertical-align: middle;"></ha-icon> Add Image
              </button>
            ` : ''}
            ${this._activeTab === 'details' && this._isEditMode ? `
              <button class="action-button" id="btn-save" style="background: #4CAF50;" ${this._isSaving ? 'disabled' : ''}>
                ${this._isSaving ? '⏳ Saving...' : '💾 Save'}
              </button>
              <button class="action-button" id="btn-cancel" style="background: #f44336;" ${this._isSaving ? 'disabled' : ''}>✕ Cancel</button>
            ` : this._activeTab === 'gallery' && this._isEditMode ? `
              <button class="action-button" id="btn-done" style="background: #607D8B;">✓ Done</button>
            ` : `
              <button class="action-button" id="btn-viewer">🧊 3D View</button>
              <button class="action-button" id="btn-download">📥 Download</button>
              <button class="action-button" id="btn-print">🖨️ Print</button>
            `}
          </div>
        </div>
      </div>
    `;
  }

  _renderTabNavigation() {
    return `
      <div class="tab-navigation">
        <button class="tab-button ${this._activeTab === 'details' ? 'active' : ''}" data-tab="details">
          Details
        </button>
        <button class="tab-button ${this._activeTab === 'gallery' ? 'active' : ''}" data-tab="gallery">
          Gallery
        </button>
        <button class="tab-button ${this._activeTab === 'prints' ? 'active' : ''}" data-tab="prints">
          Linked Prints
        </button>
      </div>
    `;
  }

  _renderTabContent(model) {
    switch (this._activeTab) {
      case "gallery":
        return this._renderGalleryTab();
      case "prints":
        return this._renderPrintsTab();
      default:
        return this._renderDetailsTab(model);
    }
  }

  _galleryItems() {
    const hiddenIds = this._hiddenMediaIdSet();
    const photos = this._modelDetail && Array.isArray(this._modelDetail.photos) ? this._modelDetail.photos : [];
    const files = (this._modelDetail && this._modelDetail.model && Array.isArray(this._modelDetail.model.files))
      ? this._modelDetail.model.files
      : [];

    const items = [];
    const seenMediaIds = new Set();

    const addItem = (item) => {
      if (!item || !item.media_id || !item.url) {
        return;
      }
      if (seenMediaIds.has(item.media_id)) {
        return;
      }
      seenMediaIds.add(item.media_id);
      item.is_hidden = hiddenIds.has(item.media_id);
      items.push(item);
    };

    photos.forEach((photo, idx) => {
        const imageUrl = this._normalizeModelApiUrl(String(photo.image_url || photo.thumbnail_url || photo.preview_url || photo.url || '').trim());
        const thumbnailUrl = this._normalizeModelApiUrl(String(photo.thumbnail_url || photo.image_url || photo.preview_url || photo.url || '').trim());
        const photoId = String(photo.id || `photo-${idx + 1}`).trim();
        addItem({
          media_id: `photo:${photoId}`,
          id: photo.id,
          url: imageUrl || thumbnailUrl,
          thumbnail_url: thumbnailUrl || imageUrl,
          filename: photo.filename || `Photo ${idx + 1}`,
          type: 'asset',
          type_label: 'Asset',
          can_set_preview: true,
          can_hide: true,
          can_delete: true,
          is_preview: Boolean(photo.is_preview),
        });
      });

    files
      .filter(file => file && file.asset_type === 'image')
      .forEach(file => {
        const imageUrl = this._normalizeModelApiUrl(String(file.image_url || file.thumbnail_url || file.preview_url || file.download_url || '').trim());
        const thumbnailUrl = this._normalizeModelApiUrl(String(file.thumbnail_url || file.image_url || file.preview_url || file.download_url || '').trim());
        const assetId = String(file.asset_id || file.id || '').trim();
        addItem({
          media_id: `asset:${assetId}`,
          id: file.id,
          asset_id: assetId,
          url: imageUrl || thumbnailUrl,
          thumbnail_url: thumbnailUrl || imageUrl,
          filename: file.filename || file.asset_filename || file.id,
          type: 'asset',
          type_label: 'Asset',
          can_set_preview: true,
          can_hide: true,
          can_delete: true,
          is_preview: Boolean(file.is_preview || file.asset_role === 'preview'),
        });
      });

    files
      .filter(file => file && file.asset_type !== 'image')
      .forEach(file => {
        const embeddedUrl = this._normalizeModelApiUrl(String(file.thumbnail_lazy_url || file.thumbnail_url || file.preview_url || '').trim());
        const embeddedThumb = this._normalizeModelApiUrl(String(file.thumbnail_url || file.thumbnail_lazy_url || file.preview_url || '').trim());
        const assetId = String(file.asset_id || file.id || '').trim();
        addItem({
          media_id: `embedded:${assetId}`,
          id: file.id,
          asset_id: assetId,
          url: embeddedUrl || embeddedThumb,
          thumbnail_url: embeddedThumb || embeddedUrl,
          filename: file.filename || file.asset_filename || file.id,
          type: 'embedded',
          type_label: 'Embedded',
          can_set_preview: true,
          can_hide: true,
          can_delete: false,
          is_preview: Boolean(file.is_preview || file.asset_role === 'preview'),
        });
      });

    return items;
  }

  _hiddenMediaIdSet() {
    const customFields = this._modelDetail && this._modelDetail.enrichment && this._modelDetail.enrichment.custom_fields
      ? this._modelDetail.enrichment.custom_fields
      : {};
    const raw = customFields ? customFields[this._heroHiddenMediaFieldKey] : null;
    const values = Array.isArray(raw)
      ? raw
      : (typeof raw === 'string' ? raw.split(',') : []);
    const normalized = values
      .map(value => String(value || '').trim())
      .filter(Boolean);
    return new Set(normalized);
  }

  async _persistHiddenMediaIds(hiddenIds) {
    const ids = Array.isArray(hiddenIds)
      ? hiddenIds
      : [];
    const base = String(this._modelSidecarUrl || '').trim().replace(/\/$/, '');
    if (!base || !this._modelRef) {
      return;
    }
    const response = await fetch(
      `${base}/api/models/${encodeURIComponent(this._modelRef)}/fields/${encodeURIComponent(this._heroHiddenMediaFieldKey)}`,
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ value: ids }),
      }
    );
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
  }

  async _toggleHeroMediaHidden(item) {
    if (!item || !item.can_hide) {
      return;
    }
    const mediaId = String(item.media_id || '').trim();
    if (!mediaId) {
      return;
    }
    try {
      const hidden = this._hiddenMediaIdSet();
      if (hidden.has(mediaId)) {
        hidden.delete(mediaId);
      } else {
        hidden.add(mediaId);
      }
      const next = Array.from(hidden.values());
      await this._persistHiddenMediaIds(next);
      await this._loadModelDetail({ silent: true });
    } catch (error) {
      this._error = `Failed to update hidden image: ${error}`;
      this._render();
    }
  }

  async _handleSetAssetPreview(assetId) {
    const normalizedAssetId = String(assetId || '').trim();
    const localModelId = String((this._modelDetail && this._modelDetail.local_model_id) || this._modelRef || '').trim();
    const base = String(this._modelSidecarUrl || '').trim().replace(/\/$/, '');
    if (!normalizedAssetId || !localModelId || !base) {
      return;
    }

    const patchAssetRole = async (targetAssetId, role) => {
      const response = await fetch(
        `${base}/api/local/models/${encodeURIComponent(localModelId)}/assets/${encodeURIComponent(String(targetAssetId))}`,
        {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ asset_role: role }),
        }
      );
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
    };

    const files = this._modelDetail && this._modelDetail.model && Array.isArray(this._modelDetail.model.files)
      ? this._modelDetail.model.files
      : [];
    const currentPreviewAssetIds = files
      .filter(file => file && file.is_preview && String(file.asset_id || file.id || '').trim() && String(file.asset_id || file.id || '').trim() !== normalizedAssetId)
      .map(file => String(file.asset_id || file.id || '').trim());

    for (const currentId of currentPreviewAssetIds) {
      await patchAssetRole(currentId, 'supporting');
    }
    await patchAssetRole(normalizedAssetId, 'preview');

    await fetch(
      `${base}/api/models/${encodeURIComponent(this._modelRef)}/fields/${encodeURIComponent('preview_photo_id')}`,
      {
        method: 'DELETE',
      }
    );
  }

  async _handleSetHeroMediaPreview(item) {
    if (!item || !item.can_set_preview || item.is_preview) {
      return;
    }
    try {
      if (item.media_id && item.media_id.startsWith('photo:')) {
        await this._handleSetPhotoPreview(String(item.id || '').trim());
        this._notifyBrowserDetailChanged();
        return;
      }
      if (item.asset_id) {
        await this._handleSetAssetPreview(item.asset_id);
        await this._loadModelDetail({ silent: true });
        this._notifyBrowserDetailChanged();
        return;
      }
    } catch (error) {
      this._error = `Failed to set preview: ${error}`;
      this._render();
    }
  }

  _handleDeleteHeroMedia(item) {
    if (!item || !item.can_delete) {
      return;
    }
    if (item.media_id && item.media_id.startsWith('photo:')) {
      this._handleDeletePhoto(String(item.id || '').trim());
    } else if (item.media_id && item.media_id.startsWith('asset:')) {
      this._handleDeleteAsset(String(item.asset_id || item.id || '').trim());
    }
  }

  _handleDeleteAsset(assetId) {
    if (confirm('Are you sure you want to delete this image?')) {
      this._performDeleteAsset(assetId);
    }
  }

  async _performDeleteAsset(assetId) {
    const localModelId = String((this._modelDetail && this._modelDetail.local_model_id) || this._modelRef || '').trim();
    const base = String(this._modelSidecarUrl || '').trim().replace(/\/$/, '');
    if (!localModelId || !base || !assetId) return;

    try {
      const response = await fetch(
        `${base}/api/local/models/${encodeURIComponent(localModelId)}/assets/${encodeURIComponent(assetId)}`,
        { method: 'DELETE' }
      );

      let payload = null;
      try {
        payload = await response.json();
      } catch (_) {
        payload = null;
      }

      if (!response.ok) {
        const errorMessage = payload && payload.error
          ? String(payload.error)
          : `HTTP ${response.status}`;
        throw new Error(errorMessage);
      }

      this._error = '';
      await this._loadModelDetail({ silent: true });
      await this._autoPromotePreviewAfterDelete();
    } catch (error) {
      console.error('Error deleting asset:', error);
      this._error = `Failed to delete asset: ${error}`;
      this._render();
    }
  }

  /**
   * After deleting a media item, if no remaining item is marked as preview,
   * auto-promote the first visible candidate (non-hidden, can_set_preview).
   * Gallery order gives natural priority: photos → image assets → embedded.
   */
  async _autoPromotePreviewAfterDelete() {
    const items = this._galleryItems();
    const hasPreview = items.some(i => i.is_preview);
    if (hasPreview) return;

    const candidate = items.find(i => !i.is_hidden && i.can_set_preview);
    if (!candidate) return;

    try {
      await this._handleSetHeroMediaPreview(candidate);
    } catch (err) {
      console.warn('Auto-promote preview failed:', err);
    }
  }

  _renderDetailsTab(model) {
    // In edit mode, show the edit form
    if (this._isEditMode) {
      return `
        <div class="tab-content" id="edit-form-container">
          <!-- Edit form will be inserted here by JavaScript -->
        </div>
      `;
    }

    const enrichment = this._modelDetail.enrichment || {};
    const files = model.files || [];
    const linkedCount = this._modelDetail.link_count || 0;
    
    return `
      <div class="tab-content">
        <div class="details-grid">
          ${model.description ? `
            <div class="detail-section" style="grid-column: 1/-1;">
              <div class="detail-section-title">Description</div>
              <div class="description-text">${this._escapeHtml(model.description)}</div>
            </div>
          ` : ''}
          
          <div class="detail-section">
            <div class="detail-section-title">Quick Stats</div>
            <ul class="stat-list">
              <li>📦 Files: ${files.length}</li>
              <li>⚙️ File types: ${files.map(f => f.asset_type || 'unknown').join(', ') || 'N/A'}</li>
              <li>🖨️ Linked archives: ${linkedCount}</li>
              ${model.created_at ? `<li>📅 Created: ${new Date(model.created_at).toLocaleDateString()}</li>` : ''}
              ${model.updated_at ? `<li>🔄 Updated: ${new Date(model.updated_at).toLocaleDateString()}</li>` : ''}
            </ul>
          </div>
          
          ${enrichment.print_notes ? `
            <div class="detail-section">
              <div class="detail-section-title">Print Notes</div>
              <div class="description-text">${this._escapeHtml(enrichment.print_notes)}</div>
            </div>
          ` : ''}
          
          ${enrichment.difficulty_level ? `
            <div class="detail-section">
              <div class="detail-section-title">Difficulty</div>
              <div class="detail-value">${this._escapeHtml(enrichment.difficulty_level)}</div>
            </div>
          ` : ''}

          ${enrichment.print_time_estimate !== null && enrichment.print_time_estimate !== undefined && enrichment.print_time_estimate !== '' ? `
            <div class="detail-section">
              <div class="detail-section-title">Print Time Estimate</div>
              <div class="detail-value">${this._escapeHtml(String(enrichment.print_time_estimate))}s</div>
            </div>
          ` : ''}

          ${enrichment.support_type_hint ? `
            <div class="detail-section">
              <div class="detail-section-title">Support Type</div>
              <div class="detail-value">${this._escapeHtml(enrichment.support_type_hint)}</div>
            </div>
          ` : ''}
        </div>
      </div>
    `;
  }

  _renderGalleryTab() {
    const galleryItems = this._galleryItems();

    const galleryModeHint = !this._isEditMode ? `
      <div style="
        margin: 0 0 16px;
        padding: 12px 14px;
        border-radius: 10px;
        background: var(--secondary-background-color);
        color: var(--secondary-text-color);
        font-size: 13px;
      ">
        Use <strong>+ Add Image</strong> to upload photos, or <strong>Manage Photos</strong> to set preview / delete.
      </div>
    ` : '';
    
    if (!galleryItems || galleryItems.length === 0) {
      return `
        <div class="tab-content">
          ${galleryModeHint}
          <div class="empty-state">
            <p>📸 No Images</p>
            <p>No photos or images available.</p>
            <p><strong>Use the + Add Image button above to upload photos.</strong></p>
          </div>
          ${this._isEditMode ? `
            <div style="padding: 20px; text-align: center;">
              <div id="photo-upload-area" style="
                border: 2px dashed var(--divider-color);
                border-radius: 8px;
                padding: 40px 20px;
                cursor: pointer;
                transition: background 0.2s;
              ">
                <p style="margin: 0; font-size: 24px;">📤</p>
                <p style="margin: 8px 0; color: var(--primary-text-color); font-weight: 500;">Click to upload photos</p>
                <p style="margin: 0; color: var(--secondary-text-color); font-size: 12px;">or drag and drop (JPG, PNG, WebP)</p>
              </div>
            </div>
          ` : ''}
          <input type="file" id="photo-file-input" multiple accept=".jpg,.jpeg,.png,.webp" style="display: none;">
        </div>
      `;
    }
    
    return `
      <div class="tab-content">
        ${galleryModeHint}
        <style>
          .gallery-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
            gap: 12px;
            margin-bottom: 20px;
          }
          
          .gallery-thumbnail {
            position: relative;
            aspect-ratio: 1;
            background: var(--secondary-background-color);
            border-radius: 8px;
            overflow: hidden;
            cursor: pointer;
            border: 1px solid var(--divider-color);
          }
          
          .gallery-thumbnail img {
            width: 100%;
            height: 100%;
            object-fit: cover;
          }
          
          .thumbnail-overlay {
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            opacity: 0;
            transition: all 0.2s;
          }
          
          .gallery-thumbnail:hover .thumbnail-overlay {
            background: rgba(0,0,0,0.5);
            opacity: 1;
          }
          
          .thumbnail-btn {
            width: 36px;
            height: 36px;
            border: none;
            border-radius: 50%;
            background: rgba(255,255,255,0.9);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
            transition: transform 0.2s;
          }
          
          .thumbnail-btn:hover {
            transform: scale(1.1);
          }
          
          .preview-badge {
            position: absolute;
            top: 6px;
            right: 6px;
            background: #4CAF50;
            color: white;
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 11px;
            font-weight: 600;
          }

          .asset-badge {
            position: absolute;
            top: 6px;
            left: 6px;
            background: #2196F3;
            color: white;
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 11px;
            font-weight: 600;
          }
        </style>
        
        <div class="gallery-grid">
          ${galleryItems.map((item, idx) => `
            <div class="gallery-thumbnail" data-photo-id="${item.id}" data-photo-index="${idx}" data-item-type="${item.type}">
              ${item.thumbnail_url || item.url ? `
                <img src="${item.thumbnail_url}" alt="${this._escapeHtml(item.filename)}" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22%3E%3Crect fill=%22%23f0f0f0%22 width=%22100%22 height=%22100%22/%3E%3Ctext x=%2250%22 y=%2250%22 text-anchor=%22middle%22 dy=%22.3em%22 fill=%22%23999%22 font-size=%2212%22%3ENo image%3C/text%3E%3C/svg%3E'">
              ` : `
                <div style="width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; color: var(--secondary-text-color);">
                  📷
                </div>
              `}
              ${item.is_preview ? `
                <div class="preview-badge">PREVIEW</div>
              ` : ''}
              ${item.type === 'asset' ? `
                <div class="asset-badge">📂 Asset</div>
              ` : ''}
              <div class="thumbnail-overlay">
                <button class="thumbnail-btn" title="View" data-action="preview">👁</button>
                ${this._isEditMode && item.type === 'photo' ? `
                  <button class="thumbnail-btn" title="Set as preview" data-action="set-preview" style="background: #FF9800;">⭐</button>
                  <button class="thumbnail-btn" title="Delete" data-action="delete" style="background: #f44336;">🗑</button>
                ` : ''}
              </div>
            </div>
          `).join('')}
        </div>
        
        ${this._isEditMode ? `
          <div style="padding: 20px; border-top: 1px solid var(--divider-color); text-align: center;">
            <div id="photo-upload-area" style="
              border: 2px dashed var(--divider-color);
              border-radius: 8px;
              padding: 40px 20px;
              cursor: pointer;
              transition: background 0.2s;
            ">
              <p style="margin: 0; font-size: 24px;">📤</p>
              <p style="margin: 8px 0; color: var(--primary-text-color); font-weight: 500;">Click to upload more photos</p>
              <p style="margin: 0; color: var(--secondary-text-color); font-size: 12px;">or drag and drop (JPG, PNG, WebP)</p>
            </div>
          </div>
        ` : ''}
        <input type="file" id="photo-file-input" multiple accept=".jpg,.jpeg,.png,.webp" style="display: none;">
      </div>
    `;
  }

  _renderPrintsTab() {
    const links = this._modelDetail.linked_archives || [];
    const bambuddyUrl = this._resolveBambuddyUrl();
    
    if (links.length === 0) {
      return `
        <div class="tab-content">
          <div class="empty-state">
            <p>🖨️ No Linked Prints</p>
            <p>This model hasn't been printed yet.</p>
          </div>
        </div>
      `;
    }
    
    // Archive grid view with filters and sorting
    return `
      <div class="tab-content">
        <style>
          .archive-controls {
            display: flex;
            gap: 12px;
            margin-bottom: 16px;
            flex-wrap: wrap;
            align-items: center;
          }
          
          .archive-filter-group {
            display: flex;
            gap: 8px;
            align-items: center;
          }
          
          .filter-label {
            font-size: 12px;
            font-weight: 500;
            color: var(--secondary-text-color);
          }
          
          .filter-btn {
            padding: 4px 12px;
            border: 1px solid var(--divider-color);
            background: var(--card-background-color);
            color: var(--primary-text-color);
            border-radius: 16px;
            cursor: pointer;
            font-size: 12px;
            transition: all 0.2s;
          }
          
          .filter-btn:hover {
            border-color: var(--primary-color);
          }
          
          .filter-btn.active {
            background: var(--primary-color);
            color: white;
            border-color: var(--primary-color);
          }
          
          .sort-select {
            padding: 4px 8px;
            border: 1px solid var(--divider-color);
            background: var(--card-background-color);
            color: var(--primary-text-color);
            border-radius: 4px;
            font-size: 12px;
            cursor: pointer;
            color-scheme: light dark;
          }

          .sort-select option,
          .sort-select optgroup {
            background: var(--card-background-color);
            color: var(--primary-text-color);
          }
          
          .archive-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
            gap: 12px;
          }
          
          .archive-card {
            border: 1px solid var(--divider-color);
            border-radius: 8px;
            overflow: hidden;
            background: var(--card-background-color);
            cursor: pointer;
            transition: all 0.2s;
          }
          
          .archive-card:hover {
            border-color: var(--primary-color);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            transform: translateY(-2px);
          }
          
          .archive-thumbnail {
            width: 100%;
            aspect-ratio: 1;
            object-fit: cover;
            background: var(--secondary-background-color);
            border-bottom: 1px solid var(--divider-color);
          }
          
          .archive-card-content {
            padding: 10px;
            display: flex;
            flex-direction: column;
            gap: 6px;
          }
          
          .archive-title {
            font-weight: 500;
            font-size: 13px;
            line-height: 1.3;
            color: var(--primary-text-color);
            overflow: hidden;
            text-overflow: ellipsis;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
          }
          
          .archive-meta {
            font-size: 11px;
            color: var(--secondary-text-color);
            display: flex;
            flex-direction: column;
            gap: 2px;
          }
          
          .archive-status {
            display: inline-block;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 10px;
            font-weight: 500;
            width: fit-content;
          }
          
          .status-success {
            background: rgba(76, 175, 80, 0.2);
            color: #2e7d32;
          }
          
          .status-failed {
            background: rgba(244, 67, 54, 0.2);
            color: #c62828;
          }
          
          .status-stopped {
            background: rgba(255, 152, 0, 0.2);
            color: #e65100;
          }
          
          .archive-actions {
            display: flex;
            gap: 4px;
            border-top: 1px solid var(--divider-color);
            padding-top: 6px;
          }
          
          .action-btn {
            flex: 1;
            padding: 4px 6px;
            border: none;
            background: var(--secondary-background-color);
            color: var(--primary-text-color);
            border-radius: 3px;
            cursor: pointer;
            font-size: 11px;
            font-weight: 500;
            transition: all 0.2s;
          }
          
          .action-btn:hover {
            background: var(--primary-color);
            color: white;
          }
        </style>
        
        <div class="archive-controls">
          <div class="archive-filter-group">
            <span class="filter-label">Filter:</span>
            <button class="filter-btn active" data-filter="all">All (${links.length})</button>
            <button class="filter-btn" data-filter="success">Success (${links.filter(l => l.status === 'success').length})</button>
            <button class="filter-btn" data-filter="failed">Failed (${links.filter(l => l.status === 'failed').length})</button>
          </div>
          
          <div class="archive-filter-group">
            <span class="filter-label">Sort:</span>
            <select class="sort-select" data-sort-by="date_newest">
              <option value="date_newest">Date (Newest)</option>
              <option value="date_oldest">Date (Oldest)</option>
              <option value="filament">Filament</option>
              <option value="name">Name</option>
            </select>
          </div>
        </div>
        
        <div class="archive-grid">
          ${links.map(link => {
            const thumbUrl = link.thumbnail_url || (bambuddyUrl && link.archive_id ? `${bambuddyUrl}/api/v1/archives/${encodeURIComponent(String(link.archive_id))}/thumbnail` : '');
            return `
            <div class="archive-card" data-archive-id="${link.archive_id}">
              ${thumbUrl ? `
                <img class="archive-thumbnail" src="${thumbUrl}" alt="Archive #${link.archive_id}" loading="lazy">
              ` : `
                <div class="archive-thumbnail" style="display: flex; align-items: center; justify-content: center;">
                  <span style="font-size: 32px;">🖨️</span>
                </div>
              `}
              <div class="archive-card-content">
                <div class="archive-title">${this._escapeHtml(link.name || ('Archive #' + link.archive_id))}</div>
                <div class="archive-meta">
                  ${link.completed_at ? `<div>📅 ${new Date(link.completed_at).toLocaleDateString()}</div>` : ''}
                  ${link.filament_name ? `<div>🎨 ${this._escapeHtml(link.filament_name)}</div>` : ''}
                  ${link.status ? `<div class="archive-status status-${link.status}">${link.status.toUpperCase()}</div>` : ''}
                </div>
                <div class="archive-actions">
                  <button class="action-btn" data-action="view-archive">View</button>
                  <button class="action-btn" data-action="print-again">Print Again</button>
                </div>
              </div>
            </div>
          `}).join('')}
        </div>
      </div>
    `;
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  _getEntityType(model) {
    const normalized = (value) => {
      const candidate = String(value || '').trim().toLowerCase();
      if (candidate === 'idea' || candidate === 'working_group' || candidate === 'model') {
        return candidate;
      }
      return '';
    };

    // Support all current payload shapes for local detail responses.
    const direct = normalized(model && model.entity_type);
    if (direct) {
      return direct;
    }

    const rootEntityType = normalized(this._modelDetail && this._modelDetail.entity_type);
    if (rootEntityType) {
      return rootEntityType;
    }

    const detailEnrichment = this._modelDetail && this._modelDetail.enrichment && typeof this._modelDetail.enrichment === 'object'
      ? this._modelDetail.enrichment
      : {};
    const enrichmentFields = detailEnrichment.custom_fields && typeof detailEnrichment.custom_fields === 'object'
      ? detailEnrichment.custom_fields
      : {};
    const enrichmentEntityType = normalized(enrichmentFields.entity_type);
    if (enrichmentEntityType) {
      return enrichmentEntityType;
    }

    const structured = detailEnrichment.structured_metadata && typeof detailEnrichment.structured_metadata === 'object'
      ? detailEnrichment.structured_metadata
      : {};
    const catalogSignals = structured.catalog_signals && typeof structured.catalog_signals === 'object'
      ? structured.catalog_signals
      : {};
    const catalogSignalType = normalized(catalogSignals.entity_type);
    if (catalogSignalType) {
      return catalogSignalType;
    }

    // Local idea metadata implies idea type even when entity_type is not projected.
    const ideaMetadata = this._modelDetail && this._modelDetail.idea_metadata && typeof this._modelDetail.idea_metadata === 'object'
      ? this._modelDetail.idea_metadata
      : null;
    if (ideaMetadata) {
      return 'idea';
    }

    return 'model';
  }

  _renderIdeaMetadataCard(model) {
    const detailIdeaMetadata = this._modelDetail && this._modelDetail.idea_metadata && typeof this._modelDetail.idea_metadata === 'object'
      ? this._modelDetail.idea_metadata
      : {};
    const enrichment = this._modelDetail && this._modelDetail.enrichment && typeof this._modelDetail.enrichment === 'object'
      ? this._modelDetail.enrichment
      : {};
    const enrichmentFields = enrichment.custom_fields && typeof enrichment.custom_fields === 'object'
      ? enrichment.custom_fields
      : {};
    const modelFields = model && model.custom_fields && typeof model.custom_fields === 'object'
      ? model.custom_fields
      : {};

    const externalLinks = Array.isArray(detailIdeaMetadata.external_links)
      ? detailIdeaMetadata.external_links
      : (Array.isArray(enrichmentFields.external_links)
        ? enrichmentFields.external_links
        : (Array.isArray(modelFields.external_links) ? modelFields.external_links : []));
    const sketchImage = detailIdeaMetadata.sketch_image && detailIdeaMetadata.sketch_image.url
      ? detailIdeaMetadata.sketch_image.url
      : (enrichmentFields.sketch_image && enrichmentFields.sketch_image.url
        ? enrichmentFields.sketch_image.url
        : (enrichmentFields.sketch_image || modelFields.sketch_image || null));
    const notes = String(
      detailIdeaMetadata.notes != null
        ? detailIdeaMetadata.notes
        : (enrichmentFields.notes != null ? enrichmentFields.notes : (modelFields.notes || ''))
    ).trim();

    const linksHtml = externalLinks.length ? externalLinks.map(link => {
      const url = this._escapeHtml(String(link.url || ''));
      const label = this._escapeHtml(String(link.label || url));
      return `
        <a href="${url}" target="_blank" rel="noopener noreferrer" style="
          display: block;
          padding: 6px 8px;
          color: var(--primary-color);
          text-decoration: none;
          border-bottom: 1px solid var(--divider-color);
          font-size: 12px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        ">${label} ↗</a>
      `;
    }).join('') : '<div style="padding: 8px; color: var(--secondary-text-color); font-size: 12px;">No links</div>';

    return `
      <section class="card">
        <div class="h">
          <span>💡 Idea Details</span>
        </div>
        <div style="padding: 10px; display: grid; gap: 8px; font-size: 12px;">
          ${notes ? `
            <div>
              <div style="font-weight: 600; margin-bottom: 4px; color: var(--secondary-text-color);">Notes</div>
              <div style="color: var(--primary-text-color); line-height: 1.4;">${this._escapeHtml(notes)}</div>
            </div>
          ` : ''}
          ${externalLinks.length ? `
            <div>
              <div style="font-weight: 600; margin-bottom: 4px; color: var(--secondary-text-color);">External Links</div>
              <div style="border: 1px solid var(--divider-color); border-radius: 8px; overflow: hidden;">
                ${linksHtml}
              </div>
            </div>
          ` : ''}
          ${sketchImage ? `
            <div>
              <div style="font-weight: 600; margin-bottom: 4px; color: var(--secondary-text-color);">Sketch/Reference</div>
              <img src="${this._escapeHtml(String(sketchImage))}" alt="Sketch" style="
                max-width: 100%;
                height: auto;
                border: 1px solid var(--divider-color);
                border-radius: 8px;
                max-height: 200px;
              " onerror="this.style.display='none'">
            </div>
          ` : ''}
          <div style="font-size: 11px; color: var(--secondary-text-color); margin-top: 4px; font-style: italic;">
            💡 This is an idea. Editing features available in Phase 2.2
          </div>
        </div>
      </section>
    `;
  }

  // Phase 3.1 Methods: Edit Mode & Conflict Detection
  
  _toggleEditMode() {
    this._isEditMode = !this._isEditMode;
    if (this._isEditMode) {
      this._lastModifiedTimestamp = this._modelDetail.model.last_modified || Date.now();
      this._editAdvancedSectionOpen = false;
    }
    this._render();
  }

  async _handleSaveEdits() {
    const editForm = this.shadowRoot.querySelector('model-detail-edit-form');
    if (editForm && typeof editForm.submitEdits === 'function') {
      editForm.submitEdits();
      return;
    }

    console.warn('Edit form is not ready; cannot save yet.');
  }

  async _fetchCurrentModel() {
    const url = `${this._modelSidecarUrl}/api/models/${encodeURIComponent(this._modelRef)}/detail`;
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    return data.model || {};
  }

  _handleConflictResolution(action) {
    this._showConflictDialog = false;
    
    if (action === 'reload') {
      // Reload model and discard changes
      this._loadModelDetail();
      this._isEditMode = false;
    } else if (action === 'overwrite') {
      // Force save (overwrite upstream)
      this._handleSaveEdits();
    }
    // 'cancel' just closes the dialog
    
    this._render();
  }

  _initializeEditForm() {
    const container = this.shadowRoot.getElementById('edit-form-container');
    if (!container) return;

    // Reuse existing form instance to preserve focus and in-progress edits.
    const existingForm = container.querySelector('model-detail-edit-form');
    if (existingForm) {
      existingForm.hass = this._hass;
      return;
    }

    const editForm = document.createElement('model-detail-edit-form');
    const modelDataForEdit = {
      ...(this._modelDetail.model || {}),
      enrichment: this._modelDetail.enrichment || {},
    };
    editForm.setConfig({
      model_data: modelDataForEdit,
      advanced_section_open: this._editAdvancedSectionOpen,
      on_advanced_toggle: (isOpen) => {
        this._editAdvancedSectionOpen = Boolean(isOpen);
      },
      on_save: (formData) => this._handleFormSave(formData),
      on_cancel: () => {
        this._isEditMode = false;
        this._editAdvancedSectionOpen = false;
        this._render();
      }
    });
    editForm.hass = this._hass;
    container.appendChild(editForm);
  }

  async _handleFormSave(formData) {
    // Show immediate feedback before network checks so save click feels responsive.
    this._isSaving = true;
    this._error = null;
    this._render();

    // Check for conflicts first
    try {
      const currentModel = await this._fetchCurrentModel();
      if (currentModel.last_modified && currentModel.last_modified > this._lastModifiedTimestamp) {
        this._isSaving = false;
        this._showConflictDialog = true;
        this._conflictDialog = {
          currentModel,
          formData,
          action: 'save',
        };
        this._render();
        return;
      }
    } catch (error) {
      console.warn('Could not check for conflicts:', error);
      // Continue with save anyway
    }

    // Save to sidecar via HA service
    if (this._hass) {
      try {
        console.log('Calling REST command with formData:', formData);
        
        const serviceResponse = await this._hass.callService('rest_command', 'model_catalog_update_model', {
          model_ref: formData.model_ref,
          model_name: formData.model_name,
          description: formData.description,
          tags: formData.tags,
          collection: formData.collection,
          enrichment: formData.enrichment,
        });
        
        console.log('REST command response:', serviceResponse);
        
        // Reload model detail
        console.log('Reloading model detail after save...');
        await this._loadModelDetail({ silent: true });
        
        // Exit edit mode and close popup
        this._isEditMode = false;
        this._editAdvancedSectionOpen = false;
        this._isSaving = false;
        this._error = null;
        console.log('Model saved successfully');
        this._render();
      } catch (error) {
        console.error('Error saving model:', error);
        const errorMsg = error?.message || String(error) || 'Unknown error';
        this._isSaving = false;
        this._error = `Failed to save: ${errorMsg}`;
        this._render();
      }
    } else {
      this._isSaving = false;
      this._error = 'Home Assistant service context unavailable.';
      this._render();
    }
  }

  _handlePhotoPreview(photoIdx) {
    const galleryItems = this._galleryItems();
    if (photoIdx < 0 || photoIdx >= galleryItems.length) return;

    this._activePhotoIndex = photoIdx;
    this._openPhotoOverlay();
  }

  _closePhotoPreview() {
    if (this._activePhotoIndex == null) {
      return;
    }
    this._activePhotoIndex = null;
    this._closePhotoOverlay();
  }

  _stepPhotoPreview(direction) {
    const galleryItems = this._galleryItems();
    
    if (!galleryItems.length || this._activePhotoIndex == null) {
      return;
    }

    const nextIndex = (this._activePhotoIndex + direction + galleryItems.length) % galleryItems.length;
    this._activePhotoIndex = nextIndex;
    this._renderPhotoOverlay();
  }

  // ── Fullscreen photo overlay (dialog on document.body) ──

  _openPhotoOverlay() {
    this._ensureOverlayRoot();
    this._renderPhotoOverlay();
    if (this._overlayRoot && !this._overlayRoot.open) {
      this._overlayRoot.showModal();
    }
    this._applyBodyScrollLock();
    document.addEventListener('keydown', this._boundKeydownHandler);
  }

  _closePhotoOverlay() {
    document.removeEventListener('keydown', this._boundKeydownHandler);
    this._restoreBodyScrollLock();
    if (this._overlayRoot && this._overlayRoot.open) {
      this._overlayRoot.close();
    }
    this._activePhotoIndex = null;
  }

  _ensureOverlayRoot() {
    if (this._overlayRoot) return;
    const dialog = document.createElement('dialog');
    dialog.setAttribute('aria-label', 'Full-screen gallery');
    dialog.style.cssText = 'border:none;padding:0;margin:0;width:100vw;height:100vh;max-width:100vw;max-height:100vh;background:transparent;overflow:hidden;';
    dialog.addEventListener('click', this._boundOverlayClickHandler);
    dialog.addEventListener('cancel', this._boundOverlayCancelHandler);
    document.body.appendChild(dialog);
    this._overlayRoot = dialog;
  }

  _destroyOverlayRoot() {
    if (!this._overlayRoot) return;
    document.removeEventListener('keydown', this._boundKeydownHandler);
    this._restoreBodyScrollLock();
    this._overlayRoot.removeEventListener('click', this._boundOverlayClickHandler);
    this._overlayRoot.removeEventListener('cancel', this._boundOverlayCancelHandler);
    if (this._overlayRoot.open) this._overlayRoot.close();
    this._overlayRoot.remove();
    this._overlayRoot = null;
  }

  _applyBodyScrollLock() {
    if (this._savedBodyOverflow == null) {
      this._savedBodyOverflow = document.body.style.overflow || '';
    }
    document.body.style.overflow = 'hidden';
  }

  _restoreBodyScrollLock() {
    if (this._savedBodyOverflow != null) {
      document.body.style.overflow = this._savedBodyOverflow;
      this._savedBodyOverflow = null;
    }
  }

  _handleOverlayClick(event) {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;

    if (target.closest('[data-action="collapse"]')) {
      event.preventDefault();
      this._closePhotoPreview();
      return;
    }
    if (target.closest('[data-action="prev"]')) {
      event.preventDefault();
      this._stepPhotoPreview(-1);
      return;
    }
    if (target.closest('[data-action="next"]')) {
      event.preventDefault();
      this._stepPhotoPreview(1);
      return;
    }
    const thumb = target.closest('[data-index]');
    if (thumb) {
      event.preventDefault();
      const idx = parseInt(thumb.dataset.index, 10);
      if (Number.isFinite(idx)) {
        this._activePhotoIndex = idx;
        this._renderPhotoOverlay();
      }
      return;
    }
  }

  _handleOverlayCancel(event) {
    event.preventDefault();
    if (this._archiveImagePreview) {
      this._closeArchiveImagePreview();
    } else {
      this._closePhotoPreview();
    }
  }

  _handleKeydown(event) {
    // Archive image preview takes precedence when open
    if (this._archiveImagePreview) {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        this._closeArchiveImagePreview();
      } else if (event.key === 'ArrowLeft') {
        event.preventDefault();
        this._archiveImagePreview.index = Math.max(0, this._archiveImagePreview.index - 1);
        this._renderArchiveImageOverlay();
      } else if (event.key === 'ArrowRight') {
        event.preventDefault();
        this._archiveImagePreview.index = Math.min(this._archiveImagePreview.images.length - 1, this._archiveImagePreview.index + 1);
        this._renderArchiveImageOverlay();
      }
      return;
    }
    if (this._activePhotoIndex == null) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      this._closePhotoPreview();
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault();
      this._stepPhotoPreview(-1);
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      this._stepPhotoPreview(1);
    }
  }

  _renderPhotoOverlay() {
    if (!this._overlayRoot) return;

    const galleryItems = this._galleryItems();
    if (!galleryItems.length || this._activePhotoIndex == null) {
      this._overlayRoot.innerHTML = '';
      return;
    }

    const index = Math.max(0, Math.min(this._activePhotoIndex, galleryItems.length - 1));
    const item = galleryItems[index] || {};
    const imageUrl = String(item.url || '').trim();
    if (!imageUrl) {
      this._overlayRoot.innerHTML = '';
      return;
    }

    const itemName = String(item.filename || `Item ${index + 1}`).trim() || `Item ${index + 1}`;
    const modelName = (this._modelDetail && this._modelDetail.model && this._modelDetail.model.name) || this._modelRef || 'Model';

    this._overlayRoot.innerHTML =
      '<style>' +
      '.mdp-frame,.mdp-frame *{box-sizing:border-box;}' +
      '.frame{position:fixed;inset:0;}' +
      '.backdrop{appearance:none;border:none;position:absolute;inset:0;background:rgba(4,8,15,0.94);padding:0;cursor:pointer;}' +
      '.shell{position:relative;z-index:1;display:grid;grid-template-rows:auto minmax(0,1fr) auto;gap:16px;height:100%;box-sizing:border-box;padding:clamp(16px,2.2vw,28px);padding-top:max(clamp(16px,2.2vw,28px), env(safe-area-inset-top));padding-right:max(clamp(16px,2.2vw,28px), env(safe-area-inset-right));padding-bottom:max(clamp(16px,2.2vw,28px), env(safe-area-inset-bottom));padding-left:max(clamp(16px,2.2vw,28px), env(safe-area-inset-left));}' +
      '.header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;color:#fff;}' +
      '.title{font:700 clamp(18px,2.2vw,28px)/1.2 system-ui,sans-serif;letter-spacing:0.01em;}' +
      '.subtitle{margin-top:6px;font:500 clamp(13px,1.4vw,15px)/1.45 system-ui,sans-serif;color:rgba(255,255,255,0.76);}' +
      '.actions{display:flex;align-items:center;gap:10px;flex-wrap:nowrap;}' +
      '.button{appearance:none;border:1px solid rgba(255,255,255,0.24);border-radius:999px;padding:12px 16px;background:rgba(255,255,255,0.10);color:#fff;font:700 13px/1 system-ui,sans-serif;cursor:pointer;backdrop-filter:blur(10px);display:inline-flex;align-items:center;gap:8px;transition:background .16s ease,border-color .16s ease,transform .16s ease;}' +
      '.button:hover,.button:focus-visible{background:rgba(255,255,255,0.18);border-color:rgba(255,255,255,0.42);box-shadow:0 0 0 1px rgba(255,255,255,0.12),0 10px 24px rgba(0,0,0,0.2);transform:translateY(-1px);outline:none;}' +
      '.button:active{transform:translateY(0);}' +
      '.stage{position:relative;display:flex;align-items:center;justify-content:center;min-height:0;border-radius:24px;overflow:hidden;background:linear-gradient(180deg, rgba(15,23,42,0.82), rgba(2,6,23,0.98));box-shadow:0 24px 60px rgba(0,0,0,0.42);}' +
      '.image-wrap{display:flex;align-items:center;justify-content:center;width:100%;height:100%;min-height:0;padding:clamp(10px,1.6vw,22px);box-sizing:border-box;}' +
      '.image{display:block;width:100%;height:100%;max-width:100%;max-height:100%;object-fit:contain;border-radius:18px;background:rgba(15,23,42,0.32);}' +
      '.nav{appearance:none;border:none;position:absolute;top:50%;transform:translateY(-50%);width:56px;height:56px;border-radius:999px;background:rgba(255,255,255,0.14);color:#fff;font-size:30px;line-height:1;cursor:pointer;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(12px);}' +
      '.nav.prev{left:16px;}' +
      '.nav.next{right:16px;}' +
      '.filmstrip{display:flex;gap:12px;overflow-x:auto;padding:2px 2px 6px;}' +
      '.thumb{appearance:none;border:2px solid transparent;background:none;padding:0;border-radius:16px;overflow:hidden;cursor:pointer;flex:0 0 auto;opacity:0.82;transition:opacity 120ms ease,border-color 120ms ease,transform 120ms ease;}' +
      '.thumb.active{border-color:#90caf9;opacity:1;transform:translateY(-1px);}' +
      '.thumb img{display:block;width:108px;height:108px;object-fit:cover;background:rgba(15,23,42,0.35);}' +
      "dialog[aria-label='Full-screen gallery']::backdrop{background:transparent;}" +
      '@media (max-width: 900px){.shell{gap:12px;}.thumb img{width:84px;height:84px;}.nav{width:48px;height:48px;font-size:26px;}}' +
      '@media (max-width: 640px){.header{gap:12px;}.title{font-size:18px;}.subtitle{font-size:13px;}.button{padding:10px 14px;}.stage{border-radius:20px;}.image-wrap{padding:10px;}.nav.prev{left:10px;}.nav.next{right:10px;}.thumb img{width:72px;height:72px;}}' +
      '</style>' +
      '<div class="frame mdp-frame">' +
      '<button class="backdrop" type="button" data-action="collapse" aria-label="Close full-screen gallery"></button>' +
      '<div class="shell" role="dialog" aria-modal="true" aria-label="' + this._escapeHtml(modelName) + '">' +
      '<div class="header">' +
      '<div><div class="title">' + this._escapeHtml(modelName) + '</div><div class="subtitle">' + this._escapeHtml(itemName) + ' \u00b7 ' + (index + 1) + ' / ' + galleryItems.length + '</div></div>' +
      '<div class="actions"><button class="button" type="button" data-action="collapse">Close</button></div>' +
      '</div>' +
      '<div class="stage">' +
      '<div class="image-wrap"><img class="image" src="' + this._escapeHtml(imageUrl) + '" alt="' + this._escapeHtml(itemName) + '" loading="eager" decoding="async"></div>' +
      (galleryItems.length > 1 ? '<button class="nav prev" type="button" data-action="prev" aria-label="Previous image">&#8249;</button><button class="nav next" type="button" data-action="next" aria-label="Next image">&#8250;</button>' : '') +
      '</div>' +
      '<div class="filmstrip">' + galleryItems.map(function (gi, idx) {
        var thumbUrl = gi.thumbnail_url || gi.url || '';
        var thumbAlt = gi.filename || 'Item ' + (idx + 1);
        return '<button class="thumb' + (idx === index ? ' active' : '') + '" type="button" data-index="' + idx + '" aria-label="' + this._escapeHtml(thumbAlt) + '">' +
          (thumbUrl ? '<img src="' + this._escapeHtml(thumbUrl) + '" alt="' + this._escapeHtml(thumbAlt) + '" loading="lazy" decoding="async">' : '') +
          '</button>';
      }.bind(this)).join('') + '</div>' +
      '</div>' +
      '</div>';
  }

  async _handleSetPhotoPreview(photoId) {
    if (!this._modelSidecarUrl || !this._modelRef) return;
    
    try {
      // Demote any file assets currently marked as preview
      const base = String(this._modelSidecarUrl || '').trim().replace(/\/$/, '');
      const localModelId = String((this._modelDetail && this._modelDetail.local_model_id) || this._modelRef || '').trim();
      const files = (this._modelDetail && this._modelDetail.model && Array.isArray(this._modelDetail.model.files))
        ? this._modelDetail.model.files
        : [];
      const previewAssetIds = files
        .filter(file => file && (file.is_preview || file.asset_role === 'preview'))
        .map(file => String(file.asset_id || file.id || '').trim())
        .filter(Boolean);
      for (const assetId of previewAssetIds) {
        await fetch(
          `${base}/api/local/models/${encodeURIComponent(localModelId)}/assets/${encodeURIComponent(assetId)}`,
          {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ asset_role: 'supporting' }),
          }
        );
      }

      const response = await fetch(
        `${base}/api/models/${encodeURIComponent(this._modelRef)}/photos/${encodeURIComponent(photoId)}/preview`,
        {
          method: 'POST',
        }
      );

      let payload = null;
      try {
        payload = await response.json();
      } catch (parseError) {
        payload = null;
      }

      if (!response.ok) {
        const errorMessage = payload && payload.error
          ? String(payload.error)
          : `HTTP ${response.status}`;
        throw new Error(errorMessage);
      }
      
      // Reload model detail
      this._error = '';
      await this._loadModelDetail({ silent: true });
    } catch (error) {
      console.error('Error setting preview photo:', error);
      this._error = `Failed to set preview: ${error}`;
      this._render();
    }
  }

  _handleDeletePhoto(photoId) {
    if (confirm('Are you sure you want to delete this photo?')) {
      this._performDeletePhoto(photoId);
    }
  }

  async _performDeletePhoto(photoId) {
    if (!this._modelSidecarUrl || !this._modelRef) return;
    
    try {
      const response = await fetch(
        `${this._modelSidecarUrl.replace(/\/$/, '')}/api/models/${encodeURIComponent(this._modelRef)}/photos/${encodeURIComponent(photoId)}`,
        {
          method: 'DELETE',
        }
      );

      let payload = null;
      try {
        payload = await response.json();
      } catch (parseError) {
        payload = null;
      }

      if (!response.ok) {
        const errorMessage = payload && payload.error
          ? String(payload.error)
          : `HTTP ${response.status}`;
        throw new Error(errorMessage);
      }
      
      // Reload model detail
      this._error = '';
      await this._loadModelDetail({ silent: true });
      await this._autoPromotePreviewAfterDelete();
    } catch (error) {
      console.error('Error deleting photo:', error);
      this._error = `Failed to delete photo: ${error}`;
      this._render();
    }
  }

  async _handlePhotoFileSelect(files) {
    if (!files || files.length === 0) return;
    
    // Process each file
    for (const file of files) {
      await this._uploadPhoto(file);
    }
  }

  async _uploadPhoto(file) {
    if (!this._modelSidecarUrl || !this._modelRef) return;
    
    // Validate file type and size
    const maxSize = 10 * 1024 * 1024; // 10MB
    if (file.size > maxSize) {
      this._error = `File too large: ${file.name} (max 10MB)`;
      this._render();
      return;
    }
    
    const validTypes = ['image/jpeg', 'image/png', 'image/webp'];
    if (!validTypes.includes(file.type)) {
      this._error = `Invalid file type: ${file.name} (must be JPG, PNG, or WebP)`;
      this._render();
      return;
    }

    try {
      const base64Data = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (event) => resolve(event.target?.result);
        reader.onerror = () => reject(reader.error || new Error('Failed to read file'));
        reader.readAsDataURL(file);
      });

      const response = await fetch(
        `${this._modelSidecarUrl.replace(/\/$/, '')}/api/models/${encodeURIComponent(this._modelRef)}/photos`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            photo_file: base64Data,
            set_as_preview: !this._modelDetail.photos || this._modelDetail.photos.length === 0,
          }),
        }
      );

      let payload = null;
      try {
        payload = await response.json();
      } catch (parseError) {
        payload = null;
      }

      if (!response.ok) {
        const errorMessage = payload && payload.error
          ? String(payload.error)
          : `HTTP ${response.status}`;
        throw new Error(errorMessage);
      }

      this._error = '';
      await this._loadModelDetail({ silent: true });
    } catch (error) {
      console.error('Error reading file:', error);
      this._error = `Failed to upload ${file.name}: ${error}`;
      this._render();
    }
  }

  _handleDownload() {
    if (!this._modelDetail || !this._modelDetail.model) {
      console.warn('No model detail available for download');
      return;
    }

    const model = this._modelDetail.model;
    const files = model.files || [];
    
    if (files.length === 0) {
      this._error = 'No files available for download';
      this._render();
      return;
    }

    // For now, log available files
    console.log('Download triggered. Available files:', files);
    
    // In future: could open a modal to select which file to download
    // For now, just show a notification
    if (this._hass) {
      this._hass.callService('persistent_notification', 'create', {
        title: 'Model Download',
        message: `${files.length} file(s) available. Download feature coming soon.`,
      }).catch(err => console.error('Notification failed:', err));
    }
  }

  _handlePrint() {
    if (!this._modelDetail || !this._modelDetail.model) {
      console.warn('No model detail available for print');
      return;
    }
    var model = this._modelDetail.model;
    var modelName = String(model.name || this._modelRef || "Model").trim() || "Model";
    // Check for existing queue entries to populate re-add warning in dialog.
    this._listUnifiedQueueEntriesForModel(this._modelRef).then(function (entries) {
      this._openQueueDialog(this._modelRef, modelName, entries, { intent: entries.length ? "re-add" : "add", defaultState: "up_next" });
    }.bind(this)).catch(function () {
      this._openQueueDialog(this._modelRef, modelName, [], { intent: "add", defaultState: "up_next" });
    }.bind(this));
  }

  // ── Unified Queue Dialog methods (#1499) ──────────────────────────────────

  _getPrinterId() {
    return String(this._config && this._config.queue_printer_id ? this._config.queue_printer_id : "p1");
  }

  async _listUnifiedQueueEntriesForModel(modelRef) {
    var queueApiBase = this._resolveModelSidecarUrl() + "/api/v1";
    var printerId = this._getPrinterId();
    var response = await fetch(queueApiBase + "/queues/" + encodeURIComponent(printerId) + "/entries?source_kind=catalog_model&limit=200");
    if (!response.ok) {
      return [];
    }
    var payload = await response.json().catch(function () { return {}; });
    var entries = Array.isArray(payload && payload.entries) ? payload.entries : [];
    return entries.filter(function (entry) {
      return String((entry && (entry.source_id || entry.source_ref)) || "").trim() === modelRef;
    });
  }

  async _openQueueDialog(modelRef, modelName, entries, options) {
    var normalizedEntries = Array.isArray(entries) ? entries : [];
    var dialogOptions = options && typeof options === "object" ? options : {};
    this._queueDialogOpen = true;
    this._queueDialogMode = "quick";
    this._queueDialogModelRef = String(modelRef || "").trim();
    this._queueDialogModelName = String(modelName || "Model").trim() || "Model";
    this._queueDialogIntent = dialogOptions.intent === "re-add" ? "re-add" : "add";
    this._queueDialogExistingCount = normalizedEntries.length;
    this._queueDialogTargetState = this._normalizeQueueDialogTargetState(dialogOptions.defaultState || "up_next");
    this._queueDialogNotes = "";
    this._queueDialogLoading = true;
    this._queueDialogSubmitting = false;
    this._queueDialogError = "";
    this._queueDialogFiles = [];
    this._render();
    try {
      this._queueDialogFiles = await this._loadQueueDialogSourceDetail(this._queueDialogModelRef);
    } catch (error) {
      this._queueDialogError = error && error.message ? String(error.message) : "Could not load model queue defaults.";
      this._queueDialogFiles = [];
    } finally {
      this._queueDialogLoading = false;
      this._render();
    }
  }

  _closeQueueDialog() {
    this._queueDialogOpen = false;
    this._queueDialogLoading = false;
    this._queueDialogSubmitting = false;
    this._queueDialogError = "";
    this._queueDialogFiles = [];
    this._render();
  }

  _normalizeQueueDialogTargetState(state) {
    var valid = ["backlog", "up_next", "preparing", "ready"];
    var s = String(state || "").trim().toLowerCase();
    return valid.indexOf(s) >= 0 ? s : "up_next";
  }

  _queueDialogTargetStateLabel(state) {
    var map = { backlog: "Backlog", up_next: "Up Next", preparing: "Preparing", ready: "Ready" };
    return map[String(state || "").trim()] || String(state || "Up Next");
  }

  async _loadQueueDialogSourceDetail(modelRef) {
    var response = await fetch(this._resolveModelSidecarUrl() + "/api/models/" + encodeURIComponent(modelRef) + "/detail");
    if (!response.ok) {
      throw new Error("Failed to load model detail (" + response.status + ").");
    }
    var payload = await response.json();
    var model = payload && payload.model && typeof payload.model === "object" ? payload.model : {};
    var files = Array.isArray(model.files) ? model.files : [];
    if (!files.length) {
      throw new Error("Selected model has no queueable files.");
    }
    var sidecarUrl = this._resolveModelSidecarUrl();
    var normalized = await Promise.all(files.map(async function (file, index) {
      var fileId = String(file.id || file.file_id || "").trim() || ("catalog-file-" + String(index + 1));
      var fileName = String(file.filename || file.name || fileId).trim();
      var fileType = String(file.file_type || file.content_type || file.asset_type || "").toLowerCase();
      var lowerName = fileName.toLowerCase();
      var plates = [{ plate_id: "default", plate_name: "Primary Plate", selected: true, is_primary: true }];
      if (lowerName.endsWith(".3mf") || fileType.indexOf("3mf") >= 0) {
        try {
          var pr = await fetch(sidecarUrl + "/api/models/" + encodeURIComponent(modelRef) + "/files/" + encodeURIComponent(fileId) + "/plates");
          if (pr.ok) {
            var pp = await pr.json();
            var rawPlates = Array.isArray(pp && pp.plates) ? pp.plates : [];
            if (rawPlates.length > 0) {
              plates = rawPlates.map(function (plate, pi) {
                return {
                  plate_id: String(plate.plate_key || plate.plate_id || plate.id || ("plate-" + String(pi + 1))).trim(),
                  plate_name: String(plate.plate_name || plate.name || ("Plate " + String(pi + 1))).trim(),
                  selected: pi === 0,
                  is_primary: pi === 0,
                };
              });
            }
          }
        } catch (_e) { /* skip */ }
      }
      return {
        file_id: fileId,
        file_name: fileName,
        selected: index === 0,
        thumbnail_url: String(file.thumbnail_url || file.preview_url || "").trim(),
        plates: plates,
      };
    }));
    if (!normalized.some(function (f) { return !!f.selected; }) && normalized.length > 0) {
      normalized[0].selected = true;
    }
    return normalized;
  }

  _setQueueDialogMode(mode) {
    var normalized = String(mode || "").trim().toLowerCase();
    if (normalized !== "quick" && normalized !== "plan") return;
    this._queueDialogMode = normalized;
    this._render();
  }

  _setQueueDialogAllPlatesSelected(selected) {
    var nextSelected = !!selected;
    this._queueDialogFiles = this._queueDialogFiles.map(function (file) {
      return Object.assign({}, file, {
        selected: nextSelected,
        plates: Array.isArray(file.plates) ? file.plates.map(function (p) { return Object.assign({}, p, { selected: nextSelected }); }) : [],
      });
    });
    this._render();
  }

  _toggleQueueDialogFileSelection(fileId) {
    if (!fileId) return;
    this._queueDialogFiles = this._queueDialogFiles.map(function (file) {
      if (String(file.file_id || "") !== fileId) return file;
      var nextSelected = !file.selected;
      return Object.assign({}, file, {
        selected: nextSelected,
        plates: Array.isArray(file.plates) ? file.plates.map(function (p, pi) {
          return Object.assign({}, p, { selected: nextSelected ? pi === 0 || !!p.selected : false });
        }) : [],
      });
    });
    this._render();
  }

  _toggleQueueDialogPlateSelection(fileId, plateId) {
    if (!fileId || !plateId) return;
    this._queueDialogFiles = this._queueDialogFiles.map(function (file) {
      if (String(file.file_id || "") !== fileId) return file;
      var nextPlates = (file.plates || []).map(function (plate) {
        if (String(plate.plate_id || "") !== plateId) return plate;
        return Object.assign({}, plate, { selected: !plate.selected });
      });
      return Object.assign({}, file, { selected: nextPlates.some(function (p) { return !!p.selected; }), plates: nextPlates });
    });
    this._render();
  }

  _getQueueDialogMetrics() {
    var files = Array.isArray(this._queueDialogFiles) ? this._queueDialogFiles : [];
    var selectedFiles = files.filter(function (f) { return !!f.selected; });
    var selectedPlates = selectedFiles.reduce(function (sum, f) {
      return sum + (Array.isArray(f.plates) ? f.plates.filter(function (p) { return !!p.selected; }).length : 0);
    }, 0);
    return { totalFiles: files.length, selectedFiles: selectedFiles.length, selectedPlates: selectedPlates };
  }

  _canSubmitQueueDialog() {
    if (this._queueDialogLoading || this._queueDialogSubmitting) return false;
    if (!Array.isArray(this._queueDialogFiles) || this._queueDialogFiles.length === 0) return false;
    if (this._queueDialogMode !== "plan") return true;
    return this._getQueueDialogMetrics().selectedPlates > 0;
  }

  _queueDialogPrimarySummary() {
    if (!Array.isArray(this._queueDialogFiles) || !this._queueDialogFiles.length) return "Loading queue defaults...";
    var primaryFile = this._queueDialogFiles[0] || {};
    var primaryPlate = Array.isArray(primaryFile.plates) && primaryFile.plates.length > 0 ? primaryFile.plates[0] : null;
    return "Will queue " + String(primaryFile.file_name || "Primary file") + " · " + String(primaryPlate && primaryPlate.plate_name ? primaryPlate.plate_name : "Primary Plate") + " on " + this._getPrinterId() + " in state " + this._queueDialogTargetStateLabel("up_next") + ".";
  }

  async _submitQueueDialog() {
    if (!this._queueDialogModelRef || this._queueDialogLoading || this._queueDialogSubmitting) return;
    if (!this._canSubmitQueueDialog()) {
      this._queueDialogError = this._queueDialogMode === "plan" ? "Select at least one file plate before adding to queue." : "No queueable files were found for this model.";
      this._render();
      return;
    }
    var targetState = this._queueDialogMode === "quick" ? "up_next" : this._normalizeQueueDialogTargetState(this._queueDialogTargetState);
    var primaryFile = this._queueDialogFiles[0] || {};
    var primaryPlate = Array.isArray(primaryFile.plates) && primaryFile.plates.length > 0 ? primaryFile.plates[0] : null;
    var payload = {
      source_kind: "catalog_model",
      source_id: this._queueDialogModelRef,
      title: this._queueDialogModelName,
      queue_notes: String(this._queueDialogNotes || "").trim(),
      selection_mode: "selected_plates",
      selected_files: this._queueDialogMode === "quick"
        ? [{ file_id: primaryFile.file_id, file_name: primaryFile.file_name, selected: true, plates: primaryPlate ? [{ plate_id: primaryPlate.plate_id, selected: true }] : [] }]
        : this._queueDialogFiles.map(function (f) { return { file_id: f.file_id, file_name: f.file_name, selected: !!f.selected, plates: (f.plates || []).map(function (p) { return { plate_id: p.plate_id, selected: !!p.selected }; }) }; }),
    };
    if (targetState !== "up_next") {
      payload.state = targetState;
    }
    this._queueDialogSubmitting = true;
    this._queueDialogError = "";
    this._render();
    try {
      await addUnifiedQueueEntry({
        queueApiBase: this._resolveModelSidecarUrl() + "/api/v1",
        printerId: this._getPrinterId(),
        payload: payload,
      });
      this._closeQueueDialog();
      // Reload model detail to refresh queued_items count
      await this._loadModelDetail({ silent: true });
    } catch (error) {
      this._queueDialogSubmitting = false;
      this._queueDialogError = error && error.message ? String(error.message) : "Could not add to queue.";
      this._render();
    }
  }

  _renderQueueDialog() {
    if (!this._queueDialogOpen) return "";
    var metrics = this._getQueueDialogMetrics();
    var canSubmit = this._canSubmitQueueDialog();
    var existingNote = this._queueDialogExistingCount > 0
      ? '<div class="queue-dialog-existing-note">This model already has ' + this._escapeHtml(String(this._queueDialogExistingCount)) + ' queue entr' + (this._queueDialogExistingCount === 1 ? 'y' : 'ies') + '. A new entry will be created.</div>'
      : "";
    var planBody = this._queueDialogLoading
      ? '<div class="queue-dialog-note">Loading model files and plates...</div>'
      : this._queueDialogFiles.length === 0
      ? '<div class="queue-dialog-note">No queueable files available for this model.</div>'
      : '<div class="queue-dialog-toolbar"><button class="toolbar-btn" type="button" data-action="queue-dialog-select-all">Select all</button><button class="toolbar-btn ghost" type="button" data-action="queue-dialog-clear-all">Deselect all</button></div>'
        + '<div class="queue-dialog-file-list">'
        + this._queueDialogFiles.map(function (file) {
            var plateCount = Array.isArray(file.plates) ? file.plates.length : 0;
            var selectedPlates = Array.isArray(file.plates) ? file.plates.filter(function (p) { return !!p.selected; }).length : 0;
            return '<section class="queue-dialog-file-block">'
              + '  <button class="queue-dialog-file-toggle' + (file.selected ? ' active' : '') + '" type="button" data-action="queue-dialog-toggle-file" data-file-id="' + this._escapeHtml(String(file.file_id || '')) + '">' + this._escapeHtml(String(file.file_name || 'Queue file')) + '<span>' + this._escapeHtml(String(selectedPlates) + '/' + String(plateCount) + ' plates') + '</span></button>'
              + '  <div class="queue-dialog-plates">'
              + (file.plates || []).map(function (plate) {
                  return '<button class="queue-dialog-plate-toggle' + (plate.selected ? ' active' : '') + '" type="button" data-action="queue-dialog-toggle-plate" data-file-id="' + this._escapeHtml(String(file.file_id || '')) + '" data-plate-id="' + this._escapeHtml(String(plate.plate_id || '')) + '">' + this._escapeHtml(String(plate.plate_name || 'Plate')) + '</button>';
                }.bind(this)).join('')
              + '  </div>'
              + '</section>';
          }.bind(this)).join('')
        + '</div>';
    return ''
      + '<div class="queue-dialog-backdrop" data-action="close-queue-dialog">'
      + '  <div class="queue-dialog" role="dialog" aria-modal="true" aria-label="Add to Queue">'
      + '    <div class="queue-dialog-header">'
      + '      <div><h3>Add to Queue</h3><div class="queue-dialog-subtitle">' + this._escapeHtml(this._queueDialogModelName) + '</div></div>'
      + '      <button class="modal-close-btn" type="button" data-action="close-queue-dialog" aria-label="Close">✕</button>'
      + '    </div>'
      + '    <div class="queue-dialog-tabs">'
      + '      <button class="queue-dialog-tab' + (this._queueDialogMode === 'quick' ? ' active' : '') + '" type="button" data-action="queue-dialog-mode" data-mode="quick">Quick</button>'
      + '      <button class="queue-dialog-tab' + (this._queueDialogMode === 'plan' ? ' active' : '') + '" type="button" data-action="queue-dialog-mode" data-mode="plan">Plan</button>'
      + '    </div>'
      + '    <div class="queue-dialog-body">'
      + existingNote
      + (this._queueDialogMode === 'quick'
          ? '<div class="queue-dialog-summary">' + this._escapeHtml(this._queueDialogPrimarySummary()) + '</div>'
          : '<div class="queue-dialog-summary">Choose plates, target state, and notes before creating the queue entry.</div>'
            + '<label class="queue-dialog-field"><span>Target state</span><select class="queue-dialog-target-state"><option value="backlog"' + (this._queueDialogTargetState === 'backlog' ? ' selected' : '') + '>Backlog</option><option value="up_next"' + (this._queueDialogTargetState === 'up_next' ? ' selected' : '') + '>Up Next</option><option value="preparing"' + (this._queueDialogTargetState === 'preparing' ? ' selected' : '') + '>Preparing</option><option value="ready"' + (this._queueDialogTargetState === 'ready' ? ' selected' : '') + '>Ready</option></select></label>'
            + '<label class="queue-dialog-field"><span>Notes</span><textarea class="queue-dialog-notes" data-queue-dialog-notes="true" rows="3" placeholder="Optional operator notes...">' + this._escapeHtml(this._queueDialogNotes) + '</textarea></label>'
            + '<div class="queue-dialog-metrics">Selected ' + this._escapeHtml(String(metrics.selectedPlates)) + ' plates across ' + this._escapeHtml(String(metrics.selectedFiles)) + ' files.</div>'
            + planBody)
      + (this._queueDialogError ? '<div class="queue-dialog-error">' + this._escapeHtml(this._queueDialogError) + '</div>' : '')
      + '    </div>'
      + '    <div class="queue-dialog-footer">'
      + '      <button class="toolbar-btn ghost" type="button" data-action="close-queue-dialog">Cancel</button>'
      + '      <button class="toolbar-btn queue-dialog-submit" type="button" data-action="queue-dialog-submit"' + (canSubmit ? '' : ' disabled') + '>' + (this._queueDialogSubmitting ? 'Adding...' : 'Add to Queue') + '</button>'
      + '    </div>'
      + '  </div>'
      + '</div>';
  }

  _buildModelViewerCardConfig() {
    const model = this._modelDetail && this._modelDetail.model ? this._modelDetail.model : {};
    return {
      type: 'custom:model-detail-3d-viewer-tab',
      model_ref: this._modelRef,
      model_name: String(model.name || '').trim(),
      model_sidecar_url: this._modelSidecarUrl,
      model_json: JSON.stringify(model),
    };
  }

  _buildModelViewerPopupContent() {
    return {
      type: 'vertical-stack',
      cards: [this._buildModelViewerCardConfig()],
    };
  }

  _notifyBrowserDetailChanged() {
    var modelRef = String((this._modelDetail && this._modelDetail.local_model_id) || this._modelRef || '').trim();
    if (!modelRef) {
      return;
    }
    try {
      window.dispatchEvent(new CustomEvent('model-catalog-detail-changed', {
        detail: { modelRef: modelRef },
      }));
    } catch (_e) { /* ignore */ }
  }

  _fireBrowserModEvent(service, data) {
    const event = new CustomEvent('ll-custom', {
      bubbles: true,
      composed: true,
      detail: {
        browser_mod: {
          service,
          data,
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

  _replaceCurrentPopup(popupConfig) {
    if (!popupConfig || typeof popupConfig !== 'object') {
      return;
    }

    this._fireBrowserModEvent('browser_mod.sequence', {
      sequence: [
        { service: 'browser_mod.close_popup' },
        { service: 'browser_mod.popup', data: popupConfig },
      ],
    });
  }

  _openViewerPopup() {
    const model = this._modelDetail && this._modelDetail.model ? this._modelDetail.model : null;

    if (!model) {
      if (this._hass) {
        this._hass.callService('persistent_notification', 'create', {
          title: '3D Viewer',
          message: 'Model details are not loaded yet. Try again in a moment.',
        }).catch(err => console.error('Notification failed:', err));
      }
      return;
    }

    this._replaceCurrentPopup({
      title: `${String(model.name || 'Model')} - 3D Viewer`,
      size: 'wide',
      content: this._buildModelViewerPopupContent(),
    });
  }

  async _markContributionAction(action, opts) {
    const skip = opts && opts.skip;
    if (!this._modelDetail || !this._modelDetail.model) {
      console.warn('No model detail available');
      return;
    }

    const model = this._modelDetail.model;
    const model_ref = this._modelRef || model.public_id || model.model_url || model.model_id;

    if (!model_ref) {
      console.warn('No model reference available');
      return;
    }

    // Optimistic local update — avoids a full re-fetch / flash
    const metadata = model.structured_metadata || (this._modelDetail.enrichment || {}).structured_metadata || {};
    const publishing = metadata.publishing || {};
    if (!publishing.contribution) publishing.contribution = {};
    const now = new Date().toISOString();
    if (skip) {
      publishing.contribution[action + '_skipped_at'] = now;
    } else {
      publishing.contribution[action + '_at'] = now;
    }
    this._render();

    try {
      const body = skip ? { skip: true } : {};
      const response = await fetch(this._resolveModelSidecarUrl() + `/api/models/${encodeURIComponent(model_ref)}/contribution/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        throw new Error(`Failed to mark ${action}: ${response.statusText}`);
      }
    } catch (error) {
      console.error('Error marking contribution action:', error);
      // Revert optimistic update on failure
      if (skip) {
        delete publishing.contribution[action + '_skipped_at'];
      } else {
        delete publishing.contribution[action + '_at'];
      }
      this._render();
      if (this._hass) {
        this._hass.callService('persistent_notification', 'create', {
          title: 'Error',
          message: `Failed to update contribution status: ${error.message}`,
        }).catch(err => console.error('Notification failed:', err));
      }
    }
  }

  // --- Source panel save/action methods ---

  async _saveSourceField(fieldKey, value) {
    if (!this._modelRef) return;
    const baseUrl = this._resolveModelSidecarUrl();
    const url = `${baseUrl}/api/models/${encodeURIComponent(this._modelRef)}/fields/${encodeURIComponent(fieldKey)}`;
    try {
      const resp = await fetch(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value }),
      });
      if (!resp.ok) {
        console.error(`Failed to save source field ${fieldKey}: ${resp.status}`);
        return;
      }
      // Optimistically update local model state
      this._applySourceFieldLocally(fieldKey, value);
      this._render();
    } catch (err) {
      console.error(`Error saving source field ${fieldKey}:`, err);
    }
  }

  _applySourceFieldLocally(fieldKey, value) {
    if (!this._modelDetail?.model) return;
    const model = this._modelDetail.model;
    if (!model.structured_metadata) model.structured_metadata = {};
    const sm = model.structured_metadata;
    if (!sm.publishing) sm.publishing = {};
    if (!sm.provenance) sm.provenance = {};

    if (fieldKey === 'publication_source') {
      sm.publishing.publication_source = value;
    } else if (fieldKey === 'source_platform_label') {
      sm.publishing.source_platform_label = value;
    } else if (fieldKey === 'source_urls') {
      sm.provenance.source_urls = value;
    }
  }

  _getSourceUrls() {
    const model = this._modelDetail?.model;
    if (!model) return [];
    const metadata = model.structured_metadata || this._modelDetail?.enrichment?.structured_metadata || {};
    const provenance = metadata.provenance || {};
    const publishing = metadata.publishing || {};
    const explicitUrls = Array.isArray(provenance.source_urls) ? [...provenance.source_urls] : [];
    const published_urls = publishing.published_urls || {};
    const legacyUrls = Object.values(published_urls).filter(u => typeof u === 'string' && u.startsWith('http'));
    const downloadUrl = typeof provenance.source_download_url === 'string' && provenance.source_download_url.startsWith('http') ? provenance.source_download_url : null;
    const seen = new Set(explicitUrls);
    const merged = [...explicitUrls];
    if (downloadUrl && !seen.has(downloadUrl)) { merged.push(downloadUrl); seen.add(downloadUrl); }
    for (const u of legacyUrls) { if (!seen.has(u)) { merged.push(u); seen.add(u); } }
    return merged;
  }

  async _addSourceUrl() {
    const urls = this._getSourceUrls();
    urls.push('');
    await this._saveSourceField('source_urls', urls);
  }

  async _removeSourceUrl(index) {
    const urls = this._getSourceUrls();
    if (index < 0 || index >= urls.length) return;
    const url = urls[index];
    const confirmMsg = url ? `Remove URL "${url}"?` : 'Remove this empty URL entry?';
    if (!confirm(confirmMsg)) return;
    urls.splice(index, 1);
    await this._saveSourceField('source_urls', urls);
  }

  _openSourceUrl(index) {
    const urls = this._getSourceUrls();
    const url = urls[index];
    if (url && typeof url === 'string' && url.startsWith('http')) {
      window.open(url, '_blank');
    }
  }

  async _updateSourceUrl(index, newValue) {
    const urls = this._getSourceUrls();
    if (index < 0 || index >= urls.length) return;
    urls[index] = newValue;
    await this._saveSourceField('source_urls', urls);
  }

  _openSourcePlatform() {
    if (!this._modelDetail || !this._modelDetail.model) {
      return;
    }

    const model = this._modelDetail.model;
    const metadata = model.structured_metadata || this._modelDetail?.enrichment?.structured_metadata || {};
    const publishing = metadata.publishing || {};
    const published_urls = publishing.published_urls || {};
    const publication_source = publishing.publication_source;

    if (!publication_source || !published_urls[publication_source]) {
      console.warn('No source platform URL available');
      return;
    }

    const url = published_urls[publication_source];
    if (typeof url === 'string' && url.startsWith('http')) {
      window.open(url, '_blank');
    }
  }

  _openPhotoGallery() {
    if (!this._modelDetail) {
      return;
    }

    // Switch to gallery tab to show photos
    this._activeTab = 'gallery';
    this._render();
  }

  getCardSize() {
    return 10;
  }
}

customElements.define("model-detail-popup-card", ModelDetailPopupCard);

Object.assign(ModelDetailPopupCard.prototype, {
  _resetQueueDialogState() {
    this._queueDialogController.resetState();
  },
  _closeQueueDialog() {
    this._queueDialogController.close();
  },
  _openQueueDialog(modelRef, modelName, entries, options) {
    return this._queueDialogController.open(modelRef, modelName, entries, options);
  },
  _setQueueDialogMode(mode) {
    this._queueDialogController.setMode(mode);
  },
  _setQueueDialogAllPlatesSelected(selected) {
    this._queueDialogController.setAllPlatesSelected(selected);
  },
  _toggleQueueDialogFileSelection(fileId) {
    this._queueDialogController.toggleFileSelection(fileId);
  },
  _toggleQueueDialogPlateSelection(fileId, plateId) {
    this._queueDialogController.togglePlateSelection(fileId, plateId);
  },
  _getQueueDialogMetrics() {
    return this._queueDialogController.getMetrics();
  },
  _queueDialogPrimarySummary() {
    return this._queueDialogController.primarySummary();
  },
  _canSubmitQueueDialog() {
    return this._queueDialogController.canSubmit();
  },
  _submitQueueDialog() {
    return this._queueDialogController.submit();
  },
  _normalizeQueueDialogTargetState(state) {
    return normalizeQueueDialogTargetState(state);
  },
  _queueDialogTargetStateLabel(state) {
    return queueDialogTargetStateLabel(state);
  },
  _renderQueueDialog() {
    return this._queueDialogController.render();
  },
});
