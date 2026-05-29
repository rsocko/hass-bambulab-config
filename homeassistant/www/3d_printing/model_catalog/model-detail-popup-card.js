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
import { UnifiedQueueDialogController, normalizeQueueDialogTargetState, queueDialogTargetStateLabel } from '../common/unified-queue-dialog.js?v=2';
import { pickIdeaPlaceholderUrl } from './idea-placeholders.js?v=1';

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
    this._error = "";
    this._activeTab = "details";
    this._isEditMode = false;
    this._refreshingCandidates = false;
    this._refreshCandidatesDone = false;
    this._archiveMetaCache = {};
    this._archiveImagePreview = null; // { archiveId, images[], index }
    this._archiveLinkageFilter = 'all';
    this._linkedArchiveSortOrder = 'desc';
    this._selectedArchiveCandidates = {};
    this._photoGallery = [];
    this._activePhotoIndex = null;
    this._heroMediaFilter = 'all';
    this._heroActiveMediaIndex = 0;
    this._heroHiddenMediaFieldKey = 'media_hidden_ids';
    this._heroSourcePreviewFieldKey = 'source_image_preview_url';
    this._overflowOpen = false;
    this._panelMode = 'tabs';
    this._panelActiveTab = 'panel-queue';
    this._supportViewMode = 'files';
    this._supportThumbSize = 'medium';
    this._supportTypeFilter = 'all';
    this._supportFolderPath = '';
    this._supportImagePreview = null; // { items: [{url,name}], index }
    this._supportRenderedImageItems = [];
    this._collapsedSections = {};
    this._modelFilePlateCounts = {};
    this._modelFilePlateCountPending = new Set();
    this._modelFilePlateCountRequestToken = 0;
    this._modelFilePlateDetails = {};
    this._modelFilePlateDetailsPending = new Set();
    this._modelFilePlateDetailsRequestToken = 0;
    this._popupExtensions = new Map();
    this._pendingPopupShellScroll = null;
    this._ideaMetaEditOpen = false;
    this._ideaMetaSaving = false;
    this._ideaPromoteBusy = false;
    this._ideaMetaDraft = {
      notes: '',
      externalLinksText: '',
      sketchImageUrl: '',
    };
    this._modelMetaEditOpen = false;
    this._modelMetaLoading = false;
    this._modelMetaSaving = false;
    this._modelMetaDraft = {
      modelName: '',
      description: '',
      collectionMemberships: [],
      projectMemberships: [],
    };
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

    // Tag picker state
    this._tagPickerOpen = false;
    this._tagSearchQuery = "";
    this._tagSearchSelectionStart = null;
    this._tagSearchSelectionEnd = null;
    this._tagPickerHighlightIndex = 0;
    this._knownTags = []; // populated on first picker open
    this._allTagsFetched = false;
    this._collectionPickerOpen = false;
    this._collectionSearchQuery = '';
    this._collectionSearchSelectionStart = null;
    this._collectionSearchSelectionEnd = null;
    this._collectionPickerHighlightIndex = 0;
    this._knownCollections = [];
    this._allCollectionsFetched = false;
    this._collectionEditFeedback = null;
    this._collectionEditFeedbackTimer = null;
    this._collectionMembershipStaleIds = [];
    this._collectionCreateBusy = false;
    this._projectPickerOpen = false;
    this._projectSearchQuery = '';
    this._projectSearchSelectionStart = null;
    this._projectSearchSelectionEnd = null;
    this._projectPickerHighlightIndex = 0;
    this._knownProjects = [];
    this._allProjectsFetched = false;
    this._projectEditFeedback = null;
    this._projectEditFeedbackTimer = null;
    this._projectMembershipStaleIds = [];
    this._projectCreateBusy = false;
    
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
    const previousModelRef = this._modelRef;
    this._config = config || {};
    this._modelRef = String(this._config.model_ref || "").trim();
    this._modelSidecarUrl = String(this._config.model_sidecar_url || "").trim();
    if (this._modelRef !== previousModelRef) {
      this._resetModelFilePlateCounts();
      this._archiveMetaCache = {};
      this._archiveLinkageFilter = 'all';
      this._linkedArchiveSortOrder = 'desc';
      this._selectedArchiveCandidates = {};
      this._supportViewMode = 'files';
      this._supportThumbSize = 'medium';
      this._supportTypeFilter = 'all';
      this._supportFolderPath = '';
      this._supportImagePreview = null;
      this._supportRenderedImageItems = [];
      this._ideaMetaEditOpen = false;
      this._ideaMetaSaving = false;
      this._ideaPromoteBusy = false;
      this._modelMetaEditOpen = false;
      this._modelMetaLoading = false;
      this._modelMetaSaving = false;
      this._collectionPickerOpen = false;
      this._collectionSearchQuery = '';
      this._collectionPickerHighlightIndex = 0;
      this._knownCollections = [];
      this._allCollectionsFetched = false;
      this._collectionEditFeedback = null;
      this._clearCollectionEditFeedbackTimer();
      this._collectionMembershipStaleIds = [];
      this._collectionCreateBusy = false;
      this._projectPickerOpen = false;
      this._projectSearchQuery = '';
      this._projectPickerHighlightIndex = 0;
      this._knownProjects = [];
      this._allProjectsFetched = false;
      this._projectEditFeedback = null;
      this._clearProjectEditFeedbackTimer();
      this._projectMembershipStaleIds = [];
      this._projectCreateBusy = false;
      this._ideaMetaDraft = {
        notes: '',
        externalLinksText: '',
        sketchImageUrl: '',
      };
      this._modelMetaDraft = {
        modelName: '',
        description: '',
        collectionMemberships: [],
        projectMemberships: [],
      };
    }
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

    // Avoid re-rendering while an inline editor is open so text input focus is stable.
    if (this._modelMetaEditOpen || this._ideaMetaEditOpen) {
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
    this.shadowRoot.addEventListener("keydown", this._boundKeydownHandler);
    this.shadowRoot.addEventListener("dragover", this._boundDragOverHandler);
    this.shadowRoot.addEventListener("dragleave", this._boundDragLeaveHandler);
    this.shadowRoot.addEventListener("drop", this._boundDropHandler);
  }

  disconnectedCallback() {
    this.shadowRoot.removeEventListener("click", this._boundClickHandler);
    this.shadowRoot.removeEventListener("change", this._boundChangeHandler);
    this.shadowRoot.removeEventListener("input", this._boundInputHandler);
    this.shadowRoot.removeEventListener("keydown", this._boundKeydownHandler);
    this.shadowRoot.removeEventListener("dragover", this._boundDragOverHandler);
    this.shadowRoot.removeEventListener("dragleave", this._boundDragLeaveHandler);
    this.shadowRoot.removeEventListener("drop", this._boundDropHandler);
    this._clearCollectionEditFeedbackTimer();
    this._clearProjectEditFeedbackTimer();
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
    
    if (target.closest('#btn-add-supporting-file')) {
      event.preventDefault();
      this._openSupportingFilePicker();
      return;
    }

    const supportThumbSizeBtn = target.closest('[data-action="support-set-thumb-size"]');
    if (supportThumbSizeBtn) {
      event.preventDefault();
      const size = String(supportThumbSizeBtn.dataset.size || '').toLowerCase();
      if (size === 'small' || size === 'medium' || size === 'large') {
        this._supportThumbSize = size;
        this._render();
      }
      return;
    }

    const supportViewBtn = target.closest('[data-action="support-set-view"]');
    if (supportViewBtn) {
      event.preventDefault();
      const view = String(supportViewBtn.dataset.view || 'files');
      if (view === 'files' || view === 'folders') {
        this._supportViewMode = view;
        this._supportTypeFilter = 'all';
        if (view === 'files') {
          this._supportFolderPath = '';
        }
        this._render();
      }
      return;
    }

    const supportTypeBtn = target.closest('[data-action="support-set-type-filter"]');
    if (supportTypeBtn) {
      event.preventDefault();
      const filter = String(supportTypeBtn.dataset.type || 'all').toLowerCase();
      if (filter === 'all' || filter === 'images' || filter === 'docs' || filter === 'other') {
        this._supportTypeFilter = filter;
        this._render();
      }
      return;
    }

    const supportFolderNavBtn = target.closest('[data-action="support-folder-enter"], [data-action="support-folder-nav"]');
    if (supportFolderNavBtn) {
      event.preventDefault();
      this._supportFolderPath = String(supportFolderNavBtn.dataset.path || '');
      this._render();
      return;
    }

    const supportFolderUpBtn = target.closest('[data-action="support-folder-up"]');
    if (supportFolderUpBtn) {
      event.preventDefault();
      const currentPath = String(this._supportFolderPath || '');
      if (!currentPath) {
        return;
      }
      const splitAt = currentPath.lastIndexOf('/');
      this._supportFolderPath = splitAt >= 0 ? currentPath.slice(0, splitAt) : '';
      this._render();
      return;
    }

    const supportPreviewBtn = target.closest('[data-action="support-preview-image"]');
    if (supportPreviewBtn) {
      event.preventDefault();
      const imageIdx = Number(supportPreviewBtn.dataset.imageIndex);
      if (Number.isFinite(imageIdx)) {
        this._openSupportingImagePreview(imageIdx);
      }
      return;
    }

    const supportOpenBtn = target.closest('[data-action="support-open-file"]');
    if (supportOpenBtn) {
      event.preventDefault();
      const fileId = String(supportOpenBtn.dataset.fileId || '');
      if (fileId) {
        this._openSupportingFileInNewTab(fileId);
      }
      return;
    }

    const supportDownloadBtn = target.closest('[data-action="support-download-file"]');
    if (supportDownloadBtn) {
      event.preventDefault();
      const fileId = String(supportDownloadBtn.dataset.fileId || '');
      if (fileId) {
        this._downloadSupportingFile(fileId);
      }
      return;
    }

    // Mark as interacting to prevent DOM re-renders during click handling
    this._isInteracting = true;

    // Use requestAnimationFrame to safely exit interaction mode after click completes
    requestAnimationFrame(() => {
      this._isInteracting = false;

      // If a render was scheduled during interaction, do it now
      if (this._renderScheduled) {
        console.log('[RAF] deferred render firing | _renderScheduled was true');
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

    const deleteModelBtn = target.closest('#btn-delete-model');
    if (deleteModelBtn) {
      event.preventDefault();
      this._handleDeleteModel();
      return;
    }

    if (!target.closest('.overflow-wrap') && this._overflowOpen) {
      this._overflowOpen = false;
      this._render();
      return;
    }

    if (target.closest('[data-action="model-edit-start"]')) {
      event.preventDefault();
      this._openModelMetadataEditor();
      return;
    }

    if (target.closest('[data-action="model-edit-cancel"]')) {
      event.preventDefault();
      this._cancelModelMetadataEditor();
      return;
    }

    if (target.closest('[data-action="model-edit-save"]')) {
      event.preventDefault();
      this._saveModelMetadataEdits();
      return;
    }

    if (target.closest('[data-action="undo-collection-change"]')) {
      event.preventDefault();
      this._undoLastCollectionMembershipChange();
      return;
    }

    if (target.closest('[data-action="undo-project-change"]')) {
      event.preventDefault();
      this._undoLastProjectMembershipChange();
      return;
    }

    if (target.closest('[data-action="dismiss-collection-feedback"]')) {
      event.preventDefault();
      this._dismissCollectionEditFeedback();
      return;
    }

    if (target.closest('[data-action="dismiss-project-feedback"]')) {
      event.preventDefault();
      this._dismissProjectEditFeedback();
      return;
    }

    if (target.closest('[data-action="refresh-collections"]')) {
      event.preventDefault();
      this._refreshCollectionEditorCollections({ showFeedback: true });
      return;
    }

    if (target.closest('[data-action="refresh-projects"]')) {
      event.preventDefault();
      this._refreshProjectEditorProjects({ showFeedback: true });
      return;
    }

    if (this._projectPickerOpen && !target.closest('.project-picker-wrap')) {
      this._projectPickerOpen = false;
      this._projectSearchQuery = '';
      this._projectPickerHighlightIndex = 0;
      this._render();
      return;
    }

    if (this._collectionPickerOpen && !target.closest('.collection-picker-wrap')) {
      this._collectionPickerOpen = false;
      this._collectionSearchQuery = '';
      this._collectionPickerHighlightIndex = 0;
      this._render();
      return;
    }

    // Close tag picker when clicking outside it
    if (this._tagPickerOpen && !target.closest('.picker-wrap')) {
      this._tagPickerOpen = false;
      this._tagSearchQuery = "";
      this._tagSearchSelectionStart = null;
      this._tagSearchSelectionEnd = null;
      this._tagPickerHighlightIndex = 0;
      this._render();
      return;
    }

    // Tag remove ✕ button
    const tagRemoveBtn = target.closest('[data-action="remove-tag"]');
    if (tagRemoveBtn) {
      event.preventDefault();
      const tagName = tagRemoveBtn.dataset.tag;
      if (tagName) this._handleTagRemove(tagName);
      return;
    }

    const collectionRemoveBtn = target.closest('[data-action="remove-collection"]');
    if (collectionRemoveBtn) {
      event.preventDefault();
      const collectionId = collectionRemoveBtn.dataset.collectionId;
      if (collectionId) {
        this._handleCollectionRemove(collectionId);
      }
      return;
    }

    const projectRemoveBtn = target.closest('[data-action="remove-project"]');
    if (projectRemoveBtn) {
      event.preventDefault();
      const projectId = projectRemoveBtn.dataset.projectId;
      if (projectId) {
        this._handleProjectRemove(projectId);
      }
      return;
    }

    const projectFocusBtn = target.closest('[data-action="focus-project"]');
    if (projectFocusBtn) {
      event.preventDefault();
      const projectId = projectFocusBtn.dataset.projectId;
      if (projectId) {
        this._focusProjectInBrowser(projectId);
      }
      return;
    }

    // Tag picker toggle
    if (target.closest('[data-action="toggle-tag-picker"]')) {
      event.preventDefault();
      this._tagPickerOpen = !this._tagPickerOpen;
      this._tagSearchQuery = "";
      this._tagSearchSelectionStart = null;
      this._tagSearchSelectionEnd = null;
      this._tagPickerHighlightIndex = 0;
      if (this._tagPickerOpen && !this._allTagsFetched) {
        this._loadAllTags().then(() => {
          this._render();
          if (this._tagPickerOpen) {
            this._focusTagSearchBox();
          }
        });
      }
      this._render();
      if (this._tagPickerOpen) {
        this._focusTagSearchBox();
      }
      return;
    }

    if (target.closest('[data-action="toggle-collection-picker"]')) {
      event.preventDefault();
      this._collectionPickerOpen = !this._collectionPickerOpen;
      this._projectPickerOpen = false;
      this._collectionSearchQuery = '';
      this._collectionPickerHighlightIndex = 0;
      this._render();
      return;
    }

    if (target.closest('[data-action="toggle-project-picker"]')) {
      event.preventDefault();
      this._projectPickerOpen = !this._projectPickerOpen;
      this._collectionPickerOpen = false;
      this._projectSearchQuery = '';
      this._projectPickerHighlightIndex = 0;
      this._render();
      return;
    }

    // Tag picker option click (add existing tag)
    const tagOpt = target.closest('[data-action="add-tag"]');
    if (tagOpt) {
      event.preventDefault();
      const tagName = tagOpt.dataset.tag;
      if (tagName) this._handleTagAdd(tagName, { keepPickerOpen: true });
      return;
    }

    const collectionOpt = target.closest('[data-action="add-collection"]');
    if (collectionOpt) {
      event.preventDefault();
      const collectionId = collectionOpt.dataset.collectionId;
      if (collectionId) this._handleCollectionAdd(collectionId);
      return;
    }

    const projectOpt = target.closest('[data-action="add-project"]');
    if (projectOpt) {
      event.preventDefault();
      const projectId = projectOpt.dataset.projectId;
      if (projectId) this._handleProjectAdd(projectId);
      return;
    }

    // Tag picker "Create new" click
    if (target.closest('[data-action="create-tag"]')) {
      event.preventDefault();
      const q = this._tagSearchQuery.trim();
      if (q) this._handleTagAdd(q, { keepPickerOpen: true });
      return;
    }

    if (target.closest('[data-action="create-collection"]')) {
      event.preventDefault();
      this._handleCollectionCreate();
      return;
    }

    if (target.closest('[data-action="create-project"]')) {
      event.preventDefault();
      this._handleProjectCreate();
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

    const promoteIdeaCatalogBtn = target.closest('[data-action="idea-promote-catalog"]');
    if (promoteIdeaCatalogBtn) {
      event.preventDefault();
      this._promoteIdeaEntity('model');
      return;
    }

    const moveIdeaWorkingBtn = target.closest('[data-action="idea-move-to-working-files"]');
    if (moveIdeaWorkingBtn) {
      event.preventDefault();
      this._moveIdeaToWorkingFiles();
      return;
    }

    const ideaEditBtn = target.closest('[data-action="idea-edit-start"]');
    if (ideaEditBtn) {
      event.preventDefault();
      this._openIdeaMetadataEditor();
      return;
    }

    const ideaEditCancelBtn = target.closest('[data-action="idea-edit-cancel"]');
    if (ideaEditCancelBtn) {
      event.preventDefault();
      this._cancelIdeaMetadataEditor();
      return;
    }

    const ideaEditSaveBtn = target.closest('[data-action="idea-edit-save"]');
    if (ideaEditSaveBtn) {
      event.preventDefault();
      this._saveIdeaMetadataEdits();
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
    if (collapseToggle && !target.closest('[data-action="toggle-archive-candidate-select"], [data-action="open-archive-preview"], [data-action="archive-candidate-link"], [data-action="archive-candidate-skip"]')) {
      event.preventDefault();
      const sectionId = String(collapseToggle.dataset.collapseToggle || '').trim();
      if (sectionId) {
        const isCollapsed = Object.prototype.hasOwnProperty.call(this._collapsedSections, sectionId)
          ? !!this._collapsedSections[sectionId]
          : true;
        this._collapsedSections[sectionId] = !isCollapsed;
        this._render();
      }
      return;
    }

    const refreshCandidatesBtn = target.closest('[data-action="refresh-model-candidates"]');
    if (refreshCandidatesBtn) {
      event.preventDefault();
      this._handleRefreshModelCandidates();
      return;
    }

    const archiveFilterBtn = target.closest('[data-action="set-archive-filter"]');
    if (archiveFilterBtn) {
      event.preventDefault();
      this._archiveLinkageFilter = String(archiveFilterBtn.dataset.archiveFilter || 'all').toLowerCase();
      this._render();
      return;
    }

    const archiveSortBtn = target.closest('[data-action="toggle-linked-sort"]');
    if (archiveSortBtn) {
      event.preventDefault();
      this._linkedArchiveSortOrder = this._linkedArchiveSortOrder === 'asc' ? 'desc' : 'asc';
      this._render();
      return;
    }

    const candidateSelectToggle = target.closest('[data-action="toggle-archive-candidate-select"]');
    if (candidateSelectToggle) {
      event.preventDefault();
      this._toggleArchiveCandidateSelection(
        candidateSelectToggle.dataset.archiveId,
        candidateSelectToggle.dataset.linkId
      );
      return;
    }

    const selectVisibleCandidatesBtn = target.closest('[data-action="select-visible-candidates"]');
    if (selectVisibleCandidatesBtn) {
      event.preventDefault();
      const visible = this._visibleCandidateEntries();
      for (let i = 0; i < visible.length; i += 1) {
        this._setArchiveCandidateSelection(visible[i].archive_id, visible[i].id, true);
      }
      this._render();
      return;
    }

    const clearCandidateSelectionBtn = target.closest('[data-action="clear-candidate-selection"]');
    if (clearCandidateSelectionBtn) {
      event.preventDefault();
      this._selectedArchiveCandidates = {};
      this._render();
      return;
    }

    const bulkArchiveLinkBtn = target.closest('[data-action="bulk-link-candidates"]');
    if (bulkArchiveLinkBtn) {
      event.preventDefault();
      this._handleBulkArchiveCandidateAction('link');
      return;
    }

    const bulkArchiveSkipBtn = target.closest('[data-action="bulk-skip-candidates"]');
    if (bulkArchiveSkipBtn) {
      event.preventDefault();
      this._handleBulkArchiveCandidateAction('skip');
      return;
    }

    const archiveCandidateLinkBtn = target.closest('[data-action="archive-candidate-link"]');
    if (archiveCandidateLinkBtn) {
      event.preventDefault();
      this._handleArchiveCandidateAction(
        archiveCandidateLinkBtn.dataset.archiveId,
        archiveCandidateLinkBtn.dataset.linkId,
        'link'
      );
      return;
    }

    const archiveCandidateSkipBtn = target.closest('[data-action="archive-candidate-skip"]');
    if (archiveCandidateSkipBtn) {
      event.preventDefault();
      this._handleArchiveCandidateAction(
        archiveCandidateSkipBtn.dataset.archiveId,
        archiveCandidateSkipBtn.dataset.linkId,
        'skip'
      );
      return;
    }

    const archiveOpenPopupBtn = target.closest('[data-action="open-archive-popup"]');
    if (archiveOpenPopupBtn) {
      event.preventDefault();
      const archiveId = String(archiveOpenPopupBtn.dataset.archiveId || '').trim();
      if (archiveId) {
        this._openArchivePopup(archiveId);
      }
      return;
    }

    const pinArchiveCoverBtn = target.closest('[data-action="pin-archive-cover"]');
    if (pinArchiveCoverBtn) {
      event.preventDefault();
      const archiveId = String(pinArchiveCoverBtn.dataset.archiveId || '').trim();
      const imageUrl = String(pinArchiveCoverBtn.dataset.imageUrl || '').trim();
      if (archiveId) {
        this._handlePinArchiveCover(archiveId, imageUrl);
      }
      return;
    }

    const unlinkArchiveBtn = target.closest('[data-action="unlink-archive"]');
    if (unlinkArchiveBtn) {
      event.preventDefault();
      const archiveId = String(unlinkArchiveBtn.dataset.archiveId || '').trim();
      const linkId = String(unlinkArchiveBtn.dataset.linkId || '').trim();
      if (archiveId && linkId) {
        this._handleUnlinkArchive(archiveId, linkId);
      }
      return;
    }

    const archivePreviewBtn = target.closest('[data-action="open-archive-preview"]');
    if (archivePreviewBtn) {
      event.preventDefault();
      const archiveId = String(archivePreviewBtn.dataset.archiveId || '').trim();
      if (archiveId) {
        this._openArchiveImagePreview(archiveId);
      }
      return;
    }

    // Archive toggle
    if (target.closest("#btn-toggle-frequent")) {
      event.preventDefault();
      this._handleToggleFrequent();
      return;
    }

    // Archive toggle
    if (target.closest("#btn-toggle-archive")) {
      event.preventDefault();
      this._handleToggleArchive();
      return;
    }

    // Un-archive link in banner
    if (target.closest("#btn-unarchive")) {
      event.preventDefault();
      this._handleToggleArchive();
      return;
    }

    // Download button
    if (target.closest("#btn-download")) {
      event.preventDefault();
      this._handleDownload();
      return;
    }

    // Create Archive button — opens slicer wizard (Slice 6.1b)
    if (target.closest("#btn-create-archive")) {
      event.preventDefault();
      this._handleCreateArchiveFromSource();
      return;
    }

    // Print button — opens unified queue dialog (#1499)
    if (target.closest("#btn-print")) {
      event.preventDefault();
      this._handlePrint();
      return;
    }

    // Queue tab shortcut — use the same add-to-queue dialog path as Print
    if (target.closest('[data-action="queue-add"]')) {
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

    // Source panel: Extract 3MF metadata
    const extract3mfBtn = target.closest('[data-action="extract-3mf-metadata"]');
    if (extract3mfBtn) {
      event.preventDefault();
      this._extract3mfMetadata();
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

  _openSupportingFilePicker() {
    const fileInput = this.shadowRoot.getElementById('supporting-file-input');
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
    if (target.id !== 'photo-file-input' && target.id !== 'hero-photo-file-input' && target.id !== 'supporting-file-input') {
      return;
    }

    const selectedFiles = Array.from(target.files || []);
    target.value = '';
    if (target.id === 'supporting-file-input') {
      this._handleSupportingFileSelect(selectedFiles);
      return;
    }
    this._handlePhotoFileSelect(selectedFiles);
  }

  _handleInput(event) {
    const target = event.target;
    if (target instanceof HTMLInputElement && target.dataset.input === 'project-search') {
      this._projectSearchQuery = String(target.value || '');
      this._projectSearchSelectionStart = Number.isFinite(target.selectionStart) ? target.selectionStart : this._projectSearchQuery.length;
      this._projectSearchSelectionEnd = Number.isFinite(target.selectionEnd) ? target.selectionEnd : this._projectSearchSelectionStart;
      this._projectPickerHighlightIndex = 0;
      const pickerDd = this.shadowRoot.querySelector('.project-picker-wrap .picker-dd');
      if (pickerDd) {
        const tmp = document.createElement('div');
        tmp.innerHTML = this._renderProjectPicker(this._selectedProjectMemberships());
        const nextDd = tmp.firstElementChild;
        if (nextDd) {
          pickerDd.replaceWith(nextDd);
          this._focusProjectSearchBox(nextDd);
        }
      }
      return;
    }
    if (target instanceof HTMLInputElement && target.dataset.input === 'collection-search') {
      this._collectionSearchQuery = String(target.value || '');
      this._collectionSearchSelectionStart = Number.isFinite(target.selectionStart) ? target.selectionStart : this._collectionSearchQuery.length;
      this._collectionSearchSelectionEnd = Number.isFinite(target.selectionEnd) ? target.selectionEnd : this._collectionSearchSelectionStart;
      this._collectionPickerHighlightIndex = 0;
      const pickerDd = this.shadowRoot.querySelector('.collection-picker-wrap .picker-dd');
      if (pickerDd) {
        const tmp = document.createElement('div');
        tmp.innerHTML = this._renderCollectionPicker(this._selectedCollectionMemberships());
        const nextDd = tmp.firstElementChild;
        if (nextDd) {
          pickerDd.replaceWith(nextDd);
          this._focusCollectionSearchBox(nextDd);
        }
      }
      return;
    }
    if (target instanceof HTMLTextAreaElement && target.getAttribute("data-queue-dialog-notes")) {
      this._queueDialogNotes = String(target.value || "");
    }
    // Source panel: custom label live update (save on blur via change)
    if (target instanceof HTMLInputElement && target.classList.contains("source-label-input")) {
      // Debounce save — we'll save on change/blur handled above
    }
    // Tag picker search
    if (target instanceof HTMLInputElement && target.dataset.input === 'tag-search') {
      this._tagSearchQuery = String(target.value || "");
      this._tagSearchSelectionStart = Number.isFinite(target.selectionStart) ? target.selectionStart : this._tagSearchQuery.length;
      this._tagSearchSelectionEnd = Number.isFinite(target.selectionEnd) ? target.selectionEnd : this._tagSearchSelectionStart;
      this._tagPickerHighlightIndex = 0;
      // Re-render only the picker dropdown to avoid full re-render losing focus
      const pickerDd = this.shadowRoot.querySelector('.picker-dd');
      if (pickerDd) {
        const model = (this._modelDetail && this._modelDetail.model) || {};
        const tags = Array.isArray(model.keywords) ? model.keywords : [];
        const tmp = document.createElement('div');
        tmp.innerHTML = this._renderTagPicker(tags);
        const newDd = tmp.firstElementChild;
        pickerDd.replaceWith(newDd);
        const searchBox = newDd.querySelector('.search-box');
        if (searchBox) {
          searchBox.focus();
          const nextStart = Number.isFinite(this._tagSearchSelectionStart)
            ? Math.max(0, Math.min(this._tagSearchSelectionStart, searchBox.value.length))
            : searchBox.value.length;
          const nextEnd = Number.isFinite(this._tagSearchSelectionEnd)
            ? Math.max(nextStart, Math.min(this._tagSearchSelectionEnd, searchBox.value.length))
            : nextStart;
          searchBox.setSelectionRange(nextStart, nextEnd);
        }
      }
    }
  }

  _focusTagSearchBox() {
    requestAnimationFrame(() => {
      const searchBox = this.shadowRoot && this.shadowRoot.querySelector
        ? this.shadowRoot.querySelector('.picker-dd .search-box')
        : null;
      if (searchBox) {
        searchBox.focus();
        const nextStart = Number.isFinite(this._tagSearchSelectionStart)
          ? Math.max(0, Math.min(this._tagSearchSelectionStart, searchBox.value.length))
          : searchBox.value.length;
        const nextEnd = Number.isFinite(this._tagSearchSelectionEnd)
          ? Math.max(nextStart, Math.min(this._tagSearchSelectionEnd, searchBox.value.length))
          : nextStart;
        searchBox.setSelectionRange(nextStart, nextEnd);
      }
    });
  }

  _focusCollectionSearchBox(scopeRoot) {
    requestAnimationFrame(() => {
      const root = scopeRoot && typeof scopeRoot.querySelector === 'function'
        ? scopeRoot
        : this.shadowRoot;
      const searchBox = root && typeof root.querySelector === 'function'
        ? root.querySelector('.search-box')
        : null;
      if (!(searchBox instanceof HTMLInputElement)) {
        return;
      }
      searchBox.focus();
      if (typeof searchBox.setSelectionRange !== 'function') {
        return;
      }
      const nextStart = Number.isFinite(this._collectionSearchSelectionStart)
        ? Math.max(0, Math.min(this._collectionSearchSelectionStart, searchBox.value.length))
        : searchBox.value.length;
      const nextEnd = Number.isFinite(this._collectionSearchSelectionEnd)
        ? Math.max(nextStart, Math.min(this._collectionSearchSelectionEnd, searchBox.value.length))
        : nextStart;
      searchBox.setSelectionRange(nextStart, nextEnd);
    });
  }

  _focusProjectSearchBox(scopeRoot) {
    requestAnimationFrame(() => {
      const root = scopeRoot && typeof scopeRoot.querySelector === 'function'
        ? scopeRoot
        : this.shadowRoot;
      const searchBox = root && typeof root.querySelector === 'function'
        ? root.querySelector('.search-box')
        : null;
      if (!(searchBox instanceof HTMLInputElement)) {
        return;
      }
      searchBox.focus();
      if (typeof searchBox.setSelectionRange !== 'function') {
        return;
      }
      const nextStart = Number.isFinite(this._projectSearchSelectionStart)
        ? Math.max(0, Math.min(this._projectSearchSelectionStart, searchBox.value.length))
        : searchBox.value.length;
      const nextEnd = Number.isFinite(this._projectSearchSelectionEnd)
        ? Math.max(nextStart, Math.min(this._projectSearchSelectionEnd, searchBox.value.length))
        : nextStart;
      searchBox.setSelectionRange(nextStart, nextEnd);
    });
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
    uploadArea.style.background = isActive ? 'color-mix(in srgb, var(--primary-color, #6edacb) 12%, transparent)' : 'transparent';
    uploadArea.style.borderColor = isActive ? 'var(--primary-color, #6edacb)' : 'var(--border)';
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

      // Seed known tags for the picker from this model's keywords
      const kw = (this._modelDetail.model && this._modelDetail.model.keywords) || [];
      for (const t of kw) {
        if (!this._knownTags.includes(t)) this._knownTags.push(t);
      }

      const modelFiles = Array.isArray(this._modelDetail?.model?.files) ? this._modelDetail.model.files : [];
      this._ensureModelFilePlateCounts(modelFiles);
      this._pruneArchiveCandidateSelection(Array.isArray(this._modelDetail.candidate_archives) ? this._modelDetail.candidate_archives : []);
      
      await this._cleanupStaleSourcePreview();
    } catch (error) {
      this._error = String(error || "Unknown error");
      this._modelDetail = null;
    } finally {
      this._loading = false;
      this._render();
    }
  }

  async _cleanupStaleSourcePreview() {
    if (!this._modelDetail) return;
    
    const photos = Array.isArray(this._modelDetail.photos) ? this._modelDetail.photos : [];
    const files = Array.isArray(this._modelDetail.model?.files) ? this._modelDetail.model.files : [];
    
    const hasPinnedPhoto = photos.some(p => Boolean(p && p.is_preview));
    const hasPinnedAsset = files.some(f => Boolean(f && (f.is_preview || f.asset_role === 'preview')));
    const hasNonSourcePreview = Boolean(hasPinnedPhoto || hasPinnedAsset);
    
    if (!hasNonSourcePreview) {
      return;
    }
    
    const sourcePreviewUrl = this._sourcePreviewUrl();
    if (sourcePreviewUrl) {
      console.log('[CLEANUP] Found stale source_image_preview_url with non-source preview present. Clearing it.');
      await this._saveSourceField(this._heroSourcePreviewFieldKey, null);
    }
  }

  _capturePopupShellScroll() {
    const anchors = [];
    const addShadowAnchor = (element) => {
      if (!element || !(element instanceof HTMLElement)) {
        return;
      }
      if (!(element.scrollHeight > element.clientHeight || element.scrollWidth > element.clientWidth)) {
        return;
      }
      const top = Number(element.scrollTop || 0);
      const left = Number(element.scrollLeft || 0);
      if (top <= 0 && left <= 0) {
        return;
      }
      const path = this._elementPathFromShadowRoot(element);
      if (!path) {
        return;
      }
      anchors.push({
        kind: 'shadow-path',
        path,
        top,
        left,
      });
    };

    const shadowRoot = this.shadowRoot;
    if (shadowRoot) {
      addShadowAnchor(shadowRoot.querySelector('.popup-shell'));
      const scrollables = shadowRoot.querySelectorAll('*');
      for (let i = 0; i < scrollables.length; i += 1) {
        addShadowAnchor(scrollables[i]);
      }
    }

    const addAnchor = (element) => {
      if (!element || anchors.some(anchor => anchor.element === element)) {
        return;
      }
      anchors.push({
        kind: 'live-element',
        element,
        top: Number(element.scrollTop || 0),
        left: Number(element.scrollLeft || 0),
      });
    };

    const popupShell = this.shadowRoot && this.shadowRoot.querySelector
      ? this.shadowRoot.querySelector('.popup-shell')
      : null;
    if (popupShell) {
      addAnchor(popupShell);
    }

    let current = this;
    while (current && current.parentElement) {
      current = current.parentElement;
      if (!current) {
        break;
      }
      if (current.scrollHeight > current.clientHeight && current.clientHeight > 0) {
        const style = window.getComputedStyle(current);
        const overflowY = String(style.overflowY || '').toLowerCase();
        if (overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay') {
          addAnchor(current);
        }
      }
    }

    const doc = document.scrollingElement || document.documentElement;
    if (doc) {
      anchors.push({
        kind: 'window',
        element: doc,
        top: Number(window.scrollY || doc.scrollTop || 0),
        left: Number(window.scrollX || doc.scrollLeft || 0),
      });
    }

    return anchors.length ? anchors : null;
  }

  _queuePopupShellScrollRestore() {
    this._pendingPopupShellScroll = this._capturePopupShellScroll();
  }

  _elementPathFromShadowRoot(element) {
    if (!this.shadowRoot || !element) {
      return null;
    }
    const path = [];
    let current = element;
    while (current && current !== this.shadowRoot) {
      const parent = current.parentElement;
      if (!parent) {
        return null;
      }
      const siblings = Array.from(parent.children);
      const index = siblings.indexOf(current);
      if (index < 0) {
        return null;
      }
      path.unshift(index);
      current = parent;
    }
    return path;
  }

  _elementFromShadowRootPath(path) {
    if (!this.shadowRoot || !Array.isArray(path)) {
      return null;
    }
    let current = this.shadowRoot;
    for (let i = 0; i < path.length; i += 1) {
      const index = Number(path[i]);
      if (!Number.isInteger(index) || index < 0 || !current.children || index >= current.children.length) {
        return null;
      }
      current = current.children[index];
    }
    return current instanceof HTMLElement ? current : null;
  }

  _restorePopupShellScroll() {
    const pending = this._pendingPopupShellScroll;
    if (!Array.isArray(pending) || !pending.length) {
      this._pendingPopupShellScroll = null;
      return;
    }
    const hasNonWindowAnchors = pending.some(anchor => anchor && anchor.kind !== 'window');

    const apply = () => {
      let restoredWindow = false;
      let restoredNonWindow = false;
      pending.forEach(anchor => {
        if (!anchor) {
          return;
        }
        if (anchor.kind === 'window') {
          window.scrollTo(Number(anchor.left || 0), Number(anchor.top || 0));
          restoredWindow = true;
          return;
        }
        const target = anchor.kind === 'shadow-path'
          ? this._elementFromShadowRootPath(anchor.path)
          : anchor.element;
        if (!target) {
          return;
        }
        if (anchor.kind === 'live-element' && !document.contains(target)) {
          return;
        }
        target.scrollTop = Number(anchor.top || 0);
        target.scrollLeft = Number(anchor.left || 0);
        restoredNonWindow = true;
      });
      return { restoredWindow, restoredNonWindow };
    };

    const firstPass = apply();
    requestAnimationFrame(() => {
      const secondPass = apply();
      const restoredWindow = !!(firstPass && firstPass.restoredWindow) || !!(secondPass && secondPass.restoredWindow);
      const restoredNonWindow = !!(firstPass && firstPass.restoredNonWindow) || !!(secondPass && secondPass.restoredNonWindow);
      const shouldClear = hasNonWindowAnchors ? restoredNonWindow : restoredWindow;
      if (shouldClear) {
        this._pendingPopupShellScroll = null;
      }
    });
  }

  _render() {
    const inlineEditorFocusState = this._captureInlineEditorState();
    const renderPath = this._loading ? 'loading' : this._error ? 'error' : this._modelDetail ? 'popup' : 'empty';
    console.log('[RENDER]', renderPath, '| _loading:', this._loading, '| keywords:', JSON.stringify(this._modelDetail?.model?.keywords));
    const html = this._loading
      ? this._renderLoading()
      : this._error
      ? this._renderError()
      : this._modelDetail
      ? this._renderPopup()
      : this._renderEmpty();
    
    this.shadowRoot.innerHTML = html;

    this._restorePopupShellScroll();

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

    this._restoreInlineEditorState(inlineEditorFocusState);

  }

  _captureInlineEditorState() {
    if (!this.shadowRoot || !this._modelMetaEditOpen) {
      return null;
    }
    const nameInput = this.shadowRoot.querySelector('#model-meta-name');
    const descriptionInput = this.shadowRoot.querySelector('#model-meta-description');
    if (nameInput instanceof HTMLInputElement) {
      this._modelMetaDraft.modelName = String(nameInput.value || '');
    }
    if (descriptionInput instanceof HTMLTextAreaElement) {
      this._modelMetaDraft.description = String(descriptionInput.value || '');
    }
    const activeElement = this.shadowRoot.activeElement instanceof Element ? this.shadowRoot.activeElement : null;
    if (!activeElement) {
      return null;
    }
    if (activeElement.id !== 'model-meta-name' && activeElement.id !== 'model-meta-description') {
      return null;
    }
    return {
      id: activeElement.id,
      selectionStart: Number.isFinite(activeElement.selectionStart) ? activeElement.selectionStart : null,
      selectionEnd: Number.isFinite(activeElement.selectionEnd) ? activeElement.selectionEnd : null,
    };
  }

  _restoreInlineEditorState(focusState) {
    if (!this.shadowRoot || !focusState || !focusState.id) {
      return;
    }
    requestAnimationFrame(() => {
      const field = this.shadowRoot && this.shadowRoot.querySelector
        ? this.shadowRoot.querySelector(`#${focusState.id}`)
        : null;
      if (!(field instanceof HTMLInputElement) && !(field instanceof HTMLTextAreaElement)) {
        return;
      }
      field.focus();
      if (typeof field.setSelectionRange !== 'function') {
        return;
      }
      const nextStart = Number.isFinite(focusState.selectionStart)
        ? Math.max(0, Math.min(focusState.selectionStart, field.value.length))
        : field.value.length;
      const nextEnd = Number.isFinite(focusState.selectionEnd)
        ? Math.max(nextStart, Math.min(focusState.selectionEnd, field.value.length))
        : nextStart;
      field.setSelectionRange(nextStart, nextEnd);
    });
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

  _normalizeComparableUrl(url) {
    return this._normalizeModelApiUrl(String(url || '').trim());
  }

  _sourceUrlMediaId(url) {
    const normalized = this._normalizeComparableUrl(url);
    if (!normalized) {
      return '';
    }
    return `source_url:${encodeURIComponent(normalized)}`;
  }

  _isLikelyImageUrl(url) {
    const value = String(url || '').trim();
    if (!/^https?:\/\//i.test(value)) {
      return false;
    }
    try {
      const parsed = new URL(value);
      const path = String(parsed.pathname || '').toLowerCase();
      if (/(\.avif|\.bmp|\.gif|\.ico|\.jpe?g|\.png|\.svg|\.tiff?|\.webp)$/i.test(path)) {
        return true;
      }
      const queryValue = String(parsed.search || '').toLowerCase();
      return /(format|fm|ext)=(avif|bmp|gif|ico|jpe?g|png|svg|tiff?|webp)\b/.test(queryValue);
    } catch (_error) {
      return /(\.avif|\.bmp|\.gif|\.ico|\.jpe?g|\.png|\.svg|\.tiff?|\.webp)(\?|#|$)/i.test(value);
    }
  }

  _readCustomField(fieldKey) {
    const key = String(fieldKey || '').trim();
    if (!key) {
      return null;
    }
    const detailEnrichment = this._modelDetail && this._modelDetail.enrichment && typeof this._modelDetail.enrichment === 'object'
      ? this._modelDetail.enrichment
      : {};
    const enrichmentFields = detailEnrichment.custom_fields && typeof detailEnrichment.custom_fields === 'object'
      ? detailEnrichment.custom_fields
      : {};
    if (Object.prototype.hasOwnProperty.call(enrichmentFields, key)) {
      return enrichmentFields[key];
    }
    const model = this._modelDetail && this._modelDetail.model && typeof this._modelDetail.model === 'object'
      ? this._modelDetail.model
      : {};
    const modelFields = model.custom_fields && typeof model.custom_fields === 'object'
      ? model.custom_fields
      : {};
    if (Object.prototype.hasOwnProperty.call(modelFields, key)) {
      return modelFields[key];
    }
    return null;
  }

  _setCustomFieldLocally(fieldKey, value) {
    const key = String(fieldKey || '').trim();
    if (!key || !this._modelDetail) {
      return;
    }
    if (!this._modelDetail.enrichment || typeof this._modelDetail.enrichment !== 'object') {
      this._modelDetail.enrichment = {};
    }
    if (!this._modelDetail.enrichment.custom_fields || typeof this._modelDetail.enrichment.custom_fields !== 'object') {
      this._modelDetail.enrichment.custom_fields = {};
    }
    if (!this._modelDetail.model || typeof this._modelDetail.model !== 'object') {
      this._modelDetail.model = {};
    }
    if (!this._modelDetail.model.custom_fields || typeof this._modelDetail.model.custom_fields !== 'object') {
      this._modelDetail.model.custom_fields = {};
    }
    if (value == null || value === '') {
      delete this._modelDetail.enrichment.custom_fields[key];
      delete this._modelDetail.model.custom_fields[key];
      return;
    }
    this._modelDetail.enrichment.custom_fields[key] = value;
    this._modelDetail.model.custom_fields[key] = value;
  }

  _sourcePreviewUrl() {
    const rawValue = this._readCustomField(this._heroSourcePreviewFieldKey);
    return this._normalizeComparableUrl(rawValue);
  }

  _resetModelFilePlateCounts() {
    this._modelFilePlateCounts = {};
    this._modelFilePlateCountPending = new Set();
    this._modelFilePlateCountRequestToken += 1;
    this._modelFilePlateDetails = {};
    this._modelFilePlateDetailsPending = new Set();
    this._modelFilePlateDetailsRequestToken += 1;
  }

  _extractModelFileId(file) {
    return String(file && (file.id || file.file_id || file.asset_id || '') || '').trim();
  }

  _is3mfModelFile(file) {
    const rawName = String(file && (file.filename || file.asset_filename || file.name || file.id || '') || '');
    const extIdx = rawName.lastIndexOf('.');
    const ext = extIdx >= 0 ? rawName.slice(extIdx + 1).toLowerCase() : '';
    if (ext === '3mf') {
      return true;
    }
    const typeHint = String(file && (file.asset_type || file.file_type || file.content_type || '') || '').toLowerCase();
    return typeHint.includes('3mf');
  }

  _isQueueDialogEligibleFile(file) {
    if (!file || typeof file !== 'object') {
      return false;
    }
    const role = String(file.asset_role || '').trim().toLowerCase();
    if (role === 'preview') {
      return false;
    }
    const rawName = String(file.filename || file.asset_filename || file.name || file.id || '').trim().toLowerCase();
    const extIdx = rawName.lastIndexOf('.');
    const ext = extIdx >= 0 ? rawName.slice(extIdx + 1) : '';
    const typeHint = String(file.asset_type || file.file_type || file.content_type || '').trim().toLowerCase();
    const modelTypes = new Set(['3mf', 'stl', 'obj', 'step', 'stp', 'gcode', 'zip']);
    return modelTypes.has(ext) || modelTypes.has(typeHint);
  }

  _getModelFilePlateCount(file) {
    const inlineCount = Number(file && file.plate_count);
    if (Number.isFinite(inlineCount) && inlineCount >= 0) {
      return inlineCount;
    }
    const inlinePlates = Array.isArray(file && file.plates) ? file.plates.length : null;
    if (inlinePlates != null) {
      return inlinePlates;
    }
    const fileId = this._extractModelFileId(file);
    if (!fileId) {
      return null;
    }
    const cached = this._modelFilePlateCounts[fileId];
    return Number.isFinite(cached) ? cached : null;
  }

  async _ensureModelFilePlateCounts(files) {
    const rows = Array.isArray(files) ? files : [];
    if (!rows.length || !this._modelRef || !this._modelSidecarUrl) {
      return;
    }

    const requestToken = this._modelFilePlateCountRequestToken;
    const sidecarUrl = String(this._modelSidecarUrl || '').trim().replace(/\/$/, '');
    if (!sidecarUrl) {
      return;
    }

    const fetches = [];
    for (const file of rows) {
      if (!this._is3mfModelFile(file)) {
        continue;
      }
      const fileId = this._extractModelFileId(file);
      if (!fileId) {
        continue;
      }
      if (Number.isFinite(this._modelFilePlateCounts[fileId]) || this._modelFilePlateCountPending.has(fileId)) {
        continue;
      }
      this._modelFilePlateCountPending.add(fileId);
      const url = `${sidecarUrl}/api/models/${encodeURIComponent(this._modelRef)}/files/${encodeURIComponent(fileId)}/plates`;
      fetches.push(
        fetch(url)
          .then(res => (res.ok ? res.json() : null))
          .then(payload => {
            if (requestToken !== this._modelFilePlateCountRequestToken) {
              return false;
            }
            const count = Array.isArray(payload && payload.plates) ? payload.plates.length : 0;
            const previous = this._modelFilePlateCounts[fileId];
            this._modelFilePlateCounts[fileId] = count;
            return previous !== count;
          })
          .catch(() => false)
          .finally(() => {
            this._modelFilePlateCountPending.delete(fileId);
          })
      );
    }

    if (!fetches.length) {
      return;
    }

    const results = await Promise.all(fetches);
    if (requestToken !== this._modelFilePlateCountRequestToken) {
      return;
    }
    if (results.some(Boolean)) {
      this._render();
    }
  }

  _getModelFilePlateDetails(file) {
    const inlinePlates = Array.isArray(file && file.plates) ? file.plates : null;
    if (inlinePlates) {
      return inlinePlates;
    }
    const fileId = String(file && (file.id || file.file_id) || '').trim();
    if (!fileId) {
      return null;
    }
    const cached = this._modelFilePlateDetails[fileId];
    return Array.isArray(cached) ? cached : null;
  }

  async _ensureModelFilePlateDetails(files) {
    const rows = Array.isArray(files) ? files : [];
    if (!rows.length || !this._modelRef || !this._modelSidecarUrl) {
      return;
    }
    const sidecarUrl = String(this._modelSidecarUrl || '').trim().replace(/\/$/, '');
    if (!sidecarUrl) {
      return;
    }
    const requestToken = this._modelFilePlateDetailsRequestToken;
    rows.forEach((file) => {
      if (!this._is3mfModelFile(file)) {
        return;
      }
      const fileId = String(file && (file.id || file.file_id) || '').trim();
      if (!fileId) {
        return;
      }
      if (Array.isArray(this._modelFilePlateDetails[fileId]) || this._modelFilePlateDetailsPending.has(fileId)) {
        return;
      }
      this._modelFilePlateDetailsPending.add(fileId);
      const url = `${sidecarUrl}/api/models/${encodeURIComponent(this._modelRef)}/files/${encodeURIComponent(fileId)}/plates`;
      fetch(url)
        .then((response) => response.ok ? response.json() : null)
        .then((payload) => {
          if (requestToken !== this._modelFilePlateDetailsRequestToken) {
            return;
          }
          const plates = Array.isArray(payload && payload.plates) ? payload.plates : [];
          this._modelFilePlateDetails[fileId] = plates;
          const previous = this._modelFilePlateCounts[fileId];
          if (!Number.isFinite(previous) || previous !== plates.length) {
            this._modelFilePlateCounts[fileId] = plates.length;
          }
          this._render();
        })
        .catch(() => {
          if (requestToken !== this._modelFilePlateDetailsRequestToken) {
            return;
          }
          this._modelFilePlateDetails[fileId] = [];
        })
        .finally(() => {
          this._modelFilePlateDetailsPending.delete(fileId);
        });
    });
  }

  _headerThumbnailUrl(model) {
    const sources = this._headerThumbnailSources(model);
    return sources.length ? sources[0] : '';
  }

  _headerThumbnailSources(model) {
    const normalizedSources = [];
    const seen = new Set();
    const addSource = (rawUrl) => {
      const candidate = this._normalizeModelApiUrl(String(rawUrl || '').trim());
      if (!candidate || seen.has(candidate)) {
        return;
      }
      seen.add(candidate);
      normalizedSources.push(candidate);
    };

    const photos = Array.isArray(this._modelDetail && this._modelDetail.photos) ? this._modelDetail.photos : [];
    const files = Array.isArray(model && model.files) ? model.files : [];
    const sourcePreviewUrl = this._sourcePreviewUrl();
    const pinnedPhoto = photos.find(photo => photo && photo.is_preview);
    if (pinnedPhoto) {
      console.log('[PIN-DEBUG] Found pinned photo:', pinnedPhoto.id, 'URL:', pinnedPhoto.image_url);
      addSource(pinnedPhoto.image_url || pinnedPhoto.thumbnail_url || pinnedPhoto.preview_url || pinnedPhoto.url);
    } else {
      console.log('[PIN-DEBUG] No pinned photo found. Total photos:', photos.length, 'preview_photo_id:', this._modelDetail?.preview_photo_id);
    }

    const pinnedAsset = files.find(file => file && (file.is_preview || file.asset_role === 'preview'));
    if (pinnedAsset) {
      addSource(pinnedAsset.image_url || pinnedAsset.thumbnail_lazy_url || pinnedAsset.thumbnail_url || pinnedAsset.preview_url || pinnedAsset.download_url);
    }

    const hasNonSourcePreview = Boolean(pinnedPhoto || pinnedAsset);
    if (sourcePreviewUrl && !hasNonSourcePreview) {
      addSource(sourcePreviewUrl);
    }

    const linkedArchives = Array.isArray(this._modelDetail && this._modelDetail.linked_archives)
      ? this._modelDetail.linked_archives
      : [];
    const bambuddyUrl = this._resolveBambuddyUrl();
    if (linkedArchives.length) {
      const firstLinked = linkedArchives[0] || {};
      const archiveId = String(firstLinked.archive_id || '').trim();
      const meta = archiveId ? this._archiveMetaCache[archiveId] : null;
      const archiveData = meta && meta.archive ? meta.archive : meta;
      const primaryPhotoPath = archiveData && archiveData.primary_photo_path ? String(archiveData.primary_photo_path).trim() : '';
      if (primaryPhotoPath && bambuddyUrl && archiveId) {
        addSource(`${bambuddyUrl}/api/v1/archives/${encodeURIComponent(archiveId)}/photos/${encodeURIComponent(primaryPhotoPath)}`);
      }
      addSource(firstLinked.preview_image_url || firstLinked.thumbnail_url);
      if (bambuddyUrl && archiveId) {
        addSource(`${bambuddyUrl}/api/v1/archives/${encodeURIComponent(archiveId)}/thumbnail`);
      }
    }

    addSource(model && model.preview_url ? model.preview_url : '');

    for (const file of files) {
      if (!file || typeof file !== 'object') {
        continue;
      }
      addSource(file.thumbnail_lazy_url || file.thumbnail_url || file.preview_url || '');
    }

    console.log('[PIN-DEBUG] Final header thumbnail sources:', normalizedSources);
    return normalizedSources;
  }

  _renderLoading() {
    return `
      <style>
        .popup { padding: 24px; text-align: center; }
        .spinner { 
          display: inline-block; 
          width: 32px; 
          height: 32px; 
          border: 3px solid color-mix(in srgb, var(--border) 50%, transparent);
          border-top-color: var(--primary-color, #6edacb); 
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
          background: color-mix(in srgb, var(--accent-red, #ef5350) 12%, transparent);
          border: 1px solid color-mix(in srgb, var(--accent-red, #ef5350) 32%, transparent); 
          border-radius: 4px; 
          padding: 16px; 
          color: #fecaca; 
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
    const _catalogSignals = (model.structured_metadata && model.structured_metadata.catalog_signals) || {};
    const isArchived = String(_catalogSignals.catalog_visibility || '').toLowerCase() === 'archived';
    const frequentState = this._resolveFrequentState(model);
    const isFrequent = frequentState.isFrequent;
    const frequentButtonClass = frequentState.source === 'manual_override' ? 'toggle-active-manual' : 'toggle-active';
    const frequentButtonTitle = frequentState.source === 'manual_override'
      ? (frequentState.isFrequent
        ? 'Manually marked as frequent. Click to clear manual override and return to inferred status.'
        : 'Manually marked as not frequent. Click to mark as frequent manually.')
      : (frequentState.isFrequentInferred
        ? ('Auto-inferred as frequent from print activity (' + String(Math.round(frequentState.weightedPrintCount * 100) / 100) + ' weighted prints, threshold ' + String(frequentState.minPrints) + '). Click to pin this as manually frequent.')
        : ('Not currently frequent by inference (' + String(Math.round(frequentState.weightedPrintCount * 100) / 100) + ' weighted prints, threshold ' + String(frequentState.minPrints) + '). Click to mark as frequent manually.'));
    const frequentButtonLabel = frequentState.source === 'manual_override'
      ? (frequentState.isFrequent ? '⚡ Frequent (Manual)' : '⚡ Not Frequent (Manual)')
      : (frequentState.isFrequentInferred ? '⚡ Frequent (Inferred)' : '⚡ Mark as Frequent');

    return `
      <style>
        :host {
          /* HA Theme Integration: Custom variables for design system */
          --bg-page: var(--primary-background-color);
          --bg-panel: var(--ha-card-background, var(--card-background-color));
          --bg-card: var(--ha-card-background, var(--card-background-color));
          --bg-card-alt: color-mix(in srgb, var(--ha-card-background, var(--card-background-color)) 92%, var(--primary-text-color) 8%);
          --border: var(--divider-color);
          --border-strong: color-mix(in srgb, var(--divider-color) 60%, var(--primary-text-color) 40%);
          --text: var(--primary-text-color);
          --text-secondary: var(--secondary-text-color);
          --text-muted: color-mix(in srgb, var(--secondary-text-color) 70%, transparent);
          --accent: var(--primary-color, #6edacb);
          --accent-teal: #5eead4;
          --accent-blue: #3aa9ff;
          --accent-amber: #ff9a3c;
          --accent-green: #4fcf75;
          --accent-red: #ff6b6b;
          --shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0, 0, 0, 0.12));
          --shadow-lg: 0 8px 24px color-mix(in srgb, rgba(0, 0, 0, 0.2), transparent);
        }

        * { box-sizing: border-box; }
        .popup-shell {
          display: grid;
          gap: 4px;
          margin-top: -12px;
          color: var(--text);
          font-family: var(--mdc-typography-font-family, 'Roboto', sans-serif);
          background: var(--bg-card);
          overflow-y: auto;
          max-height: calc(100vh - 120px);
        }
        .topbar {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 8px;
          flex-wrap: wrap;
          border-bottom: 1px solid var(--border);
          padding: 0 10px 4px;
        }
        .popup-shell.is-idea .topbar {
          border-bottom-color: color-mix(in srgb, #ffc107 38%, transparent);
          box-shadow: inset 0 -1px 0 color-mix(in srgb, #ffc107 16%, transparent);
        }
        .title { display: flex; align-items: center; }
        .title span { color: var(--text-secondary); font-size: 11px; line-height: 1.2; }
        .entity-type-badge {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          border: 1px solid var(--border);
          border-radius: 999px;
          padding: 4px 10px;
          font-size: 11px;
          font-weight: 600;
          background: var(--bg-card);
          color: var(--text-secondary);
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
          background: var(--bg-card-alt);
          color: var(--text);
        }
        .action-button.toggle-active {
          border: 1px solid var(--accent);
          background: color-mix(in srgb, var(--accent) 12%, transparent);
          color: var(--accent);
        }
        .action-button.toggle-active-manual {
          border: 1px solid color-mix(in srgb, var(--accent-amber) 48%, transparent);
          background: color-mix(in srgb, var(--accent-amber) 16%, transparent);
          color: #fde68a;
        }
        .action-button.toggle-active-warn {
          border: 1px solid color-mix(in srgb, var(--border) 44%, transparent);
          background: color-mix(in srgb, var(--border) 14%, transparent);
          color: var(--text-secondary);
        }
        .archived-banner {
          padding: 8px 18px;
          background: color-mix(in srgb, var(--border) 8%, transparent);
          border-bottom: 1px solid color-mix(in srgb, var(--border) 28%, transparent);
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 12px;
          color: var(--text-muted);
        }
        .archived-banner button {
          background: none;
          border: none;
          color: var(--accent);
          cursor: pointer;
          font-size: 12px;
          text-decoration: underline;
          padding: 0;
        }
        .queue-dialog-backdrop{position:fixed;inset:0;z-index:30;display:flex;align-items:center;justify-content:center;padding:20px;background:color-mix(in srgb, rgba(0,0,0,0.8) 72%, transparent);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);}
        .queue-dialog{width:min(680px,calc(100vw - 32px));max-height:calc(100vh - 40px);display:grid;grid-template-rows:auto auto minmax(0,1fr) auto;overflow:hidden;border-radius:20px;border:1px solid var(--border-strong);background:var(--bg-panel);box-shadow:var(--shadow-lg);}
        .queue-dialog-header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:18px 20px 14px;border-bottom:1px solid color-mix(in srgb, var(--border) 18%, transparent);}
        .queue-dialog-header h3{margin:0;font-size:18px;font-weight:800;color:var(--text);}
        .queue-dialog-subtitle{margin-top:4px;font-size:12px;color:var(--text-secondary);}
        .queue-dialog-tabs{display:flex;gap:8px;padding:12px 20px;border-bottom:1px solid color-mix(in srgb, var(--border) 16%, transparent);}
        .queue-dialog-tab{min-height:34px;padding:0 14px;border-radius:999px;border:1px solid color-mix(in srgb, var(--border) 22%, transparent);background:color-mix(in srgb, var(--text) 6%, transparent);color:var(--text-secondary);font-size:12px;font-weight:800;cursor:pointer;}
        .queue-dialog-tab.active{background:color-mix(in srgb, var(--accent-blue) 18%, transparent);border-color:color-mix(in srgb, var(--accent-blue) 34%, transparent);color:var(--text);}
        .queue-dialog-body{display:grid;gap:12px;padding:18px 20px;overflow:auto;}
        .queue-dialog-summary,.queue-dialog-existing-note,.queue-dialog-note,.queue-dialog-metrics{padding:12px 14px;border-radius:14px;border:1px solid color-mix(in srgb, var(--border) 18%, transparent);background:color-mix(in srgb, var(--border) 8%, transparent);font-size:13px;line-height:1.45;color:var(--text);}
        .queue-dialog-existing-note{background:color-mix(in srgb, var(--accent-blue) 12%, transparent);border-color:color-mix(in srgb, var(--accent-blue) 24%, transparent);color:#dbeafe;}
        .queue-dialog-field{display:grid;gap:6px;}
        .queue-dialog-field span{font-size:11px;font-weight:800;color:var(--text-secondary);text-transform:uppercase;letter-spacing:.04em;}
        .queue-dialog-target-state,.queue-dialog-notes{width:100%;box-sizing:border-box;border-radius:12px;border:1px solid color-mix(in srgb, var(--border) 26%, transparent);background:color-mix(in srgb, var(--text) 6%, transparent);color:var(--text);padding:10px 12px;font:inherit;}
        .queue-dialog-target-state{appearance:none;-webkit-appearance:none;color-scheme:dark;background-color:color-mix(in srgb, var(--text) 6%, transparent);}
        .queue-dialog-target-state:focus{outline:none;border-color:color-mix(in srgb, var(--accent-blue) 46%, transparent);box-shadow:0 0 0 1px color-mix(in srgb, var(--accent-blue) 26%, transparent);}
        .queue-dialog-target-state option{background-color:var(--bg-panel);color:var(--text);}
        .queue-dialog-toolbar{display:flex;gap:8px;flex-wrap:wrap;}
        .queue-dialog-file-list{display:grid;gap:10px;}
        .queue-dialog-file-block{display:grid;gap:8px;padding:12px;border-radius:16px;border:1px solid color-mix(in srgb, var(--border) 18%, transparent);background:color-mix(in srgb, var(--text) 4%, transparent);}
        .queue-dialog-file-toggle,.queue-dialog-plate-toggle{display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:38px;padding:0 12px;border-radius:12px;border:1px solid color-mix(in srgb, var(--border) 20%, transparent);background:color-mix(in srgb, var(--text) 4%, transparent);color:var(--text);font-size:12px;font-weight:700;cursor:pointer;text-align:left;}
        .queue-dialog-file-toggle span{font-size:11px;color:var(--text-secondary);font-weight:700;}
        .queue-dialog-file-toggle.active,.queue-dialog-plate-toggle.active{background:color-mix(in srgb, var(--accent-blue) 18%, transparent);border-color:color-mix(in srgb, var(--accent-blue) 34%, transparent);}
        .queue-dialog-plates{display:grid;gap:8px;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));}
        .queue-dialog-error{padding:12px 14px;border-radius:14px;border:1px solid color-mix(in srgb, var(--accent-red) 32%, transparent);background:color-mix(in srgb, var(--accent-red) 12%, transparent);color:#fecaca;font-size:13px;}
        .queue-dialog-footer{display:flex;align-items:center;justify-content:flex-end;gap:10px;padding:14px 20px 18px;border-top:1px solid color-mix(in srgb, var(--border) 16%, transparent);}
        .queue-dialog-submit{background:color-mix(in srgb, var(--accent-blue) 22%, transparent);border-color:color-mix(in srgb, var(--accent-blue) 34%, transparent);}
        .overflow-wrap { position: relative; }
        .overflow-menu {
          position: absolute;
          right: 0;
          top: calc(100% + 4px);
          min-width: 270px;
          border: 1px solid var(--border);
          border-radius: 10px;
          background: var(--bg-card);
          box-shadow: var(--shadow-lg);
          padding: 8px;
          z-index: 10;
          display: none;
        }
        .overflow-menu.open { display: grid; gap: 6px; }
        .overflow-row {
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 8px;
          background: var(--bg-card-alt);
        }
        .overflow-row .label { font-size: 12px; font-weight: 600; color: var(--text); }
        .overflow-row .meta { font-size: 10px; color: var(--text-secondary); margin-top: 3px; }
        .overflow-row.danger {
          border-color: color-mix(in srgb, var(--accent-red) 32%, transparent);
          background: color-mix(in srgb, var(--accent-red) 12%, transparent);
        }
        .overflow-row.danger .label { color: #fca5a5; }
        .overflow-row.danger .meta { color: #f87171; }
        .overflow-row.danger:hover {
          background: color-mix(in srgb, var(--accent-red) 18%, transparent);
        }

        .hero {
          display: grid;
          grid-template-columns: 1fr 1fr;
          align-items: start;
        }
        .left {
          border-right: 1px solid var(--border);
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
          border: 1px solid var(--border);
          border-radius: 999px;
          padding: 4px 8px;
          font-size: 11px;
          color: var(--text-secondary);
          background: var(--bg-card);
          cursor: pointer;
        }
        .chip.active {
          border-color: var(--primary-color);
          color: var(--text);
        }
        .main-media {
          margin: 12px;
          border: 1px solid var(--border);
          border-radius: 12px;
          overflow: hidden;
          position: relative;
          aspect-ratio: 4 / 3;
          background: var(--bg-card-alt);
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .popup-shell.is-idea .main-media {
          border-color: color-mix(in srgb, #ffc107 55%, transparent);
          box-shadow: inset 0 0 0 1px color-mix(in srgb, #ffc107 22%, transparent);
        }
        .main-media img {
          max-width: 100%;
          max-height: 100%;
          object-fit: contain;
          display: block;
        }
        .main-media .badge {
          position: absolute;
          top: 10px;
          left: 10px;
          border-radius: 999px;
          border: 1px solid var(--border);
          background: color-mix(in srgb, rgba(0, 0, 0, 0.7), transparent);
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
          border: 1px solid color-mix(in srgb, var(--border) 28%, transparent);
          border-radius: 999px;
          background: color-mix(in srgb, var(--text) 4%, transparent);
          color: var(--text);
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
          background: var(--bg-card-alt);
          color: var(--text);
          border-color: color-mix(in srgb, var(--border) 54%, transparent);
          box-shadow: 0 0 0 1px color-mix(in srgb, var(--text) 16%, transparent), var(--shadow);
          transform: translateY(-1px);
          outline: none;
        }
        .icon-action:active { transform: translateY(0); }
        .icon-action.viewer {
          background: color-mix(in srgb, var(--accent-green) 12%, transparent);
          border-color: color-mix(in srgb, var(--accent-green) 28%, transparent);
          color: var(--text);
        }
        .icon-action.viewer:hover,
        .icon-action.viewer:focus-visible {
          background: color-mix(in srgb, var(--accent-green) 18%, transparent);
          color: var(--text);
          border-color: color-mix(in srgb, var(--accent-green) 46%, transparent);
          box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent-green) 18%, transparent), var(--shadow);
          transform: translateY(-1px);
          outline: none;
        }
        .icon-action.viewer:active { transform: translateY(0); }
        .icon-action.expand {
          background: color-mix(in srgb, var(--accent-blue) 12%, transparent);
          border-color: color-mix(in srgb, var(--accent-blue) 30%, transparent);
          color: var(--text);
        }
        .icon-action.expand:hover,
        .icon-action.expand:focus-visible {
          background: color-mix(in srgb, var(--accent-blue) 18%, transparent);
          color: var(--text);
          border-color: color-mix(in srgb, var(--accent-blue) 48%, transparent);
          box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent-blue) 18%, transparent), var(--shadow);
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
          border: 1px solid var(--border);
          background: color-mix(in srgb, rgba(0, 0, 0, 0.55), var(--bg-overlay));
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
          border: 1px solid color-mix(in srgb, var(--border) 32%, transparent);
          border-radius: 999px;
          padding: 8px 12px;
          background: color-mix(in srgb, var(--text) 4%, transparent);
          color: var(--text);
          font-size: 12px;
          font-weight: 700;
          cursor: pointer;
          white-space: nowrap;
          transition: background .16s ease,color .16s ease,box-shadow .16s ease,border-color .16s ease;
        }
        .media-actions .action-button:hover,
        .media-actions .action-button:focus-visible {
          background: color-mix(in srgb, var(--text) 10%, transparent);
          border-color: color-mix(in srgb, var(--border) 60%, transparent);
          box-shadow: 0 0 0 1px color-mix(in srgb, var(--text) 14%, transparent), var(--shadow);
          outline: none;
        }
        .media-actions .action-button.danger {
          background: color-mix(in srgb, var(--accent-red) 8%, transparent);
          border-color: color-mix(in srgb, var(--accent-red) 28%, transparent);
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
          border-left: 1px solid var(--border);
        }
        .thumb {
          flex: 0 0 72px;
          width: 72px;
          height: 72px;
          border: 1px solid var(--border);
          border-radius: 9px;
          overflow: hidden;
          background: var(--bg-card-alt);
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
          background: color-mix(in srgb, rgba(0,0,0,0.8), transparent);
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
          background: color-mix(in srgb, var(--accent-red) 60%, transparent);
          color: #fff;
          font-size: 10px;
          font-weight: 700;
          line-height: 16px;
          text-align: center;
        }

        .panel-shell {
          margin: 0 12px 12px;
          border: 1px solid var(--border);
          border-radius: 12px;
          overflow: hidden;
          background: var(--bg-card-alt);
        }
        .panel-toolbar {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 8px;
          flex-wrap: wrap;
          border-bottom: 1px solid var(--border);
          padding: 8px 10px;
        }
        .view-mode {
          display: inline-flex;
          border: 1px solid var(--border);
          border-radius: 999px;
          overflow: hidden;
        }
        .view-mode button {
          border: 0;
          background: transparent;
          color: var(--text-secondary);
          padding: 5px 10px;
          font-size: 11px;
          cursor: pointer;
        }
        .view-mode button.active {
          background: var(--bg-card);
          color: var(--text);
        }
        .tabs {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          border-bottom: 1px solid var(--border);
          padding: 9px 10px 0;
        }
        .tabs button {
          border: 1px solid transparent;
          border-bottom: 0;
          border-radius: 10px 10px 0 0;
          padding: 7px 10px;
          background: var(--bg-card);
          color: var(--text-secondary);
          cursor: pointer;
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }
        .tabs button.active {
          color: var(--text);
          border-color: var(--border);
          box-shadow: inset 0 -2px 0 var(--primary-color);
        }
        .count {
          border: 1px solid var(--border);
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
          border-bottom: 1px solid var(--border);
        }
        .stacked .tab-panel:last-child { border-bottom: 0; }

        .queue-list, .related-list, .support-list { display: grid; gap: 7px; }
        .queue-row, .related, .support {
          border: 1px solid var(--border);
          border-radius: 9px;
          background: var(--bg-card);
          padding: 8px;
          font-size: 12px;
        }
        .support-toolbar {
          display: grid;
          gap: 8px;
          margin-bottom: 10px;
        }
        .support-toolbar-main {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          flex-wrap: wrap;
        }
        .support-toggle-wrap {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          flex-wrap: wrap;
        }
        .support-segmented {
          display: inline-flex;
          padding: 2px;
          border-radius: 999px;
          border: 1px solid var(--border);
          background: var(--bg-card-alt);
        }
        .support-segmented button {
          border: 0;
          background: transparent;
          color: var(--text-secondary);
          padding: 4px 10px;
          border-radius: 999px;
          font-size: 10px;
          font-weight: 800;
          letter-spacing: 0.05em;
          text-transform: uppercase;
          cursor: pointer;
        }
        .support-segmented button.active {
          background: color-mix(in srgb, var(--accent-blue) 20%, transparent);
          color: var(--text);
        }
        .support-browser {
          border: 1px solid var(--border);
          border-radius: 10px;
          background: var(--bg-card-alt);
          padding: 8px;
        }
        .support-browser[data-thumb="small"] { --support-thumb-size: 34px; --support-row-pad: 6px 8px; }
        .support-browser[data-thumb="medium"] { --support-thumb-size: 58px; --support-row-pad: 8px 10px; }
        .support-browser[data-thumb="large"] { --support-thumb-size: 116px; --support-row-pad: 10px 12px; }
        .support-rows {
          display: grid;
          gap: 7px;
        }
        .support-file-row,
        .support-folder-row {
          display: grid;
          grid-template-columns: var(--support-thumb-size, 58px) minmax(0, 1fr) auto;
          align-items: center;
          gap: 10px;
          border: 1px solid var(--border);
          border-radius: 10px;
          background: var(--bg-card);
          padding: var(--support-row-pad, 8px 10px);
        }
        .support-file-row {
          grid-template-columns: var(--support-thumb-size, 58px) minmax(0, 1fr) auto auto;
        }
        .support-folder-row {
          cursor: pointer;
        }
        .support-folder-row:hover {
          background: color-mix(in srgb, var(--accent-blue) 10%, transparent);
        }
        .support-thumb {
          width: var(--support-thumb-size, 58px);
          height: var(--support-thumb-size, 58px);
          border-radius: 9px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          border: 1px solid var(--border);
          background: color-mix(in srgb, var(--accent-teal) 10%, transparent);
          overflow: hidden;
          color: var(--text);
        }
        .support-thumb.has-image {
          padding: 0;
          background: color-mix(in srgb, var(--text) 3%, transparent);
          position: relative;
        }
        .support-thumb img {
          width: 100%;
          height: 100%;
          object-fit: cover;
          display: block;
          opacity: 0;
          transition: opacity 140ms ease;
          position: relative;
          z-index: 2;
        }
        .support-thumb.has-image.thumb-ready img {
          opacity: 1;
        }
        .support-thumb.has-image.thumb-failed img {
          display: none;
        }
        .support-thumb-placeholder {
          position: absolute;
          inset: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1;
          overflow: hidden;
        }
        .support-thumb.has-image.thumb-ready .support-thumb-placeholder {
          opacity: 0;
          pointer-events: none;
        }
        .support-thumb-shimmer {
          position: absolute;
          inset: 0;
          background: linear-gradient(90deg, color-mix(in srgb, var(--text) 4%, transparent) 25%, color-mix(in srgb, var(--text) 8%, transparent) 50%, color-mix(in srgb, var(--text) 4%, transparent) 75%);
          background-size: 220% 100%;
          animation: shimmer 1.4s infinite;
        }
        .support-thumb-placeholder ha-icon {
          --mdc-icon-size: calc(var(--support-thumb-size, 58px) * 0.38);
          width: calc(var(--support-thumb-size, 58px) * 0.38);
          height: calc(var(--support-thumb-size, 58px) * 0.38);
          position: relative;
          z-index: 2;
          opacity: 0.95;
        }
        .support-thumb-placeholder-images { color: #93c5fd; }
        .support-thumb-placeholder-docs { color: #7dd3fc; }
        .support-thumb-placeholder-other { color: #fcd34d; }
        .support-thumb.has-image.thumb-failed .support-thumb-placeholder {
          opacity: 1;
          background: color-mix(in srgb, var(--text) 5%, transparent);
        }
        .support-thumb.has-image.thumb-failed .support-thumb-shimmer {
          display: none;
        }
        .support-ext {
          font-size: calc(var(--support-thumb-size, 58px) * 0.2);
          font-weight: 800;
          letter-spacing: 0.01em;
          text-transform: uppercase;
          color: var(--text-secondary);
          white-space: nowrap;
        }
        .support-folder-icon {
          font-size: calc(var(--support-thumb-size, 58px) * 0.45);
          line-height: 1;
        }
        .support-main {
          min-width: 0;
          display: flex;
          flex-direction: column;
          justify-content: center;
          gap: 2px;
        }
        .support-name {
          font-size: 12px;
          font-weight: 700;
          color: var(--text);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .support-subpath {
          margin-top: 3px;
          font-size: 10.5px;
          color: var(--text-secondary);
          font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, monospace;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .support-meta {
          text-align: right;
          min-width: 82px;
          font-size: 11px;
          color: var(--text-secondary);
          font-variant-numeric: tabular-nums;
        }
        .support-size {
          min-width: 56px;
          text-align: right;
          font-size: 11px;
          color: var(--text-secondary);
          font-variant-numeric: tabular-nums;
          white-space: nowrap;
          align-self: center;
        }
        .support-type-chips {
          display: inline-flex;
          flex-wrap: wrap;
          gap: 6px;
        }
        .support-type-chips button {
          border: 1px solid var(--border);
          border-radius: 999px;
          background: var(--bg-card-alt);
          color: var(--text-secondary);
          font-size: 10px;
          font-weight: 800;
          letter-spacing: 0.03em;
          padding: 4px 10px;
          cursor: pointer;
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }
        .support-type-chips button.active {
          color: var(--text);
        }
        .support-type-chips button .ct {
          color: var(--text-muted, var(--text-secondary));
          font-weight: 600;
          letter-spacing: 0;
        }
        .support-type-chips button ha-icon {
          --mdc-icon-size: 15px;
          width: 15px;
          height: 15px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
        }
        .support-type-chips button.cat-all.active {
          background: rgba(139, 92, 246, 0.16);
          border-color: rgba(167, 139, 250, 0.34);
          color: #c4b5fd;
        }
        .support-type-chips button.cat-all.active .ct { color: #c4b5fd; }
        .support-type-chips button.cat-images.active {
          background: rgba(37, 99, 235, 0.16);
          border-color: rgba(147, 197, 253, 0.34);
          color: #93c5fd;
        }
        .support-type-chips button.cat-images.active .ct { color: #93c5fd; }
        .support-type-chips button.cat-docs.active {
          background: rgba(56, 189, 248, 0.16);
          border-color: rgba(125, 211, 252, 0.34);
          color: #7dd3fc;
        }
        .support-type-chips button.cat-docs.active .ct { color: #7dd3fc; }
        .support-type-chips button.cat-other.active {
          background: rgba(245, 158, 11, 0.16);
          border-color: rgba(252, 211, 77, 0.34);
          color: #fcd34d;
        }
        .support-type-chips button.cat-other.active .ct { color: #fcd34d; }
        .support-actions {
          display: inline-flex;
          gap: 6px;
          justify-content: flex-end;
          flex-wrap: wrap;
          align-items: center;
        }
        .support-action {
          border: 1px solid var(--border);
          border-radius: 999px;
          background: var(--bg-card-alt);
          color: var(--text);
          font-size: 10px;
          font-weight: 700;
          letter-spacing: 0.03em;
          text-transform: uppercase;
          padding: 4px 9px;
          cursor: pointer;
        }
        .support-action:hover {
          border-color: color-mix(in srgb, var(--accent-blue) 45%, transparent);
          background: color-mix(in srgb, var(--accent-blue) 16%, transparent);
        }
        .support-breadcrumbs {
          margin-bottom: 8px;
          display: flex;
          align-items: center;
          flex-wrap: wrap;
          gap: 6px;
          font-size: 11px;
          color: var(--text-secondary);
          font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, monospace;
        }
        .support-breadcrumb-link {
          border: 0;
          background: transparent;
          color: var(--primary-color);
          cursor: pointer;
          font: inherit;
          padding: 0;
        }
        .support-breadcrumb-link:hover {
          text-decoration: underline;
        }
        .support-breadcrumb-up {
          width: 24px;
          height: 24px;
          border-radius: 6px;
          border: 1px solid var(--border);
          background: var(--bg-card-alt);
          color: var(--text);
          cursor: pointer;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          line-height: 1;
        }
        .support-breadcrumb-up:disabled {
          opacity: 0.45;
          cursor: default;
        }
        .support-breadcrumb-current {
          color: var(--text);
          font-weight: 700;
        }
        .support-empty {
          border: 1px dashed var(--border);
          border-radius: 10px;
          padding: 12px;
          font-size: 12px;
          color: var(--text-secondary);
          background: var(--bg-card);
        }
        .right {
          padding: 12px;
          display: grid;
          grid-template-rows: auto auto 1fr;
          gap: 10px;
          overflow: visible;
        }
        .card {
          border: 1px solid var(--border);
          border-radius: 12px;
          overflow: hidden;
          background: var(--bg-card-alt);
        }
        .card .h {
          border-bottom: 1px solid var(--border);
          background: var(--bg-card);
          padding: 8px 10px;
          font-size: 12px;
          text-transform: uppercase;
          letter-spacing: 0.03em;
          color: var(--text-secondary);
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
          color: var(--text-secondary);
          transition: background 0.2s, border-color 0.2s, color 0.2s;
          --mdc-icon-size: 20px;
        }
        .refresh-candidates-btn:hover:not([disabled]) {
          background: var(--bg-card-alt);
          border-color: var(--border);
          color: var(--text);
        }
        .refresh-candidates-btn:active:not([disabled]) {
          background: var(--border);
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
        .archive-header-tools {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .archive-header-main {
          display: flex;
          align-items: center;
          gap: 8px;
          min-width: 0;
        }
        section[data-slot="sections:archive-linkage"] .h {
          flex-wrap: wrap;
          row-gap: 8px;
        }
        .linked-sort-btn {
          border: 1px solid var(--border);
          border-radius: 999px;
          background: var(--bg-card-alt);
          color: var(--text-secondary);
          padding: 4px 10px;
          font-size: 11px;
          font-weight: 600;
          cursor: pointer;
        }
        .linked-sort-btn:hover {
          color: var(--text);
          border-color: var(--primary-color);
        }
        .archive-filter-row {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          margin-bottom: 2px;
        }
        .archive-filter-row.header {
          margin-bottom: 0;
        }
        .archive-filter-btn {
          border: 1px solid var(--border);
          border-radius: 999px;
          background: var(--bg-card);
          color: var(--text-secondary);
          padding: 4px 9px;
          font-size: 11px;
          font-weight: 600;
          cursor: pointer;
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }
        .archive-filter-btn.active {
          color: var(--text);
          border-color: var(--primary-color);
          background: color-mix(in srgb, var(--accent-blue) 12%, transparent);
        }
        .archive-filter-btn.active[data-archive-filter="linked"] {
          border-color: color-mix(in srgb, var(--accent-teal) 45%, transparent);
          background: color-mix(in srgb, var(--accent-teal) 12%, transparent);
          color: #b8fff3;
        }
        .archive-filter-btn.active[data-archive-filter="candidates"] {
          border-color: color-mix(in srgb, var(--accent-amber) 45%, transparent);
          background: color-mix(in srgb, var(--accent-amber) 12%, transparent);
          color: #ffe0ae;
        }
        .archive-filter-btn span {
          color: var(--text);
          opacity: 0.86;
        }
        .archive-bulk-toolbar {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 6px;
          margin: 2px 0 4px;
        }
        .archive-bulk-count {
          font-size: 11px;
          color: var(--text-secondary);
          margin-right: 4px;
        }
        .candidate-checkbox {
          width: 14px;
          height: 14px;
          cursor: pointer;
          flex-shrink: 0;
        }
        .collapsible-group.candidate-selected {
          border-color: rgba(96, 165, 250, 0.42);
          box-shadow: inset 0 0 0 1px rgba(96, 165, 250, 0.24);
        }
        .summary { padding: 10px; display: grid; gap: 8px; }
        .summary .name { font-size: 15px; font-weight: 700; }
        .summary .meta { color: var(--text-secondary); font-size: 12px; }
        .summary .desc { color: var(--text); font-size: 12px; line-height: 1.45; white-space: pre-wrap; }
        .summary-edit-grid { display: grid; gap: 8px; }
        .summary-edit-grid label { display: grid; gap: 4px; }
        .summary-edit-grid label > span { font-size: 11px; color: var(--text-secondary); font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; }
        .summary-input,
        .summary-textarea {
          width: 100%;
          box-sizing: border-box;
          border: 1px solid var(--border);
          border-radius: 8px;
          background: var(--bg-card-alt);
          color: var(--text);
          padding: 8px 10px;
          font: inherit;
        }
        .summary-textarea { min-height: 88px; resize: vertical; }
        .chip-group.stack { align-items: flex-start; flex-direction: column; }
        .chip-row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
        .summary-empty { color: var(--text-secondary); font-size: 12px; }
        .collection-edit-feedback {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          padding: 8px 10px;
          border-radius: 10px;
          border: 1px solid var(--border);
          background: color-mix(in srgb, var(--accent-blue) 10%, transparent);
          margin-bottom: 8px;
        }
        .collection-edit-feedback.warning {
          background: rgba(245, 158, 11, 0.12);
          border-color: rgba(245, 158, 11, 0.28);
        }
        .collection-edit-feedback.error {
          background: rgba(239, 68, 68, 0.12);
          border-color: rgba(239, 68, 68, 0.28);
        }
        .collection-edit-feedback-message { font-size: 12px; color: var(--text); line-height: 1.35; }
        .collection-edit-feedback-actions { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
        .action-button.small { padding: 5px 9px; font-size: 10px; }
        .meta-warning {
          margin-top: 8px;
          padding: 8px 10px;
          border-radius: 10px;
          border: 1px solid rgba(245, 158, 11, 0.28);
          background: rgba(245, 158, 11, 0.10);
          color: var(--text);
          font-size: 12px;
          line-height: 1.35;
        }
        .meta-warning-actions { margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap; }

        /* tag / collection chip UX */
        .chip-group { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
        .chip-group .label { font-size: 11px; color: var(--text-secondary); font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; margin-right: 4px; }
        .card:has(.picker-wrap) { overflow: visible; }
        .tag-chip {
          display: inline-flex; align-items: center; gap: 4px;
          padding: 3px 9px; border-radius: 999px; font-size: 11px; font-weight: 600;
          background: rgba(110,218,203,0.10); color: var(--accent-color, #6edacb); border: 1px solid rgba(110,218,203,0.28);
        }
        .tag-chip-button {
          appearance: none;
          -webkit-appearance: none;
          cursor: pointer;
          font: inherit;
          line-height: inherit;
        }
        .tag-chip-button:hover,
        .tag-chip-button:focus-visible {
          background: rgba(110,218,203,0.16);
          border-color: rgba(110,218,203,0.42);
          color: var(--text);
          outline: none;
        }
        .tag-chip.stale {
          background: rgba(239, 68, 68, 0.12);
          border-color: rgba(239, 68, 68, 0.28);
          color: #fca5a5;
        }
        .tag-chip .stale-note {
          font-size: 10px;
          font-weight: 800;
          letter-spacing: 0.04em;
          text-transform: uppercase;
          opacity: 0.92;
        }
        .tag-chip .x { cursor: pointer; opacity: 0.6; font-size: 12px; margin-left: 2px; line-height: 1; }
        .tag-chip .x:hover { opacity: 1; }
        .add-chip {
          display: inline-flex; align-items: center; gap: 3px;
          padding: 3px 9px; border-radius: 999px; font-size: 11px; font-weight: 700;
          background: transparent; color: var(--text-secondary); border: 1px dashed var(--border);
          cursor: pointer;
        }
        .add-chip:hover { color: var(--text); border-color: var(--accent, #6edacb); background: color-mix(in srgb, var(--accent, #6edacb) 6%, transparent); }
        .picker-wrap { position: relative; display: inline-block; }
        .picker-dd {
          position: absolute; top: calc(100% + 4px); left: 0; z-index: 90;
          min-width: 220px; max-height: 250px; overflow-y: auto;
          background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px;
          box-shadow: 0 10px 36px rgba(0,0,0,0.44); padding: 6px;
        }
        .picker-dd .search-box {
          width: 100%; box-sizing: border-box; margin-bottom: 4px;
          background: var(--bg-card-alt); border: 1px solid var(--border); border-radius: 8px;
          color: var(--text); font-size: 12px; padding: 7px 10px; outline: none;
        }
        .picker-dd .search-box:focus { border-color: var(--accent-color, #6edacb); box-shadow: 0 0 0 2px rgba(110,218,203,0.18); }
        .picker-dd .opt {
          padding: 7px 10px; border-radius: 8px; cursor: pointer; font-size: 12px; color: var(--text);
        }
        .picker-dd .opt:hover { background: color-mix(in srgb, var(--text) 6%, transparent); }
        .picker-dd .opt.selected { background: color-mix(in srgb, var(--text) 10%, transparent); }
        .picker-dd .opt.already { color: var(--accent, #6edacb); opacity: 0.6; cursor: default; }
        .picker-dd .path-meta { display: block; margin-top: 2px; font-size: 10px; color: var(--text-secondary); }
        .picker-dd .create-new {
          color: var(--accent, #6edacb); font-weight: 700; font-size: 12px;
          padding: 7px 10px; border-top: 1px solid var(--border); cursor: pointer;
        }
        .picker-dd .create-new:hover { background: color-mix(in srgb, var(--accent-teal) 8%, transparent); }
        .picker-dd .create-new.selected { background: color-mix(in srgb, var(--accent-teal) 12%, transparent); }

        .status { display: flex; gap: 6px; flex-wrap: wrap; }
        .status span {
          border: 1px solid var(--border);
          border-radius: 999px;
          padding: 4px 8px;
          font-size: 10px;
          color: var(--text-secondary);
          background: var(--bg-card);
        }
        .files { padding: 8px; display: grid; gap: 7px; }
        .card[data-slot="sections:archive-linkage"] > .files {
          max-height: 420px;
          overflow-y: auto;
          scrollbar-width: thin;
        }
        .file-preview { width: 40px; height: 40px; border-radius: 6px; border: 1px solid var(--border); object-fit: cover; flex-shrink: 0; }
        .file-ext-badge { width: 40px; height: 40px; border-radius: 6px; border: 1px solid color-mix(in srgb, var(--border) 25%, transparent); display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 800; color: var(--text-secondary); background: color-mix(in srgb, var(--text) 4%, transparent); flex-shrink: 0; }
        .file-ext-badge.x-3mf { color: #5eead4; border-color: rgba(94,234,212,0.3); background: rgba(94,234,212,0.12); }
        .file-ext-badge.x-stl, .file-ext-badge.x-step, .file-ext-badge.x-stp, .file-ext-badge.x-obj { color: #93c5fd; border-color: rgba(96,165,250,0.32); background: rgba(96,165,250,0.12); }
        .collapsible-group {
          border: 1px solid var(--border);
          border-radius: 9px;
          overflow: hidden;
          background: var(--bg-card);
        }
        .collapsible-group.is-linked {
          border-color: color-mix(in srgb, var(--accent-teal) 20%, transparent);
          background: linear-gradient(0deg, color-mix(in srgb, var(--accent-teal) 4%, transparent), color-mix(in srgb, var(--accent-teal) 4%, transparent)), var(--bg-card);
        }
        .collapsible-group.is-candidate {
          border-color: color-mix(in srgb, var(--accent-amber) 24%, transparent);
          background: linear-gradient(0deg, color-mix(in srgb, var(--accent-amber) 5%, transparent), color-mix(in srgb, var(--accent-amber) 5%, transparent)), var(--bg-card);
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
        .file-row-toggle {
          align-items: center;
          gap: 14px;
          padding: 10px 12px;
        }
        .file-row-main {
          display: flex;
          align-items: center;
          gap: 12px;
          min-width: 0;
        }
        .file-row-main > div:last-child {
          min-width: 0;
        }
        .file-row-main strong {
          display: block;
          font-size: 13px;
          line-height: 1.3;
          color: var(--text);
          word-break: break-word;
        }
        .file-row-side {
          display: flex;
          align-items: center;
          justify-content: flex-end;
          gap: 12px;
        }
        .file-total-estimate {
          display: grid;
          justify-items: end;
          gap: 1px;
          min-width: 68px;
        }
        .file-total-label {
          font-size: 10px;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: var(--text-secondary);
        }
        .file-total-estimate strong {
          font-size: 14px;
          color: var(--text);
        }
        .file-total-subtle {
          font-size: 11px;
          color: var(--text-secondary);
        }
        .file-chevron {
          width: 24px;
          text-align: center;
          font-size: 14px;
          color: var(--text-secondary);
        }
        .collapse-toggle.archive-row-static {
          cursor: default;
        }
        .collapse-body {
          padding: 8px;
          border-top: 1px solid var(--border);
          font-size: 11px;
          color: var(--text-secondary);
        }
        .file-collapse-body {
          padding: 10px 12px 12px;
          background: color-mix(in srgb, var(--bg-card-alt) 72%, transparent);
        }
        .file-plate-list {
          display: grid;
          gap: 10px;
        }
        .file-plate-row {
          display: grid;
          grid-template-columns: 96px minmax(0, 1fr);
          gap: 12px;
          align-items: center;
          padding: 10px 0;
        }
        .file-plate-row + .file-plate-row {
          border-top: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
        }
        .file-plate-visual {
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .file-plate-card {
          width: 78px;
          height: 78px;
          border-radius: 10px;
          border: 1px solid color-mix(in srgb, var(--border) 60%, transparent);
          background:
            linear-gradient(135deg, color-mix(in srgb, var(--text) 8%, transparent), transparent),
            color-mix(in srgb, var(--bg-card) 80%, var(--text) 20%);
          box-shadow: inset 0 1px 0 color-mix(in srgb, #fff 18%, transparent);
          position: relative;
          overflow: hidden;
        }
        .file-plate-card.has-image {
          background-size: cover;
          background-position: center;
          background-repeat: no-repeat;
        }
        .file-plate-card::after {
          content: '';
          position: absolute;
          inset: 10px;
          border-radius: 12px;
          border: 1px solid color-mix(in srgb, var(--text) 10%, transparent);
          background: color-mix(in srgb, var(--bg-card) 84%, transparent);
        }
        .file-plate-card.has-image::after {
          inset: 0;
          border-radius: inherit;
          border: 1px solid color-mix(in srgb, rgba(255,255,255,0.5) 45%, transparent);
          background: linear-gradient(to top, rgba(0, 0, 0, 0.42), rgba(0, 0, 0, 0.06) 55%, transparent 100%);
        }
        .plate-color-swatch {
          display: inline-block;
          width: 10px;
          height: 10px;
          min-width: 10px;
          min-height: 10px;
          aspect-ratio: 1 / 1;
          border-radius: 50%;
          border: 1px solid rgba(255,255,255,0.35);
          box-shadow: 0 1px 2px rgba(0,0,0,0.25);
          flex: 0 0 auto;
          box-sizing: border-box;
        }
        .file-plate-color-chip {
          display: inline-flex;
          align-items: center;
          gap: 5px;
          padding-right: 6px;
        }
        .file-plate-meta .file-plate-color-chip {
          padding: 0;
          border: 0;
          border-radius: 0;
          background: transparent;
        }
        .file-plate-color-chip .plate-color-swatch {
          display: inline-block;
          width: 9px;
          height: 9px;
          min-width: 9px;
          min-height: 9px;
        }
        .file-plate-color-chip .color-count-label {
          font-size: 11px;
          color: inherit;
        }
        .file-plate-main {
          min-width: 0;
          display: grid;
          gap: 4px;
        }
        .file-plate-name {
          font-size: 12px;
          font-weight: 700;
          color: var(--text);
          line-height: 1.3;
        }
        .file-plate-meta {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
          font-size: 11px;
          color: var(--text-secondary);
        }
        .file-plate-meta > span {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          padding: 3px 8px;
          border-radius: 999px;
          border: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
          background: color-mix(in srgb, var(--bg-card) 80%, transparent);
        }
        .file-plate-loading,
        .file-plate-empty {
          padding: 8px 0 4px;
          font-size: 11px;
          color: var(--text-secondary);
        }
        .hidden { display: none !important; }
        .state {
          font-size: 10px;
          border: 1px solid var(--border);
          border-radius: 999px;
          padding: 3px 7px;
          margin-right: 4px;
        }
        .collapsible-group.is-linked .state {
          border-color: color-mix(in srgb, var(--accent-teal) 45%, transparent);
          background: color-mix(in srgb, var(--accent-teal) 14%, transparent);
          color: #b8fff3;
        }

        .collapsible-group.is-candidate .state {
          border-color: color-mix(in srgb, var(--accent-amber) 45%, transparent);
          background: color-mix(in srgb, var(--accent-amber) 14%, transparent);
          color: #ffe0ae;
        }

        .icon-action-btn {
          background: none;
          border: none;
          padding: 2px 4px;
          margin: 0;
          border-radius: 6px;
          color: var(--text-secondary);
          cursor: pointer;
          display: inline-flex;
          align-items: center;
          transition: background 0.15s, color 0.15s;
        }
        .icon-action-btn:hover {
          background: rgba(255,255,255,0.08);
          color: var(--primary-color);
        }
        .icon-action-btn.archive-skip {
          color: rgba(180,180,190,0.55);
        }
        .icon-action-btn.archive-skip:hover {
          color: rgba(220,220,225,0.85);
          background: rgba(255,255,255,0.06);
        }
        .icon-action-btn.archive-link {
          color: rgba(94,234,212,0.7);
        }
        .icon-action-btn.archive-link:hover {
          color: #5eeadc;
          background: rgba(94,234,212,0.1);
        }
        .archive-actions-right {
          display: flex;
          flex-direction: column;
          align-items: flex-end;
          gap: 1px;
        }
        .archive-actions-right .archive-action-row {
          display: flex;
          align-items: center;
          gap: 4px;
        }

        @media (max-width: 980px) {
          .hero { grid-template-columns: 1fr; align-items: stretch; }
          .card[data-slot="sections:archive-linkage"] > .files { max-height: none; }
          .left { border-right: 0; border-bottom: 1px solid var(--border); }
          .media-with-thumbs { flex-direction: column; }
          .thumbs {
            flex: 0 0 auto;
          .file-row-toggle {
            grid-template-columns: 1fr;
          }
          .file-row-side {
            justify-content: space-between;
          }
          .file-total-estimate {
            justify-items: start;
          }
          .file-plate-row {
            grid-template-columns: 1fr;
          }
          .file-plate-visual {
            justify-content: flex-start;
          }
            flex-direction: row;
            max-height: none;
            overflow-x: auto;
            overflow-y: hidden;
            border-left: 0;
            border-top: 1px solid var(--border);
            padding: 6px 12px;
          }
          .thumb { flex: 0 0 72px; }
          .panel-shell { margin-bottom: 0; }
          .main-media { aspect-ratio: 4 / 3; max-height: 50vh; }
        }
      </style>

      <div class="popup-shell ${isIdea ? 'is-idea' : ''}">
        <div class="topbar">
          <div class="title">
            <span>Creator ${creator} | Collection ${collectionText}</span>
          </div>
          <div class="top-actions">
            ${isIdea ? `<span class="entity-type-badge idea">💡 Idea</span>` : ''}
            ${this._renderExtensionSlot('actions:top-bar', '')}
            ${isIdea ? `<button class="action-button" data-action="idea-promote-catalog" ${this._ideaPromoteBusy ? 'disabled' : ''}>⬆ Promote to Catalog</button>` : ''}
            ${isIdea ? `<button class="action-button ghost" data-action="idea-move-to-working-files" ${this._ideaPromoteBusy ? 'disabled' : ''}>➡ Move to Working Files</button>` : ''}
            ${isIdea ? '' : `<button class="action-button ghost ${isFrequent ? frequentButtonClass : ''}" id="btn-toggle-frequent" title="${frequentButtonTitle}">${frequentButtonLabel}</button>`}
            <button class="action-button ghost ${isArchived ? 'toggle-active-warn' : ''}" id="btn-toggle-archive" title="${isArchived ? 'This model is archived — hidden from default Catalog views. Click to un-archive.' : 'Archive this model — hides from default Catalog views while preserving all data.'}">${isArchived ? '📦 Archived' : '📦 Archive'}</button>
            ${isIdea ? '' : '<button class="action-button ghost" id="btn-viewer">3D View</button>'}
            ${isIdea ? '' : '<button class="action-button ghost" id="btn-download">Download</button>'}
            ${isIdea ? '' : '<button class="action-button ghost" id="btn-create-archive">Create Archive</button>'}
            ${isIdea ? '' : '<button class="action-button" id="btn-print">Print</button>'}
            <div class="overflow-wrap">
              <button class="action-button ghost" id="btn-overflow-toggle">More</button>
              <div class="overflow-menu ${this._overflowOpen ? 'open' : ''}">
                ${this._renderExtensionSlot('actions:overflow', `
                  <div class="overflow-row">
                    <div class="label">Recover Print History wizard</div>
                    <div class="meta">Extension host for #1483 backfill flow</div>
                  </div>
                `)}
                <div class="overflow-row danger" id="btn-delete-model" style="cursor: pointer;">
                  <div class="label">Delete model</div>
                  <div class="meta">Permanently remove from catalog</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        ${isArchived ? `
        <div class="archived-banner">
          <span>📦</span>
          <span><strong>Archived</strong> — this model is hidden from default Catalog views. <button id="btn-unarchive">Un-archive</button></span>
        </div>
        ` : ''}

        <div class="hero">
          <div class="left">
            ${this._renderExtensionSlot('hero-left:media', `
              <div class="media-with-thumbs">
                <div class="main-media">
                  ${activeMedia && activeMedia.url ? `<img src="${this._escapeHtml(activeMedia.url)}" alt="Model media" loading="lazy">` : '<span>No preview</span>'}
                  ${activeMedia && activeMedia.type_label ? `<span class="badge">${this._escapeHtml(activeMedia.type_label)}</span>` : ''}
                  <div class="main-overlay-tools">
                    ${isIdea ? '' : '<button class="icon-action viewer" id="btn-viewer" type="button" aria-label="Open 3D viewer" title="Open 3D Viewer"><ha-icon icon="mdi:cube-scan"></ha-icon></button>'}
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
      <input type="file" id="supporting-file-input" multiple style="display: none;">

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
    // Preview image always first within each group
    const sortPreviewFirst = (arr) => {
      const preview = arr.filter(item => item && item.is_preview);
      const rest = arr.filter(item => !item || !item.is_preview);
      return [...preview, ...rest];
    };
    return [...sortPreviewFirst(visible), ...sortPreviewFirst(hidden)];
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
    const supportCount = (() => {
      const NON_SUPPORT_ROLES = new Set(['primary']);
      const MODEL_TYPES = new Set(['3mf', 'stl', 'obj', 'step', 'stp', 'gcode', 'zip']);
      return (Array.isArray(model.files) ? model.files : []).filter(f => {
        const role = String(f.asset_role || '').toLowerCase();
        const type = String(f.asset_type || '').toLowerCase();
        return !NON_SUPPORT_ROLES.has(role) && !MODEL_TYPES.has(type);
      }).length;
    })();
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
          <button data-panel-tab="panel-queue" class="${this._panelActiveTab === 'panel-queue' ? 'active' : ''}">Queued Prints <span class="count">${queueCount}</span></button>
          <button data-panel-tab="panel-related" class="${this._panelActiveTab === 'panel-related' ? 'active' : ''}">Related Models <span class="count">${relatedCount}</span></button>
          <button data-panel-tab="panel-support" class="${this._panelActiveTab === 'panel-support' ? 'active' : ''}">Supporting Files <span class="count">${supportCount}</span></button>
          <button data-panel-tab="panel-contribution" class="${this._panelActiveTab === 'panel-contribution' ? 'active' : ''}">Source</button>
          <button data-panel-tab="panel-publication" class="${this._panelActiveTab === 'panel-publication' ? 'active' : ''}">Publication</button>
        </div>
        ${panel('panel-queue', 'Queued Prints', this._renderExtensionSlot('sections:queue-status', this._renderQueueStatusPanel()))}
        ${panel('panel-related', 'Related Models', this._renderExtensionSlot('sections:related-models', this._renderRelatedModelsPanel(model)))}
        ${panel('panel-support', 'Supporting Files', this._renderExtensionSlot('sections:supporting-files', this._renderSupportingFilesPanel(model)))}
        ${panel('panel-contribution', 'Source & Contribution', this._renderExtensionSlot('sections:contribution-lifecycle', this._renderContributionPanel(model)))}
        ${panel('panel-publication', 'Publication Pipeline', '<div class="queue-row"><strong>Extension host for #1495</strong><div class="detail">Mount publication pipeline workflow here.</div></div>')}
      </section>
    `;
  }

  _renderQueueStatusPanel() {
    const queued = Array.isArray(this._modelDetail.queued_items) ? this._modelDetail.queued_items : [];
    const addToQueueAction = '<div style="display:flex;justify-content:flex-end;margin-bottom:8px;"><button class="action-button" type="button" data-action="queue-add">Add To Queue</button></div>';
    if (!queued.length) {
      return addToQueueAction + '<div class="queue-list"><article class="queue-row"><strong>No queued prints</strong><div class="detail">When this model is added to the print queue, its entries will appear here.</div></article></div>';
    }
    const stateLabel = (s) => {
      const labels = { backlog: 'Backlog', up_next: 'Up Next', preparing: 'Preparing', ready: 'Ready', in_progress: 'In Progress', blocked: 'Blocked', done: 'Done' };
      return labels[s] || s;
    };
    const STATE_PALETTE = { backlog: '#7a6a57', up_next: '#a07cff', preparing: '#ff9a3c', ready: '#e6d84a', in_progress: '#3aa9ff', blocked: '#ff6b6b', done: '#4fcf75' };
    const stateBadge = (s) => {
      const c = STATE_PALETTE[s] || '#9eacba';
      return `<span style="display:inline-flex;align-items:center;padding:3px 10px;border-radius:999px;background:color-mix(in srgb,${c} 14%,transparent);color:${c};border:1px solid color-mix(in srgb,${c} 50%,transparent);font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:0.05em;vertical-align:middle;">${this._escapeHtml(stateLabel(s))}</span>`;
    };
    const plateBadge = (s) => {
      const isDone = s === 'done';
      const c = isDone ? (STATE_PALETTE.done) : (STATE_PALETTE.in_progress);
      const label = isDone ? 'Done' : 'Pending';
      return `<span style="display:inline-flex;align-items:center;justify-content:center;padding:3px 8px;border-radius:999px;border:1px solid color-mix(in srgb,${c} 38%,transparent);background:color-mix(in srgb,${c} 16%,transparent);color:${c};font-size:10px;font-weight:700;text-transform:uppercase;">${label}</span>`;
    };
    const rows = queued.map(entry => {
      const summary = entry.summary || {};
      const files = Array.isArray(entry.files) ? entry.files : [];
      const progressParts = [];
      if (summary.done_plate_count != null && summary.plate_count != null) {
        progressParts.push(`${summary.done_plate_count}/${summary.plate_count} plates done`);
      }
      if (entry.copies_requested > 1) {
        progressParts.push(`${entry.copies_completed || 0}/${entry.copies_requested} copies`);
      }
      if (entry.duration_bucket && entry.duration_bucket !== 'unknown') {
        progressParts.push(entry.duration_bucket);
      }
      const progressLine = progressParts.length ? `<div class="detail">${this._escapeHtml(progressParts.join(' · '))}</div>` : '';
      const notesLine = entry.queue_notes ? `<div class="detail" style="font-style:italic;">${this._escapeHtml(entry.queue_notes)}</div>` : '';
      const blockedLine = entry.state === 'blocked' && entry.blocked_reason ? `<div class="detail" style="color:#f44336;">Blocked: ${this._escapeHtml(entry.blocked_reason)}</div>` : '';

      const fileRows = files.map(f => {
        const plates = Array.isArray(f.plates) ? f.plates : [];
        const plateItems = plates.map(p => {
          const name = p.plate_name || p.plate_key || 'Plate';
          return `<div style="display:flex;align-items:center;gap:5px;">${plateBadge(p.state)} <span style="font-size:11px;">${this._escapeHtml(name)}</span></div>`;
        }).join('');
        return `
          <div style="margin-top:6px;padding:6px 8px;background:var(--primary-background-color);border-radius:7px;">
            <div style="font-size:11px;font-weight:600;margin-bottom:4px;">${this._escapeHtml(f.file_name || 'File')}</div>
            ${plates.length ? `<div style="display:flex;flex-wrap:wrap;gap:4px;">${plateItems}</div>` : '<div class="detail">No plates</div>'}
          </div>
        `;
      }).join('');

      return `
        <article class="queue-row">
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
            <strong style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${this._escapeHtml(entry.title || 'Queue Entry')}</strong>
            ${stateBadge(entry.state)}
          </div>
          ${progressLine}
          ${blockedLine}
          ${notesLine}
          ${fileRows}
        </article>
      `;
    });
    return `${addToQueueAction}<div class="queue-list">${rows.join('')}</div>`;
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
    const NON_SUPPORT_ROLES = new Set(['primary']);
    const MODEL_TYPES = new Set(['3mf', 'stl', 'obj', 'step', 'stp', 'gcode', 'zip']);
    const files = (Array.isArray(model.files) ? model.files : []).filter(f => {
      const role = String(f.asset_role || '').toLowerCase();
      const type = String(f.asset_type || '').toLowerCase();
      return !NON_SUPPORT_ROLES.has(role) && !MODEL_TYPES.has(type);
    });
    const browserEntries = files.map((file) => {
      const folderPath = this._supportingFolderPath(file);
      return {
        file,
        folderPath,
      };
    });
    const supportViewMode = this._supportViewMode === 'folders' ? 'folders' : 'files';
    const supportTypeFilter = this._supportTypeFilter === 'images' || this._supportTypeFilter === 'docs' || this._supportTypeFilter === 'other'
      ? this._supportTypeFilter
      : 'all';
    const supportThumbSize = this._supportThumbSize === 'small' || this._supportThumbSize === 'large'
      ? this._supportThumbSize
      : 'medium';
    const counts = { all: browserEntries.length, images: 0, docs: 0, other: 0 };
    browserEntries.forEach((entry) => {
      const type = this._supportingEntryType(entry.file);
      counts[type] = (counts[type] || 0) + 1;
    });
    const uploadToolbar = `
      <div class="support-toolbar">
        <div class="support-toolbar-main">
          <button class="action-button" id="btn-add-supporting-file">
            <ha-icon icon="mdi:plus" style="--mdc-icon-size: 16px; vertical-align: middle;"></ha-icon> Add File
          </button>
          <div class="support-toggle-wrap">
            <div class="support-segmented" role="group" aria-label="Supporting files view mode">
              <button type="button" data-action="support-set-view" data-view="files" class="${supportViewMode === 'files' ? 'active' : ''}">Files</button>
              <button type="button" data-action="support-set-view" data-view="folders" class="${supportViewMode === 'folders' ? 'active' : ''}">Folders</button>
            </div>
            <div class="support-segmented" role="group" aria-label="Supporting files preview size">
              <button type="button" data-action="support-set-thumb-size" data-size="small" class="${supportThumbSize === 'small' ? 'active' : ''}">Small</button>
              <button type="button" data-action="support-set-thumb-size" data-size="medium" class="${supportThumbSize === 'medium' ? 'active' : ''}">Medium</button>
              <button type="button" data-action="support-set-thumb-size" data-size="large" class="${supportThumbSize === 'large' ? 'active' : ''}">Large</button>
            </div>
          </div>
        </div>
        <div class="support-type-chips" role="group" aria-label="Supporting files filter">
          <button type="button" data-action="support-set-type-filter" data-type="all" class="cat-all ${supportTypeFilter === 'all' ? 'active' : ''}">All <span class="ct">· ${counts.all}</span></button>
          <button type="button" data-action="support-set-type-filter" data-type="images" class="cat-images ${supportTypeFilter === 'images' ? 'active' : ''}"><ha-icon icon="mdi:image-multiple-outline" aria-hidden="true"></ha-icon>Images <span class="ct">· ${counts.images}</span></button>
          <button type="button" data-action="support-set-type-filter" data-type="docs" class="cat-docs ${supportTypeFilter === 'docs' ? 'active' : ''}"><ha-icon icon="mdi:file-document-outline" aria-hidden="true"></ha-icon>Docs <span class="ct">· ${counts.docs}</span></button>
          <button type="button" data-action="support-set-type-filter" data-type="other" class="cat-other ${supportTypeFilter === 'other' ? 'active' : ''}"><ha-icon icon="mdi:file-outline" aria-hidden="true"></ha-icon>Other <span class="ct">· ${counts.other}</span></button>
        </div>
      </div>
    `;

    if (!browserEntries.length) {
      this._supportRenderedImageItems = [];
      return `${uploadToolbar}<div class="support-list"><article class="support"><strong>No supporting files</strong><div class="detail">Documentation and references appear here.</div></article></div>`;
    }

    let bodyHtml = '';
    if (supportViewMode === 'folders') {
      bodyHtml = this._renderSupportingFoldersView(browserEntries, supportTypeFilter);
    } else {
      const sortedEntries = browserEntries
        .filter((entry) => this._supportingEntryMatchesFilter(entry.file, supportTypeFilter))
        .slice()
        .sort((a, b) => {
          const pathA = String(a.folderPath || '').toLowerCase();
          const pathB = String(b.folderPath || '').toLowerCase();
          if (pathA !== pathB) {
            return pathA < pathB ? -1 : 1;
          }
          const nameA = this._supportingFileName(a.file).toLowerCase();
          const nameB = this._supportingFileName(b.file).toLowerCase();
          return nameA < nameB ? -1 : (nameA > nameB ? 1 : 0);
        });
      this._supportRenderedImageItems = sortedEntries
        .filter((entry) => this._supportingEntryType(entry.file) === 'images')
        .map((entry) => ({
          fileId: this._supportingFileId(entry.file),
          url: this._supportingPreviewUrl(entry.file) || this._supportingPrimaryUrl(entry.file),
          name: this._supportingFileName(entry.file),
        }))
        .filter((entry) => Boolean(entry.fileId && entry.url));
      bodyHtml = sortedEntries.length
        ? `<div class="support-rows">${sortedEntries.map((entry) => this._renderSupportingFileRow(entry.file, entry.folderPath)).join('')}</div>`
        : '<div class="support-empty">No files match this type filter.</div>';
    }

    return `${uploadToolbar}<div class="support-browser" data-thumb="${supportThumbSize}">${bodyHtml}</div>`;
  }

  _supportingFileId(file) {
    return String(file && (file.asset_id || file.file_id || file.id || '') || '').trim();
  }

  _supportingFileName(file) {
    return String(file && (file.filename || file.asset_filename || file.name || file.id) || 'Support file');
  }

  _supportingFileExtension(file) {
    const filename = this._supportingFileName(file);
    const dotIndex = filename.lastIndexOf('.');
    if (dotIndex < 0 || dotIndex === filename.length - 1) {
      return '';
    }
    return filename.slice(dotIndex + 1).toLowerCase();
  }

  _supportingFolderPath(file) {
    const filename = this._supportingFileName(file);
    const rawPath = String(file && (file.storage_path || file.source_path_canonical || file.source_path_raw || '') || '').trim().replace(/\\/g, '/');
    if (!rawPath) {
      return '';
    }

    const marker = '/supporting_files/';
    const markerIndex = rawPath.toLowerCase().indexOf(marker);
    if (markerIndex >= 0) {
      const tail = rawPath.slice(markerIndex + marker.length);
      const cut = tail.lastIndexOf('/');
      return cut > 0 ? tail.slice(0, cut) : '';
    }

    if (filename && rawPath.toLowerCase().endsWith('/' + filename.toLowerCase())) {
      const parentPath = rawPath.slice(0, rawPath.length - filename.length - 1);
      const parentBits = parentPath.split('/').filter(Boolean);
      if (parentBits.length <= 1) {
        return '';
      }
      return parentBits.slice(Math.max(0, parentBits.length - 2)).join('/');
    }

    return '';
  }

  _supportingPreviewUrl(file) {
    const ext = this._supportingFileExtension(file);
    const isImageExt = /^(avif|bmp|gif|ico|jpe?g|png|svg|tiff?|webp)$/i.test(ext);
    const candidate = String(
      file && (file.thumbnail_lazy_url || file.thumbnail_url || file.image_url || file.preview_url || (isImageExt ? file.download_url : '')) || ''
    ).trim();
    if (!candidate) {
      return '';
    }
    return this._normalizeModelApiUrl(candidate);
  }

  _supportingPrimaryUrl(file) {
    const candidate = String(file && (file.download_url || file.preview_url || file.image_url || file.thumbnail_url || '') || '').trim();
    if (!candidate) {
      return '';
    }
    return this._normalizeModelApiUrl(candidate);
  }

  _supportingEntryType(file) {
    const ext = this._supportingFileExtension(file);
    if (/^(avif|bmp|gif|ico|jpe?g|png|svg|tiff?|webp)$/i.test(ext)) {
      return 'images';
    }
    if (/^(pdf|txt|md|markdown|rtf|csv|json|ya?ml|xml|log|ini|cfg|toml|doc|docx|odt)$/i.test(ext)) {
      return 'docs';
    }
    return 'other';
  }

  _supportingEntryMatchesFilter(file, filter) {
    const active = String(filter || 'all').toLowerCase();
    if (active === 'all') {
      return true;
    }
    return this._supportingEntryType(file) === active;
  }

  _supportingIsBrowserOpenable(file) {
    const ext = this._supportingFileExtension(file);
    return /^(avif|bmp|gif|ico|jpe?g|png|svg|tiff?|webp|pdf|txt|md|markdown|csv|json|ya?ml|xml|log|ini|cfg|toml|html?|htm)$/i.test(ext);
  }

  _supportingPathLabel(folderPath) {
    const normalized = String(folderPath || '').trim();
    return normalized ? `/${normalized}/` : '/';
  }

  _supportingSizeLabel(bytes) {
    const value = Number(bytes);
    if (!Number.isFinite(value) || value <= 0) {
      return '';
    }
    const kb = value / 1024;
    if (kb < 1024) {
      return `${Math.max(1, Math.round(kb))} KB`;
    }
    const mb = kb / 1024;
    return `${mb.toFixed(mb >= 10 ? 0 : 1)} MB`;
  }

  _renderSupportingFileRow(file, folderPath) {
    const fileId = this._supportingFileId(file);
    const filenameRaw = this._supportingFileName(file);
    const filename = this._escapeHtml(filenameRaw);
    const previewUrl = this._supportingPreviewUrl(file);
    const primaryUrl = this._supportingPrimaryUrl(file);
    const extension = this._supportingFileExtension(file);
    const extensionLabel = this._escapeHtml((extension || 'file').toUpperCase().slice(0, 8));
    const entryType = this._supportingEntryType(file);
    const placeholderIconByType = {
      images: 'mdi:image-outline',
      docs: 'mdi:file-document-outline',
      other: 'mdi:file-outline',
    };
    const placeholderIcon = placeholderIconByType[entryType] || 'mdi:file-outline';
    const imageIndex = this._supportRenderedImageItems.findIndex((entry) => entry.fileId === fileId);
    const sizeLabel = this._supportingSizeLabel(file && file.file_size_bytes);
    const sizeDisplay = this._escapeHtml(sizeLabel || '--');
    const previewAction = entryType === 'images' && imageIndex >= 0
      ? `<button type="button" class="support-action" data-action="support-preview-image" data-image-index="${imageIndex}">Preview</button>`
      : '';
    const openAction = this._supportingIsBrowserOpenable(file) && primaryUrl
      ? `<button type="button" class="support-action" data-action="support-open-file" data-file-id="${this._escapeHtml(fileId)}">Open</button>`
      : '';
    const downloadAction = primaryUrl
      ? `<button type="button" class="support-action" data-action="support-download-file" data-file-id="${this._escapeHtml(fileId)}">Download</button>`
      : '';
    return `
      <article class="support-file-row">
        <div class="support-thumb ${previewUrl ? 'has-image' : ''}">
          ${previewUrl
            ? `<div class="support-thumb-placeholder support-thumb-placeholder-${entryType}"><div class="support-thumb-shimmer"></div><ha-icon icon="${this._escapeHtml(placeholderIcon)}" aria-hidden="true"></ha-icon></div><img data-thumbnail-lazy-url="${this._escapeHtml(previewUrl)}" alt="${filename}" loading="lazy" onload="const p=this.parentElement;if(p){p.classList.add('thumb-ready');p.classList.remove('thumb-failed');}this.style.display='block';" onerror="const p=this.parentElement;if(p){p.classList.add('thumb-failed');p.classList.remove('thumb-ready');}this.style.display='none';">`
            : `<span class="support-ext">${extensionLabel}</span>`}
        </div>
        <div class="support-main">
          <div class="support-name">${filename}</div>
          <div class="support-subpath">${this._escapeHtml(this._supportingPathLabel(folderPath))}</div>
        </div>
        <div class="support-size">${sizeDisplay}</div>
        <div class="support-actions">${previewAction}${openAction}${downloadAction}</div>
      </article>
    `;
  }

  _renderSupportingFoldersView(entries, typeFilter) {
    const currentPath = String(this._supportFolderPath || '');
    const folderMap = {};
    const filesAtPath = [];
    const prefix = currentPath ? `${currentPath}/` : '';

    const filteredEntries = entries.filter((entry) => this._supportingEntryMatchesFilter(entry.file, typeFilter));

    this._supportRenderedImageItems = filteredEntries
      .filter((entry) => this._supportingEntryType(entry.file) === 'images')
      .filter((entry) => {
        const folderPath = String(entry.folderPath || '');
        return folderPath === currentPath;
      })
      .map((entry) => ({
        fileId: this._supportingFileId(entry.file),
        url: this._supportingPreviewUrl(entry.file) || this._supportingPrimaryUrl(entry.file),
        name: this._supportingFileName(entry.file),
      }))
      .filter((entry) => Boolean(entry.fileId && entry.url));

    filteredEntries.forEach((entry) => {
      const folderPath = String(entry.folderPath || '');
      if (folderPath === currentPath) {
        filesAtPath.push(entry);
        return;
      }
      if (currentPath && !folderPath.startsWith(prefix)) {
        return;
      }
      const relative = folderPath.slice(prefix.length);
      if (!relative) {
        return;
      }
      const parts = relative.split('/').filter(Boolean);
      if (!parts.length) {
        return;
      }
      const first = parts[0];
      const childPath = currentPath ? `${currentPath}/${first}` : first;
      if (!folderMap[first]) {
        folderMap[first] = { name: first, path: childPath, fileCount: 0 };
      }
      folderMap[first].fileCount += 1;
    });

    const folderRows = Object.keys(folderMap)
      .sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }))
      .map((name) => {
        const info = folderMap[name];
        return `
          <article class="support-folder-row" data-action="support-folder-enter" data-path="${this._escapeHtml(info.path)}">
            <div class="support-thumb"><span class="support-folder-icon">📁</span></div>
            <div class="support-main">
              <div class="support-name">${this._escapeHtml(name)}</div>
              <div class="support-subpath">${this._escapeHtml(this._supportingPathLabel(info.path))}</div>
            </div>
            <div class="support-meta">${this._escapeHtml(String(info.fileCount))} files</div>
          </article>
        `;
      }).join('');

    const fileRows = filesAtPath
      .slice()
      .sort((a, b) => this._supportingFileName(a.file).localeCompare(this._supportingFileName(b.file), undefined, { sensitivity: 'base' }))
      .map((entry) => this._renderSupportingFileRow(entry.file, entry.folderPath)).join('');

    const hasRows = Boolean(folderRows || fileRows);
    return `
      ${this._renderSupportingBreadcrumb(currentPath)}
      ${hasRows ? `<div class="support-rows">${folderRows}${fileRows}</div>` : '<div class="support-empty">This folder has no files.</div>'}
    `;
  }

  _renderSupportingBreadcrumb(currentPath) {
    const path = String(currentPath || '');
    const segments = path ? path.split('/').filter(Boolean) : [];
    const crumbs = [
      '<button class="support-breadcrumb-link" data-action="support-folder-nav" data-path="">Supporting Files</button>'
    ];
    let cursor = '';
    segments.forEach((segment, index) => {
      cursor = cursor ? `${cursor}/${segment}` : segment;
      if (index === segments.length - 1) {
        crumbs.push(`<span class="support-breadcrumb-current">${this._escapeHtml(segment)}</span>`);
      } else {
        crumbs.push(`<button class="support-breadcrumb-link" data-action="support-folder-nav" data-path="${this._escapeHtml(cursor)}">${this._escapeHtml(segment)}</button>`);
      }
    });
    return `
      <div class="support-breadcrumbs">
        <button class="support-breadcrumb-up" data-action="support-folder-up" title="Up one folder" ${path ? '' : 'disabled'}>↑</button>
        ${crumbs.join('<span>›</span>')}
      </div>
    `;
  }

  _supportingFileById(fileId) {
    const id = String(fileId || '').trim();
    if (!id || !this._modelDetail || !this._modelDetail.model) {
      return null;
    }
    const files = Array.isArray(this._modelDetail.model.files) ? this._modelDetail.model.files : [];
    return files.find((file) => this._supportingFileId(file) === id) || null;
  }

  _openUrlInNewTab(url) {
    const normalized = String(url || '').trim();
    if (!normalized) {
      return;
    }
    const win = window.open(normalized, '_blank', 'noopener,noreferrer');
    if (win) {
      win.opener = null;
    }
  }

  async _openSupportingMarkdownInNewTab(url, title) {
    const normalizedUrl = String(url || '').trim();
    if (!normalizedUrl) {
      return;
    }
    try {
      const response = await fetch(normalizedUrl, { credentials: 'same-origin' });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const markdown = await response.text();
      const body = this._renderBasicMarkdown(markdown);
      const win = window.open('', '_blank', 'noopener,noreferrer');
      if (!win) {
        this._openUrlInNewTab(normalizedUrl);
        return;
      }
      const safeTitle = this._escapeHtml(title || 'Markdown');
      win.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${safeTitle}</title><style>body{margin:0;padding:20px 24px;font:14px/1.55 "Segoe UI",Tahoma,sans-serif;background:#0b1220;color:#dbe7f5;}a{color:#7dd3fc;}pre{background:#111a2d;border:1px solid #22314f;border-radius:8px;padding:12px;overflow:auto;}code{font-family:Consolas,Monaco,monospace;}h1,h2,h3,h4{margin-top:1.2em;}blockquote{border-left:3px solid #334155;padding-left:10px;color:#93a4bf;}ul{padding-left:20px;}</style></head><body>${body}</body></html>`);
      win.document.close();
      win.opener = null;
    } catch (_error) {
      this._openUrlInNewTab(normalizedUrl);
    }
  }

  _renderBasicMarkdown(markdown) {
    const raw = String(markdown || '').replace(/\r\n/g, '\n');
    const escaped = this._escapeHtml(raw);
    const blocks = escaped.split('\n\n').map((chunk) => chunk.trim()).filter(Boolean);
    const rendered = blocks.map((chunk) => {
      if (/^#{1,6}\s/.test(chunk)) {
        const level = Math.min(6, (chunk.match(/^#+/) || ['#'])[0].length);
        const text = chunk.replace(/^#{1,6}\s*/, '');
        return `<h${level}>${text}</h${level}>`;
      }
      if (/^```/.test(chunk) && /```$/.test(chunk)) {
        return `<pre><code>${chunk.replace(/^```[\s\S]*?\n?/, '').replace(/```$/, '')}</code></pre>`;
      }
      if (/^[-*]\s+/m.test(chunk)) {
        const items = chunk.split('\n').map((line) => line.trim()).filter(Boolean).map((line) => line.replace(/^[-*]\s+/, ''));
        return `<ul>${items.map((item) => `<li>${item}</li>`).join('')}</ul>`;
      }
      return `<p>${chunk.replace(/\n/g, '<br>')}</p>`;
    }).join('');

    return rendered
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\*([^*]+)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  }

  _openSupportingFileInNewTab(fileId) {
    const file = this._supportingFileById(fileId);
    if (!file) {
      return;
    }
    const url = this._supportingPrimaryUrl(file);
    if (!url) {
      return;
    }
    const ext = this._supportingFileExtension(file);
    if (ext === 'md' || ext === 'markdown') {
      this._openSupportingMarkdownInNewTab(url, this._supportingFileName(file));
      return;
    }
    this._openUrlInNewTab(url);
  }

  async _downloadSupportingFile(fileId) {
    const file = this._supportingFileById(fileId);
    if (!file) {
      return;
    }
    const url = this._supportingPrimaryUrl(file);
    if (!url) {
      return;
    }
    const filename = this._supportingFileName(file) || 'download';
    try {
      const response = await fetch(url, { credentials: 'same-origin' });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = filename;
      anchor.rel = 'noopener noreferrer';
      anchor.style.display = 'none';
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    } catch (_error) {
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = filename;
      anchor.rel = 'noopener noreferrer';
      anchor.target = '_blank';
      anchor.style.display = 'none';
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
    }
  }

  _openSupportingImagePreview(imageIndex) {
    const idx = Number(imageIndex);
    if (!Number.isFinite(idx) || idx < 0 || idx >= this._supportRenderedImageItems.length) {
      return;
    }
    this._supportImagePreview = {
      items: this._supportRenderedImageItems.slice(),
      index: idx,
    };
    this._ensureOverlayRoot();
    this._renderSupportingImageOverlay();
    if (this._overlayRoot && !this._overlayRoot.open) {
      this._overlayRoot.showModal();
    }
    this._applyBodyScrollLock();
    document.addEventListener('keydown', this._boundKeydownHandler);
  }

  _closeSupportingImagePreview() {
    this._supportImagePreview = null;
    document.removeEventListener('keydown', this._boundKeydownHandler);
    this._restoreBodyScrollLock();
    if (this._overlayRoot && this._overlayRoot.open) {
      this._overlayRoot.close();
    }
  }

  _stepSupportingImagePreview(direction) {
    if (!this._supportImagePreview || !Array.isArray(this._supportImagePreview.items) || !this._supportImagePreview.items.length) {
      return;
    }
    const count = this._supportImagePreview.items.length;
    this._supportImagePreview.index = (this._supportImagePreview.index + direction + count) % count;
    this._renderSupportingImageOverlay();
  }

  _openSupportingPreviewImageInNewTab() {
    if (!this._supportImagePreview || !Array.isArray(this._supportImagePreview.items)) {
      return;
    }
    const idx = Math.max(0, Math.min(this._supportImagePreview.index, this._supportImagePreview.items.length - 1));
    const item = this._supportImagePreview.items[idx] || null;
    if (!item || !item.url) {
      return;
    }
    this._openUrlInNewTab(item.url);
  }

  _renderSupportingImageOverlay() {
    if (!this._overlayRoot || !this._supportImagePreview || !Array.isArray(this._supportImagePreview.items) || !this._supportImagePreview.items.length) {
      return;
    }
    const items = this._supportImagePreview.items;
    const index = Math.max(0, Math.min(this._supportImagePreview.index, items.length - 1));
    const current = items[index] || {};
    const imageUrl = String(current.url || '').trim();
    if (!imageUrl) {
      return;
    }
    const itemName = String(current.name || `Image ${index + 1}`);
    this._overlayRoot.innerHTML =
      '<style>' +
      '.support-preview-root,.support-preview-root *{box-sizing:border-box;}' +
      '.support-preview-root{position:fixed;inset:0;}' +
      '.support-preview-backdrop{position:absolute;inset:0;border:0;background:rgba(4,8,15,0.94);cursor:pointer;}' +
      '.support-preview-shell{position:relative;z-index:1;display:grid;grid-template-rows:auto minmax(0,1fr) auto;gap:14px;height:100%;padding:18px 20px;}' +
      '.support-preview-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;color:#e8f0ff;}' +
      '.support-preview-title{font:700 18px/1.3 "Segoe UI",sans-serif;}' +
      '.support-preview-sub{margin-top:5px;font:500 12px/1.4 "Segoe UI",sans-serif;color:rgba(232,240,255,0.78);}' +
      '.support-preview-actions{display:flex;gap:8px;}' +
      '.support-preview-btn{border:1px solid rgba(255,255,255,0.25);background:rgba(255,255,255,0.1);color:#fff;border-radius:999px;padding:9px 13px;font:700 12px/1 "Segoe UI",sans-serif;cursor:pointer;}' +
      '.support-preview-stage{position:relative;display:flex;align-items:center;justify-content:center;border-radius:16px;overflow:hidden;background:linear-gradient(180deg, rgba(15,23,42,0.82), rgba(2,6,23,0.98));}' +
      '.support-preview-stage img{display:block;max-width:100%;max-height:100%;width:100%;height:100%;object-fit:contain;padding:12px;}' +
      '.support-preview-nav{position:absolute;top:50%;transform:translateY(-50%);width:44px;height:44px;border-radius:999px;border:0;background:rgba(255,255,255,0.15);color:#fff;font-size:24px;cursor:pointer;}' +
      '.support-preview-nav.prev{left:10px;}.support-preview-nav.next{right:10px;}' +
      '.support-preview-strip{display:flex;gap:10px;overflow-x:auto;}' +
      '.support-preview-thumb{border:2px solid transparent;border-radius:10px;overflow:hidden;background:none;padding:0;cursor:pointer;opacity:0.85;}' +
      '.support-preview-thumb.active{border-color:#90caf9;opacity:1;}' +
      '.support-preview-thumb img{width:84px;height:84px;display:block;object-fit:cover;}' +
      '</style>' +
      '<div class="support-preview-root">' +
      '<button class="support-preview-backdrop" type="button" data-action="support-preview-close" aria-label="Close image preview"></button>' +
      '<div class="support-preview-shell" role="dialog" aria-modal="true" aria-label="Supporting file image preview">' +
      '<div class="support-preview-head">' +
      '<div><div class="support-preview-title">' + this._escapeHtml(itemName) + '</div><div class="support-preview-sub">' + (index + 1) + ' / ' + items.length + '</div></div>' +
      '<div class="support-preview-actions"><button class="support-preview-btn" type="button" data-action="support-preview-open-tab">Open in New Tab</button><button class="support-preview-btn" type="button" data-action="support-preview-close">Close</button></div>' +
      '</div>' +
      '<div class="support-preview-stage"><img src="' + this._escapeHtml(imageUrl) + '" alt="' + this._escapeHtml(itemName) + '" loading="eager">' +
      (items.length > 1 ? '<button class="support-preview-nav prev" type="button" data-action="support-preview-prev" aria-label="Previous">‹</button><button class="support-preview-nav next" type="button" data-action="support-preview-next" aria-label="Next">›</button>' : '') +
      '</div>' +
      (items.length > 1 ? '<div class="support-preview-strip">' + items.map((itemEntry, thumbIndex) => '<button class="support-preview-thumb' + (thumbIndex === index ? ' active' : '') + '" type="button" data-support-preview-index="' + thumbIndex + '"><img src="' + this._escapeHtml(itemEntry.url) + '" alt="' + this._escapeHtml(itemEntry.name || ('Image ' + (thumbIndex + 1))) + '" loading="lazy"></button>').join('') + '</div>' : '') +
      '</div></div>';
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
    const hiddenSourceMediaIds = this._hiddenMediaIdSet();
    const urlRows = source_urls.map((url, idx) => {
      const normalized = this._normalizeComparableUrl(url);
      const isImage = this._isLikelyImageUrl(url);
      const sourceMediaId = isImage ? this._sourceUrlMediaId(normalized) : '';
      const isHiddenImage = Boolean(sourceMediaId && hiddenSourceMediaIds.has(sourceMediaId));
      const rowStatus = isHiddenImage ? '<span class="source-url-status hidden">Hidden</span>' : '';
      const hoverThumb = isImage && normalized
        ? `<div class="source-url-thumb-preview" role="tooltip"><img src="${this._escapeHtml(normalized)}" alt="Source image preview" loading="lazy"></div>`
        : '';
      return `
      <div class="source-url-row ${isHiddenImage ? 'is-hidden-image' : ''}" data-url-index="${idx}">
        <div class="source-url-input-wrap">
          <input type="text" class="source-url-input" data-source-url-index="${idx}"
            value="${this._escapeHtml(url)}" placeholder="https://…" />
          ${rowStatus ? `<div class="source-url-statuses">${rowStatus}</div>` : ''}
        </div>
        <div class="source-url-open-wrap">
          <button class="url-action-btn url-open ${isImage ? 'url-open-image' : ''}" data-action="open-source-url" data-url-index="${idx}" title="${isImage ? 'Open image URL' : 'Open URL'}"
            ${url && url.startsWith('http') ? '' : 'disabled'}>${isImage ? '🖼' : '🔗'}</button>
          ${hoverThumb}
        </div>
        <button class="url-action-btn url-remove" data-action="remove-source-url" data-url-index="${idx}" title="Remove URL">✕</button>
      </div>
    `;
    }).join('');

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
      const linkedArchives = Array.isArray(this._modelDetail?.linked_archives) ? this._modelDetail.linked_archives : [];
      const linkedCount = linkedArchives.length || Number(this._modelDetail?.link_count || 0);
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
            <div class="status-badge ${linkedCount > 0 ? 'complete' : 'pending'}">
              ${linkedCount > 0 ? '✓' : '☐'}
            </div>
            <div class="item-content">
              <strong>Printed</strong>
              <div class="detail">${linkedCount > 0 ? `${linkedCount} linked archive${linkedCount !== 1 ? 's' : ''}` : 'No linked prints yet'}</div>
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
              <div class="detail">${photoCaptureCount > 0 ? `${photoCaptureCount} photo(s) available` : 'No photos captured yet'}</div>
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

    // Check if model has any 3MF files (for extract button)
    const modelFiles = Array.isArray(model.files) ? model.files : [];
    const has3mf = modelFiles.some(f => {
      const name = String(f.filename || f.name || '').toLowerCase();
      const type = String(f.file_type || f.asset_type || '').toLowerCase();
      return name.endsWith('.3mf') || type.includes('3mf');
    });

    const extract3mfButton = has3mf ? `
      <div class="extract-3mf-section">
        <button class="action-button extract-3mf-btn" data-action="extract-3mf-metadata" title="Extract source metadata from 3MF file">
          📦 Extract from 3MF
        </button>
      </div>` : '';

    return `
      ${sourcePicker}
      ${extract3mfButton}
      ${sourceUrlsEditor}
      ${checklistHtml}

      <style>
        .extract-3mf-section {
          margin-bottom: 12px;
        }
        .extract-3mf-btn {
          font-size: 12px;
          padding: 6px 12px;
          border-radius: 6px;
          border: 1px solid var(--border);
          background: var(--bg-card-alt);
          color: var(--text);
          cursor: pointer;
        }
        .extract-3mf-btn:hover { background: var(--primary-color, #6edacb); color: #fff; }
        .extract-3mf-btn:disabled { opacity: 0.5; cursor: default; }
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
          color: var(--text-secondary);
        }
        .source-select {
          padding: 6px 8px;
          border-radius: 6px;
          border: 1px solid var(--border);
          background: var(--bg-card-alt);
          color: var(--text);
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
          position: relative;
        }
        .source-url-input-wrap {
          position: relative;
          width: 100%;
          min-width: 0;
        }
        .source-url-input {
          width: 100%;
          padding: 6px 8px;
          border-radius: 6px;
          border: 1px solid var(--divider-color);
          background: var(--secondary-background-color);
          color: var(--primary-text-color);
          font-size: 13px;
          min-width: 0;
          box-sizing: border-box;
        }
        .source-url-statuses {
          position: absolute;
          right: 8px;
          top: 50%;
          transform: translateY(-50%);
          display: inline-flex;
          gap: 4px;
          pointer-events: none;
        }
        .source-url-status {
          font-size: 10px;
          line-height: 1;
          padding: 3px 6px;
          border-radius: 999px;
          border: 1px solid var(--divider-color);
          background: rgba(148, 163, 184, 0.15);
          color: var(--secondary-text-color);
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.03em;
        }
        .source-url-status.hidden {
          border-color: rgba(239, 68, 68, 0.85);
          background: rgba(239, 68, 68, 0.28);
          color: rgb(255, 228, 228);
          font-weight: 800;
        }
        .source-url-row.is-hidden-image {
          background: rgba(239, 68, 68, 0.14);
          border: 2px solid rgba(239, 68, 68, 0.65);
          border-left: 5px solid rgba(239, 68, 68, 0.95);
          border-radius: 8px;
          padding: 4px;
          box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.05);
        }
        .source-url-row.is-hidden-image .source-url-input {
          border-color: rgba(239, 68, 68, 0.75);
          background: rgba(44, 12, 12, 0.55);
        }
        .source-url-row.is-hidden-image .url-action-btn {
          border-color: rgba(239, 68, 68, 0.65);
        }
        .source-url-open-wrap {
          position: relative;
          display: inline-flex;
        }
        .source-url-thumb-preview {
          position: absolute;
          right: calc(100% + 8px);
          top: calc(100% + 6px);
          z-index: 12;
          width: 168px;
          height: 168px;
          border-radius: 10px;
          border: 1px solid rgba(148, 163, 184, 0.4);
          background: rgba(2, 6, 23, 0.96);
          box-shadow: 0 10px 28px rgba(2, 6, 23, 0.45);
          padding: 4px;
          display: none;
          pointer-events: none;
        }
        .source-url-thumb-preview img {
          width: 100%;
          height: 100%;
          object-fit: cover;
          border-radius: 7px;
          display: block;
        }
        .source-url-open-wrap:hover .source-url-thumb-preview,
        .source-url-open-wrap:focus-within .source-url-thumb-preview {
          display: block;
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
    const tags = Array.isArray(model.keywords) ? model.keywords : [];
    const isIdea = this._getEntityType(model) === 'idea';
    const selectedCollections = this._selectedCollectionMemberships();
    const selectedProjects = this._selectedProjectMemberships();
    const staleCollectionIds = Array.isArray(this._collectionMembershipStaleIds) ? this._collectionMembershipStaleIds : [];
    const staleProjectIds = Array.isArray(this._projectMembershipStaleIds) ? this._projectMembershipStaleIds : [];
    const staleCollectionSet = new Set(staleCollectionIds);
    const staleProjectSet = new Set(staleProjectIds);
    const collectionLabels = this._modelMetaEditOpen
      ? selectedCollections.map((item) => item.path || item.name || item.collection_id)
      : (Array.isArray(model.collection_names) ? model.collection_names : []);
    const staticProjectMemberships = this._normalizeProjectRows(Array.isArray(model.projects) ? model.projects : []);
    const projectRows = this._modelMetaEditOpen ? selectedProjects : staticProjectMemberships;

    return `
      <section class="card" data-slot="hero-right:summary">
        <div class="h">
          <span>Summary</span>
          <span>
            ${this._modelMetaEditOpen
              ? `<button class="action-button ghost" data-action="model-edit-cancel" ${this._modelMetaSaving || this._modelMetaLoading ? 'disabled' : ''}>Cancel</button>
                 <button class="action-button" data-action="model-edit-save" ${this._modelMetaSaving || this._modelMetaLoading ? 'disabled' : ''}>${this._modelMetaSaving ? 'Saving...' : 'Save'}</button>`
              : '<button class="action-button ghost" data-action="model-edit-start">Edit</button>'}
          </span>
        </div>
        ${this._renderExtensionSlot('hero-right:summary', `
          <div class="summary">
            ${this._modelMetaEditOpen ? this._renderCollectionEditFeedback() : ''}
            ${this._modelMetaEditOpen ? this._renderProjectEditFeedback() : ''}
            ${this._modelMetaEditOpen ? `
              <div class="summary-edit-grid">
                <label>
                  <span>${isIdea ? 'Idea Name' : 'Model Name'}</span>
                  <input id="model-meta-name" class="summary-input" type="text" maxlength="255" value="${this._escapeHtml(String(this._modelMetaDraft.modelName || ''))}">
                </label>
                <label>
                  <span>Description</span>
                  <textarea id="model-meta-description" class="summary-textarea" maxlength="5000">${this._escapeHtml(String(this._modelMetaDraft.description || ''))}</textarea>
                </label>
              </div>
            ` : `
              <div class="name">${this._escapeHtml(String(model.name || 'Untitled Model'))}</div>
              ${model.description ? `<div class="desc">${this._escapeHtml(String(model.description || ''))}</div>` : ''}
            `}
            <div class="chip-group">
              <span class="label">Tags</span>
              ${tags.length ? tags.map(t => `<span class="tag-chip">${this._escapeHtml(t)} <span class="x" data-action="remove-tag" data-tag="${this._escapeHtml(t)}" title="Remove tag">✕</span></span>`).join('') : ''}
              <div class="picker-wrap">
                <button class="add-chip" data-action="toggle-tag-picker" title="Add tag">+ Tag</button>
                ${this._tagPickerOpen ? this._renderTagPicker(tags) : ''}
              </div>
            </div>
            <div class="chip-group stack">
              <span class="label">Collections</span>
              <div class="chip-row">
                ${collectionLabels.length
                  ? collectionLabels.map((label, index) => {
                      const membership = selectedCollections[index] || null;
                      const collectionId = String(membership && membership.collection_id || '').trim().toLowerCase();
                      const isStaleMembership = this._modelMetaEditOpen && staleCollectionSet.has(collectionId);
                      return `<span class="tag-chip${isStaleMembership ? ' stale' : ''}">${this._escapeHtml(String(label || ''))}${isStaleMembership ? ' <span class="stale-note">Missing</span>' : ''}${this._modelMetaEditOpen && membership ? ` <span class="x" data-action="remove-collection" data-collection-id="${this._escapeHtml(String(membership.collection_id || ''))}" title="Remove collection">✕</span>` : ''}</span>`;
                    }).join('')
                  : '<span class="summary-empty">No Collection</span>'}
                ${this._modelMetaEditOpen ? `<div class="collection-picker-wrap picker-wrap">
                  <button class="add-chip" data-action="toggle-collection-picker" title="Add collection">+ Collection</button>
                  ${this._collectionPickerOpen ? this._renderCollectionPicker(selectedCollections) : ''}
                </div>` : ''}
              </div>
              ${this._modelMetaEditOpen && staleCollectionIds.length ? `<div class="meta-warning">${this._escapeHtml(staleCollectionIds.length === 1 ? 'One selected collection no longer exists. Refresh the collection list or remove the stale chip before saving.' : `${staleCollectionIds.length} selected collections no longer exist. Refresh the collection list or remove the stale chips before saving.`)}</div><div class="meta-warning-actions"><button class="action-button ghost small" data-action="refresh-collections" ${this._modelMetaLoading || this._modelMetaSaving ? 'disabled' : ''}>Refresh collections</button></div>` : ''}
            </div>
            <div class="chip-group stack">
              <span class="label">Projects</span>
              <div class="chip-row">
                ${projectRows.length
                  ? projectRows.map((membership) => {
                      const projectId = String(membership && membership.project_id || '').trim();
                      const isStaleMembership = this._modelMetaEditOpen && staleProjectSet.has(projectId);
                      const chipLabel = this._escapeHtml(this._projectMembershipLabel(membership));
                      if (!this._modelMetaEditOpen && !isStaleMembership && projectId) {
                        return `<button class="tag-chip tag-chip-button" type="button" data-action="focus-project" data-project-id="${this._escapeHtml(projectId)}" title="Open project">${chipLabel}</button>`;
                      }
                      return `<span class="tag-chip${isStaleMembership ? ' stale' : ''}">${chipLabel}${isStaleMembership ? ' <span class="stale-note">Missing</span>' : ''}${this._modelMetaEditOpen ? ` <span class="x" data-action="remove-project" data-project-id="${this._escapeHtml(projectId)}" title="Remove project">✕</span>` : ''}</span>`;
                    }).join('')
                  : '<span class="summary-empty">No Project</span>'}
                ${this._modelMetaEditOpen ? `<div class="project-picker-wrap picker-wrap">
                  <button class="add-chip" data-action="toggle-project-picker" title="Add project">+ Project</button>
                  ${this._projectPickerOpen ? this._renderProjectPicker(selectedProjects) : ''}
                </div>` : ''}
              </div>
              ${this._modelMetaEditOpen && staleProjectIds.length ? `<div class="meta-warning">${this._escapeHtml(staleProjectIds.length === 1 ? 'One selected project no longer exists. Refresh the project list or remove the stale chip before saving.' : `${staleProjectIds.length} selected projects no longer exist. Refresh the project list or remove the stale chips before saving.`)}</div><div class="meta-warning-actions"><button class="action-button ghost small" data-action="refresh-projects" ${this._modelMetaLoading || this._modelMetaSaving ? 'disabled' : ''}>Refresh projects</button></div>` : ''}
            </div>
            ${this._modelMetaLoading ? '<div class="meta">Loading collection and project memberships…</div>' : ''}
            <div class="meta">${this._getEntityType(model) === 'idea' ? 'Idea entry: no model files or print history required yet.' : `Print history links: ${linkedCount} linked, ${candidateCount} candidates`}</div>
          </div>
        `)}
      </section>
    `;
  }

  _getModelPrintEstimates(model) {
    const detailModel = this._modelDetail && this._modelDetail.model && typeof this._modelDetail.model === 'object'
      ? this._modelDetail.model
      : {};
    const detailFields = detailModel.custom_fields && typeof detailModel.custom_fields === 'object'
      ? detailModel.custom_fields
      : {};
    const modelFields = model && model.custom_fields && typeof model.custom_fields === 'object'
      ? model.custom_fields
      : {};
    const rawEstimates = Array.isArray(detailFields.print_estimates)
      ? detailFields.print_estimates
      : (Array.isArray(modelFields.print_estimates) ? modelFields.print_estimates : []);
    return rawEstimates.filter((item) => item && typeof item === 'object');
  }

  _printEstimateMinutes(value) {
    if (typeof value === 'number' && Number.isFinite(value) && value > 0) {
      return value > 1000 ? Math.round(value / 60) : Math.round(value);
    }
    if (!value || typeof value !== 'object') {
      return null;
    }
    if (typeof value.printTimeMinutes === 'number' && Number.isFinite(value.printTimeMinutes) && value.printTimeMinutes > 0) {
      return Math.round(value.printTimeMinutes);
    }
    if (typeof value.minutes === 'number' && Number.isFinite(value.minutes) && value.minutes > 0) {
      return Math.round(value.minutes);
    }
    if (typeof value.printTimeSeconds === 'number' && Number.isFinite(value.printTimeSeconds) && value.printTimeSeconds > 0) {
      return Math.round(value.printTimeSeconds / 60);
    }
    if (typeof value.seconds === 'number' && Number.isFinite(value.seconds) && value.seconds > 0) {
      return Math.round(value.seconds / 60);
    }
    return null;
  }

  _formatPrintEstimate(value) {
    const minutes = this._printEstimateMinutes(value);
    if (!minutes) {
      return 'Unknown';
    }
    const hours = Math.floor(minutes / 60);
    const remainder = minutes % 60;
    if (hours <= 0) {
      return `${minutes}m`;
    }
    if (remainder <= 0) {
      return `${hours}h`;
    }
    return `${hours}h ${remainder}m`;
  }

  _formatWeightGrams(value) {
    const grams = Number(value);
    if (!Number.isFinite(grams) || grams <= 0) {
      return '';
    }
    const rounded = Math.round(grams * 10) / 10;
    return `${Number.isInteger(rounded) ? rounded.toFixed(0) : rounded.toFixed(1)}g`;
  }

  _renderPrintEstimateLine(estimate) {
    const title = String(estimate.title || estimate.profile_id || estimate.instance_id || 'Profile').trim();
    const plateEstimates = Array.isArray(estimate.plate_estimates) ? estimate.plate_estimates : [];
    const plateSummary = plateEstimates.length
      ? ` · Plates: ${plateEstimates.map((plate) => {
          const plateLabel = String(plate && plate.plate_id || '').trim();
          const plateDuration = this._formatPrintEstimate(plate && plate.estimated_print_time_seconds);
          return plateLabel ? `${plateLabel} ${plateDuration}` : plateDuration;
        }).join(', ')}`
      : '';
    return `<div class="meta"><strong>${this._escapeHtml(title)}</strong>: ${this._escapeHtml(this._formatPrintEstimate(estimate.estimated_print_time_seconds))}${this._escapeHtml(plateSummary)}</div>`;
  }

  _normalizePlateKey(value, fallbackIndex = 0) {
    const normalized = String(value || '').trim();
    if (normalized) {
      return normalized;
    }
    return String(fallbackIndex + 1);
  }

  _fileEstimateMatchScore(file, estimate) {
    const filename = String(file && (file.filename || file.asset_filename || '') || '').trim().toLowerCase();
    const title = String(estimate && estimate.title || '').trim().toLowerCase();
    const instanceId = String(estimate && estimate.instance_id || '').trim();
    const profileId = String(estimate && estimate.profile_id || '').trim();
    let score = 0;
    if (instanceId && filename.includes(instanceId)) {
      score += 100;
    }
    if (profileId && filename.includes(profileId)) {
      score += 20;
    }
    if (title) {
      const titleSlug = title.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
      if (titleSlug && filename.includes(titleSlug)) {
        score += 40;
      }
    }
    return score;
  }

  _estimateForModelFile(file, estimates) {
    const rows = Array.isArray(estimates) ? estimates : [];
    let bestEstimate = null;
    let bestScore = 0;
    rows.forEach((estimate) => {
      const score = this._fileEstimateMatchScore(file, estimate);
      if (score > bestScore) {
        bestEstimate = estimate;
        bestScore = score;
      }
    });
    return bestEstimate;
  }

  _plateEstimateMap(estimate) {
    const map = {};
    const rows = Array.isArray(estimate && estimate.plate_estimates) ? estimate.plate_estimates : [];
    rows.forEach((plate, index) => {
      const key = this._normalizePlateKey(plate && plate.plate_id, index);
      map[key] = plate;
    });
    return map;
  }

  _plateColorsMetaHtml(plate) {
    const colors = Array.isArray(plate && plate.filament_colors) ? plate.filament_colors.filter(Boolean) : [];
    if (!colors.length) {
      return '';
    }
    return `<span class="file-plate-color-chip">${colors.map((color) => {
      const safeColor = this._escapeHtml(String(color));
      return `<span class="plate-color-swatch" style="background:${safeColor};" title="${safeColor}"></span>`;
    }).join('')}<span class="color-count-label">${this._escapeHtml(String(colors.length))} ${colors.length === 1 ? 'color' : 'colors'}</span></span>`;
  }

  _plateThumbnailUrl(file, plate, index) {
    if (!this._modelRef || !this._modelSidecarUrl || !this._is3mfModelFile(file)) {
      return '';
    }
    const fileId = String(file && (file.id || file.file_id) || '').trim();
    if (!fileId) {
      return '';
    }
    const plateIndex = Number(index) + 1;
    if (!Number.isFinite(plateIndex) || plateIndex <= 0) {
      return '';
    }
    const base = String(this._modelSidecarUrl || '').trim().replace(/\/$/, '');
    return `${base}/api/models/${encodeURIComponent(this._modelRef)}/files/${encodeURIComponent(fileId)}/plates/${encodeURIComponent(String(plateIndex))}/thumbnail`;
  }

  _renderPlateDetailRows(file, estimate) {
    const plates = this._getModelFilePlateDetails(file);
    if (!Array.isArray(plates)) {
      return '<div class="file-plate-loading">Loading plate details…</div>';
    }
    if (!plates.length) {
      return '<div class="file-plate-empty">No plate details available.</div>';
    }
    const estimateByPlate = this._plateEstimateMap(estimate);
    return `<div class="file-plate-list">${plates.map((plate, index) => {
      const key = this._normalizePlateKey(plate && plate.id, index);
      const matchedEstimate = estimateByPlate[key] || estimateByPlate[String(index + 1)] || null;
      const baseTitle = String(plate && (plate.name || plate.plate_name || plate.plate_key) || `Plate ${index + 1}`).trim();
      const detailTitle = String(
        plate && (plate.title || plate.plate_title)
        || matchedEstimate && matchedEstimate.title
        || ''
      ).trim();
      const title = detailTitle && detailTitle.toLowerCase() !== baseTitle.toLowerCase()
        ? `${baseTitle} - ${detailTitle}`
        : baseTitle;
      const timeLabel = matchedEstimate ? this._formatPrintEstimate(matchedEstimate.estimated_print_time_seconds) : '';
      const weightLabel = this._formatWeightGrams(plate && plate.weight_grams);
      const objectCount = Array.isArray(plate && plate.object_ids) ? plate.object_ids.length : 0;
      const thumbnailUrl = this._plateThumbnailUrl(file, plate, index);
      return `
        <div class="file-plate-row">
          <div class="file-plate-visual">
            <div class="file-plate-card${thumbnailUrl ? ' has-image' : ''}"${thumbnailUrl ? ` style="background-image:url('${this._escapeHtml(thumbnailUrl)}');"` : ''}></div>
          </div>
          <div class="file-plate-main">
            <div class="file-plate-name">${this._escapeHtml(title)}</div>
            <div class="file-plate-meta">
              ${timeLabel ? `<span>${this._escapeHtml(timeLabel)}</span>` : ''}
              ${weightLabel ? `<span>${this._escapeHtml(weightLabel)}</span>` : ''}
              ${objectCount ? `<span>${this._escapeHtml(String(objectCount))} ${objectCount === 1 ? 'object' : 'objects'}</span>` : ''}
              ${this._plateColorsMetaHtml(plate)}
            </div>
          </div>
        </div>
      `;
    }).join('')}</div>`;
  }

  _renderModelFilesCard(model) {
    const MODEL_ROLES = new Set(['primary']);
    const MODEL_TYPES = new Set(['3mf', 'stl', 'obj', 'step', 'stp', 'gcode', 'zip']);
    const files = (Array.isArray(model.files) ? model.files : []).filter(f => {
      const role = String(f.asset_role || '').toLowerCase();
      const type = String(f.asset_type || '').toLowerCase();
      return MODEL_ROLES.has(role) || MODEL_TYPES.has(type);
    });
    this._ensureModelFilePlateCounts(files);
    this._ensureModelFilePlateDetails(files);
    const printEstimates = this._getModelPrintEstimates(model);
    const rows = files.length ? files.map(file => {
      const filename = this._escapeHtml(String(file.filename || file.asset_filename || file.id || 'file'));
      const rawName = String(file.filename || file.asset_filename || file.id || '');
      const extIdx = rawName.lastIndexOf('.');
      const ext = extIdx >= 0 ? rawName.slice(extIdx + 1).toLowerCase() : '';
      const extUpper = ext.toUpperCase() || 'FILE';
      const extClass = ext ? `x-${this._escapeHtml(ext)}` : '';
      const thumbUrl = this._normalizeModelApiUrl(String(file.thumbnail_lazy_url || file.thumbnail_url || file.preview_url || '').trim());
      const plateCount = this._getModelFilePlateCount(file);
      const fileEstimate = this._estimateForModelFile(file, printEstimates);
      const totalEstimate = fileEstimate ? this._formatPrintEstimate(fileEstimate.estimated_print_time_seconds) : '';
      const filePlateDetails = this._getModelFilePlateDetails(file);
      const totalWeight = Array.isArray(filePlateDetails)
        ? filePlateDetails.reduce((sum, plate) => sum + (Number(plate && plate.weight_grams) || 0), 0)
        : 0;
      const totalWeightLabel = this._formatWeightGrams(totalWeight);
      const sectionId = `file-${String(file.id || filename)}`;
      const isCollapsed = Object.prototype.hasOwnProperty.call(this._collapsedSections, sectionId)
        ? !!this._collapsedSections[sectionId]
        : true;
      const meta = [
        file.asset_type ? String(file.asset_type) : '',
        file.file_size_bytes ? `${Math.round(Number(file.file_size_bytes) / (1024 * 1024))} MB` : '',
        this._is3mfModelFile(file) && Number.isFinite(plateCount) && plateCount > 1 ? `${plateCount} plates` : '',
      ].filter(Boolean).join(' | ');
      const previewHtml = thumbUrl
        ? `<img class="file-preview" src="${this._escapeHtml(thumbUrl)}" alt="${filename}" loading="lazy">`
        : `<span class="file-ext-badge ${extClass}">${this._escapeHtml(extUpper)}</span>`;
      return `
        <article class="collapsible-group">
          <button class="collapse-toggle file-row-toggle" data-collapse-toggle="${this._escapeHtml(sectionId)}">
            <div class="file-row-main">${previewHtml}<div><strong>${filename}</strong><div class="detail">${this._escapeHtml(meta || 'Model file')}</div></div></div>
            <div class="file-row-side">
              ${(totalEstimate || totalWeightLabel) ? `<div class="file-total-estimate"><span class="file-total-label">Total</span>${totalEstimate ? `<strong>${this._escapeHtml(totalEstimate)}</strong>` : ''}${totalWeightLabel ? `<span class="file-total-subtle">${this._escapeHtml(totalWeightLabel)}</span>` : ''}</div>` : ''}
              <div class="file-chevron">${isCollapsed ? '▸' : '▾'}</div>
            </div>
          </button>
          <div class="collapse-body file-collapse-body ${isCollapsed ? 'hidden' : ''}">
            ${this._renderPlateDetailRows(file, fileEstimate)}
          </div>
        </article>
      `;
    }).join('') : '<article class="queue-row"><strong>No files found</strong><div class="detail">Model file inventory is empty.</div></article>';

    return `
      <section class="card" data-slot="panel:files-core">
        <div class="h">
          <span>Model Files</span>
          <span>${files.length}</span>
        </div>
        <div class="files">${rows}</div>
      </section>
    `;
  }


  async _handleArchiveCandidateAction(archiveId, linkId, action) {
    if (!this._modelRef || !this._modelSidecarUrl) return;
    this._queuePopupShellScrollRestore();
    try {
      const endpoint = action === 'link' ? 'accept' : 'reject';
      const url = `${this._modelSidecarUrl}/api/archive-links/${encodeURIComponent(archiveId)}/${encodeURIComponent(linkId)}/${endpoint}`;
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      this._setArchiveCandidateSelection(archiveId, linkId, false);
      await this._loadModelDetail({ silent: true });
    } catch (e) {
      alert('Failed to update archive linkage: ' + e);
    }
  }

  async _handleUnlinkArchive(archiveId, linkId) {
    if (!this._modelRef || !this._modelSidecarUrl) return;
    if (!confirm('Unlink this archive from the model?')) return;
    try {
      const url = `${this._modelSidecarUrl}/api/archive-links/${encodeURIComponent(archiveId)}/${encodeURIComponent(linkId)}/deactivate`;
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await this._loadModelDetail({ silent: true });
    } catch (e) {
      alert('Failed to unlink archive: ' + e);
    }
  }

  _archiveCandidateSelectionKey(archiveId, linkId) {
    return String(archiveId || '').trim() + '|' + String(linkId || '').trim();
  }

  _setArchiveCandidateSelection(archiveId, linkId, selected) {
    const key = this._archiveCandidateSelectionKey(archiveId, linkId);
    if (!key || key === '|') {
      return;
    }
    if (selected) {
      this._selectedArchiveCandidates[key] = true;
    } else {
      delete this._selectedArchiveCandidates[key];
    }
  }

  _isArchiveCandidateSelected(archiveId, linkId) {
    const key = this._archiveCandidateSelectionKey(archiveId, linkId);
    return !!(key && this._selectedArchiveCandidates[key]);
  }

  _toggleArchiveCandidateSelection(archiveId, linkId) {
    this._setArchiveCandidateSelection(archiveId, linkId, !this._isArchiveCandidateSelected(archiveId, linkId));
    this._queuePopupShellScrollRestore();
    this._render();
  }

  _selectedArchiveCandidateCount() {
    return Object.keys(this._selectedArchiveCandidates).length;
  }

  _pruneArchiveCandidateSelection(candidates) {
    const allowed = {};
    const list = Array.isArray(candidates) ? candidates : [];
    for (let i = 0; i < list.length; i += 1) {
      const candidate = list[i] || {};
      const key = this._archiveCandidateSelectionKey(candidate.archive_id, candidate.id);
      if (key && key !== '|') {
        allowed[key] = true;
      }
    }
    const next = {};
    const keys = Object.keys(this._selectedArchiveCandidates);
    for (let i = 0; i < keys.length; i += 1) {
      const key = keys[i];
      if (allowed[key]) {
        next[key] = true;
      }
    }
    this._selectedArchiveCandidates = next;
  }

  _visibleCandidateEntries() {
    const allCandidates = Array.isArray(this._modelDetail && this._modelDetail.candidate_archives) ? this._modelDetail.candidate_archives : [];
    if (this._archiveLinkageFilter === 'linked') {
      return [];
    }
    return allCandidates.slice();
  }

  async _handleBulkArchiveCandidateAction(action) {
    const candidates = this._visibleCandidateEntries();
    const selected = candidates.filter(candidate => this._isArchiveCandidateSelected(candidate.archive_id, candidate.id));
    if (!selected.length) {
      return;
    }
    this._queuePopupShellScrollRestore();
    const endpoint = action === 'link' ? 'accept' : 'reject';
    let successCount = 0;
    let failureCount = 0;
    for (let i = 0; i < selected.length; i += 1) {
      const candidate = selected[i] || {};
      const archiveId = String(candidate.archive_id || '').trim();
      const linkId = String(candidate.id || '').trim();
      if (!archiveId || !linkId) {
        failureCount += 1;
        continue;
      }
      try {
        const url = `${this._modelSidecarUrl}/api/archive-links/${encodeURIComponent(archiveId)}/${encodeURIComponent(linkId)}/${endpoint}`;
        const res = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        });
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        this._setArchiveCandidateSelection(archiveId, linkId, false);
        successCount += 1;
      } catch (_error) {
        failureCount += 1;
      }
    }
    await this._loadModelDetail({ silent: true });
    if (failureCount) {
      alert(`Updated ${successCount} archive links, ${failureCount} failed.`);
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
    if (this._archiveMetaCache[id] !== undefined) return this._archiveMetaCache[id];
    if (!this._hass) return null;
    try {
      const result = await this._callServiceWithResponse('bambuddy', 'get_print_history_archive_detail', { archive_id: Number(archiveId) });
      this._archiveMetaCache[id] = result;
      return result;
    } catch {
      this._archiveMetaCache[id] = null;
      return null;
    }
  }

  async _loadArchiveMetaForLinks() {
    if (!this._hass) return;
    const linked = Array.isArray(this._modelDetail && this._modelDetail.linked_archives) ? this._modelDetail.linked_archives : [];
    const candidates = Array.isArray(this._modelDetail && this._modelDetail.candidate_archives) ? this._modelDetail.candidate_archives : [];
    const allLinks = [...linked, ...candidates];
    const ids = [...new Set(allLinks.map(l => String(l.archive_id || l.id || '')).filter(Boolean))];
    const uncached = ids.filter(id => !(id in this._archiveMetaCache));
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
    this._render();
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
      this._render();
      setTimeout(() => { this._refreshCandidatesDone = false; this._render(); }, 2000);
      return;
    } catch (e) {
      alert('Failed to refresh candidates: ' + e);
    } finally {
      this._refreshingCandidates = false;
      this._refreshCandidatesDone = false;
      this._render();
    }
  }

  _renderArchiveLinkageCard() {
    const linked = Array.isArray(this._modelDetail.linked_archives) ? this._modelDetail.linked_archives : [];
    const candidates = Array.isArray(this._modelDetail.candidate_archives) ? this._modelDetail.candidate_archives : [];
    this._pruneArchiveCandidateSelection(candidates);
    const bambuddyUrl = this._resolveBambuddyUrl();
    const linkedCount = linked.length;
    const candidateCount = candidates.length;
    const allCount = linkedCount + candidateCount;

    const sortLinkedByDate = (items) => {
      return [...items].sort((a, b) => {
        const metaA = this._archiveMetaCache[String(a.archive_id || '')];
        const metaB = this._archiveMetaCache[String(b.archive_id || '')];
        const dataA = metaA && metaA.archive ? metaA.archive : metaA;
        const dataB = metaB && metaB.archive ? metaB.archive : metaB;
        const tA = String((dataA && dataA.started_at) || a.created_at || '');
        const tB = String((dataB && dataB.started_at) || b.created_at || '');
        if (tA === tB) return 0;
        if (this._linkedArchiveSortOrder === 'asc') {
          return tA < tB ? -1 : 1;
        }
        return tA > tB ? -1 : 1;
      });
    };

    const sortedLinked = sortLinkedByDate(linked);
    const sortedCandidates = [...candidates].sort((a, b) => {
      const rank = { high: 0, medium: 1, low: 2 };
      const rA = rank[a.match_confidence] ?? 3;
      const rB = rank[b.match_confidence] ?? 3;
      return rA - rB;
    });

    const showLinked = this._archiveLinkageFilter === 'all' || this._archiveLinkageFilter === 'linked';
    const showCandidates = this._archiveLinkageFilter === 'all' || this._archiveLinkageFilter === 'candidates';
    const visibleCandidates = showCandidates ? sortedCandidates : [];
    const selectedCandidateCount = this._selectedArchiveCandidateCount();

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
      const showOutcome = status && status !== 'completed' && status !== 'printing' && status !== 'archived';
      const outcomeBadge = showOutcome
        ? ` <span style="display:inline-block;padding:1px 6px;border-radius:4px;font-size:10px;font-weight:600;background:${status === 'cancelled' ? 'rgba(255,180,60,0.22);color:#ffcc66' : 'rgba(255,80,80,0.22);color:#ff8a8a'};">${this._escapeHtml(status.charAt(0).toUpperCase() + status.slice(1))}</span>`
        : '';

      const metaLine = this._escapeHtml(metaParts.join(' · '));

      // Build match rationale line for candidates
      let matchInfoHtml = '';
      if (isCandidate) {
        const conf = archive.match_confidence || '';
        const method = (archive.match_method || '').replace(/_/g, ' ');
        let reviewNote = null;
        if (archive.review_note) {
          try { reviewNote = typeof archive.review_note === 'string' ? JSON.parse(archive.review_note) : archive.review_note; } catch { /* skip */ }
        }
        const confColors = { high: 'rgba(76,175,80,0.25);color:#8dda8d', medium: 'rgba(255,180,60,0.22);color:#ffcc66', low: 'rgba(255,80,80,0.22);color:#ff8a8a' };
        const confStyle = confColors[conf] || confColors.low;
        const confLabel = conf ? conf.charAt(0).toUpperCase() + conf.slice(1) : 'Unknown';
        const reasonSummary = reviewNote && reviewNote.summary ? reviewNote.summary : method;
        matchInfoHtml = `<div class="detail" style="margin-top:2px;"><span style="display:inline-block;padding:1px 5px;border-radius:4px;font-size:9px;font-weight:600;background:${confStyle};margin-right:4px;">${this._escapeHtml(confLabel)}</span><span style="opacity:0.7;font-size:10px;">${this._escapeHtml(reasonSummary)}</span></div>`;
      }
      const candidateSelected = isCandidate && this._isArchiveCandidateSelected(archiveId, linkId);
      const archiveTypeClass = isCandidate ? 'is-candidate' : 'is-linked';

      return `
        <article class="collapsible-group ${archiveTypeClass} ${candidateSelected ? 'candidate-selected' : ''}" data-slot="actions:per-archive">
          <div class="collapse-toggle archive-row-static">
            <div style="display:flex;align-items:center;gap:10px;">
              ${isCandidate ? `<input type="checkbox" class="candidate-checkbox" data-action="toggle-archive-candidate-select" data-archive-id="${this._escapeHtml(archiveId)}" data-link-id="${this._escapeHtml(linkId)}" ${candidateSelected ? 'checked' : ''} ${this._archiveBulkBusy ? 'disabled' : ''} aria-label="Select candidate ${title}">` : ''}
              ${thumb ? `<img src="${this._escapeHtml(thumb)}" alt="Preview" data-action="open-archive-preview" data-archive-id="${this._escapeHtml(archiveId)}" style="width:48px;height:48px;border-radius:6px;border:1px solid #334;object-fit:cover;cursor:pointer;" title="Click to enlarge">` : ''}
              <div><strong>${title}</strong>${outcomeBadge}<div class="detail">${metaLine || (meta ? '' : '<span style=\"opacity:0.5\">Loading metadata…</span>')}</div>${matchInfoHtml}</div>
            </div>
            <div class="archive-actions-right">
              <span class="state ${isCandidate ? 'candidate' : 'success'}">${isCandidate ? 'Candidate' : 'Linked'}</span>
              ${isCandidate ? `<div class="archive-action-row">
                <span class="icon-action-btn archive-skip" role="button" tabindex="0" title="Skip" data-action="archive-candidate-skip" data-archive-id="${this._escapeHtml(archiveId)}" data-link-id="${this._escapeHtml(linkId)}">
                  <svg width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="5" x2="15" y2="15"/><line x1="15" y1="5" x2="5" y2="15"/></svg>
                </span>
                <span class="icon-action-btn archive-link" role="button" tabindex="0" title="Link" data-action="archive-candidate-link" data-archive-id="${this._escapeHtml(archiveId)}" data-link-id="${this._escapeHtml(linkId)}">
                  <svg width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="5 11 9 15 15 7"/></svg>
                </span>
              </div>` : ''}
            </div>
          </div>
          ${!isCandidate ? `<div class="collapse-body">
            <button class="action-button ghost" data-action="open-archive-popup" data-archive-id="${archiveId}">Open archive</button>
            <button class="action-button ghost" data-action="pin-archive-cover" data-archive-id="${archiveId}" data-image-url="${this._escapeHtml(thumb || '')}">Pin cover</button>
            <button class="action-button ghost danger" data-action="unlink-archive" data-archive-id="${this._escapeHtml(archiveId)}" data-link-id="${this._escapeHtml(linkId)}">Unlink</button>
            ${this._renderExtensionSlot('actions:per-archive', '')}
          </div>` : this._renderExtensionSlot('actions:per-archive', '')}
        </article>
      `;
    };

    const renderFilterButton = (filter, label, count) => {
      const active = this._archiveLinkageFilter === filter;
      return `<button class="archive-filter-btn${active ? ' active' : ''}" type="button" data-action="set-archive-filter" data-archive-filter="${this._escapeHtml(filter)}">${this._escapeHtml(label)} <span>${this._escapeHtml(String(count))}</span></button>`;
    };

    const bulkToolbar = visibleCandidates.length
      ? `<div class="archive-bulk-toolbar">
          <button class="action-button ghost" type="button" data-action="select-visible-candidates" ${this._archiveBulkBusy ? 'disabled' : ''}>Select visible</button>
          <button class="action-button ghost" type="button" data-action="clear-candidate-selection" ${(selectedCandidateCount && !this._archiveBulkBusy) ? '' : 'disabled'}>Clear selection</button>
          <span class="archive-bulk-count">${selectedCandidateCount} selected</span>
          <button class="action-button" type="button" data-action="bulk-link-candidates" ${(selectedCandidateCount && !this._archiveBulkBusy) ? '' : 'disabled'}>${this._archiveBulkBusy ? 'Linking...' : 'Link selected'}</button>
          <button class="action-button ghost" type="button" data-action="bulk-skip-candidates" ${(selectedCandidateCount && !this._archiveBulkBusy) ? '' : 'disabled'}>${this._archiveBulkBusy ? 'Skipping...' : 'Skip selected'}</button>
        </div>`
      : '';

    return `
      <section class="card" data-slot="sections:archive-linkage">
        <div class="h">
          <div class="archive-header-main">
            <span>Print History</span>
            <div class="archive-filter-row header">
              ${renderFilterButton('all', 'All', allCount)}
              ${renderFilterButton('linked', 'Linked', linkedCount)}
              ${renderFilterButton('candidates', 'Candidates', candidateCount)}
            </div>
          </div>
          <div class="archive-header-tools">
            <button class="linked-sort-btn" type="button" data-action="toggle-linked-sort" title="Sort linked prints by date">
              Linked date: ${this._linkedArchiveSortOrder === 'asc' ? 'Oldest' : 'Newest'}
            </button>
            <button class="refresh-candidates-btn${this._refreshingCandidates ? ' spinning' : ''}${this._refreshCandidatesDone ? ' done' : ''}" data-action="refresh-model-candidates" title="${this._refreshingCandidates ? 'Refreshing candidates…' : this._refreshCandidatesDone ? 'Refresh complete' : 'Refresh candidate matches'}" ${this._refreshingCandidates ? 'disabled' : ''}>
            <ha-icon icon="${this._refreshCandidatesDone ? 'mdi:check-circle' : 'mdi:refresh'}"></ha-icon>
            </button>
          </div>
        </div>
        <div class="files">
          ${bulkToolbar}
          ${showLinked ? sortedLinked.map(item => renderArchive(item, false)).join('') : ''}
          ${showCandidates ? sortedCandidates.map(item => renderArchive(item, true)).join('') : ''}
          ${this._renderExtensionSlot('sections:archive-linkage', '')}
          ${!showLinked && !showCandidates ? '<article class="queue-row"><strong>No print history filter selected</strong><div class="detail">Choose All, Linked, or Candidates.</div></article>' : ''}
          ${(showLinked && !sortedLinked.length && !showCandidates) ? '<article class="queue-row"><strong>No linked archives</strong><div class="detail">Accepted print history links appear here.</div></article>' : ''}
          ${(showCandidates && !sortedCandidates.length && !showLinked) ? '<article class="queue-row"><strong>No candidate archives</strong><div class="detail">Potential matches appear here for review.</div></article>' : ''}
          ${(!linked.length && !candidates.length) ? '<article class="queue-row"><strong>No linked or candidate archives</strong><div class="detail">Archive linkage review appears here.</div></article>' : ''}
        </div>
      </section>
    `;
  }

  _ideaPlaceholderUrl(model) {
    const fields = model && model.custom_fields && typeof model.custom_fields === 'object' ? model.custom_fields : {};
    const seed = String(
      this._modelRef
      || (model && model.local_model_id)
      || (model && model.public_id)
      || fields.local_model_id
      || (model && model.name)
      || 'idea'
    ).trim();
    return pickIdeaPlaceholderUrl(seed);
  }

  _galleryItems() {
    const model = this._modelDetail && this._modelDetail.model && typeof this._modelDetail.model === 'object'
      ? this._modelDetail.model
      : {};
    const isIdea = this._getEntityType(model) === 'idea';
    const hiddenIds = this._hiddenMediaIdSet();
    const sourcePreviewUrl = this._sourcePreviewUrl();
    const photos = this._modelDetail && Array.isArray(this._modelDetail.photos) ? this._modelDetail.photos : [];
    const files = (this._modelDetail && this._modelDetail.model && Array.isArray(this._modelDetail.model.files))
      ? this._modelDetail.model.files
      : [];
    const sourceUrls = this._getSourceUrls();
    const hasNonSourcePreview = photos.some(photo => Boolean(photo && photo.is_preview))
      || files.some(file => Boolean(file && (file.is_preview || file.asset_role === 'preview')));

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

    sourceUrls.forEach((rawUrl, idx) => {
      const sourceUrl = String(rawUrl || '').trim();
      if (!sourceUrl || !this._isLikelyImageUrl(sourceUrl)) {
        return;
      }
      const normalizedUrl = this._normalizeComparableUrl(sourceUrl);
      const mediaId = this._sourceUrlMediaId(normalizedUrl);
      if (!normalizedUrl || !mediaId) {
        return;
      }
      addItem({
        media_id: mediaId,
        id: normalizedUrl,
        url: normalizedUrl,
        thumbnail_url: normalizedUrl,
        filename: `Source URL ${idx + 1}`,
        type: 'asset',
        type_label: 'Source URL',
        can_set_preview: true,
        can_hide: true,
        can_delete: false,
        is_preview: Boolean(!hasNonSourcePreview && sourcePreviewUrl && sourcePreviewUrl === normalizedUrl),
      });
    });

    if (!items.length && isIdea) {
      const placeholderUrl = this._ideaPlaceholderUrl(model);
      if (placeholderUrl) {
        addItem({
          media_id: 'idea:placeholder',
          id: 'idea-placeholder',
          url: placeholderUrl,
          thumbnail_url: placeholderUrl,
          filename: 'Idea concept placeholder',
          type: 'asset',
          type_label: 'Idea Concept',
          can_set_preview: false,
          can_hide: false,
          can_delete: false,
          is_preview: false,
        });
      }
    }

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

  async _clearEmbeddedPreviewSelections() {
    const base = String(this._modelSidecarUrl || '').trim().replace(/\/$/, '');
    const localModelId = String((this._modelDetail && this._modelDetail.local_model_id) || this._modelRef || '').trim();
    if (!base || !this._modelRef) {
      return;
    }

    const files = this._modelDetail && this._modelDetail.model && Array.isArray(this._modelDetail.model.files)
      ? this._modelDetail.model.files
      : [];
    const previewAssetIds = files
      .filter(file => file && (file.is_preview || file.asset_role === 'preview'))
      .map(file => String(file.asset_id || file.id || '').trim())
      .filter(Boolean);

    if (localModelId) {
      for (const assetId of previewAssetIds) {
        try {
          await fetch(
            `${base}/api/local/models/${encodeURIComponent(localModelId)}/assets/${encodeURIComponent(assetId)}`,
            {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ asset_role: 'supporting' }),
            }
          );
        } catch (_e) { /* best effort */ }
      }
    }

    try {
      await fetch(
        `${base}/api/models/${encodeURIComponent(this._modelRef)}/fields/${encodeURIComponent('preview_photo_id')}`,
        {
          method: 'DELETE',
        }
      );
    } catch (_e) { /* best effort */ }

    // Keep UI consistent immediately until next detail reload.
    const photos = this._modelDetail && Array.isArray(this._modelDetail.photos)
      ? this._modelDetail.photos
      : [];
    for (const photo of photos) {
      if (photo && typeof photo === 'object') {
        photo.is_preview = false;
      }
    }
    for (const file of files) {
      if (file && typeof file === 'object') {
        file.is_preview = false;
        if (String(file.asset_role || '').toLowerCase() === 'preview') {
          file.asset_role = 'supporting';
        }
      }
    }
  }

  async _handleSetHeroMediaPreview(item) {
    if (!item || !item.can_set_preview || item.is_preview) {
      return;
    }
    try {
      if (item.media_id && item.media_id.startsWith('source_url:')) {
        await this._clearEmbeddedPreviewSelections();
        await this._saveSourceField(this._heroSourcePreviewFieldKey, this._normalizeComparableUrl(item.url));
        this._heroActiveMediaIndex = 0;
        this._notifyBrowserDetailChanged();
        return;
      }
      if (item.media_id && item.media_id.startsWith('photo:')) {
        await this._saveSourceField(this._heroSourcePreviewFieldKey, null);
        await this._handleSetPhotoPreview(String(item.id || '').trim());
        this._heroActiveMediaIndex = 0;
        this._notifyBrowserDetailChanged();
        return;
      }
      if (item.asset_id) {
        await this._saveSourceField(this._heroSourcePreviewFieldKey, null);
        await this._handleSetAssetPreview(item.asset_id);
        await this._loadModelDetail({ silent: true });
        this._heroActiveMediaIndex = 0;
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

  async _handlePinArchiveCover(archiveId, imageUrl) {
    if (!this._modelRef || !this._modelSidecarUrl) {
      return;
    }
    const bambuddyUrl = this._resolveBambuddyUrl();
    if (!bambuddyUrl && !imageUrl) {
      alert('Bambuddy API URL not configured. Set input_text.bambuddy_api_base_url or add bambuddy_url to card config.');
      return;
    }

    try {
      console.log('[PIN-DEBUG] Pinning archive', archiveId, 'with imageUrl:', imageUrl);
      const url = `${this._modelSidecarUrl}/api/models/${encodeURIComponent(this._modelRef)}/preview/pin-from-archive`;
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          archive_id: Number(archiveId),
          bambuddy_url: bambuddyUrl,
          image_url: imageUrl || undefined,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      console.log('[PIN-DEBUG] Backend response:', payload);
      if (!response.ok || payload.success === false) {
        const message = payload && payload.error ? payload.error : `HTTP ${response.status}`;
        throw new Error(message);
      }
      // Reset hero active index so header shows the new pinned preview
      this._heroActiveMediaIndex = 0;
      console.log('[PIN-DEBUG] Loading detail after pin...');
      await this._loadModelDetail({ silent: true });
      console.log('[PIN-DEBUG] Detail loaded. Model detail preview_photo_id:', this._modelDetail?.preview_photo_id);
      console.log('[PIN-DEBUG] Model detail photos:', this._modelDetail?.photos);
      // Explicitly render to ensure UI updates with pinned preview
      this._render();
      this._notifyBrowserDetailChanged();
      console.log('[PIN-DEBUG] Render complete.');
    } catch (error) {
      console.error('[PIN-DEBUG] Error pinning preview:', error);
      alert(`Failed to pin archive preview: ${error}`);
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
      this._notifyBrowserDetailChanged();
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

  _decodeHtmlEntities(text) {
    const textarea = document.createElement('textarea');
    textarea.innerHTML = String(text || '');
    return textarea.value;
  }

  _normalizeSourceUrlValue(value) {
    let text = String(value || '').trim();
    if (!text) {
      return '';
    }

    for (let i = 0; i < 3; i += 1) {
      const decoded = this._decodeHtmlEntities(text);
      if (decoded === text) {
        break;
      }
      text = decoded;
    }

    const suffixPattern = /(?:&(?:quot|#34|#x22);?|#34;?|quot;)$/i;
    while (suffixPattern.test(text)) {
      text = text.replace(suffixPattern, '').trimEnd();
    }

    return text;
  }

  _getEntityType(model) {
    const normalized = (value) => {
      const candidate = String(value || '').trim().toLowerCase();
      if (candidate === 'idea' || candidate === 'model') {
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

  _coerceBoolish(value) {
    if (typeof value === 'boolean') {
      return value;
    }
    const normalized = String(value || '').trim().toLowerCase();
    if (!normalized) {
      return null;
    }
    if (normalized === 'true' || normalized === '1' || normalized === 'yes' || normalized === 'on') {
      return true;
    }
    if (normalized === 'false' || normalized === '0' || normalized === 'no' || normalized === 'off') {
      return false;
    }
    return null;
  }

  _resolveFrequentState(model) {
    const detail = this._modelDetail && typeof this._modelDetail === 'object' ? this._modelDetail : {};
    const ranking = detail.ranking && typeof detail.ranking === 'object' ? detail.ranking : {};
    const frequents = detail.frequents && typeof detail.frequents === 'object' ? detail.frequents : {};
    const structured = model && model.structured_metadata && typeof model.structured_metadata === 'object'
      ? model.structured_metadata
      : {};
    const catalogSignals = structured.catalog_signals && typeof structured.catalog_signals === 'object'
      ? structured.catalog_signals
      : {};

    const manualOverride = this._coerceBoolish(catalogSignals.model_frequent_override);
    const minPrintsRaw = frequents.min_prints;
    const minPrints = Number.isFinite(Number(minPrintsRaw)) ? Math.max(1, Number(minPrintsRaw)) : 3;
    const weightedRaw = frequents.weighted_print_count;
    let weightedPrintCount = Number(weightedRaw);
    if (!Number.isFinite(weightedPrintCount)) {
      weightedPrintCount = Number(ranking.frequent_score || 0);
    }
    if (!Number.isFinite(weightedPrintCount)) {
      weightedPrintCount = 0;
    }

    const inferredFlag = this._coerceBoolish(frequents.is_frequent_inferred);
    const isFrequentInferred = inferredFlag !== null ? inferredFlag : weightedPrintCount >= minPrints;
    const isFrequent = manualOverride !== null ? !!manualOverride : isFrequentInferred;

    const source = manualOverride !== null
      ? 'manual_override'
      : (isFrequentInferred ? 'inferred' : 'none');

    return {
      isFrequent: isFrequent,
      isFrequentInferred: isFrequentInferred,
      manualOverride: manualOverride,
      source: source,
      weightedPrintCount: weightedPrintCount,
      minPrints: minPrints,
    };
  }

  _renderIdeaMetadataCard(model) {
    const metadata = this._resolveIdeaMetadata(model);
    const externalLinks = metadata.external_links;
    const sketchImage = metadata.sketch_image;
    const notes = metadata.notes;

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

    const editNotes = this._escapeHtml(this._ideaMetaDraft.notes || '');
    const editLinks = this._escapeHtml(this._ideaMetaDraft.externalLinksText || '');
    const editSketch = this._escapeHtml(this._ideaMetaDraft.sketchImageUrl || '');

    return `
      <section class="card">
        <div class="h">
          <span>💡 Idea Details</span>
          <span>
            ${this._ideaMetaEditOpen
              ? `<button class="action-button ghost" data-action="idea-edit-cancel" ${this._ideaMetaSaving ? 'disabled' : ''}>Cancel</button>
                 <button class="action-button" data-action="idea-edit-save" ${this._ideaMetaSaving ? 'disabled' : ''}>${this._ideaMetaSaving ? 'Saving...' : 'Save'}</button>`
              : '<button class="action-button ghost" data-action="idea-edit-start">Edit</button>'}
          </span>
        </div>
        <div style="padding: 10px; display: grid; gap: 8px; font-size: 12px;">
          ${this._ideaMetaEditOpen ? `
            <label style="display:grid; gap:4px;">
              <span style="font-weight: 600; color: var(--secondary-text-color);">Notes</span>
              <textarea id="idea-notes-input" rows="4" maxlength="5000" style="width:100%; resize:vertical; border:1px solid var(--divider-color); border-radius:8px; background:var(--card-background-color); color:var(--primary-text-color); padding:8px;">${editNotes}</textarea>
            </label>
            <label style="display:grid; gap:4px;">
              <span style="font-weight: 600; color: var(--secondary-text-color);">External Links</span>
              <textarea id="idea-links-input" rows="4" placeholder="One per line. Use url|label for custom labels." style="width:100%; resize:vertical; border:1px solid var(--divider-color); border-radius:8px; background:var(--card-background-color); color:var(--primary-text-color); padding:8px;">${editLinks}</textarea>
            </label>
            <label style="display:grid; gap:4px;">
              <span style="font-weight: 600; color: var(--secondary-text-color);">Sketch Image URL</span>
              <input id="idea-sketch-input" type="url" placeholder="https://..." value="${editSketch}" style="border:1px solid var(--divider-color); border-radius:8px; background:var(--card-background-color); color:var(--primary-text-color); padding:8px;" />
            </label>
          ` : `
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
            ${!notes && !externalLinks.length && !sketchImage ? '<div style="color: var(--secondary-text-color);">No idea details yet.</div>' : ''}
          `}
          <div style="font-size: 11px; color: var(--secondary-text-color); margin-top: 4px;">
            Promoting this Idea keeps project/collection/tag memberships and changes entity type.
          </div>
        </div>
      </section>
    `;
  }

  _resolveIdeaMetadata(model) {
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

    const sketchCandidate = detailIdeaMetadata.sketch_image != null
      ? detailIdeaMetadata.sketch_image
      : (enrichmentFields.sketch_image != null ? enrichmentFields.sketch_image : modelFields.sketch_image);
    const sketchUrl = sketchCandidate && typeof sketchCandidate === 'object'
      ? String(sketchCandidate.url || '').trim()
      : String(sketchCandidate || '').trim();

    const notes = String(
      detailIdeaMetadata.notes != null
        ? detailIdeaMetadata.notes
        : (enrichmentFields.notes != null ? enrichmentFields.notes : (modelFields.notes || ''))
    ).trim();

    return {
      notes,
      external_links: externalLinks,
      sketch_image: sketchUrl,
    };
  }

  _ideaExternalLinksToText(links) {
    const rows = Array.isArray(links) ? links : [];
    return rows.map((entry) => {
      if (!entry || typeof entry !== 'object') {
        return '';
      }
      const url = String(entry.url || '').trim();
      const label = String(entry.label || '').trim();
      if (!url) {
        return '';
      }
      return label ? `${url}|${label}` : url;
    }).filter(Boolean).join('\n');
  }

  _parseIdeaExternalLinks(rawValue) {
    const text = String(rawValue || '').trim();
    if (!text) {
      return [];
    }
    const tokens = text.split(/[\n,]+/);
    const links = [];
    for (let i = 0; i < tokens.length; i += 1) {
      const token = String(tokens[i] || '').trim();
      if (!token) {
        continue;
      }
      const parts = token.split('|');
      const url = String(parts[0] || '').trim();
      const label = String(parts[1] || '').trim();
      if (!url) {
        continue;
      }
      if (label) {
        links.push({ url, label });
      } else {
        links.push({ url });
      }
    }
    return links;
  }

  _openIdeaMetadataEditor() {
    const model = this._modelDetail && this._modelDetail.model ? this._modelDetail.model : {};
    const metadata = this._resolveIdeaMetadata(model);
    this._ideaMetaDraft = {
      notes: String(metadata.notes || ''),
      externalLinksText: this._ideaExternalLinksToText(metadata.external_links),
      sketchImageUrl: String(metadata.sketch_image || ''),
    };
    this._ideaMetaEditOpen = true;
    this._render();
  }

  _cancelIdeaMetadataEditor() {
    this._ideaMetaEditOpen = false;
    this._ideaMetaSaving = false;
    this._render();
  }

  async _saveIdeaMetadataEdits() {
    if (this._ideaMetaSaving) {
      return;
    }
    const localModelId = String((this._modelDetail && this._modelDetail.local_model_id) || this._modelRef || '').trim();
    if (!localModelId || !this._modelSidecarUrl) {
      return;
    }

    const notesInput = this.shadowRoot && this.shadowRoot.querySelector ? this.shadowRoot.querySelector('#idea-notes-input') : null;
    const linksInput = this.shadowRoot && this.shadowRoot.querySelector ? this.shadowRoot.querySelector('#idea-links-input') : null;
    const sketchInput = this.shadowRoot && this.shadowRoot.querySelector ? this.shadowRoot.querySelector('#idea-sketch-input') : null;

    const notes = String(notesInput && 'value' in notesInput ? notesInput.value : this._ideaMetaDraft.notes || '').trim();
    const externalLinksText = String(linksInput && 'value' in linksInput ? linksInput.value : this._ideaMetaDraft.externalLinksText || '').trim();
    const sketchImageUrl = String(sketchInput && 'value' in sketchInput ? sketchInput.value : this._ideaMetaDraft.sketchImageUrl || '').trim();

    this._ideaMetaSaving = true;
    this._ideaMetaDraft = { notes, externalLinksText, sketchImageUrl };
    this._render();

    try {
      const payload = {
        notes: notes || null,
        external_links: this._parseIdeaExternalLinks(externalLinksText),
        sketch_image: sketchImageUrl ? { url: sketchImageUrl } : null,
      };
      const base = String(this._modelSidecarUrl || '').trim().replace(/\/$/, '');
      const response = await fetch(`${base}/api/local/models/${encodeURIComponent(localModelId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok || body.success === false) {
        throw new Error(String(body.error || `Idea metadata update failed (HTTP ${response.status})`));
      }
      await this._loadModelDetail({ silent: true });
      this._ideaMetaSaving = false;
      this._ideaMetaEditOpen = false;
      this._notifyBrowserDetailChanged();
    } catch (error) {
      this._ideaMetaSaving = false;
      this._error = `Failed to save idea metadata: ${error}`;
      this._render();
    }
  }

  async _promoteIdeaEntity(toEntityType) {
    if (this._ideaPromoteBusy) {
      return;
    }
    const localModelId = String((this._modelDetail && this._modelDetail.local_model_id) || this._modelRef || '').trim();
    const model = this._modelDetail && this._modelDetail.model ? this._modelDetail.model : {};
    const fromEntityType = this._getEntityType(model);
    const target = String(toEntityType || '').trim().toLowerCase();
    if (!localModelId || fromEntityType !== 'idea' || target !== 'model') {
      return;
    }
    if (!window.confirm(`Promote "${String(model.name || localModelId)}" to Catalog?`)) {
      return;
    }

    this._ideaPromoteBusy = true;
    this._render();
    try {
      const base = String(this._modelSidecarUrl || '').trim().replace(/\/$/, '');
      const response = await fetch(`${base}/api/local/models/${encodeURIComponent(localModelId)}/promote`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          from_entity_type: 'idea',
          to_entity_type: target,
        }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok || body.success === false) {
        throw new Error(String(body.error || `Promotion failed (HTTP ${response.status})`));
      }
      await this._loadModelDetail({ silent: true });
      this._ideaPromoteBusy = false;
      this._notifyBrowserDetailChanged();
    } catch (error) {
      this._ideaPromoteBusy = false;
      this._error = `Failed to promote idea: ${error}`;
      this._render();
    }
  }

  async _moveIdeaToWorkingFiles() {
    if (this._ideaPromoteBusy) {
      return;
    }
    const localModelId = String((this._modelDetail && this._modelDetail.local_model_id) || this._modelRef || '').trim();
    const model = this._modelDetail && this._modelDetail.model ? this._modelDetail.model : {};
    const fromEntityType = this._getEntityType(model);
    if (!localModelId || fromEntityType !== 'idea') {
      return;
    }
    const displayName = String(model.name || localModelId);
    if (!window.confirm(`Move "${displayName}" to Working Files?\n\nThe idea will be removed from the catalog and materialized as a folder on disk.`)) {
      return;
    }

    this._ideaPromoteBusy = true;
    this._render();
    try {
      const base = String(this._modelSidecarUrl || '').trim().replace(/\/$/, '');
      const response = await fetch(`${base}/api/local/models/${encodeURIComponent(localModelId)}/move-to-working-files`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok || body.success === false) {
        throw new Error(String(body.message || body.error || `Move failed (HTTP ${response.status})`));
      }
      // Idea row has been hard-deleted; notify browser to refresh, then close popup.
      this._ideaPromoteBusy = false;
      this._notifyBrowserDetailChanged();
      this.dispatchEvent(new CustomEvent('model-deleted', { detail: { modelRef: this._modelRef, reason: 'moved-to-working-files' } }));
      if (window && window.parent) {
        try {
          window.parent.postMessage({ type: 'close-popup' }, '*');
        } catch (_) {
          // ignore
        }
      }
      this._modelDetail = null;
      this._render();
    } catch (error) {
      this._ideaPromoteBusy = false;
      this._error = `Failed to move idea to Working Files: ${error}`;
      this._render();
    }
  }

  async _openModelMetadataEditor() {
    if (this._modelMetaLoading || this._modelMetaSaving) {
      return;
    }
    const model = (this._modelDetail && this._modelDetail.model) || {};
    const modelRef = String(model.model_ref || this._modelRef || '').trim();
    const base = String(this._resolveModelSidecarUrl() || '').trim().replace(/\/$/, '');
    if (!modelRef || !base) {
      return;
    }
    this._modelMetaEditOpen = true;
    this._modelMetaLoading = true;
    this._collectionPickerOpen = false;
    this._collectionSearchQuery = '';
    this._collectionPickerHighlightIndex = 0;
    this._projectPickerOpen = false;
    this._projectSearchQuery = '';
    this._projectPickerHighlightIndex = 0;
    this._modelMetaDraft = {
      modelName: String(model.name || ''),
      description: String(model.description || ''),
      collectionMemberships: [],
      projectMemberships: [],
    };
    this._render();
    try {
      const [collectionsResponse, membershipsResponse, projectsResponse, projectMembershipsResponse] = await Promise.all([
        fetch(`${base}/api/collections`),
        fetch(`${base}/api/models/${encodeURIComponent(modelRef)}/collections`),
        fetch(`${base}/api/projects?show_archived=true&limit=500`),
        fetch(`${base}/api/models/${encodeURIComponent(modelRef)}/projects`),
      ]);
      const collectionsBody = await collectionsResponse.json().catch(() => ({}));
      const membershipsBody = await membershipsResponse.json().catch(() => ({}));
      const projectsBody = await projectsResponse.json().catch(() => ({}));
      const projectMembershipsBody = await projectMembershipsResponse.json().catch(() => ({}));
      if (!collectionsResponse.ok) {
        throw new Error(String(collectionsBody.error || `Collections load failed (HTTP ${collectionsResponse.status})`));
      }
      if (!membershipsResponse.ok) {
        throw new Error(String(membershipsBody.error || `Membership load failed (HTTP ${membershipsResponse.status})`));
      }
      if (!projectsResponse.ok) {
        throw new Error(String(projectsBody.error || `Projects load failed (HTTP ${projectsResponse.status})`));
      }
      if (!projectMembershipsResponse.ok) {
        throw new Error(String(projectMembershipsBody.error || `Project membership load failed (HTTP ${projectMembershipsResponse.status})`));
      }
      this._knownCollections = this._normalizeCollectionRows(Array.isArray(collectionsBody.items) ? collectionsBody.items : []);
      this._allCollectionsFetched = true;
      this._modelMetaDraft.collectionMemberships = this._normalizeCollectionRows(Array.isArray(membershipsBody.items) ? membershipsBody.items : []);
      this._knownProjects = this._normalizeProjectRows(Array.isArray(projectsBody.projects) ? projectsBody.projects : []);
      this._allProjectsFetched = true;
      this._modelMetaDraft.projectMemberships = this._normalizeProjectRows(Array.isArray(projectMembershipsBody.items) ? projectMembershipsBody.items : []);
      this._syncCollectionMembershipStaleness();
      this._syncProjectMembershipStaleness();
    } catch (error) {
      this._error = `Failed to load model editor: ${error}`;
    } finally {
      this._modelMetaLoading = false;
      this._render();
    }
  }

  _cancelModelMetadataEditor() {
    this._modelMetaEditOpen = false;
    this._modelMetaLoading = false;
    this._modelMetaSaving = false;
    this._collectionPickerOpen = false;
    this._collectionSearchQuery = '';
    this._collectionPickerHighlightIndex = 0;
    this._projectPickerOpen = false;
    this._projectSearchQuery = '';
    this._projectPickerHighlightIndex = 0;
    this._collectionMembershipStaleIds = [];
    this._projectMembershipStaleIds = [];
    this._dismissCollectionEditFeedback();
    this._dismissProjectEditFeedback();
  }

  _normalizeCollectionRows(rows) {
    const normalizedRows = Array.isArray(rows) ? rows.map((row) => ({
      collection_id: String(row && row.collection_id || '').trim().toLowerCase(),
      name: String(row && row.name || '').trim(),
      parent_collection_id: String(row && row.parent_collection_id || '').trim().toLowerCase() || null,
      path: String(row && row.path || '').trim(),
    })).filter((row) => row.collection_id) : [];
    const rowsById = {};
    normalizedRows.forEach((row) => {
      rowsById[row.collection_id] = row;
    });
    const resolvePath = (row) => {
      if (!row) {
        return '';
      }
      if (row.path) {
        return row.path;
      }
      const labels = [];
      const visited = new Set();
      let cursor = row;
      while (cursor && !visited.has(cursor.collection_id)) {
        visited.add(cursor.collection_id);
        labels.push(cursor.name || cursor.collection_id);
        cursor = cursor.parent_collection_id ? rowsById[cursor.parent_collection_id] : null;
      }
      return labels.reverse().join(' / ');
    };
    return normalizedRows.map((row) => Object.assign({}, row, { path: resolvePath(row) || row.name || row.collection_id }));
  }

  _selectedCollectionMemberships() {
    return this._modelMetaDraft && Array.isArray(this._modelMetaDraft.collectionMemberships)
      ? this._modelMetaDraft.collectionMemberships
      : [];
  }

  _normalizeProjectRows(rows) {
    return Array.isArray(rows) ? rows.map((row) => {
      const project = row && typeof row.project === 'object' ? row.project : row;
      const projectId = String(project && project.id != null ? project.id : row && row.project_id != null ? row.project_id : '').trim();
      return {
        project_id: projectId,
        title: String(project && project.title || row && row.title || '').trim(),
        status: String(project && project.status || row && row.status || '').trim().toLowerCase(),
        project_type: String(project && project.project_type || row && row.project_type || '').trim().toLowerCase(),
        origin: String(project && project.origin || row && row.origin || '').trim().toLowerCase(),
        archived_at: String(project && project.archived_at || row && row.archived_at || '').trim() || null,
        member_state: String(row && row.member_state || '').trim().toLowerCase() || 'candidate',
      };
    }).filter((row) => row.project_id) : [];
  }

  _selectedProjectMemberships() {
    return this._modelMetaDraft && Array.isArray(this._modelMetaDraft.projectMemberships)
      ? this._modelMetaDraft.projectMemberships
      : [];
  }

  _clearCollectionEditFeedbackTimer() {
    if (this._collectionEditFeedbackTimer) {
      window.clearTimeout(this._collectionEditFeedbackTimer);
      this._collectionEditFeedbackTimer = null;
    }
  }

  _showCollectionEditFeedback(feedback, options) {
    var settings = options && typeof options === 'object' ? options : {};
    this._clearCollectionEditFeedbackTimer();
    this._collectionEditFeedback = feedback && typeof feedback === 'object' ? Object.assign({}, feedback) : null;
    if (this._collectionEditFeedback && settings.autoDismiss !== false) {
      this._collectionEditFeedbackTimer = window.setTimeout(function () {
        this._collectionEditFeedbackTimer = null;
        this._collectionEditFeedback = null;
        this._render();
      }.bind(this), Math.max(1000, Number(settings.timeoutMs || 5000) || 5000));
    }
    this._render();
  }

  _dismissCollectionEditFeedback() {
    this._clearCollectionEditFeedbackTimer();
    this._collectionEditFeedback = null;
    this._render();
  }

  _clearProjectEditFeedbackTimer() {
    if (this._projectEditFeedbackTimer) {
      window.clearTimeout(this._projectEditFeedbackTimer);
      this._projectEditFeedbackTimer = null;
    }
  }

  _showProjectEditFeedback(feedback, options) {
    var settings = options && typeof options === 'object' ? options : {};
    this._clearProjectEditFeedbackTimer();
    this._projectEditFeedback = feedback && typeof feedback === 'object' ? Object.assign({}, feedback) : null;
    if (this._projectEditFeedback && settings.autoDismiss !== false) {
      this._projectEditFeedbackTimer = window.setTimeout(function () {
        this._projectEditFeedbackTimer = null;
        this._projectEditFeedback = null;
        this._render();
      }.bind(this), Math.max(1000, Number(settings.timeoutMs || 5000) || 5000));
    }
    this._render();
  }

  _dismissProjectEditFeedback() {
    this._clearProjectEditFeedbackTimer();
    this._projectEditFeedback = null;
    this._render();
  }

  _computeStaleCollectionMembershipIds(selectedRows, knownCollections) {
    var knownIds = new Set((Array.isArray(knownCollections) ? knownCollections : []).map(function (row) {
      return String(row && row.collection_id || '').trim().toLowerCase();
    }).filter(Boolean));
    return (Array.isArray(selectedRows) ? selectedRows : []).map(function (row) {
      return String(row && row.collection_id || '').trim().toLowerCase();
    }).filter(function (collectionId) {
      return collectionId && !knownIds.has(collectionId);
    });
  }

  _syncCollectionMembershipStaleness() {
    this._collectionMembershipStaleIds = this._computeStaleCollectionMembershipIds(this._selectedCollectionMemberships(), this._knownCollections);
    return this._collectionMembershipStaleIds.slice(0);
  }

  _computeStaleProjectMembershipIds(selectedRows, knownProjects) {
    var knownIds = new Set((Array.isArray(knownProjects) ? knownProjects : []).map(function (row) {
      return String(row && row.project_id || '').trim();
    }).filter(Boolean));
    return (Array.isArray(selectedRows) ? selectedRows : []).map(function (row) {
      return String(row && row.project_id || '').trim();
    }).filter(function (projectId) {
      return projectId && !knownIds.has(projectId);
    });
  }

  _syncProjectMembershipStaleness() {
    this._projectMembershipStaleIds = this._computeStaleProjectMembershipIds(this._selectedProjectMemberships(), this._knownProjects);
    return this._projectMembershipStaleIds.slice(0);
  }

  async _refreshCollectionEditorCollections(options) {
    var settings = options && typeof options === 'object' ? options : {};
    var base = String(this._resolveModelSidecarUrl() || '').trim().replace(/\/$/, '');
    if (!base) {
      return [];
    }
    var response = await fetch(base + '/api/collections');
    var body = await response.json().catch(function () { return {}; });
    if (!response.ok) {
      throw new Error(String(body.error || ('Collections load failed (HTTP ' + response.status + ')')));
    }
    this._knownCollections = this._normalizeCollectionRows(Array.isArray(body.items) ? body.items : []);
    this._allCollectionsFetched = true;
    var staleIds = this._syncCollectionMembershipStaleness();
    if (settings.showFeedback) {
      if (staleIds.length) {
        this._showCollectionEditFeedback({
          kind: 'warning',
          message: staleIds.length === 1
            ? 'One selected collection no longer exists. Remove the stale chip before saving.'
            : staleIds.length + ' selected collections no longer exist. Remove the stale chips before saving.',
        }, { autoDismiss: false });
      } else {
        this._showCollectionEditFeedback({ kind: 'info', message: 'Collection list refreshed.' }, { timeoutMs: 2500 });
      }
    } else if (settings.render !== false) {
      this._render();
    }
    return this._knownCollections;
  }

  async _refreshProjectEditorProjects(options) {
    var settings = options && typeof options === 'object' ? options : {};
    var base = String(this._resolveModelSidecarUrl() || '').trim().replace(/\/$/, '');
    if (!base) {
      return [];
    }
    var response = await fetch(base + '/api/projects?show_archived=true&limit=500');
    var body = await response.json().catch(function () { return {}; });
    if (!response.ok) {
      throw new Error(String(body.error || ('Projects load failed (HTTP ' + response.status + ')')));
    }
    this._knownProjects = this._normalizeProjectRows(Array.isArray(body.projects) ? body.projects : []);
    this._allProjectsFetched = true;
    var staleIds = this._syncProjectMembershipStaleness();
    if (settings.showFeedback) {
      if (staleIds.length) {
        this._showProjectEditFeedback({
          kind: 'warning',
          message: staleIds.length === 1
            ? 'One selected project no longer exists. Remove the stale chip before saving.'
            : staleIds.length + ' selected projects no longer exist. Remove the stale chips before saving.',
        }, { autoDismiss: false });
      } else {
        this._showProjectEditFeedback({ kind: 'info', message: 'Project list refreshed.' }, { timeoutMs: 2500 });
      }
    } else if (settings.render !== false) {
      this._render();
    }
    return this._knownProjects;
  }

  _undoLastCollectionMembershipChange() {
    var feedback = this._collectionEditFeedback && typeof this._collectionEditFeedback === 'object' ? this._collectionEditFeedback : null;
    var undo = feedback && feedback.undo && typeof feedback.undo === 'object' ? feedback.undo : null;
    if (!undo || !undo.collectionId) {
      return;
    }
    var current = this._selectedCollectionMemberships().slice(0);
    if (undo.type === 'add') {
      this._modelMetaDraft.collectionMemberships = current.filter(function (row) {
        return String(row && row.collection_id || '').trim().toLowerCase() !== undo.collectionId;
      });
    } else if (undo.type === 'remove') {
      var exists = current.some(function (row) {
        return String(row && row.collection_id || '').trim().toLowerCase() === undo.collectionId;
      });
      if (!exists && undo.row) {
        var insertIndex = Math.max(0, Math.min(Number(undo.index || 0) || 0, current.length));
        current.splice(insertIndex, 0, undo.row);
      }
      this._modelMetaDraft.collectionMemberships = current;
    } else {
      return;
    }
    this._syncCollectionMembershipStaleness();
    this._showCollectionEditFeedback({ kind: 'info', message: 'Collection change undone.' }, { timeoutMs: 2500 });
  }

  _undoLastProjectMembershipChange() {
    var feedback = this._projectEditFeedback && typeof this._projectEditFeedback === 'object' ? this._projectEditFeedback : null;
    var undo = feedback && feedback.undo && typeof feedback.undo === 'object' ? feedback.undo : null;
    if (!undo || !undo.projectId) {
      return;
    }
    var current = this._selectedProjectMemberships().slice(0);
    if (undo.type === 'add') {
      this._modelMetaDraft.projectMemberships = current.filter(function (row) {
        return String(row && row.project_id || '').trim() !== undo.projectId;
      });
    } else if (undo.type === 'remove') {
      var exists = current.some(function (row) {
        return String(row && row.project_id || '').trim() === undo.projectId;
      });
      if (!exists && undo.row) {
        var insertIndex = Math.max(0, Math.min(Number(undo.index || 0) || 0, current.length));
        current.splice(insertIndex, 0, undo.row);
      }
      this._modelMetaDraft.projectMemberships = current;
    } else {
      return;
    }
    this._syncProjectMembershipStaleness();
    this._showProjectEditFeedback({ kind: 'info', message: 'Project change undone.' }, { timeoutMs: 2500 });
  }

  _renderCollectionEditFeedback() {
    var feedback = this._collectionEditFeedback && typeof this._collectionEditFeedback === 'object' ? this._collectionEditFeedback : null;
    var canUndo = !!(feedback && feedback.undo && feedback.undo.collectionId);
    if (!feedback || !feedback.message) {
      return '';
    }
    return ''
      + '<div class="collection-edit-feedback ' + this._escapeHtml(String(feedback.kind || 'info')) + '" role="status" aria-live="polite">'
      + '  <div class="collection-edit-feedback-message">' + this._escapeHtml(String(feedback.message || '')) + '</div>'
      + '  <div class="collection-edit-feedback-actions">'
      + (canUndo ? '    <button class="action-button ghost small" data-action="undo-collection-change">Undo</button>' : '')
      + '    <button class="action-button ghost small" data-action="dismiss-collection-feedback">Dismiss</button>'
      + '  </div>'
      + '</div>';
  }

  _renderProjectEditFeedback() {
    var feedback = this._projectEditFeedback && typeof this._projectEditFeedback === 'object' ? this._projectEditFeedback : null;
    var canUndo = !!(feedback && feedback.undo && feedback.undo.projectId);
    if (!feedback || !feedback.message) {
      return '';
    }
    return ''
      + '<div class="collection-edit-feedback ' + this._escapeHtml(String(feedback.kind || 'info')) + '" role="status" aria-live="polite">'
      + '  <div class="collection-edit-feedback-message">' + this._escapeHtml(String(feedback.message || '')) + '</div>'
      + '  <div class="collection-edit-feedback-actions">'
      + (canUndo ? '    <button class="action-button ghost small" data-action="undo-project-change">Undo</button>' : '')
      + '    <button class="action-button ghost small" data-action="dismiss-project-feedback">Dismiss</button>'
      + '  </div>'
      + '</div>';
  }

  _projectMembershipLabel(row) {
    return String(row && row.title || row && row.project_id || 'Project').trim();
  }

  _projectPickerMeta(row) {
    var details = [];
    if (row && row.status) {
      details.push(String(row.status).replace(/_/g, ' '));
    }
    if (row && row.project_type) {
      details.push(String(row.project_type).replace(/_/g, ' '));
    }
    return details.join(' · ');
  }

  _buildProjectPickerState(selectedRows) {
    const selectedIds = new Set((Array.isArray(selectedRows) ? selectedRows : []).map((row) => String(row.project_id || '').trim()));
    const query = String(this._projectSearchQuery || '').trim();
    const queryNormalized = query.toLowerCase();
    const suggestions = (Array.isArray(this._knownProjects) ? this._knownProjects : [])
      .filter((row) => !selectedIds.has(String(row.project_id || '').trim()))
      .filter((row) => !(row.archived_at || '') && String(row.status || '') !== 'archived')
      .filter((row) => {
        if (!queryNormalized) {
          return true;
        }
        return String(row.title || '').toLowerCase().includes(queryNormalized)
          || String(row.status || '').toLowerCase().includes(queryNormalized)
          || String(row.project_type || '').toLowerCase().includes(queryNormalized)
          || String(row.origin || '').toLowerCase().includes(queryNormalized);
      })
      .slice(0, 8)
      .map((row) => ({
        type: 'project',
        value: row.project_id,
        label: this._projectMembershipLabel(row),
        meta: this._projectPickerMeta(row),
      }));
    const exactMatch = (Array.isArray(this._knownProjects) ? this._knownProjects : []).some((row) => String(row.title || '').trim().toLowerCase() === queryNormalized);
    const options = suggestions.slice(0);
    if (query && !exactMatch) {
      options.push({ type: 'create', value: query, label: query, meta: 'new project' });
    }
    return { options };
  }

  _renderProjectPicker(selectedRows) {
    const pickerState = this._buildProjectPickerState(selectedRows);
    const options = pickerState.options;
    if (this._projectPickerHighlightIndex < 0 || this._projectPickerHighlightIndex >= options.length) {
      this._projectPickerHighlightIndex = options.length ? 0 : -1;
    }
    return `
      <div class="picker-dd">
        <input class="search-box" type="text" placeholder="Search or create project…" data-input="project-search" value="${this._escapeHtml(this._projectSearchQuery)}" />
        ${options.map((option, index) => {
          const selectedClass = index === this._projectPickerHighlightIndex ? ' selected' : '';
          if (option.type === 'create') {
            return `<div class="create-new${selectedClass}" data-action="create-project">+ Create "${this._escapeHtml(option.value)}"</div>`;
          }
          return `<div class="opt${selectedClass}" data-action="add-project" data-project-id="${this._escapeHtml(option.value)}">${this._escapeHtml(option.label)}${option.meta ? `<span class="path-meta">${this._escapeHtml(option.meta)}</span>` : ''}</div>`;
        }).join('')}
      </div>
    `;
  }

  _buildCollectionPickerState(selectedRows) {
    const selectedIds = new Set((Array.isArray(selectedRows) ? selectedRows : []).map((row) => String(row.collection_id || '').trim().toLowerCase()));
    const query = String(this._collectionSearchQuery || '').trim();
    const queryNormalized = query.toLowerCase();
    const suggestions = (Array.isArray(this._knownCollections) ? this._knownCollections : [])
      .filter((row) => !selectedIds.has(String(row.collection_id || '').trim().toLowerCase()))
      .filter((row) => {
        if (!queryNormalized) {
          return true;
        }
        return String(row.path || '').toLowerCase().includes(queryNormalized)
          || String(row.name || '').toLowerCase().includes(queryNormalized);
      })
      .slice(0, 8)
      .map((row) => ({ type: 'collection', value: row.collection_id, label: row.path || row.name || row.collection_id }));
    const exactMatch = (Array.isArray(this._knownCollections) ? this._knownCollections : []).some((row) => String(row.path || '').toLowerCase() === queryNormalized);
    const options = suggestions.slice(0);
    if (query && !exactMatch) {
      options.push({ type: 'create', value: query, label: query });
    }
    return { options };
  }

  _renderCollectionPicker(selectedRows) {
    const pickerState = this._buildCollectionPickerState(selectedRows);
    const options = pickerState.options;
    if (this._collectionPickerHighlightIndex < 0 || this._collectionPickerHighlightIndex >= options.length) {
      this._collectionPickerHighlightIndex = options.length ? 0 : -1;
    }
    return `
      <div class="picker-dd">
        <input class="search-box" type="text" placeholder="Search or create collection path…" data-input="collection-search" value="${this._escapeHtml(this._collectionSearchQuery)}" />
        ${options.map((option, index) => {
          const selectedClass = index === this._collectionPickerHighlightIndex ? ' selected' : '';
          if (option.type === 'create') {
            return `<div class="create-new${selectedClass}" data-action="create-collection">+ Create "${this._escapeHtml(option.value)}"</div>`;
          }
          return `<div class="opt${selectedClass}" data-action="add-collection" data-collection-id="${this._escapeHtml(option.value)}">${this._escapeHtml(option.label)}<span class="path-meta">existing</span></div>`;
        }).join('')}
      </div>
    `;
  }

  _handleCollectionRemove(collectionId) {
    const normalizedId = String(collectionId || '').trim().toLowerCase();
    const current = this._selectedCollectionMemberships();
    const removedIndex = current.findIndex((row) => String(row && row.collection_id || '').trim().toLowerCase() === normalizedId);
    if (removedIndex === -1) {
      return;
    }
    const removedRow = current[removedIndex];
    this._modelMetaDraft.collectionMemberships = current.filter((row) => String(row.collection_id || '').trim().toLowerCase() !== normalizedId);
    this._syncCollectionMembershipStaleness();
    this._showCollectionEditFeedback({
      kind: 'info',
      message: `Removed ${String(removedRow && (removedRow.path || removedRow.name || removedRow.collection_id) || 'collection')}.`,
      undo: {
        type: 'remove',
        collectionId: normalizedId,
        row: removedRow,
        index: removedIndex,
      },
    });
  }

  _handleProjectRemove(projectId) {
    const normalizedId = String(projectId || '').trim();
    const current = this._selectedProjectMemberships();
    const removedIndex = current.findIndex((row) => String(row && row.project_id || '').trim() === normalizedId);
    if (removedIndex === -1) {
      return;
    }
    const removedRow = current[removedIndex];
    this._modelMetaDraft.projectMemberships = current.filter((row) => String(row.project_id || '').trim() !== normalizedId);
    this._syncProjectMembershipStaleness();
    this._showProjectEditFeedback({
      kind: 'info',
      message: `Removed ${this._projectMembershipLabel(removedRow)}.`,
      undo: {
        type: 'remove',
        projectId: normalizedId,
        row: removedRow,
        index: removedIndex,
      },
    });
  }

  _handleCollectionAdd(collectionId) {
    const normalizedId = String(collectionId || '').trim().toLowerCase();
    const existingIds = new Set(this._selectedCollectionMemberships().map((row) => String(row.collection_id || '').trim().toLowerCase()));
    if (!normalizedId || existingIds.has(normalizedId)) {
      if (normalizedId) {
        this._showCollectionEditFeedback({ kind: 'info', message: 'That collection is already selected.' }, { timeoutMs: 2500 });
      }
      return;
    }
    const match = (Array.isArray(this._knownCollections) ? this._knownCollections : []).find((row) => String(row.collection_id || '').trim().toLowerCase() === normalizedId);
    if (!match) {
      this._showCollectionEditFeedback({ kind: 'warning', message: 'That collection is no longer available. Refresh the collection list and try again.' }, { autoDismiss: false });
      return;
    }
    this._modelMetaDraft.collectionMemberships = this._selectedCollectionMemberships().concat([match]);
    this._collectionSearchQuery = '';
    this._collectionPickerHighlightIndex = 0;
    this._syncCollectionMembershipStaleness();
    this._showCollectionEditFeedback({
      kind: 'info',
      message: `Added ${String(match.path || match.name || match.collection_id)}.`,
      undo: {
        type: 'add',
        collectionId: normalizedId,
        row: match,
      },
    });
  }

  _handleProjectAdd(projectId) {
    const normalizedId = String(projectId || '').trim();
    const existingIds = new Set(this._selectedProjectMemberships().map((row) => String(row.project_id || '').trim()));
    if (!normalizedId || existingIds.has(normalizedId)) {
      if (normalizedId) {
        this._showProjectEditFeedback({ kind: 'info', message: 'That project is already selected.' }, { timeoutMs: 2500 });
      }
      return;
    }
    const match = (Array.isArray(this._knownProjects) ? this._knownProjects : []).find((row) => String(row.project_id || '').trim() === normalizedId);
    if (!match) {
      this._showProjectEditFeedback({ kind: 'warning', message: 'That project is no longer available. Refresh the project list and try again.' }, { autoDismiss: false });
      return;
    }
    this._modelMetaDraft.projectMemberships = this._selectedProjectMemberships().concat([
      Object.assign({}, match, { member_state: String(match.member_state || 'candidate').trim().toLowerCase() || 'candidate' }),
    ]);
    this._projectSearchQuery = '';
    this._projectPickerHighlightIndex = 0;
    this._syncProjectMembershipStaleness();
    this._showProjectEditFeedback({
      kind: 'info',
      message: `Added ${this._projectMembershipLabel(match)}.`,
      undo: {
        type: 'add',
        projectId: normalizedId,
        row: match,
      },
    });
  }

  async _handleCollectionCreate() {
    if (this._collectionCreateBusy) {
      return;
    }
    const rawQuery = String(this._collectionSearchQuery || '').trim();
    const base = String(this._resolveModelSidecarUrl() || '').trim().replace(/\/$/, '');
    if (!rawQuery || !base) {
      return;
    }
    const segments = rawQuery.split('/').map((part) => part.trim()).filter(Boolean);
    if (!segments.length) {
      return;
    }
    this._collectionCreateBusy = true;
    this._render();
    try {
      let parentCollectionId = null;
      for (let index = 0; index < segments.length; index += 1) {
        const segment = segments[index];
        const candidateId = segments.slice(0, index + 1).map((part) => part.toLowerCase()).join(' / ');
        const existing = (Array.isArray(this._knownCollections) ? this._knownCollections : []).find((row) => row.collection_id === candidateId);
        if (existing) {
          parentCollectionId = existing.collection_id;
          continue;
        }
        const response = await fetch(`${base}/api/collections`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: segment, parent_collection_id: parentCollectionId }),
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok && response.status !== 409) {
          throw new Error(String(body.error || `Collection create failed (HTTP ${response.status})`));
        }
        const row = body && body.item ? body.item : { collection_id: candidateId, name: segment, parent_collection_id: parentCollectionId };
        this._knownCollections = this._normalizeCollectionRows(this._knownCollections.concat([row]));
        parentCollectionId = candidateId;
      }
      this._handleCollectionAdd(segments.map((part) => part.toLowerCase()).join(' / '));
      this._collectionPickerOpen = true;
    } catch (error) {
      this._error = `Failed to create collection: ${error}`;
      this._render();
    } finally {
      this._collectionCreateBusy = false;
    }
  }

  async _handleProjectCreate() {
    if (this._projectCreateBusy) {
      return;
    }
    const rawQuery = String(this._projectSearchQuery || '').trim();
    const base = String(this._resolveModelSidecarUrl() || '').trim().replace(/\/$/, '');
    if (!rawQuery || !base) {
      return;
    }
    this._projectCreateBusy = true;
    this._render();
    try {
      const response = await fetch(`${base}/api/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: rawQuery }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok || body.success === false) {
        throw new Error(String(body.error || body.message || `Project create failed (HTTP ${response.status})`));
      }
      const createdProject = body && body.project ? body.project : null;
      if (createdProject) {
        this._knownProjects = this._normalizeProjectRows(this._knownProjects.concat([createdProject]));
        this._allProjectsFetched = true;
        this._handleProjectAdd(createdProject.id);
      }
      this._projectPickerOpen = true;
    } catch (error) {
      this._error = `Failed to create project: ${error}`;
      this._render();
    } finally {
      this._projectCreateBusy = false;
    }
  }

  async _saveModelMetadataEdits() {
    if (this._modelMetaSaving || this._modelMetaLoading) {
      return;
    }
    const model = (this._modelDetail && this._modelDetail.model) || {};
    const modelRef = String(model.model_ref || this._modelRef || '').trim();
    const base = String(this._resolveModelSidecarUrl() || '').trim().replace(/\/$/, '');
    if (!modelRef || !base) {
      return;
    }
    const nameInput = this.shadowRoot && this.shadowRoot.querySelector ? this.shadowRoot.querySelector('#model-meta-name') : null;
    const descriptionInput = this.shadowRoot && this.shadowRoot.querySelector ? this.shadowRoot.querySelector('#model-meta-description') : null;
    const modelName = String(nameInput && 'value' in nameInput ? nameInput.value : this._modelMetaDraft.modelName || '').trim();
    const description = String(descriptionInput && 'value' in descriptionInput ? descriptionInput.value : this._modelMetaDraft.description || '').trim();
    if (!modelName) {
      this._error = 'Model name is required.';
      this._render();
      return;
    }
    this._modelMetaSaving = true;
    this._modelMetaDraft.modelName = modelName;
    this._modelMetaDraft.description = description;
    this._render();
    try {
      await this._refreshCollectionEditorCollections({ showFeedback: false, render: false });
      await this._refreshProjectEditorProjects({ showFeedback: false, render: false });
      const staleIds = this._syncCollectionMembershipStaleness();
      if (staleIds.length) {
        this._modelMetaSaving = false;
        this._showCollectionEditFeedback({
          kind: 'warning',
          message: staleIds.length === 1
            ? 'One selected collection no longer exists. Remove the stale chip before saving.'
            : `${staleIds.length} selected collections no longer exist. Remove the stale chips before saving.`,
        }, { autoDismiss: false });
        return;
      }
      const staleProjectIds = this._syncProjectMembershipStaleness();
      if (staleProjectIds.length) {
        this._modelMetaSaving = false;
        this._showProjectEditFeedback({
          kind: 'warning',
          message: staleProjectIds.length === 1
            ? 'One selected project no longer exists. Remove the stale chip before saving.'
            : `${staleProjectIds.length} selected projects no longer exist. Remove the stale chips before saving.`,
        }, { autoDismiss: false });
        return;
      }
      const patchResponse = await fetch(`${base}/api/models/${encodeURIComponent(modelRef)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_name: modelName, description: description }),
      });
      const patchBody = await patchResponse.json().catch(() => ({}));
      if (!patchResponse.ok || patchBody.success === false) {
        throw new Error(String(patchBody.error || `Model update failed (HTTP ${patchResponse.status})`));
      }
      const collectionResponse = await fetch(`${base}/api/models/${encodeURIComponent(modelRef)}/collections`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ collection_ids: this._selectedCollectionMemberships().map((row) => String(row.collection_id || '').trim()).filter(Boolean) }),
      });
      const collectionBody = await collectionResponse.json().catch(() => ({}));
      if (!collectionResponse.ok || collectionBody.success === false) {
        throw new Error(String(collectionBody.error || `Collection update failed (HTTP ${collectionResponse.status})`));
      }
      const projectResponse = await fetch(`${base}/api/models/${encodeURIComponent(modelRef)}/projects`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_memberships: this._selectedProjectMemberships().map((row) => ({
            project_id: Number(row.project_id),
            member_state: String(row.member_state || 'candidate').trim().toLowerCase() || 'candidate',
          })).filter((row) => Number.isFinite(row.project_id) && row.project_id > 0),
        }),
      });
      const projectBody = await projectResponse.json().catch(() => ({}));
      if (!projectResponse.ok || projectBody.success === false) {
        throw new Error(String(projectBody.error || `Project update failed (HTTP ${projectResponse.status})`));
      }
      await this._loadModelDetail({ silent: true });
      this._modelMetaSaving = false;
      this._modelMetaEditOpen = false;
      this._collectionPickerOpen = false;
      this._collectionSearchQuery = '';
      this._collectionPickerHighlightIndex = 0;
      this._projectPickerOpen = false;
      this._projectSearchQuery = '';
      this._projectPickerHighlightIndex = 0;
      this._collectionMembershipStaleIds = [];
      this._projectMembershipStaleIds = [];
      this._dismissCollectionEditFeedback();
      this._dismissProjectEditFeedback();
      this._notifyBrowserDetailChanged();
      this._render();
    } catch (error) {
      this._modelMetaSaving = false;
      this._error = `Failed to save model metadata: ${error}`;
      this._render();
    }
  }

  // ── Tag chip helpers ──

  async _loadAllTags() {
    if (this._allTagsFetched) return;
    try {
      const response = await fetch(this._resolveModelSidecarUrl() + '/api/models');
      if (!response.ok) return;
      const data = await response.json();
      const models = Array.isArray(data.models) ? data.models : [];
      for (const m of models) {
        const kw = Array.isArray(m.keyword_names) ? m.keyword_names : (Array.isArray(m.keywords) ? m.keywords : []);
        for (const t of kw) {
          if (t && !this._knownTags.includes(t)) this._knownTags.push(t);
        }
      }
      this._knownTags.sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }));
      this._allTagsFetched = true;
    } catch (e) {
      // silently fail — picker still works with locally known tags
    }
  }

  _renderTagPicker(currentTags) {
    const pickerState = this._buildTagPickerState(currentTags);
    const options = pickerState.options;
    if (this._tagPickerHighlightIndex < 0 || this._tagPickerHighlightIndex >= options.length) {
      this._tagPickerHighlightIndex = options.length ? 0 : -1;
    }
    return `
      <div class="picker-dd">
        <input class="search-box" type="text" placeholder="Search or create tag…" data-input="tag-search" value="${this._escapeHtml(this._tagSearchQuery)}" />
        ${options.map((option, index) => {
          const selectedClass = index === this._tagPickerHighlightIndex ? ' selected' : '';
          if (option.type === 'create') {
            return `<div class="create-new${selectedClass}" data-action="create-tag" data-tag="${this._escapeHtml(option.value)}">+ Create "${this._escapeHtml(option.value)}"</div>`;
          }
          return `<div class="opt${selectedClass}" data-action="add-tag" data-tag="${this._escapeHtml(option.value)}">${this._escapeHtml(option.label)}</div>`;
        }).join('')}
      </div>
    `;
  }

  _buildTagPickerState(currentTags) {
    const query = String(this._tagSearchQuery || '').trim();
    const queryNormalized = query.toLowerCase();
    const selectedTagSet = new Set((Array.isArray(currentTags) ? currentTags : []).map(tag => String(tag || '').toLowerCase()));
    const suggestions = this._knownTags
      .filter(tag => !selectedTagSet.has(String(tag || '').toLowerCase()))
      .filter(tag => !queryNormalized || String(tag || '').toLowerCase().includes(queryNormalized));
    const exactMatch = selectedTagSet.has(queryNormalized) || suggestions.some(tag => String(tag || '').toLowerCase() === queryNormalized);
    const options = suggestions.map(tag => ({ type: 'tag', value: tag, label: tag }));
    if (query && !exactMatch) {
      options.push({ type: 'create', value: query, label: query });
    }
    return { options: options };
  }

  async _handleTagRemove(tagName) {
    const model = (this._modelDetail && this._modelDetail.model) || {};
    const tags = Array.isArray(model.keywords) ? [...model.keywords] : [];
    const updated = tags.filter(t => t !== tagName);

    // Optimistic update
    if (this._modelDetail && this._modelDetail.model) {
      this._modelDetail.model.keywords = updated;
    }
    this._render();

    try {
      const modelRef = model.model_ref || this._modelRef;
      const response = await fetch(this._resolveModelSidecarUrl() + '/api/models/' + encodeURIComponent(modelRef), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tags: updated }),
      });
      if (!response.ok) throw new Error('Failed to remove tag: ' + response.statusText);
      await this._loadModelDetail({ silent: true });
      this._notifyBrowserDetailChanged();
    } catch (error) {
      console.error('Error removing tag:', error);
      // Revert
      if (this._modelDetail && this._modelDetail.model) {
        this._modelDetail.model.keywords = tags;
      }
      this._render();
    }
  }

  async _handleTagAdd(tagName, options) {
    const addOptions = options && typeof options === 'object' ? options : {};
    const keepPickerOpen = !!addOptions.keepPickerOpen;
    const normalizedTagName = String(tagName || '').trim();
    if (!normalizedTagName) return;
    const model = (this._modelDetail && this._modelDetail.model) || {};
    const tags = Array.isArray(model.keywords) ? [...model.keywords] : [];
    const lowerTagName = normalizedTagName.toLowerCase();
    if (tags.some(tag => String(tag || '').toLowerCase() === lowerTagName)) return;
    const updated = [...tags, normalizedTagName];

    console.log('[TAG-ADD] starting add of', normalizedTagName, '| current keywords:', JSON.stringify(tags), '| updated:', JSON.stringify(updated));

    // Close picker and optimistic update
    this._tagPickerOpen = keepPickerOpen;
    this._tagSearchQuery = "";
    this._tagSearchSelectionStart = null;
    this._tagSearchSelectionEnd = null;
    this._tagPickerHighlightIndex = 0;
    if (this._modelDetail && this._modelDetail.model) {
      this._modelDetail.model.keywords = updated;
    }
    // Track the new tag for future suggestions
    if (!this._knownTags.some(tag => String(tag || '').toLowerCase() === lowerTagName)) {
      this._knownTags.push(normalizedTagName);
      this._knownTags.sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }));
    }
    console.log('[TAG-ADD] before optimistic render | _loading:', this._loading, '| model.keywords:', JSON.stringify(this._modelDetail?.model?.keywords));
    this._render();
    if (keepPickerOpen) {
      requestAnimationFrame(() => {
        const searchBox = this.shadowRoot.querySelector('.picker-dd .search-box');
        if (searchBox) {
          searchBox.focus();
          searchBox.setSelectionRange(searchBox.value.length, searchBox.value.length);
        }
      });
    }
    console.log('[TAG-ADD] after optimistic render | chips in DOM:', this.shadowRoot.querySelectorAll('.tag-chip').length);

    try {
      const modelRef = model.model_ref || this._modelRef;
      const response = await fetch(this._resolveModelSidecarUrl() + '/api/models/' + encodeURIComponent(modelRef), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tags: updated }),
      });
      if (!response.ok) throw new Error('Failed to add tag: ' + response.statusText);
      console.log('[TAG-ADD] PATCH succeeded, loading detail silently');
      await this._loadModelDetail({ silent: true });
      this._notifyBrowserDetailChanged();
      console.log('[TAG-ADD] detail reloaded | model.keywords:', JSON.stringify(this._modelDetail?.model?.keywords), '| chips:', this.shadowRoot.querySelectorAll('.tag-chip').length);
    } catch (error) {
      console.error('Error adding tag:', error);
      // Revert
      if (this._modelDetail && this._modelDetail.model) {
        this._modelDetail.model.keywords = tags;
      }
      this._render();
    } finally {
      if (keepPickerOpen) {
        this._focusTagSearchBox();
      }
    }
  }

  async _handleToggleArchive() {
    const model = (this._modelDetail && this._modelDetail.model) || {};
    const modelRef = model.model_ref || this._modelRef;
    if (!modelRef) return;

    const sm = (model.structured_metadata && model.structured_metadata.catalog_signals) || {};
    const currentVisibility = String(sm.catalog_visibility || 'active').toLowerCase();
    const newVisibility = currentVisibility === 'archived' ? 'active' : 'archived';

    // Optimistic update
    if (this._modelDetail && this._modelDetail.model) {
      const m = this._modelDetail.model;
      if (!m.structured_metadata) m.structured_metadata = {};
      if (!m.structured_metadata.catalog_signals) m.structured_metadata.catalog_signals = {};
      m.structured_metadata.catalog_signals.catalog_visibility = newVisibility;
    }
    this._render();

    try {
      const response = await fetch(this._resolveModelSidecarUrl() + '/api/models/' + encodeURIComponent(modelRef), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          enrichment: {
            structured_metadata: {
              catalog_signals: {
                catalog_visibility: newVisibility,
              },
            },
          },
        }),
      });

      if (!response.ok) {
        let detail = response.statusText;
        try { const body = await response.json(); detail = body.error || JSON.stringify(body); } catch (_) {}
        throw new Error(`${response.status} ${detail}`);
      }

      // Reload to get fresh state
      await this._loadModelDetail({ silent: true });
      this._render();
      this._notifyBrowserDetailChanged();
    } catch (error) {
      console.error('Error toggling archive:', error);
      // Revert optimistic update
      if (this._modelDetail && this._modelDetail.model) {
        const m = this._modelDetail.model;
        if (!m.structured_metadata) m.structured_metadata = {};
        if (!m.structured_metadata.catalog_signals) m.structured_metadata.catalog_signals = {};
        m.structured_metadata.catalog_signals.catalog_visibility = currentVisibility;
      }
      this._render();
      if (this._hass) {
        this._hass.callService('persistent_notification', 'create', {
          title: 'Archive toggle failed',
          message: `Failed to update archive status: ${error.message}`,
        }).catch(err => console.error('Notification failed:', err));
      }
    }
  }

  async _handleToggleFrequent() {
    const model = (this._modelDetail && this._modelDetail.model) || {};
    const modelRef = model.model_ref || this._modelRef;
    if (!modelRef) return;

    const frequentState = this._resolveFrequentState(model);
    const currentOverride = frequentState.manualOverride;
    const nextOverride = currentOverride === true ? null : true;

    // Optimistic update so button state changes immediately.
    if (this._modelDetail && this._modelDetail.model) {
      const m = this._modelDetail.model;
      if (!m.structured_metadata) m.structured_metadata = {};
      if (!m.structured_metadata.catalog_signals) m.structured_metadata.catalog_signals = {};
      if (nextOverride === null) {
        delete m.structured_metadata.catalog_signals.model_frequent_override;
      } else {
        m.structured_metadata.catalog_signals.model_frequent_override = true;
      }
    }
    this._render();

    try {
      const response = await fetch(this._resolveModelSidecarUrl() + '/api/models/' + encodeURIComponent(modelRef), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          enrichment: {
            structured_metadata: {
              catalog_signals: {
                model_frequent_override: nextOverride,
              },
            },
          },
        }),
      });

      if (!response.ok) {
        let detail = response.statusText;
        try { const body = await response.json(); detail = body.error || JSON.stringify(body); } catch (_) {}
        throw new Error(`${response.status} ${detail}`);
      }

      await this._loadModelDetail({ silent: true });
      this._render();
      this._notifyBrowserDetailChanged();
    } catch (error) {
      console.error('Error toggling frequent override:', error);
      if (this._modelDetail && this._modelDetail.model) {
        const m = this._modelDetail.model;
        if (!m.structured_metadata) m.structured_metadata = {};
        if (!m.structured_metadata.catalog_signals) m.structured_metadata.catalog_signals = {};
        if (currentOverride === null) {
          delete m.structured_metadata.catalog_signals.model_frequent_override;
        } else {
          m.structured_metadata.catalog_signals.model_frequent_override = currentOverride;
        }
      }
      this._render();
      if (this._hass) {
        this._hass.callService('persistent_notification', 'create', {
          title: 'Frequent toggle failed',
          message: `Failed to update frequent status: ${error.message}`,
        }).catch(err => console.error('Notification failed:', err));
      }
    }
  }

  async _handleDeleteModel() {
    if (!this._modelDetail || !this._hass) return;

    const model = this._modelDetail.model || {};
    const localModelId = String((this._modelDetail && this._modelDetail.local_model_id) || this._modelRef || '').trim();
    const modelName = String(model.name || this._modelRef || 'Model').trim();
    const linkedCount = Number(this._modelDetail.linked_archive_count || 0);

    if (!localModelId) {
      this._error = "Could not identify model for deletion.";
      this._render();
      return;
    }

    // Build warning message about what will be deleted
    const warningLines = [
      `Delete ${modelName} from the Model Catalog?`,
      "",
      "This will delete:",
      "• Model metadata and database entries",
      "• All stored model files and assets",
    ];

    if (linkedCount > 0) {
      warningLines.push(
        "",
        `This model has ${linkedCount} linked print archive${linkedCount === 1 ? "" : "s"}. The archives will NOT be deleted, but the model reference will be removed.`
      );
    }

    warningLines.push("", "This action cannot be undone.");

    const confirmMsg = warningLines.join("\n");
    if (!window.confirm(confirmMsg)) {
      return;
    }

    // Proceed with deletion
    await this._executeModelDeletion(localModelId);
  }

  async _executeModelDeletion(localModelId) {
    if (!this._hass || !localModelId) {
      return;
    }

    try {
      this._loading = true;
      this._error = "";
      this._render();

      const sidecarUrl = this._resolveModelSidecarUrl();
      if (!sidecarUrl) {
        throw new Error("Model Catalog sidecar URL not configured");
      }

      const auth = this._hass && this._hass.auth ? this._hass.auth : null;
      if (!auth) {
        throw new Error("Not authenticated with Home Assistant");
      }

      const deleteUrl = sidecarUrl + "/api/local/models/" + encodeURIComponent(localModelId) + "?hard_delete=false";
      const response = await fetch(deleteUrl, {
        method: "DELETE",
        headers: {
          "Authorization": "Bearer " + auth.accessToken,
          "Content-Type": "application/json",
        },
      });

      if (!response.ok) {
        let errorData = null;
        try {
          errorData = await response.json();
        } catch (_) {
          errorData = { error: "Unknown error", status: response.status };
        }
        const errorMsg = errorData && errorData.error ? String(errorData.error) : "HTTP " + String(response.status);
        throw new Error("Delete failed: " + errorMsg);
      }

      const result = await response.json();
      if (!result.success) {
        throw new Error(result.error || "Delete operation failed");
      }

      this._loading = false;
      this._error = "";

      // Show success notification
      try {
        await this._hass.callService("persistent_notification", "create", {
          title: "Model Deleted",
          message: "Model successfully deleted from the catalog.",
          notification_id: "model_catalog_delete_success",
        });
      } catch (err) {
        console.error('Notification failed:', err);
      }

      // Close the popup by triggering a browser_mod command to close
      // First, emit an event that the browser card can listen for
      this.dispatchEvent(new CustomEvent('model-deleted', { detail: { modelRef: this._modelRef } }));

      // Then close this popup window
      if (window && window.parent) {
        try {
          window.parent.postMessage({ type: 'close-popup' }, '*');
        } catch (_) {
          // If we can't communicate with parent, just wait for event handler
        }
      }

      // Also trigger a re-render to show the deletion state
      this._modelDetail = null;
      this._render();

    } catch (error) {
      console.error('Delete failed:', error);
      this._loading = false;
      this._error = `Delete failed: ${error.message}`;
      this._render();

      if (this._hass) {
        this._hass.callService('persistent_notification', 'create', {
          title: 'Model Delete Failed',
          message: `Failed to delete model: ${error.message}`,
          notification_id: 'model_catalog_delete_failed',
        }).catch(err => console.error('Notification failed:', err));
      }
    }
  }

  _handlePhotoPreview(photoIdx) {
    const galleryItems = this._heroOrderMediaItems(this._galleryItems());
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
    const galleryItems = this._heroOrderMediaItems(this._galleryItems());
    
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

    if (this._supportImagePreview) {
      if (target.closest('[data-action="support-preview-close"]')) {
        event.preventDefault();
        this._closeSupportingImagePreview();
        return;
      }
      if (target.closest('[data-action="support-preview-prev"]')) {
        event.preventDefault();
        this._stepSupportingImagePreview(-1);
        return;
      }
      if (target.closest('[data-action="support-preview-next"]')) {
        event.preventDefault();
        this._stepSupportingImagePreview(1);
        return;
      }
      if (target.closest('[data-action="support-preview-open-tab"]')) {
        event.preventDefault();
        this._openSupportingPreviewImageInNewTab();
        return;
      }
      const supportThumb = target.closest('[data-support-preview-index]');
      if (supportThumb) {
        event.preventDefault();
        const idx = parseInt(String(supportThumb.getAttribute('data-support-preview-index') || ''), 10);
        if (Number.isFinite(idx)) {
          this._supportImagePreview.index = idx;
          this._renderSupportingImageOverlay();
        }
        return;
      }
    }

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
    } else if (this._supportImagePreview) {
      this._closeSupportingImagePreview();
    } else {
      this._closePhotoPreview();
    }
  }

  _commitTagPickerSelection() {
    const model = (this._modelDetail && this._modelDetail.model) || {};
    const tags = Array.isArray(model.keywords) ? model.keywords : [];
    const options = this._buildTagPickerState(tags).options;
    const selected = options[this._tagPickerHighlightIndex] || null;
    if (selected && selected.value) {
      this._handleTagAdd(selected.value, { keepPickerOpen: true });
      return true;
    }
    const q = this._tagSearchQuery.trim();
    if (q) {
      this._handleTagAdd(q, { keepPickerOpen: true });
      return true;
    }
    return false;
  }

  _commitCollectionPickerSelection() {
    const options = this._buildCollectionPickerState(this._selectedCollectionMemberships()).options;
    const selected = options[this._collectionPickerHighlightIndex] || null;
    if (selected && selected.type === 'collection' && selected.value) {
      this._handleCollectionAdd(selected.value);
      return true;
    }
    if (selected && selected.type === 'create') {
      this._handleCollectionCreate();
      return true;
    }
    if (this._collectionSearchQuery.trim()) {
      this._handleCollectionCreate();
      return true;
    }
    return false;
  }

  _commitProjectPickerSelection() {
    const options = this._buildProjectPickerState(this._selectedProjectMemberships()).options;
    const selected = options[this._projectPickerHighlightIndex] || null;
    if (selected && selected.type === 'project' && selected.value) {
      this._handleProjectAdd(selected.value);
      return true;
    }
    if (selected && selected.type === 'create') {
      this._handleProjectCreate();
      return true;
    }
    if (this._projectSearchQuery.trim()) {
      this._handleProjectCreate();
      return true;
    }
    return false;
  }

  _handleKeydown(event) {
    if (this._projectPickerOpen) {
      const rawTarget = event.composedPath ? event.composedPath()[0] : event.target;
      const isProjectSearch = rawTarget instanceof HTMLInputElement && rawTarget.dataset && rawTarget.dataset.input === 'project-search';
      if ((event.key === 'ArrowDown' || event.key === 'ArrowUp' || event.key === 'Home' || event.key === 'End') && isProjectSearch) {
        const options = this._buildProjectPickerState(this._selectedProjectMemberships()).options;
        if (options.length) {
          event.preventDefault();
          this._projectSearchSelectionStart = Number.isFinite(rawTarget.selectionStart) ? rawTarget.selectionStart : this._projectSearchQuery.length;
          this._projectSearchSelectionEnd = Number.isFinite(rawTarget.selectionEnd) ? rawTarget.selectionEnd : this._projectSearchSelectionStart;
          if (event.key === 'ArrowDown') {
            this._projectPickerHighlightIndex = Math.min(this._projectPickerHighlightIndex + 1, options.length - 1);
          } else if (event.key === 'ArrowUp') {
            this._projectPickerHighlightIndex = Math.max(this._projectPickerHighlightIndex - 1, 0);
          } else if (event.key === 'Home') {
            this._projectPickerHighlightIndex = 0;
          } else if (event.key === 'End') {
            this._projectPickerHighlightIndex = options.length - 1;
          }
          this._render();
          this._focusProjectSearchBox();
        }
        return;
      }
      if (event.key === 'Escape') {
        event.preventDefault();
        this._projectPickerOpen = false;
        this._projectSearchQuery = '';
        this._projectSearchSelectionStart = null;
        this._projectSearchSelectionEnd = null;
        this._projectPickerHighlightIndex = 0;
        this._render();
        return;
      }
      if ((event.key === 'Enter' || event.key === 'Tab') && isProjectSearch) {
        const committed = this._commitProjectPickerSelection();
        if (!committed && event.key === 'Tab') {
          return;
        }
        event.preventDefault();
        return;
      }
    }

    if (this._collectionPickerOpen) {
      const rawTarget = event.composedPath ? event.composedPath()[0] : event.target;
      const isCollectionSearch = rawTarget instanceof HTMLInputElement && rawTarget.dataset && rawTarget.dataset.input === 'collection-search';
      if ((event.key === 'ArrowDown' || event.key === 'ArrowUp' || event.key === 'Home' || event.key === 'End') && isCollectionSearch) {
        const options = this._buildCollectionPickerState(this._selectedCollectionMemberships()).options;
        if (options.length) {
          event.preventDefault();
          this._collectionSearchSelectionStart = Number.isFinite(rawTarget.selectionStart) ? rawTarget.selectionStart : this._collectionSearchQuery.length;
          this._collectionSearchSelectionEnd = Number.isFinite(rawTarget.selectionEnd) ? rawTarget.selectionEnd : this._collectionSearchSelectionStart;
          if (event.key === 'ArrowDown') {
            this._collectionPickerHighlightIndex = Math.min(this._collectionPickerHighlightIndex + 1, options.length - 1);
          } else if (event.key === 'ArrowUp') {
            this._collectionPickerHighlightIndex = Math.max(this._collectionPickerHighlightIndex - 1, 0);
          } else if (event.key === 'Home') {
            this._collectionPickerHighlightIndex = 0;
          } else if (event.key === 'End') {
            this._collectionPickerHighlightIndex = options.length - 1;
          }
          this._render();
          this._focusCollectionSearchBox();
        }
        return;
      }
      if (event.key === 'Escape') {
        event.preventDefault();
        this._collectionPickerOpen = false;
        this._collectionSearchQuery = '';
        this._collectionSearchSelectionStart = null;
        this._collectionSearchSelectionEnd = null;
        this._collectionPickerHighlightIndex = 0;
        this._render();
        return;
      }
      if ((event.key === 'Enter' || event.key === 'Tab') && isCollectionSearch) {
        const committed = this._commitCollectionPickerSelection();
        if (!committed && event.key === 'Tab') {
          return;
        }
        event.preventDefault();
        return;
      }
    }

    // Tag picker: Enter/Tab/comma to add/create, arrows and Home/End to navigate, Escape to close
    if (this._tagPickerOpen) {
      // Use composedPath()[0] to get the real target inside shadow DOM (event.target at document level is the host element)
      const _cpTarget = event.composedPath ? event.composedPath()[0] : event.target;
      const _isTagSearch = _cpTarget instanceof HTMLInputElement && _cpTarget.dataset && _cpTarget.dataset.input === 'tag-search';
      if ((event.key === 'ArrowDown' || event.key === 'ArrowUp' || event.key === 'Home' || event.key === 'End') && _isTagSearch) {
        const model = (this._modelDetail && this._modelDetail.model) || {};
        const tags = Array.isArray(model.keywords) ? model.keywords : [];
        const options = this._buildTagPickerState(tags).options;
        if (options.length) {
          event.preventDefault();
          if (event.key === 'ArrowDown') {
            this._tagPickerHighlightIndex = Math.min(this._tagPickerHighlightIndex + 1, options.length - 1);
          } else if (event.key === 'ArrowUp') {
            this._tagPickerHighlightIndex = Math.max(this._tagPickerHighlightIndex - 1, 0);
          } else if (event.key === 'Home') {
            this._tagPickerHighlightIndex = 0;
          } else if (event.key === 'End') {
            this._tagPickerHighlightIndex = options.length - 1;
          }
          this._render();
          requestAnimationFrame(() => {
            const searchBox = this.shadowRoot.querySelector('.picker-dd .search-box');
            if (searchBox) searchBox.focus();
          });
        }
        return;
      }
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        if (event.stopImmediatePropagation) {
          event.stopImmediatePropagation();
        }
        this._tagPickerOpen = false;
        this._tagSearchQuery = "";
        this._tagSearchSelectionStart = null;
        this._tagSearchSelectionEnd = null;
        this._tagPickerHighlightIndex = 0;
        this._render();
        return;
      }
      if ((event.key === 'Enter' || event.key === 'Tab' || event.key === ',') && _isTagSearch) {
        const committed = this._commitTagPickerSelection();
        if (!committed && event.key === 'Tab') {
          return;
        }
        event.preventDefault();
        return;
      }
    }

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

    if (this._supportImagePreview) {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        this._closeSupportingImagePreview();
      } else if (event.key === 'ArrowLeft') {
        event.preventDefault();
        this._stepSupportingImagePreview(-1);
      } else if (event.key === 'ArrowRight') {
        event.preventDefault();
        this._stepSupportingImagePreview(1);
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

    const galleryItems = this._heroOrderMediaItems(this._galleryItems());
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
      this._notifyBrowserDetailChanged();
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
      this._notifyBrowserDetailChanged();
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
  
  async _handleSupportingFileSelect(files) {
    if (!files || files.length === 0) return;

    for (const file of files) {
      await this._uploadSupportingFile(file);
    }
  }

  async _uploadSupportingFile(file) {
    if (!this._modelSidecarUrl || !this._modelRef) return;

    const maxSize = 100 * 1024 * 1024;
    if (file.size > maxSize) {
      this._error = `File too large: ${file.name} (max 100MB)`;
      this._render();
      return;
    }

    try {
      const formData = new FormData();
      formData.append('file', file, file.name || 'upload.bin');

      const response = await fetch(
        `${this._modelSidecarUrl.replace(/\/$/, '')}/api/models/${encodeURIComponent(this._modelRef)}/supporting-files`,
        {
          method: 'POST',
          body: formData,
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
      this._notifyBrowserDetailChanged();
    } catch (error) {
      console.error('Error uploading supporting file:', error);
      this._error = `Failed to upload ${file.name}: ${error}`;
      this._render();
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
      this._notifyBrowserDetailChanged();
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

  _handleCreateArchiveFromSource() {
    if (!this._hass) {
      console.warn('Home Assistant instance not available');
      return;
    }
    if (!this._modelDetail || !this._modelDetail.model) {
      console.warn('No model detail available for archive creation');
      return;
    }
    var model = this._modelDetail.model;
    var modelName = String(model.name || this._modelRef || "Model").trim() || "Model";
    var modelEntity = 'input_text.model_catalog_sidecar_base_url';

    this._replaceCurrentPopup({
      title: 'Create Archive From Source: ' + modelName,
      size: 'wide',
      content: {
        type: 'custom:slicer-wizard-card',
        model_ref: this._modelRef,
        model_entity: modelEntity
      }
    });
  }

  _handlePrint() {
    if (!this._modelDetail || !this._modelDetail.model) {
      console.warn('No model detail available for print');
      return;
    }
    var model = this._modelDetail.model;
    var modelName = String(model.name || this._modelRef || "Model").trim() || "Model";
    // Match list-view behavior: always open the unified Add to Queue dialog.
    this._listUnifiedQueueEntriesForModel(this._modelRef).then(function (entries) {
      this._openQueueDialog(this._modelRef, modelName, entries, { intent: "add", defaultState: "up_next" });
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
    this._queueDialogEntityType = String(model.entity_type || "model").trim().toLowerCase() || "model";
    var files = Array.isArray(model.files) ? model.files.filter(file => this._isQueueDialogEligibleFile(file)) : [];
    if (!files.length) {
      // Idea entities and file-less models are still queueable: return an empty
      // file list so the dialog can submit an idea-style entry.
      return [];
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

  _isQueueDialogIdeaMode() {
    if (this._queueDialogLoading) return false;
    if (String(this._queueDialogEntityType || "").toLowerCase() === "idea") return true;
    return !Array.isArray(this._queueDialogFiles) || this._queueDialogFiles.length === 0;
  }

  _canSubmitQueueDialog() {
    if (this._queueDialogLoading || this._queueDialogSubmitting) return false;
    if (this._isQueueDialogIdeaMode()) return !!this._queueDialogModelRef;
    if (!Array.isArray(this._queueDialogFiles) || this._queueDialogFiles.length === 0) return false;
    if (this._queueDialogMode !== "plan") return true;
    return this._getQueueDialogMetrics().selectedPlates > 0;
  }

  _queueDialogPrimarySummary() {
    if (this._queueDialogLoading) return "Loading queue defaults...";
    if (this._isQueueDialogIdeaMode()) {
      var ideaState = this._queueDialogMode === "quick"
        ? "up_next"
        : this._normalizeQueueDialogTargetState(this._queueDialogTargetState);
      return "Will queue idea " + String(this._queueDialogModelName || "Idea")
        + " on " + this._getPrinterId()
        + " in state " + this._queueDialogTargetStateLabel(ideaState)
        + " (no files to select).";
    }
    if (!Array.isArray(this._queueDialogFiles) || !this._queueDialogFiles.length) return "Loading queue defaults...";
    var primaryFile = this._queueDialogFiles[0] || {};
    var primaryPlate = Array.isArray(primaryFile.plates) && primaryFile.plates.length > 0 ? primaryFile.plates[0] : null;
    return "Will queue " + String(primaryFile.file_name || "Primary file") + " · " + String(primaryPlate && primaryPlate.plate_name ? primaryPlate.plate_name : "Primary Plate") + " on " + this._getPrinterId() + " in state " + this._queueDialogTargetStateLabel("up_next") + ".";
  }

  async _submitQueueDialog() {
    if (!this._queueDialogModelRef || this._queueDialogLoading || this._queueDialogSubmitting) return;
    var ideaMode = this._isQueueDialogIdeaMode();
    if (!this._canSubmitQueueDialog()) {
      this._queueDialogError = ideaMode
        ? "Cannot add to queue right now."
        : (this._queueDialogMode === "plan" ? "Select at least one file plate before adding to queue." : "No queueable files were found for this model.");
      this._render();
      return;
    }
    var targetState = (ideaMode || this._queueDialogMode === "quick")
      ? "up_next"
      : this._normalizeQueueDialogTargetState(this._queueDialogTargetState);
    var payload;
    if (ideaMode) {
      var ideaSourceKind = String(this._queueDialogEntityType || "").toLowerCase() === "idea"
        ? "idea"
        : "catalog_model";
      payload = {
        source_kind: ideaSourceKind,
        source_id: this._queueDialogModelRef,
        title: this._queueDialogModelName,
        state: targetState,
        queue_notes: String(this._queueDialogNotes || "").trim(),
      };
    } else {
      var primaryFile = this._queueDialogFiles[0] || {};
      var primaryPlate = Array.isArray(primaryFile.plates) && primaryFile.plates.length > 0 ? primaryFile.plates[0] : null;
      payload = {
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
    var ideaMode = this._isQueueDialogIdeaMode();
    var existingNote = this._queueDialogExistingCount > 0
      ? '<div class="queue-dialog-existing-note">This model already has ' + this._escapeHtml(String(this._queueDialogExistingCount)) + ' queue entr' + (this._queueDialogExistingCount === 1 ? 'y' : 'ies') + '. A new entry will be created.</div>'
      : "";
    var ideaNote = ideaMode
      ? '<div class="queue-dialog-note">This entry has no printable files. It will be added as an idea-style queue entry — set a target state and notes below.</div>'
      : "";
    var planBody = this._queueDialogLoading
      ? '<div class="queue-dialog-note">Loading model files and plates...</div>'
      : this._queueDialogFiles.length === 0
      ? ''
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
      + (ideaMode
          ? ''
          : '      <button class="queue-dialog-tab' + (this._queueDialogMode === 'quick' ? ' active' : '') + '" type="button" data-action="queue-dialog-mode" data-mode="quick">Quick</button>'
            + '      <button class="queue-dialog-tab' + (this._queueDialogMode === 'plan' ? ' active' : '') + '" type="button" data-action="queue-dialog-mode" data-mode="plan">Plan</button>')
      + '    </div>'
      + '    <div class="queue-dialog-body">'
      + existingNote
      + ideaNote
      + (ideaMode
          ? '<div class="queue-dialog-summary">' + this._escapeHtml(this._queueDialogPrimarySummary()) + '</div>'
            + '<label class="queue-dialog-field"><span>Target state</span><select class="queue-dialog-target-state"><option value="backlog"' + (this._queueDialogTargetState === 'backlog' ? ' selected' : '') + '>Backlog</option><option value="up_next"' + (this._queueDialogTargetState === 'up_next' ? ' selected' : '') + '>Up Next</option><option value="preparing"' + (this._queueDialogTargetState === 'preparing' ? ' selected' : '') + '>Preparing</option><option value="ready"' + (this._queueDialogTargetState === 'ready' ? ' selected' : '') + '>Ready</option></select></label>'
            + '<label class="queue-dialog-field"><span>Notes</span><textarea class="queue-dialog-notes" data-queue-dialog-notes="true" rows="3" placeholder="Optional operator notes...">' + this._escapeHtml(this._queueDialogNotes) + '</textarea></label>'
          : (this._queueDialogMode === 'quick'
              ? '<div class="queue-dialog-summary">' + this._escapeHtml(this._queueDialogPrimarySummary()) + '</div>'
              : '<div class="queue-dialog-summary">Choose plates, target state, and notes before creating the queue entry.</div>'
                + '<label class="queue-dialog-field"><span>Target state</span><select class="queue-dialog-target-state"><option value="backlog"' + (this._queueDialogTargetState === 'backlog' ? ' selected' : '') + '>Backlog</option><option value="up_next"' + (this._queueDialogTargetState === 'up_next' ? ' selected' : '') + '>Up Next</option><option value="preparing"' + (this._queueDialogTargetState === 'preparing' ? ' selected' : '') + '>Preparing</option><option value="ready"' + (this._queueDialogTargetState === 'ready' ? ' selected' : '') + '>Ready</option></select></label>'
                + '<label class="queue-dialog-field"><span>Notes</span><textarea class="queue-dialog-notes" data-queue-dialog-notes="true" rows="3" placeholder="Optional operator notes...">' + this._escapeHtml(this._queueDialogNotes) + '</textarea></label>'
                + '<div class="queue-dialog-metrics">Selected ' + this._escapeHtml(String(metrics.selectedPlates)) + ' plates across ' + this._escapeHtml(String(metrics.selectedFiles)) + ' files.</div>'
                + planBody))
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

  _focusProjectInBrowser(projectId) {
    const normalizedProjectId = parseInt(String(projectId || '').trim(), 10);
    if (!Number.isFinite(normalizedProjectId) || normalizedProjectId <= 0) {
      return;
    }
    try {
      window.dispatchEvent(new CustomEvent('model-catalog-project-focus', {
        detail: { projectId: normalizedProjectId, scope: 'projects' },
      }));
    } catch (_e) { /* ignore */ }
    this._fireBrowserModEvent('browser_mod.close_popup', {});
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
      this._notifyBrowserDetailChanged();
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
    } else if (fieldKey === 'source_download_url') {
      sm.provenance.source_download_url = value;
    } else if (fieldKey === 'published_urls') {
      sm.publishing.published_urls = value;
    } else {
      this._setCustomFieldLocally(fieldKey, value);
    }
  }

  async _syncSourceUrlMediaState(sourceUrls) {
    const urls = Array.isArray(sourceUrls) ? sourceUrls : [];
    const normalizedImageUrls = urls
      .map(url => String(url || '').trim())
      .filter(url => this._isLikelyImageUrl(url))
      .map(url => this._normalizeComparableUrl(url))
      .filter(Boolean);
    const imageUrlSet = new Set(normalizedImageUrls);
    const validSourceMediaIds = new Set(normalizedImageUrls.map(url => this._sourceUrlMediaId(url)).filter(Boolean));

    const hiddenIds = this._hiddenMediaIdSet();
    const cleanedHiddenIds = Array.from(hiddenIds).filter(mediaId => {
      const id = String(mediaId || '').trim();
      if (!id.startsWith('source_url:')) {
        return true;
      }
      return validSourceMediaIds.has(id);
    });
    if (cleanedHiddenIds.length !== hiddenIds.size) {
      await this._saveSourceField(this._heroHiddenMediaFieldKey, cleanedHiddenIds);
    }

    const previewUrl = this._sourcePreviewUrl();
    if (previewUrl && !imageUrlSet.has(previewUrl)) {
      await this._saveSourceField(this._heroSourcePreviewFieldKey, null);
    }
  }

  _getSourceUrls() {
    const model = this._modelDetail?.model;
    if (!model) return [];
    const metadata = model.structured_metadata || this._modelDetail?.enrichment?.structured_metadata || {};
    const provenance = metadata.provenance || {};
    const publishing = metadata.publishing || {};
    const explicitUrls = Array.isArray(provenance.source_urls)
      ? provenance.source_urls.map((u) => this._normalizeSourceUrlValue(u)).filter(Boolean)
      : [];
    const published_urls = publishing.published_urls || {};
    const legacyUrls = Object.values(published_urls)
      .map((u) => this._normalizeSourceUrlValue(u))
      .filter((u) => typeof u === 'string' && u.startsWith('http'));
    const normalizedDownloadUrl = this._normalizeSourceUrlValue(provenance.source_download_url);
    const downloadUrl = normalizedDownloadUrl && normalizedDownloadUrl.startsWith('http') ? normalizedDownloadUrl : null;
    const seen = new Set(explicitUrls);
    const merged = [...explicitUrls];
    if (downloadUrl && !seen.has(downloadUrl)) { merged.push(downloadUrl); seen.add(downloadUrl); }
    for (const u of legacyUrls) { if (!seen.has(u)) { merged.push(u); seen.add(u); } }
    return merged;
  }

  async _addSourceUrl() {
    const urls = this._getSourceUrls();
    urls.push('https://');
    await this._saveSourceField('source_urls', urls);
    await this._syncSourceUrlMediaState(urls);
    const newIndex = urls.length - 1;
    requestAnimationFrame(() => {
      const input = this.shadowRoot
        ? this.shadowRoot.querySelector(`.source-url-input[data-source-url-index="${newIndex}"]`)
        : null;
      if (input && typeof input.focus === 'function') {
        input.focus();
        if (typeof input.setSelectionRange === 'function') {
          input.setSelectionRange(0, String(input.value || '').length);
        }
      }
    });
  }

  async _extract3mfMetadata() {
    const localModelId = this._modelDetail?.local_model_id || this._modelDetail?.model_ref;
    if (!localModelId) return;
    const base = this._resolveModelSidecarUrl();
    const btn = this.shadowRoot?.querySelector('.extract-3mf-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Extracting…'; }
    try {
      const resp = await fetch(
        `${base}/api/local/models/${encodeURIComponent(localModelId)}/extract-3mf-metadata`,
        { method: 'POST' }
      );
      const result = await resp.json();
      if (!resp.ok) {
        alert(result.error || 'Failed to extract 3MF metadata');
        return;
      }
      // Refresh model detail to pick up new fields
      await this._loadModelDetail({ silent: true });
    } catch (err) {
      alert('Error extracting 3MF metadata: ' + err.message);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '📦 Extract from 3MF'; }
    }
  }

  async _removeSourceUrl(index) {
    const urls = this._getSourceUrls();
    if (index < 0 || index >= urls.length) return;
    const url = urls[index];
    const confirmMsg = url ? `Remove URL "${url}"?` : 'Remove this empty URL entry?';
    if (!confirm(confirmMsg)) return;

    // Check if the removed URL matches source_download_url or published_urls
    // so we clear the origin field — otherwise _getSourceUrls() re-merges it back.
    const model = this._modelDetail?.model;
    const metadata = model?.structured_metadata || this._modelDetail?.enrichment?.structured_metadata || {};
    const provenance = metadata.provenance || {};
    const publishing = metadata.publishing || {};
    const downloadUrl = this._normalizeSourceUrlValue(provenance.source_download_url);
    const published_urls = publishing.published_urls || {};

    if (url && url === downloadUrl) {
      await this._saveSourceField('source_download_url', null);
    }
    const matchingKeys = Object.entries(published_urls)
      .filter(([, v]) => this._normalizeSourceUrlValue(v) === url)
      .map(([k]) => k);
    if (matchingKeys.length > 0) {
      const updated = { ...published_urls };
      for (const k of matchingKeys) delete updated[k];
      await this._saveSourceField('published_urls', updated);
    }

    urls.splice(index, 1);
    await this._saveSourceField('source_urls', urls);
    await this._syncSourceUrlMediaState(urls);
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
    urls[index] = this._normalizeSourceUrlValue(newValue);
    await this._saveSourceField('source_urls', urls);
    await this._syncSourceUrlMediaState(urls);
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
