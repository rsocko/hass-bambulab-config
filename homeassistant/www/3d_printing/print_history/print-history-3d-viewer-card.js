const PRINT_HISTORY_VIEWER_CDN_MODULE_URL = "https://cdn.jsdelivr.net/npm/gcode-preview@2.18.0/+esm";
const CROP_PRESETS = {
  free: null,
  square: 1,
  landscape4x3: 4 / 3,
  landscape16x9: 16 / 9,
};

class PrintHistory3dViewerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._loadToken = 0;
    this._loadedSignature = "";
    this._preview = null;
    this._capture = null;
    this._uploadInProgress = false;
    this._rendererMode = "gcode";
    this._renderAnimated = false;
    this._totalLayers = 0;
    this._resolvedBuildVolume = { x: 256, y: 256, z: 256 };
    this._resolvedNozzleDiameter = 0.4;
    this._viewerSettings = {
      showLayerScrubber: true,
      endLayer: null,
      renderBuildVolume: true,
      buildVolumeX: null,
      buildVolumeY: null,
      buildVolumeZ: null,
      backgroundColor: "#08101A",
      gridColor: "#888888",
      renderTubes: false,
      extrusionWidth: null,
      lineWidth: 1,
      useFixedLineHeight: false,
      lineHeight: 0.2,
      showTravelMoves: false,
      travelColor: "#990000",
      useColorGradient: false,
    };
    this._configurationPanelOpen = false;
    this._previewRerenderTimer = null;
    this._layerScrubberTimer = null;
    this._pendingCameraState = null;
    this._cropMode = false;
    this._cropAspectPreset = "square";
    this._cropRect = null;
    this._cropDrag = null;
    this._globalListenersAttached = false;
    this._refreshButton = null;
    this._animateButton = null;
    this._configurationButton = null;
    this._configurationPanel = null;
    this._lineWidthRange = null;
    this._lineWidthValue = null;
    this._lineHeightToggleButton = null;
    this._lineHeightRange = null;
    this._lineHeightValue = null;
    this._layerScrubberToggleButton = null;
    this._layerScrubberPanel = null;
    this._layerScrubberEndRange = null;
    this._buildVolumeToggleButton = null;
    this._buildVolumeXInput = null;
    this._buildVolumeYInput = null;
    this._buildVolumeZRange = null;
    this._buildVolumeZValue = null;
    this._backgroundColorInput = null;
    this._gridColorInput = null;
    this._tubeToggleButton = null;
    this._tubeWidthRange = null;
    this._tubeWidthValue = null;
    this._travelToggleButton = null;
    this._travelColorInput = null;
    this._gradientToggleButton = null;
    this._captureButton = null;
    this._cropToggleButton = null;
    this._cropAspectSelect = null;
    this._resetCropButton = null;
    this._cancelCropButton = null;
    this._cropLayer = null;
    this._capturePanel = null;
    this._downloadCaptureButton = null;
    this._uploadCaptureButton = null;
    this._boundRefreshHandler = this._handleRefresh.bind(this);
    this._boundAnimateHandler = this._handleAnimate.bind(this);
    this._boundConfigurationPanelToggleHandler = this._handleConfigurationPanelToggle.bind(this);
    this._boundLineWidthInputHandler = this._handleLineWidthInput.bind(this);
    this._boundLineHeightToggleHandler = this._handleLineHeightToggle.bind(this);
    this._boundLineHeightInputHandler = this._handleLineHeightInput.bind(this);
    this._boundLayerScrubberToggleHandler = this._handleLayerScrubberToggle.bind(this);
    this._boundLayerScrubberInputHandler = this._handleLayerScrubberInput.bind(this);
    this._boundBuildVolumeToggleHandler = this._handleBuildVolumeToggle.bind(this);
    this._boundBuildVolumeDimensionInputHandler = this._handleBuildVolumeDimensionInput.bind(this);
    this._boundBuildVolumeZInputHandler = this._handleBuildVolumeZInput.bind(this);
    this._boundBackgroundColorInputHandler = this._handleBackgroundColorInput.bind(this);
    this._boundGridColorInputHandler = this._handleGridColorInput.bind(this);
    this._boundTubeToggleHandler = this._handleTubeToggle.bind(this);
    this._boundTubeWidthInputHandler = this._handleTubeWidthInput.bind(this);
    this._boundTravelToggleHandler = this._handleTravelToggle.bind(this);
    this._boundTravelColorInputHandler = this._handleTravelColorInput.bind(this);
    this._boundGradientToggleHandler = this._handleGradientToggle.bind(this);
    this._boundCaptureHandler = this._handleCapture.bind(this);
    this._boundCropToggleHandler = this._handleCropToggle.bind(this);
    this._boundCropAspectChangeHandler = this._handleCropAspectChange.bind(this);
    this._boundResetCropHandler = this._handleResetCrop.bind(this);
    this._boundCancelCropHandler = this._handleCancelCrop.bind(this);
    this._boundCropPointerDownHandler = this._handleCropPointerDown.bind(this);
    this._boundWindowPointerDownHandler = this._handleWindowPointerDown.bind(this);
    this._boundWindowPointerMoveHandler = this._handleWindowPointerMove.bind(this);
    this._boundWindowPointerUpHandler = this._handleWindowPointerUp.bind(this);
    this._boundWindowResizeHandler = this._handleWindowResize.bind(this);
    this._boundDownloadCaptureHandler = this._downloadCapture.bind(this);
    this._boundUploadCaptureHandler = this._handleUploadCapture.bind(this);
  }

  setConfig(config) {
    if (!config || config.archive_id == null || String(config.archive_id).trim() === "") {
      throw new Error("print-history-3d-viewer-card requires archive_id");
    }
    this._config = {
      archive_id: String(config.archive_id).trim(),
      archive_name: String(config.archive_name || "").trim(),
      archive: this._parseArchiveConfig(config.archive_json || config.archive || null),
      entry_id: String(config.entry_id || "").trim(),
    };
    this._renderAnimated = false;
    this._totalLayers = 0;
    this._viewerSettings.endLayer = null;
    this._loadedSignature = "";
    this._renderShell();
    this._maybeLoad();
  }

  set hass(hass) {
    this._hass = hass;
    this._maybeLoad();
  }

  connectedCallback() {
    this._attachGlobalListeners();
    this._maybeLoad();
  }

  disconnectedCallback() {
    this._disposePreview(true);
    this._revokeCapture();
    this._detachShellListeners();
    this._detachGlobalListeners();
  }

  getCardSize() {
    return 18;
  }

  _handleRefresh() {
    this._loadedSignature = "";
    this._maybeLoad();
  }

  _detachShellListeners() {
    if (this._refreshButton) {
      this._refreshButton.removeEventListener("click", this._boundRefreshHandler);
      this._refreshButton = null;
    }
    if (this._animateButton) {
      this._animateButton.removeEventListener("click", this._boundAnimateHandler);
      this._animateButton = null;
    }
    if (this._configurationButton) {
      this._configurationButton.removeEventListener("click", this._boundConfigurationPanelToggleHandler);
      this._configurationButton = null;
    }
    if (this._lineWidthRange) {
      this._lineWidthRange.removeEventListener("change", this._boundLineWidthInputHandler);
      this._lineWidthRange = null;
    }
    if (this._lineWidthValue) {
      this._lineWidthValue = null;
    }
    if (this._lineHeightToggleButton) {
      this._lineHeightToggleButton.removeEventListener("click", this._boundLineHeightToggleHandler);
      this._lineHeightToggleButton = null;
    }
    if (this._lineHeightRange) {
      this._lineHeightRange.removeEventListener("change", this._boundLineHeightInputHandler);
      this._lineHeightRange = null;
    }
    if (this._lineHeightValue) {
      this._lineHeightValue = null;
    }
    if (this._layerScrubberToggleButton) {
      this._layerScrubberToggleButton.removeEventListener("click", this._boundLayerScrubberToggleHandler);
      this._layerScrubberToggleButton = null;
    }
    if (this._layerScrubberEndRange) {
      this._layerScrubberEndRange.removeEventListener("input", this._boundLayerScrubberInputHandler);
      this._layerScrubberEndRange = null;
    }
    if (this._buildVolumeToggleButton) {
      this._buildVolumeToggleButton.removeEventListener("click", this._boundBuildVolumeToggleHandler);
      this._buildVolumeToggleButton = null;
    }
    if (this._buildVolumeXInput) {
      this._buildVolumeXInput.removeEventListener("change", this._boundBuildVolumeDimensionInputHandler);
      this._buildVolumeXInput = null;
    }
    if (this._buildVolumeYInput) {
      this._buildVolumeYInput.removeEventListener("change", this._boundBuildVolumeDimensionInputHandler);
      this._buildVolumeYInput = null;
    }
    if (this._buildVolumeZRange) {
      this._buildVolumeZRange.removeEventListener("change", this._boundBuildVolumeZInputHandler);
      this._buildVolumeZRange = null;
    }
    if (this._buildVolumeZValue) {
      this._buildVolumeZValue = null;
    }
    if (this._backgroundColorInput) {
      this._backgroundColorInput.removeEventListener("change", this._boundBackgroundColorInputHandler);
      this._backgroundColorInput = null;
    }
    if (this._gridColorInput) {
      this._gridColorInput.removeEventListener("change", this._boundGridColorInputHandler);
      this._gridColorInput = null;
    }
    if (this._tubeToggleButton) {
      this._tubeToggleButton.removeEventListener("click", this._boundTubeToggleHandler);
      this._tubeToggleButton = null;
    }
    if (this._tubeWidthRange) {
      this._tubeWidthRange.removeEventListener("change", this._boundTubeWidthInputHandler);
      this._tubeWidthRange = null;
    }
    if (this._tubeWidthValue) {
      this._tubeWidthValue = null;
    }
    if (this._travelToggleButton) {
      this._travelToggleButton.removeEventListener("click", this._boundTravelToggleHandler);
      this._travelToggleButton = null;
    }
    if (this._travelColorInput) {
      this._travelColorInput.removeEventListener("change", this._boundTravelColorInputHandler);
      this._travelColorInput = null;
    }
    if (this._gradientToggleButton) {
      this._gradientToggleButton.removeEventListener("click", this._boundGradientToggleHandler);
      this._gradientToggleButton = null;
    }
    if (this._captureButton) {
      this._captureButton.removeEventListener("click", this._boundCaptureHandler);
      this._captureButton = null;
    }
    if (this._cropToggleButton) {
      this._cropToggleButton.removeEventListener("click", this._boundCropToggleHandler);
      this._cropToggleButton = null;
    }
    if (this._cropAspectSelect) {
      this._cropAspectSelect.removeEventListener("change", this._boundCropAspectChangeHandler);
      this._cropAspectSelect = null;
    }
    if (this._resetCropButton) {
      this._resetCropButton.removeEventListener("click", this._boundResetCropHandler);
      this._resetCropButton = null;
    }
    if (this._cancelCropButton) {
      this._cancelCropButton.removeEventListener("click", this._boundCancelCropHandler);
      this._cancelCropButton = null;
    }
    if (this._cropLayer) {
      this._cropLayer.removeEventListener("pointerdown", this._boundCropPointerDownHandler);
      this._cropLayer = null;
    }
    if (this._downloadCaptureButton) {
      this._downloadCaptureButton.removeEventListener("click", this._boundDownloadCaptureHandler);
      this._downloadCaptureButton = null;
    }
    if (this._uploadCaptureButton) {
      this._uploadCaptureButton.removeEventListener("click", this._boundUploadCaptureHandler);
      this._uploadCaptureButton = null;
    }
  }

  _attachGlobalListeners() {
    if (this._globalListenersAttached || typeof window === "undefined") {
      return;
    }
    window.addEventListener("pointerdown", this._boundWindowPointerDownHandler);
    window.addEventListener("pointermove", this._boundWindowPointerMoveHandler);
    window.addEventListener("pointerup", this._boundWindowPointerUpHandler);
    window.addEventListener("resize", this._boundWindowResizeHandler);
    this._globalListenersAttached = true;
  }

  _detachGlobalListeners() {
    if (!this._globalListenersAttached || typeof window === "undefined") {
      return;
    }
    window.removeEventListener("pointerdown", this._boundWindowPointerDownHandler);
    window.removeEventListener("pointermove", this._boundWindowPointerMoveHandler);
    window.removeEventListener("pointerup", this._boundWindowPointerUpHandler);
    window.removeEventListener("resize", this._boundWindowResizeHandler);
    this._globalListenersAttached = false;
  }

  _disposePreview(invalidateLoad = false) {
    if (invalidateLoad) {
      this._loadToken += 1;
    }
    if (this._preview && typeof this._preview.dispose === "function") {
      this._preview.dispose();
    }
    this._preview = null;
  }

  _buildLoadSignature() {
    return JSON.stringify({
      config: this._config,
      renderAnimated: this._renderAnimated,
      viewerSettings: {
        renderBuildVolume: this._viewerSettings.renderBuildVolume,
        buildVolumeX: this._viewerSettings.buildVolumeX,
        buildVolumeY: this._viewerSettings.buildVolumeY,
        buildVolumeZ: this._viewerSettings.buildVolumeZ,
        backgroundColor: this._viewerSettings.backgroundColor,
        gridColor: this._viewerSettings.gridColor,
        renderTubes: this._viewerSettings.renderTubes,
        extrusionWidth: this._viewerSettings.extrusionWidth,
        lineWidth: this._viewerSettings.lineWidth,
        useFixedLineHeight: this._viewerSettings.useFixedLineHeight,
        lineHeight: this._viewerSettings.lineHeight,
        showTravelMoves: this._viewerSettings.showTravelMoves,
        travelColor: this._viewerSettings.travelColor,
        useColorGradient: this._viewerSettings.useColorGradient,
      },
    });
  }

  _syncLoadedSignature() {
    this._loadedSignature = this._buildLoadSignature();
  }

  _clearTimer(name) {
    if (this[name] != null) {
      clearTimeout(this[name]);
      this[name] = null;
    }
  }

  _captureCameraState(preview) {
    const sceneManager = preview && preview.sceneManager ? preview.sceneManager : null;
    if (!sceneManager || !sceneManager.camera || !sceneManager.controls) {
      return null;
    }
    return {
      position: { x: sceneManager.camera.position.x, y: sceneManager.camera.position.y, z: sceneManager.camera.position.z },
      rotation: { x: sceneManager.camera.rotation.x, y: sceneManager.camera.rotation.y, z: sceneManager.camera.rotation.z },
      zoom: sceneManager.camera.zoom,
      target: { x: sceneManager.controls.target.x, y: sceneManager.controls.target.y, z: sceneManager.controls.target.z },
    };
  }

  _restoreCameraState(preview, state) {
    const sceneManager = preview && preview.sceneManager ? preview.sceneManager : null;
    if (!sceneManager || !sceneManager.camera || !sceneManager.controls || !state) {
      return;
    }
    sceneManager.camera.position.set(state.position.x, state.position.y, state.position.z);
    sceneManager.camera.rotation.set(state.rotation.x, state.rotation.y, state.rotation.z);
    sceneManager.camera.zoom = state.zoom;
    if (typeof sceneManager.camera.updateProjectionMatrix === "function") {
      sceneManager.camera.updateProjectionMatrix();
    }
    sceneManager.controls.target.set(state.target.x, state.target.y, state.target.z);
    if (typeof sceneManager.controls.update === "function") {
      sceneManager.controls.update();
    }
  }

  _maybeLoad() {
    if (!this.isConnected || !this._config || !this.shadowRoot || !this._hass) {
      return;
    }
    const signature = this._buildLoadSignature();
    if (signature === this._loadedSignature) {
      return;
    }
    this._loadedSignature = signature;
    this._loadViewer();
  }

  _renderShell() {
    this._detachShellListeners();
    this.shadowRoot.innerHTML = "" +
      "<style>" +
      ":host{display:block;}" +
      "ha-card{padding:0;overflow:hidden;border-radius:24px;background:linear-gradient(180deg,#071019 0%,#09111b 100%);color:#f8fafc;}" +
      ".shell{display:grid;grid-template-rows:auto auto auto;gap:14px;min-height:720px;padding:22px 18px 18px;}" +
      ".panel{border:1px solid rgba(125,211,200,0.18);border-radius:20px;background:rgba(13,23,35,0.94);box-shadow:0 18px 50px rgba(0,0,0,0.22);backdrop-filter:blur(10px);}" +
      ".header{display:grid;gap:12px;padding:18px 20px 16px;}" +
      ".eyebrow{font-size:11px;letter-spacing:0.08em;text-transform:uppercase;color:#7dd3c8;font-weight:700;margin-bottom:6px;}" +
      "h1{margin:0;font-size:clamp(1.05rem,1.3vw + 0.8rem,1.55rem);line-height:1.2;}" +
      ".header-meta{display:flex;flex-wrap:wrap;align-items:center;gap:12px 14px;}" +
      ".subtitle{color:#9fb0c0;font-size:0.9rem;font-weight:600;}" +
      ".subtitle[hidden]{display:none;}" +
      ".button,.button:visited{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:42px;padding:0 16px;border-radius:14px;border:1px solid rgba(125,211,200,0.18);background:linear-gradient(180deg,rgba(24,37,50,0.96),rgba(10,18,29,0.98));box-shadow:inset 0 1px 0 rgba(255,255,255,0.08),0 10px 22px rgba(0,0,0,0.18);color:#f8fafc;text-decoration:none;font-size:0.92rem;font-weight:700;letter-spacing:0.01em;cursor:pointer;transition:transform 0.16s ease,box-shadow 0.16s ease,border-color 0.16s ease,background 0.16s ease,color 0.16s ease;}" +
      ".button:hover,.button:focus-visible{border-color:rgba(125,211,200,0.42);background:linear-gradient(180deg,rgba(34,52,68,0.98),rgba(13,24,36,0.98));box-shadow:inset 0 1px 0 rgba(255,255,255,0.12),0 14px 28px rgba(4,12,20,0.28);transform:translateY(-1px);outline:none;}" +
      ".button:active{transform:translateY(0);box-shadow:inset 0 1px 0 rgba(255,255,255,0.06),0 8px 18px rgba(4,12,20,0.22);}" +
      ".button.primary{border-color:rgba(125,211,200,0.36);background:linear-gradient(180deg,rgba(27,92,87,0.98),rgba(10,44,48,0.98));color:#ecfeff;box-shadow:inset 0 1px 0 rgba(255,255,255,0.12),0 14px 30px rgba(13,86,82,0.24);}" +
      ".button.primary:hover,.button.primary:focus-visible{border-color:rgba(153,246,228,0.52);background:linear-gradient(180deg,rgba(39,118,111,0.98),rgba(14,56,59,0.98));box-shadow:inset 0 1px 0 rgba(255,255,255,0.16),0 18px 34px rgba(13,86,82,0.3);}" +
      ".button.ghost{border-color:rgba(148,163,184,0.22);background:linear-gradient(180deg,rgba(19,28,40,0.92),rgba(9,16,26,0.96));color:#dbe7f3;}" +
      ".button.ghost:hover,.button.ghost:focus-visible{border-color:rgba(125,211,200,0.36);color:#f8fafc;}" +
      ".button:disabled,.button[aria-disabled='true']{opacity:0.45;pointer-events:none;box-shadow:none;transform:none;}" +
      ".chips{display:flex;flex-wrap:wrap;gap:8px;}" +
      ".chip{display:inline-flex;align-items:center;gap:6px;min-height:26px;padding:0 10px;border-radius:999px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.06);color:#f8fafc;font-size:0.76rem;font-weight:700;letter-spacing:0.01em;}" +
      ".chip.warn{color:#fde68a;border-color:rgba(245,158,11,0.34);background:rgba(245,158,11,0.12);}" +
      ".viewer-workbench{--viewer-stage-height:min(72vh,680px);display:grid;grid-template-columns:minmax(0,1.7fr) minmax(320px,0.95fr);grid-template-areas:'stage capture';gap:14px;align-items:stretch;}" +
      ".stage{position:relative;min-height:var(--viewer-stage-height);height:var(--viewer-stage-height);overflow:hidden;background:linear-gradient(180deg,rgba(10,19,30,0.92),rgba(8,14,23,0.98)),radial-gradient(circle at top,rgba(125,211,200,0.08),transparent 34%);}" +
      ".stage-panel{grid-area:stage;align-self:stretch;}" +
      ".canvas{position:absolute;inset:0;width:100%;height:100%;display:block;}" +
      ".stage-status{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:24px;z-index:2;pointer-events:none;transition:opacity 0.18s ease,visibility 0.18s ease;}" +
      ".stage-status.hidden{opacity:0;visibility:hidden;}" +
      ".stage-status-card{display:grid;justify-items:center;gap:12px;width:min(420px,100%);padding:24px 26px;border-radius:24px;border:1px solid rgba(125,211,200,0.2);background:linear-gradient(180deg,rgba(10,18,29,0.88),rgba(15,25,37,0.96));box-shadow:0 24px 56px rgba(0,0,0,0.32);backdrop-filter:blur(12px);text-align:center;}" +
      ".stage-status.error .stage-status-card{border-color:rgba(248,113,113,0.28);background:linear-gradient(180deg,rgba(49,17,17,0.86),rgba(24,11,11,0.96));}" +
      ".stage-status-spinner{width:42px;height:42px;border-radius:999px;border:3px solid rgba(148,163,184,0.28);border-top-color:#7dd3c8;box-shadow:0 0 0 1px rgba(255,255,255,0.04) inset;animation:stageSpinner 0.9s linear infinite;}" +
      ".stage-status.error .stage-status-spinner{border-top-color:#fda4af;}" +
      ".stage-status-label{font-size:1.16rem;font-weight:700;line-height:1.35;color:#f8fafc;}" +
      ".stage-status-copy{max-width:34ch;color:#c7d5e3;font-size:0.96rem;line-height:1.55;}" +
      ".stage-toolbar{position:absolute;left:16px;top:16px;display:flex;flex-wrap:wrap;gap:10px;z-index:4;}" +
      ".stage-toolbar .button{min-height:38px;padding:0 14px;backdrop-filter:blur(8px);}" +
      ".button.toggle-on{border-color:rgba(125,211,200,0.36);background:linear-gradient(180deg,rgba(20,66,67,0.96),rgba(8,29,33,0.98));color:#ecfeff;}" +
      ".button.toggle-on:hover,.button.toggle-on:focus-visible{border-color:rgba(153,246,228,0.52);background:linear-gradient(180deg,rgba(28,88,87,0.98),rgba(10,41,45,0.98));}" +
      ".button.toggle-off{border-color:rgba(148,163,184,0.22);background:linear-gradient(180deg,rgba(30,41,59,0.9),rgba(15,23,42,0.96));color:#cbd5e1;}" +
      ".configuration-button{position:absolute;right:16px;bottom:16px;z-index:6;width:44px;min-width:44px;height:44px;padding:0;border-radius:999px;}" +
      ".configuration-panel{position:absolute;right:16px;bottom:70px;display:grid;gap:10px;width:min(390px,calc(100% - 32px));max-height:min(78vh,720px);overflow:auto;padding:14px;border-radius:18px;border:1px solid rgba(125,211,200,0.16);background:linear-gradient(180deg,rgba(9,18,29,0.96),rgba(14,24,37,0.98));box-shadow:0 18px 44px rgba(0,0,0,0.28);backdrop-filter:blur(12px);z-index:6;}" +
      ".configuration-panel[hidden]{display:none;}" +
      ".configuration-panel-header{display:grid;gap:4px;}" +
      ".configuration-panel-title{font-size:0.93rem;font-weight:700;color:#f8fafc;}" +
      ".configuration-panel-copy{font-size:0.82rem;line-height:1.45;color:#9fb0c0;}" +
      ".configuration-grid{display:grid;gap:8px;}" +
      ".configuration-row{display:grid;gap:10px;padding:12px 14px;border-radius:16px;border:1px solid rgba(255,255,255,0.06);background:rgba(255,255,255,0.03);}" +
      ".configuration-row-top{display:flex;align-items:center;justify-content:space-between;gap:12px;}" +
      ".configuration-copy{display:grid;gap:3px;min-width:0;}" +
      ".configuration-title{font-size:0.86rem;font-weight:700;color:#f8fafc;}" +
      ".configuration-desc{font-size:0.77rem;line-height:1.4;color:#9fb0c0;}" +
      ".configuration-row .button{flex:0 0 auto;min-height:34px;padding:0 12px;font-size:0.78rem;}" +
      ".configuration-slider{display:grid;gap:6px;}" +
      ".configuration-slider[hidden]{display:none;}" +
      ".configuration-slider input[type='range']{width:100%;accent-color:#7dd3c8;}" +
      ".configuration-slider-meta{display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:0.76rem;color:#c7d5e3;}" +
      ".configuration-input-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;}" +
      ".configuration-input-stack{display:grid;gap:6px;}" +
      ".configuration-label{font-size:0.72rem;letter-spacing:0.04em;text-transform:uppercase;color:#9fb0c0;font-weight:700;}" +
      ".configuration-number,.configuration-color{width:100%;min-height:40px;padding:0 12px;border-radius:12px;border:1px solid rgba(125,211,200,0.18);background:linear-gradient(180deg,rgba(24,37,50,0.96),rgba(10,18,29,0.98));color:#f8fafc;box-sizing:border-box;}" +
      ".configuration-color{padding:4px 6px;}" +
      ".configuration-inline-note{font-size:0.74rem;line-height:1.45;color:#8fa5b6;}" +
      ".layer-scrubber{position:absolute;right:18px;top:92px;bottom:92px;width:30px;display:flex;align-items:center;justify-content:center;z-index:5;}" +
      ".layer-scrubber[hidden]{display:none;}" +
      ".layer-scrubber-track{position:relative;display:flex;align-items:center;justify-content:center;min-height:0;height:100%;width:24px;padding:8px 0;}" +
      ".layer-scrubber-rail{position:absolute;top:12px;bottom:12px;left:50%;width:4px;transform:translateX(-50%);border-radius:999px;background:linear-gradient(180deg,rgba(148,163,184,0.24),rgba(71,85,105,0.3));pointer-events:none;}" +
      ".layer-scrubber-range{position:absolute;inset:0;appearance:none;-webkit-appearance:none;width:24px;height:100%;min-height:220px;writing-mode:vertical-lr;direction:rtl;background:transparent;cursor:pointer;}" +
      ".layer-scrubber-range:hover,.layer-scrubber-range:focus-visible{outline:none;filter:brightness(1.08);}" +
      ".layer-scrubber-range::-webkit-slider-runnable-track{width:8px;border-color:transparent;background:transparent;box-shadow:none;}" +
      ".layer-scrubber-range:hover::-webkit-slider-runnable-track,.layer-scrubber-range:focus-visible::-webkit-slider-runnable-track{border-color:transparent;background:transparent;box-shadow:none;}" +
      ".layer-scrubber-range::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;width:12px;height:12px;margin-left:0;border-radius:999px;border:none;background:#38bdf8;box-shadow:0 0 0 2px rgba(8,15,26,0.82),0 2px 8px rgba(0,0,0,0.22);transition:transform 0.16s ease,box-shadow 0.16s ease;}" +
      ".layer-scrubber-range:hover::-webkit-slider-thumb,.layer-scrubber-range:focus-visible::-webkit-slider-thumb{transform:scale(1.04);box-shadow:0 0 0 2px rgba(8,15,26,0.86),0 0 0 4px rgba(125,211,252,0.12),0 4px 12px rgba(0,0,0,0.28);}" +
      ".layer-scrubber-range::-moz-range-track{width:8px;border-color:transparent;background:transparent;box-shadow:none;}" +
      ".layer-scrubber-range:hover::-moz-range-track,.layer-scrubber-range:focus-visible::-moz-range-track{border-color:transparent;background:transparent;box-shadow:none;}" +
      ".layer-scrubber-range::-moz-range-progress{background:transparent;}" +
      ".layer-scrubber-range::-moz-range-thumb{width:12px;height:12px;border-radius:999px;border:none;background:#38bdf8;box-shadow:0 0 0 2px rgba(8,15,26,0.82),0 2px 8px rgba(0,0,0,0.22);transition:transform 0.16s ease,box-shadow 0.16s ease;}" +
      ".layer-scrubber-range:hover::-moz-range-thumb,.layer-scrubber-range:focus-visible::-moz-range-thumb{transform:scale(1.04);box-shadow:0 0 0 2px rgba(8,15,26,0.86),0 0 0 4px rgba(125,211,252,0.12),0 4px 12px rgba(0,0,0,0.28);}" +
      ".overlay{position:absolute;inset:18px 18px auto auto;display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px;max-width:calc(100% - 36px);pointer-events:none;}" +
      ".overlay .chip{pointer-events:auto;}" +
      ".crop-layer{position:absolute;inset:0;pointer-events:none;opacity:0;transition:opacity 0.14s ease;z-index:3;}" +
      ".crop-layer.active{pointer-events:auto;opacity:1;}" +
      ".crop-mask{position:absolute;background:rgba(3,8,14,0.6);backdrop-filter:blur(1px);}" +
      ".crop-box{position:absolute;border:2px solid rgba(125,211,200,0.96);border-radius:18px;box-shadow:0 0 0 9999px rgba(3,8,14,0.24),inset 0 0 0 1px rgba(255,255,255,0.18);cursor:move;touch-action:none;display:none;overflow:hidden;background:linear-gradient(180deg,rgba(125,211,200,0.06),rgba(125,211,200,0.02));}" +
      ".crop-layer.active .crop-box{display:block;}" +
      ".crop-grid{position:absolute;inset:0;background-image:linear-gradient(to right,transparent 33.333%,rgba(255,255,255,0.18) 33.333%,rgba(255,255,255,0.18) calc(33.333% + 1px),transparent calc(33.333% + 1px),transparent 66.666%,rgba(255,255,255,0.18) 66.666%,rgba(255,255,255,0.18) calc(66.666% + 1px),transparent calc(66.666% + 1px)),linear-gradient(to bottom,transparent 33.333%,rgba(255,255,255,0.18) 33.333%,rgba(255,255,255,0.18) calc(33.333% + 1px),transparent calc(33.333% + 1px),transparent 66.666%,rgba(255,255,255,0.18) 66.666%,rgba(255,255,255,0.18) calc(66.666% + 1px),transparent calc(66.666% + 1px));}" +
      ".crop-handle{position:absolute;width:22px;height:22px;border-radius:999px;border:2px solid rgba(255,255,255,0.92);background:rgba(125,211,200,0.94);box-shadow:0 4px 16px rgba(0,0,0,0.24);touch-action:none;}" +
      ".crop-handle.nw{left:-11px;top:-11px;cursor:nwse-resize;}" +
      ".crop-handle.ne{right:-11px;top:-11px;cursor:nesw-resize;}" +
      ".crop-handle.sw{left:-11px;bottom:-11px;cursor:nesw-resize;}" +
      ".crop-handle.se{right:-11px;bottom:-11px;cursor:nwse-resize;}" +
      ".capture-panel{grid-area:capture;display:grid;grid-template-rows:auto minmax(0,1fr);gap:14px;padding:18px 20px;position:sticky;top:18px;align-self:stretch;min-height:var(--viewer-stage-height);height:var(--viewer-stage-height);box-sizing:border-box;}" +
      ".capture-panel.idle{border-color:rgba(255,255,255,0.08);}" +
      ".capture-panel.crop-active{border-color:rgba(245,158,11,0.34);box-shadow:0 18px 50px rgba(245,158,11,0.12);}" +
      ".capture-panel.capture-ready{border-color:rgba(125,211,200,0.34);box-shadow:0 22px 56px rgba(125,211,200,0.16);}" +
      ".capture-hero{display:grid;gap:12px;padding:14px 16px;border-radius:18px;border:1px solid rgba(255,255,255,0.06);background:linear-gradient(180deg,rgba(18,31,46,0.98),rgba(11,20,31,0.98));}" +
      ".capture-hero.status-crop{border-color:rgba(245,158,11,0.26);background:linear-gradient(180deg,rgba(66,43,11,0.44),rgba(27,21,10,0.7));}" +
      ".capture-hero.status-ready{border-color:rgba(125,211,200,0.28);background:linear-gradient(180deg,rgba(15,50,47,0.6),rgba(9,22,26,0.96));animation:capturePulse 1.3s ease-out 1;}" +
      ".capture-hero.status-upload{border-color:rgba(56,189,248,0.28);background:linear-gradient(180deg,rgba(10,39,54,0.6),rgba(9,22,31,0.96));}" +
      ".capture-hero.status-error{border-color:rgba(248,113,113,0.28);background:linear-gradient(180deg,rgba(59,17,17,0.62),rgba(28,12,12,0.96));}" +
      ".capture-hero-top{display:flex;align-items:center;justify-content:space-between;gap:10px;}" +
      ".capture-primary-actions{display:flex;flex-wrap:wrap;gap:10px;}" +
      ".capture-chip{display:inline-flex;align-items:center;gap:8px;min-height:28px;padding:0 12px;border-radius:999px;font-size:0.78rem;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.1);}" +
      ".capture-chip::before{content:'';width:9px;height:9px;border-radius:999px;background:currentColor;box-shadow:0 0 0 4px rgba(255,255,255,0.06);}" +
      ".capture-chip.idle{color:#cbd5e1;}" +
      ".capture-chip.crop{color:#fde68a;}" +
      ".capture-chip.ready{color:#7dd3c8;}" +
      ".capture-chip.error{color:#fca5a5;}" +
      ".capture-chip.upload{color:#7dd3fc;}" +
      ".capture-hero-title{font-size:1.1rem;font-weight:700;color:#f8fafc;}" +
      ".capture-preview-stack{display:grid;grid-template-rows:minmax(0,1fr) auto;gap:14px;min-height:0;}" +
      ".capture-preview-wrap{position:relative;min-height:240px;border-radius:18px;overflow:hidden;border:1px solid rgba(255,255,255,0.06);background:linear-gradient(180deg,rgba(8,16,26,0.98),rgba(12,22,35,0.98));display:flex;align-items:center;justify-content:center;}" +
      ".capture-preview-wrap img{display:none;width:100%;height:100%;object-fit:contain;background:radial-gradient(circle at top,rgba(125,211,200,0.08),transparent 44%),#060c14;}" +
      ".capture-preview-wrap.has-image img{display:block;}" +
      ".capture-empty{padding:22px;color:#9fb0c0;font-size:0.94rem;line-height:1.6;text-align:left;}" +
      ".capture-meta{display:grid;align-content:start;gap:10px;}" +
      ".capture-kicker{font-size:11px;letter-spacing:0.08em;text-transform:uppercase;color:#7dd3c8;font-weight:700;}" +
      ".capture-title-row{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap;}" +
      ".capture-title{font-size:1.1rem;font-weight:700;color:#f8fafc;}" +
      ".capture-status{min-height:22px;font-size:0.9rem;color:#9fb0c0;}" +
      ".capture-status.error{color:#fecaca;}" +
      ".capture-status.success{color:#86efac;}" +
      ".capture-controls{display:none;gap:10px;flex-wrap:wrap;align-items:center;}" +
      ".capture-controls.visible{display:flex;}" +
      ".capture-controls select{appearance:none;min-height:42px;padding:0 42px 0 16px;border-radius:14px;border:1px solid rgba(125,211,200,0.18);background:linear-gradient(180deg,rgba(24,37,50,0.96),rgba(10,18,29,0.98));box-shadow:inset 0 1px 0 rgba(255,255,255,0.08),0 10px 22px rgba(0,0,0,0.18);color:#f8fafc;font-size:0.92rem;font-weight:700;}" +
      ".capture-controls select:hover,.capture-controls select:focus-visible{border-color:rgba(125,211,200,0.42);background:linear-gradient(180deg,rgba(34,52,68,0.98),rgba(13,24,36,0.98));outline:none;}" +
      ".capture-actions{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:flex-end;flex:0 0 auto;}" +
      ".fallback{display:none;padding:18px 20px 22px;border-top:1px solid rgba(255,255,255,0.06);background:rgba(18,31,46,0.98);}" +
      ".fallback.visible{display:block;}" +
      ".fallback-title{margin:0 0 8px;font-size:0.96rem;font-weight:700;}" +
      ".fallback-copy{margin:0 0 12px;color:#9fb0c0;line-height:1.5;font-size:0.92rem;}" +
      ".fallback pre{margin:0;padding:14px;border-radius:14px;overflow:auto;background:rgba(0,0,0,0.22);border:1px solid rgba(255,255,255,0.06);color:#dbeafe;font-family:'Cascadia Code',Consolas,monospace;font-size:0.8rem;line-height:1.45;max-height:220px;}" +
      ".footnote{padding:0 4px;color:#9fb0c0;font-size:0.88rem;line-height:1.55;}" +
      ".footnote.error{color:#fecaca;}" +
      "@keyframes capturePulse{0%{transform:translateY(0);box-shadow:0 0 0 0 rgba(125,211,200,0);}35%{transform:translateY(-2px);box-shadow:0 14px 38px rgba(125,211,200,0.2);}100%{transform:translateY(0);box-shadow:0 22px 56px rgba(125,211,200,0.16);}}" +
      "@keyframes stageSpinner{0%{transform:rotate(0deg);}100%{transform:rotate(360deg);}}" +
      "@media (max-width:1100px){.viewer-workbench{grid-template-columns:minmax(0,1.35fr) minmax(300px,0.95fr);}}" +
      "@media (max-width:900px){.viewer-workbench{grid-template-columns:1fr;grid-template-areas:'capture' 'stage';}.capture-panel{position:relative;top:auto;min-height:auto;height:auto;}}" +
      "@media (max-width:720px){.shell{padding:16px 12px 12px;min-height:600px;}.header{padding:16px;}.fallback,.capture-panel{padding-left:16px;padding-right:16px;}.capture-panel{padding-top:16px;padding-bottom:16px;}.stage{min-height:58vh;height:58vh;}.stage-toolbar{left:12px;top:12px;right:12px;}.overlay{inset:14px 14px auto auto;max-width:calc(100% - 28px);}.capture-title-row{align-items:stretch;}.capture-actions{width:100%;justify-content:flex-start;}}" +
      "</style>" +
      "<ha-card>" +
      "<div class='shell'>" +
      "<section class='panel'>" +
      "<div class='header'>" +
      "<div>" +
        "<div class='eyebrow'>3D Viewer</div>" +
      "<h1 id='viewer-title'>3D Viewer</h1>" +
      "</div>" +
      "<div class='header-meta'>" +
      "<div id='viewer-subtitle' class='subtitle' hidden></div>" +
      "<div id='capability-chips' class='chips'></div>" +
      "</div></div>" +
      "</section>" +
      "<section class='viewer-workbench'>" +
      "<section id='viewer-stage' class='panel stage stage-panel'>" +
      "<div class='stage-toolbar'>" +
      "<button id='refresh-button' class='button ghost' type='button'>Refresh</button>" +
      "<button id='animate-button' class='button ghost' type='button' aria-pressed='false'>Animate</button>" +
      "<a id='download-link' class='button ghost' href='#' download='archive.gcode'>Download G-code</a>" +
      "</div>" +
      "<button id='configuration-button' class='button ghost configuration-button' type='button' aria-expanded='false' aria-label='Viewer configuration' title='Viewer configuration'><ha-icon icon='mdi:cog'></ha-icon></button>" +
      "<div id='configuration-panel' class='configuration-panel' hidden>" +
      "<div class='configuration-panel-header'>" +
      "<div class='configuration-panel-title'>Viewer Configuration</div>" +
      "<div class='configuration-panel-copy'>Adjust how the G-code preview is rendered for this viewer session.</div>" +
      "</div>" +
      "<div class='configuration-grid'>" +
      "<div class='configuration-row'>" +
      "<div class='configuration-row-top'><div class='configuration-copy'><div class='configuration-title'>Layer Scrubber</div><div class='configuration-desc'>Show the vertical layer scrubber on the stage by default.</div></div><button id='layer-scrubber-toggle-button' class='button' type='button'>On</button></div>" +
      "</div>" +
      "<div class='configuration-row'>" +
      "<div class='configuration-row-top'><div class='configuration-copy'><div class='configuration-title'>Build Volume</div><div class='configuration-desc'>Render the printer volume grid and volume frame behind the toolpath.</div></div><button id='build-volume-toggle-button' class='button' type='button'>On</button></div>" +
      "<div class='configuration-input-grid'><label class='configuration-input-stack'><span class='configuration-label'>Volume X</span><input id='build-volume-x-input' class='configuration-number' type='number' min='1' max='512' step='1' value='256'></label><label class='configuration-input-stack'><span class='configuration-label'>Volume Y</span><input id='build-volume-y-input' class='configuration-number' type='number' min='1' max='512' step='1' value='256'></label></div>" +
      "<div class='configuration-slider'><input id='build-volume-z-range' type='range' min='0' max='512' step='1' value='256'><div class='configuration-slider-meta'><span>Volume Z</span><span id='build-volume-z-value'>256</span></div></div>" +
      "<div class='configuration-inline-note'>X and Y default to inferred job dimensions when available, otherwise 256 mm.</div>" +
      "</div>" +
      "<div class='configuration-row'>" +
      "<div class='configuration-copy'><div class='configuration-title'>Stage Colors</div><div class='configuration-desc'>Tune the preview background and build-volume grid colors.</div></div>" +
      "<div class='configuration-input-grid'><label class='configuration-input-stack'><span class='configuration-label'>Background</span><input id='background-color-input' class='configuration-color' type='color' value='#08101a'></label><label class='configuration-input-stack'><span class='configuration-label'>Grid</span><input id='grid-color-input' class='configuration-color' type='color' value='#888888'></label></div>" +
      "</div>" +
      "<div class='configuration-row'>" +
      "<div class='configuration-row-top'><div class='configuration-copy'><div class='configuration-title'>Render As Tubes</div><div class='configuration-desc'>Render extrusion as volumetric tubes using the configured nozzle width.</div></div><button id='tube-toggle-button' class='button' type='button'>Off</button></div>" +
      "<div id='tube-width-slider' class='configuration-slider' hidden><input id='tube-width-range' type='range' min='0.2' max='1.0' step='0.05' value='0.4'><div class='configuration-slider-meta'><span>Nozzle Width</span><span id='tube-width-value'>0.40</span></div></div>" +
      "</div>" +
      "<div class='configuration-row'>" +
      "<div class='configuration-copy'><div class='configuration-title'>Line Width</div><div class='configuration-desc'>Used when tube rendering is off.</div></div>" +
      "<div id='line-width-slider' class='configuration-slider'><input id='line-width-range' type='range' min='1' max='10' step='0.5' value='1'><div class='configuration-slider-meta'><span>Width</span><span id='line-width-value'>1.0</span></div></div>" +
      "</div>" +
      "<div class='configuration-row'>" +
      "<div class='configuration-row-top'><div class='configuration-copy'><div class='configuration-title'>Fixed Line Height</div><div class='configuration-desc'>Use a fixed layer height value for preview rendering.</div></div><button id='line-height-toggle-button' class='button' type='button'>Off</button></div>" +
      "<div id='line-height-slider' class='configuration-slider' hidden><input id='line-height-range' type='range' min='0.05' max='0.4' step='0.01' value='0.2'><div class='configuration-slider-meta'><span>Height</span><span id='line-height-value'>0.20</span></div></div>" +
      "</div>" +
      "<div class='configuration-row'>" +
      "<div class='configuration-row-top'><div class='configuration-copy'><div class='configuration-title'>Show Travel Moves</div><div class='configuration-desc'>Render non-extrusion travel paths with a dedicated color.</div></div><button id='travel-toggle-button' class='button' type='button'>Off</button></div>" +
      "<div id='travel-color-row' class='configuration-input-grid' hidden><label class='configuration-input-stack'><span class='configuration-label'>Travel Color</span><input id='travel-color-input' class='configuration-color' type='color' value='#990000'></label></div>" +
      "</div>" +
      "<div class='configuration-row'>" +
      "<div class='configuration-row-top'><div class='configuration-copy'><div class='configuration-title'>Color Gradient</div><div class='configuration-desc'>Blend color shading across extrusion paths instead of using flat colors.</div></div><button id='gradient-toggle-button' class='button' type='button'>Off</button></div>" +
      "</div>" +
      "</div>" +
      "</div>" +
      "<div id='layer-scrubber' class='layer-scrubber'>" +
      "<div class='layer-scrubber-track'>" +
      "<div class='layer-scrubber-rail'></div>" +
      "<input id='layer-scrubber-end-range' class='layer-scrubber-range' type='range' min='1' max='1' step='1' value='1' aria-label='Visible layers'>" +
      "</div>" +
      "</div>" +
      "<canvas id='viewer-canvas' class='canvas'></canvas>" +
      "<div id='stage-status' class='stage-status' aria-live='polite'>" +
      "<div class='stage-status-card'>" +
      "<div id='stage-status-spinner' class='stage-status-spinner'></div>" +
      "<div id='stage-status-label' class='stage-status-label'>Loading 3D viewer</div>" +
      "<div id='stage-status-copy' class='stage-status-copy'>Preparing archive preview inside the render stage.</div>" +
      "</div>" +
      "</div>" +
      "<div id='viewer-overlay' class='overlay'></div>" +
      "<div id='crop-layer' class='crop-layer' aria-hidden='true'>" +
      "<div id='crop-mask-top' class='crop-mask'></div>" +
      "<div id='crop-mask-left' class='crop-mask'></div>" +
      "<div id='crop-mask-right' class='crop-mask'></div>" +
      "<div id='crop-mask-bottom' class='crop-mask'></div>" +
      "<div id='crop-box' class='crop-box'>" +
      "<div class='crop-grid'></div>" +
      "<div class='crop-handle nw' data-handle='nw'></div>" +
      "<div class='crop-handle ne' data-handle='ne'></div>" +
      "<div class='crop-handle sw' data-handle='sw'></div>" +
      "<div class='crop-handle se' data-handle='se'></div>" +
      "</div></div>" +
      "</section>" +
      "<section id='capture-panel' class='panel capture-panel idle'>" +
      "<div id='capture-hero' class='capture-hero'>" +
      "<div class='capture-hero-top'>" +
      "<span id='capture-chip' class='capture-chip idle'>Waiting</span>" +
      "<span class='capture-kicker'>Viewer Capture</span>" +
      "</div>" +
      "<div id='capture-hero-title' class='capture-hero-title'>Capture workspace</div>" +
      "<div class='capture-primary-actions'>" +
      "<button id='capture-button' class='button primary' type='button'>Capture View</button>" +
      "<button id='crop-toggle-button' class='button ghost' type='button'>Crop View</button>" +
      "</div>" +
      "<div id='capture-controls' class='capture-controls'>" +
      "<select id='crop-aspect-select' aria-label='Crop aspect preset'>" +
      "<option value='square'>Square</option>" +
      "<option value='free'>Freeform</option>" +
      "<option value='landscape4x3'>Landscape 4:3</option>" +
      "<option value='landscape16x9'>Landscape 16:9</option>" +
      "</select>" +
      "<button id='reset-crop-button' class='button ghost' type='button'>Reset Crop</button>" +
      "<button id='cancel-crop-button' class='button ghost' type='button'>Cancel Crop</button>" +
      "</div>" +
      "</div>" +
      "<div class='capture-preview-stack'>" +
      "<div class='capture-preview-wrap'>" +
      "<img id='capture-preview-image' alt='Captured viewer render' hidden>" +
      "<div id='capture-empty' class='capture-empty'>No capture yet.</div>" +
      "</div>" +
      "<div class='capture-meta'>" +
      "<div class='capture-title-row'>" +
      "<div id='capture-title' class='capture-title'>No render captured yet</div>" +
      "<div class='capture-actions'>" +
      "<button id='download-capture-button' class='button primary' type='button' disabled>Download PNG</button>" +
      "<button id='upload-capture-button' class='button primary' type='button' disabled>Upload to Archive</button>" +
      "</div>" +
      "</div>" +
      "<div id='capture-status' class='capture-status'></div>" +
      "</div>" +
      "</div>" +
      "</section>" +
      "</section>" +
      "<section id='fallback-panel' class='panel fallback'>" +
      "<p class='fallback-title'>Raw G-code Fallback</p>" +
      "<p id='fallback-copy' class='fallback-copy'></p>" +
      "<pre id='fallback-snippet'></pre>" +
      "</section>" +
      "<div id='viewer-footnote' class='footnote'>Rendered G-code preview. Use drag, pan, and zoom inside the canvas.</div>" +
      "</div>" +
      "</ha-card>";

    this._refreshButton = this.shadowRoot.getElementById("refresh-button");
    this._animateButton = this.shadowRoot.getElementById("animate-button");
    this._configurationButton = this.shadowRoot.getElementById("configuration-button");
    this._configurationPanel = this.shadowRoot.getElementById("configuration-panel");
    this._layerScrubberToggleButton = this.shadowRoot.getElementById("layer-scrubber-toggle-button");
    this._buildVolumeToggleButton = this.shadowRoot.getElementById("build-volume-toggle-button");
    this._buildVolumeXInput = this.shadowRoot.getElementById("build-volume-x-input");
    this._buildVolumeYInput = this.shadowRoot.getElementById("build-volume-y-input");
    this._buildVolumeZRange = this.shadowRoot.getElementById("build-volume-z-range");
    this._buildVolumeZValue = this.shadowRoot.getElementById("build-volume-z-value");
    this._backgroundColorInput = this.shadowRoot.getElementById("background-color-input");
    this._gridColorInput = this.shadowRoot.getElementById("grid-color-input");
    this._tubeToggleButton = this.shadowRoot.getElementById("tube-toggle-button");
    this._tubeWidthRange = this.shadowRoot.getElementById("tube-width-range");
    this._tubeWidthValue = this.shadowRoot.getElementById("tube-width-value");
    this._lineWidthRange = this.shadowRoot.getElementById("line-width-range");
    this._lineWidthValue = this.shadowRoot.getElementById("line-width-value");
    this._lineHeightToggleButton = this.shadowRoot.getElementById("line-height-toggle-button");
    this._lineHeightRange = this.shadowRoot.getElementById("line-height-range");
    this._lineHeightValue = this.shadowRoot.getElementById("line-height-value");
    this._travelToggleButton = this.shadowRoot.getElementById("travel-toggle-button");
    this._travelColorInput = this.shadowRoot.getElementById("travel-color-input");
    this._gradientToggleButton = this.shadowRoot.getElementById("gradient-toggle-button");
    this._layerScrubberPanel = this.shadowRoot.getElementById("layer-scrubber");
    this._layerScrubberEndRange = this.shadowRoot.getElementById("layer-scrubber-end-range");
    this._captureButton = this.shadowRoot.getElementById("capture-button");
    this._cropToggleButton = this.shadowRoot.getElementById("crop-toggle-button");
    this._cropAspectSelect = this.shadowRoot.getElementById("crop-aspect-select");
    this._resetCropButton = this.shadowRoot.getElementById("reset-crop-button");
    this._cancelCropButton = this.shadowRoot.getElementById("cancel-crop-button");
    this._cropLayer = this.shadowRoot.getElementById("crop-layer");
    this._capturePanel = this.shadowRoot.getElementById("capture-panel");
    this._downloadCaptureButton = this.shadowRoot.getElementById("download-capture-button");
    this._uploadCaptureButton = this.shadowRoot.getElementById("upload-capture-button");
    if (this._refreshButton) {
      this._refreshButton.addEventListener("click", this._boundRefreshHandler);
    }
    if (this._animateButton) {
      this._animateButton.addEventListener("click", this._boundAnimateHandler);
    }
    if (this._configurationButton) {
      this._configurationButton.addEventListener("click", this._boundConfigurationPanelToggleHandler);
    }
    if (this._layerScrubberToggleButton) {
      this._layerScrubberToggleButton.addEventListener("click", this._boundLayerScrubberToggleHandler);
    }
    if (this._buildVolumeToggleButton) {
      this._buildVolumeToggleButton.addEventListener("click", this._boundBuildVolumeToggleHandler);
    }
    if (this._buildVolumeXInput) {
      this._buildVolumeXInput.addEventListener("change", this._boundBuildVolumeDimensionInputHandler);
    }
    if (this._buildVolumeYInput) {
      this._buildVolumeYInput.addEventListener("change", this._boundBuildVolumeDimensionInputHandler);
    }
    if (this._buildVolumeZRange) {
      this._buildVolumeZRange.addEventListener("change", this._boundBuildVolumeZInputHandler);
    }
    if (this._backgroundColorInput) {
      this._backgroundColorInput.addEventListener("change", this._boundBackgroundColorInputHandler);
    }
    if (this._gridColorInput) {
      this._gridColorInput.addEventListener("change", this._boundGridColorInputHandler);
    }
    if (this._tubeToggleButton) {
      this._tubeToggleButton.addEventListener("click", this._boundTubeToggleHandler);
    }
    if (this._tubeWidthRange) {
      this._tubeWidthRange.addEventListener("change", this._boundTubeWidthInputHandler);
    }
    if (this._lineWidthRange) {
      this._lineWidthRange.addEventListener("change", this._boundLineWidthInputHandler);
    }
    if (this._lineHeightToggleButton) {
      this._lineHeightToggleButton.addEventListener("click", this._boundLineHeightToggleHandler);
    }
    if (this._lineHeightRange) {
      this._lineHeightRange.addEventListener("change", this._boundLineHeightInputHandler);
    }
    if (this._travelToggleButton) {
      this._travelToggleButton.addEventListener("click", this._boundTravelToggleHandler);
    }
    if (this._travelColorInput) {
      this._travelColorInput.addEventListener("change", this._boundTravelColorInputHandler);
    }
    if (this._gradientToggleButton) {
      this._gradientToggleButton.addEventListener("click", this._boundGradientToggleHandler);
    }
    if (this._layerScrubberEndRange) {
      this._layerScrubberEndRange.addEventListener("input", this._boundLayerScrubberInputHandler);
    }
    if (this._captureButton) {
      this._captureButton.addEventListener("click", this._boundCaptureHandler);
    }
    if (this._cropToggleButton) {
      this._cropToggleButton.addEventListener("click", this._boundCropToggleHandler);
    }
    if (this._cropAspectSelect) {
      this._cropAspectSelect.addEventListener("change", this._boundCropAspectChangeHandler);
    }
    if (this._resetCropButton) {
      this._resetCropButton.addEventListener("click", this._boundResetCropHandler);
    }
    if (this._cancelCropButton) {
      this._cancelCropButton.addEventListener("click", this._boundCancelCropHandler);
    }
    if (this._cropLayer) {
      this._cropLayer.addEventListener("pointerdown", this._boundCropPointerDownHandler);
    }
    if (this._downloadCaptureButton) {
      this._downloadCaptureButton.addEventListener("click", this._boundDownloadCaptureHandler);
    }
    if (this._uploadCaptureButton) {
      this._uploadCaptureButton.addEventListener("click", this._boundUploadCaptureHandler);
    }
    this._updateAnimateButton();
    this._updateConfigurationControls();
    this._updateCapturePanel();
  }

  _updateAnimateButton() {
    if (!this._animateButton) {
      return;
    }
    this._animateButton.textContent = this._renderAnimated ? "Animated" : "Animate";
    this._animateButton.setAttribute("aria-pressed", this._renderAnimated ? "true" : "false");
    this._animateButton.disabled = this._renderAnimated;
    this._animateButton.className = this._renderAnimated ? "button toggle-on" : "button ghost";
  }

  _handleAnimate() {
    if (this._renderAnimated) {
      return;
    }
    this._renderAnimated = true;
    this._updateAnimateButton();
    this._setStageStatus("Animating preview", "Redrawing the toolpath with animated path build enabled.");
    this._setStatus("Redrawing G-code preview with animated path build...");
    this._loadedSignature = "";
    this._maybeLoad();
  }

  _reloadForViewerSettings(message) {
    this._pendingCameraState = this._captureCameraState(this._preview);
    this._loadedSignature = "";
    this._disposePreview();
    this._setStageStatus("Updating viewer", "Re-rendering the preview with the selected viewer configuration.");
    this._setStatus(message || "Updating viewer configuration...");
    this._maybeLoad();
  }

  _handleWindowPointerDown(event) {
    if (!this._configurationPanelOpen) {
      return;
    }
    const path = event && typeof event.composedPath === "function" ? event.composedPath() : [];
    const clickedToggle = path.indexOf(this._configurationButton) >= 0;
    const clickedPanel = path.indexOf(this._configurationPanel) >= 0;
    if (!clickedToggle && !clickedPanel) {
      this._configurationPanelOpen = false;
      this._updateConfigurationControls();
    }
  }

  _formatViewerSettingValue(value, decimals) {
    const places = Number.isInteger(decimals) && decimals >= 0 ? decimals : 2;
    const numericValue = Number(value);
    return Number.isFinite(numericValue) ? numericValue.toFixed(places) : "";
  }

  _clampNumber(value, minimum, maximum, fallback) {
    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) {
      return fallback;
    }
    return Math.min(maximum, Math.max(minimum, numericValue));
  }

  _normalizeColorValue(value, fallback) {
    const normalized = this._normalizeHex(value);
    return normalized || fallback;
  }

  _effectiveBuildVolume() {
    return {
      x: this._clampNumber(this._viewerSettings.buildVolumeX, 1, 512, this._resolvedBuildVolume.x),
      y: this._clampNumber(this._viewerSettings.buildVolumeY, 1, 512, this._resolvedBuildVolume.y),
      z: this._clampNumber(this._viewerSettings.buildVolumeZ, 0, 512, this._resolvedBuildVolume.z),
    };
  }

  _effectiveNozzleDiameter() {
    return this._clampNumber(this._resolvedNozzleDiameter, 0.2, 1.2, 0.4);
  }

  _effectiveTubeWidth() {
    return this._clampNumber(this._viewerSettings.extrusionWidth, 0.2, 1.0, this._effectiveNozzleDiameter());
  }

  _effectiveLayerWindow() {
    const maxLayer = Math.max(this._totalLayers, 1);
    const startLayer = 1;
    const endLayer = this._clampNumber(this._viewerSettings.endLayer, startLayer, maxLayer, maxLayer);
    return {
      startLayer,
      endLayer,
    };
  }

  _resolvePreviewLayerCount(preview) {
    if (!preview) {
      return 0;
    }
    if (Number.isFinite(preview.countLayers) && preview.countLayers > 0) {
      return Math.round(preview.countLayers);
    }
    if (preview.job && Number.isFinite(preview.job.countLayers) && preview.job.countLayers > 0) {
      return Math.round(preview.job.countLayers);
    }
    if (Array.isArray(preview.layers) && preview.layers.length > 0) {
      return preview.layers.length;
    }
    if (preview.sceneManager && preview.sceneManager.job && Number.isFinite(preview.sceneManager.job.countLayers) && preview.sceneManager.job.countLayers > 0) {
      return Math.round(preview.sceneManager.job.countLayers);
    }
    return 0;
  }

  _setPreviewLayerWindow(preview, startLayer, endLayer) {
    const target = preview && preview.sceneManager ? preview.sceneManager : preview;
    if (!target) {
      return;
    }
    if ("startLayer" in target) {
      target.startLayer = startLayer;
    }
    if ("endLayer" in target) {
      target.endLayer = endLayer;
    }
  }

  _updateLayerScrubberSelection() {
    return;
  }

  _applyLayerScrubberState() {
    if (!this._preview || !this._totalLayers) {
      return;
    }
    const window = this._effectiveLayerWindow();
    this._viewerSettings.endLayer = window.endLayer;
    this._setPreviewLayerWindow(this._preview, window.startLayer, window.endLayer);
    if (typeof this._preview.render === "function") {
      this._preview.render();
    }
  }

  _scheduleLayerScrubberApply() {
    this._clearTimer("_layerScrubberTimer");
    this._layerScrubberTimer = setTimeout(() => {
      this._layerScrubberTimer = null;
      this._applyLayerScrubberState();
    }, 60);
  }

  _applySceneManagerSettings() {
    const sceneManager = this._preview && this._preview.sceneManager ? this._preview.sceneManager : null;
    if (!sceneManager) {
      return false;
    }

    sceneManager.backgroundColor = this._viewerSettings.backgroundColor;
    sceneManager.travelColor = this._viewerSettings.travelColor;

    if (this._viewerSettings.renderBuildVolume) {
      sceneManager.buildVolume = {
        x: this._effectiveBuildVolume().x,
        y: this._effectiveBuildVolume().y,
        z: this._effectiveBuildVolume().z,
        smallGrid: true,
      };
    } else {
      sceneManager.buildVolume = undefined;
    }

    this._applySceneManagerColors(this._preview);
    return true;
  }

  _schedulePreviewRerender(message, delay) {
    if (!this._preview || !this._preview.sceneManager) {
      this._reloadForViewerSettings(message);
      return;
    }

    this._clearTimer("_previewRerenderTimer");
    this._previewRerenderTimer = setTimeout(() => {
      const preview = this._preview;
      this._previewRerenderTimer = null;
      if (!preview || !preview.sceneManager) {
        return;
      }
      const sceneManager = preview.sceneManager;
      const cameraState = this._captureCameraState(preview);
      sceneManager.renderTravel = this._viewerSettings.showTravelMoves;
      sceneManager.renderTubes = this._viewerSettings.renderTubes;
      sceneManager.extrusionWidth = this._viewerSettings.renderTubes ? this._effectiveTubeWidth() : undefined;
      sceneManager.lineWidth = this._viewerSettings.renderTubes ? undefined : this._viewerSettings.lineWidth;
      sceneManager.lineHeight = this._viewerSettings.useFixedLineHeight ? this._viewerSettings.lineHeight : 0.2;
      sceneManager.disableGradient = !this._viewerSettings.useColorGradient;
      this._applySceneManagerSettings();
      preview.render();
      this._restoreCameraState(preview, cameraState);
      this._applyLayerScrubberState();
      this._syncLoadedSignature();
      if (message) {
        this._setStatus(message);
      }
    }, Number.isFinite(delay) ? delay : 140);
  }

  _handleConfigurationPanelToggle() {
    this._configurationPanelOpen = !this._configurationPanelOpen;
    this._updateConfigurationControls();
  }

  _handleLayerScrubberToggle() {
    this._viewerSettings.showLayerScrubber = !this._viewerSettings.showLayerScrubber;
    if (!this._viewerSettings.showLayerScrubber && this._totalLayers) {
      this._viewerSettings.endLayer = this._totalLayers;
      this._applyLayerScrubberState();
    }
    this._updateConfigurationControls();
  }

  _handleLayerScrubberInput(event) {
    const target = event && event.target;
    const maxLayer = Math.max(this._totalLayers, 1);
    if (!(target instanceof HTMLInputElement)) {
      return;
    }
    this._viewerSettings.endLayer = this._clampNumber(target.value, 1, maxLayer, maxLayer);
    this._updateConfigurationControls();
    this._scheduleLayerScrubberApply();
  }

  _handleBuildVolumeToggle() {
    this._viewerSettings.renderBuildVolume = !this._viewerSettings.renderBuildVolume;
    this._updateConfigurationControls();
    this._schedulePreviewRerender(
      this._viewerSettings.renderBuildVolume
        ? "Build volume rendering is enabled."
        : "Build volume rendering is hidden."
    );
  }

  _handleBuildVolumeDimensionInput(event) {
    const target = event && event.target;
    if (!(target instanceof HTMLInputElement)) {
      return;
    }
    const nextValue = this._clampNumber(target.value, 1, 512, 256);
    if (target.id === "build-volume-x-input") {
      this._viewerSettings.buildVolumeX = nextValue;
    } else if (target.id === "build-volume-y-input") {
      this._viewerSettings.buildVolumeY = nextValue;
    }
    this._updateConfigurationControls();
    this._schedulePreviewRerender("Updated the configured build volume footprint.");
  }

  _handleBuildVolumeZInput(event) {
    this._viewerSettings.buildVolumeZ = this._clampNumber(event && event.target ? event.target.value : this._viewerSettings.buildVolumeZ, 0, 512, this._resolvedBuildVolume.z);
    this._updateConfigurationControls();
    this._schedulePreviewRerender("Updated the configured build volume height.");
  }

  _handleBackgroundColorInput(event) {
    this._viewerSettings.backgroundColor = this._normalizeColorValue(event && event.target ? event.target.value : this._viewerSettings.backgroundColor, "#08101A");
    this._updateConfigurationControls();
    this._applySceneManagerSettings();
    this._syncLoadedSignature();
    this._setStatus("Updated the stage background color.");
  }

  _handleGridColorInput(event) {
    this._viewerSettings.gridColor = this._normalizeColorValue(event && event.target ? event.target.value : this._viewerSettings.gridColor, "#888888");
    this._updateConfigurationControls();
    this._applySceneManagerSettings();
    this._syncLoadedSignature();
    this._setStatus("Updated the build volume grid color.");
  }

  _handleTubeToggle() {
    this._viewerSettings.renderTubes = !this._viewerSettings.renderTubes;
    if (this._viewerSettings.renderTubes && this._viewerSettings.extrusionWidth == null) {
      this._viewerSettings.extrusionWidth = this._effectiveNozzleDiameter();
    }
    this._updateConfigurationControls();
    this._schedulePreviewRerender(
      this._viewerSettings.renderTubes
        ? "Tube extrusion rendering is enabled."
        : "Tube extrusion rendering is disabled."
    );
  }

  _handleTubeWidthInput(event) {
    this._viewerSettings.extrusionWidth = this._clampNumber(event && event.target ? event.target.value : this._viewerSettings.extrusionWidth, 0.2, 1.0, this._effectiveNozzleDiameter());
    this._updateConfigurationControls();
    this._schedulePreviewRerender(`Updated tube nozzle width to ${this._formatViewerSettingValue(this._viewerSettings.extrusionWidth, 2)}.`);
  }

  _handleLineWidthInput(event) {
    this._viewerSettings.lineWidth = this._clampNumber(event && event.target ? event.target.value : this._viewerSettings.lineWidth, 1, 10, 1);
    this._updateConfigurationControls();
    this._schedulePreviewRerender(`Updated line width to ${this._formatViewerSettingValue(this._viewerSettings.lineWidth, 1)}.`);
  }

  _handleLineHeightToggle() {
    this._viewerSettings.useFixedLineHeight = !this._viewerSettings.useFixedLineHeight;
    this._updateConfigurationControls();
    this._schedulePreviewRerender(
      this._viewerSettings.useFixedLineHeight
        ? `Applied fixed line height (${this._formatViewerSettingValue(this._viewerSettings.lineHeight, 2)}).`
        : "Reverted to the default line height behavior."
    );
  }

  _handleLineHeightInput(event) {
    this._viewerSettings.lineHeight = this._clampNumber(event && event.target ? event.target.value : this._viewerSettings.lineHeight, 0.05, 0.4, 0.2);
    this._updateConfigurationControls();
    this._schedulePreviewRerender(`Updated fixed line height to ${this._formatViewerSettingValue(this._viewerSettings.lineHeight, 2)}.`);
  }

  _handleTravelToggle() {
    this._viewerSettings.showTravelMoves = !this._viewerSettings.showTravelMoves;
    this._updateConfigurationControls();
    this._schedulePreviewRerender(
      this._viewerSettings.showTravelMoves
        ? "Travel moves are visible in the preview."
        : "Travel moves are hidden in the preview."
    );
  }

  _handleTravelColorInput(event) {
    this._viewerSettings.travelColor = this._normalizeColorValue(event && event.target ? event.target.value : this._viewerSettings.travelColor, "#990000");
    this._updateConfigurationControls();
    this._applySceneManagerSettings();
    this._syncLoadedSignature();
    this._setStatus("Updated the travel move color.");
  }

  _handleGradientToggle() {
    this._viewerSettings.useColorGradient = !this._viewerSettings.useColorGradient;
    this._updateConfigurationControls();
    this._schedulePreviewRerender(
      this._viewerSettings.useColorGradient
        ? "Color gradient shading is enabled."
        : "Flat filament colors are enabled."
    );
  }

  _updateToggleButton(button, isEnabled) {
    if (!button) {
      return;
    }
    button.textContent = isEnabled ? "On" : "Off";
    button.className = isEnabled ? "button toggle-on" : "button toggle-off";
    button.setAttribute("aria-pressed", isEnabled ? "true" : "false");
  }

  _updateConfigurationControls() {
    if (this._configurationButton) {
      this._configurationButton.className = this._configurationPanelOpen ? "button toggle-on configuration-button" : "button ghost configuration-button";
      this._configurationButton.setAttribute("aria-expanded", this._configurationPanelOpen ? "true" : "false");
    }
    if (this._configurationPanel) {
      this._configurationPanel.hidden = !this._configurationPanelOpen;
    }
    this._updateToggleButton(this._layerScrubberToggleButton, !!this._viewerSettings.showLayerScrubber);
    this._updateToggleButton(this._buildVolumeToggleButton, !!this._viewerSettings.renderBuildVolume);
    this._updateToggleButton(this._tubeToggleButton, !!this._viewerSettings.renderTubes);
    this._updateToggleButton(this._lineHeightToggleButton, !!this._viewerSettings.useFixedLineHeight);
    this._updateToggleButton(this._travelToggleButton, !!this._viewerSettings.showTravelMoves);
    this._updateToggleButton(this._gradientToggleButton, !!this._viewerSettings.useColorGradient);
    if (this._layerScrubberPanel) {
      this._layerScrubberPanel.hidden = !this._viewerSettings.showLayerScrubber;
    }
    const maxLayer = Math.max(this._totalLayers, 1);
    const layerWindow = this._effectiveLayerWindow();
    if (this._layerScrubberEndRange) {
      this._layerScrubberEndRange.min = this._totalLayers ? "1" : "0";
      this._layerScrubberEndRange.max = String(maxLayer);
      this._layerScrubberEndRange.value = String(layerWindow.endLayer);
      this._layerScrubberEndRange.disabled = this._totalLayers <= 1;
    if (this._buildVolumeYInput) {
      this._buildVolumeYInput.value = String(Math.round(effectiveBuildVolume.y));
    }
    if (this._buildVolumeZRange) {
      this._buildVolumeZRange.value = String(Math.round(effectiveBuildVolume.z));
    }
      this._buildVolumeZValue.textContent = String(Math.round(effectiveBuildVolume.z));
    }
    if (this._backgroundColorInput) {
      this._backgroundColorInput.value = this._viewerSettings.backgroundColor;
    }
    if (this._gridColorInput) {
      this._gridColorInput.value = this._viewerSettings.gridColor;
    }
    if (this._tubeWidthRange) {
      this._tubeWidthRange.value = this._formatViewerSettingValue(this._effectiveTubeWidth(), 2);
      const tubeWidthSlider = this.shadowRoot && this.shadowRoot.getElementById("tube-width-slider");
      if (tubeWidthSlider) {
        tubeWidthSlider.hidden = !this._viewerSettings.renderTubes;
      }
    }
    if (this._tubeWidthValue) {
      this._tubeWidthValue.textContent = this._formatViewerSettingValue(this._effectiveTubeWidth(), 2);
    }
    if (this._lineWidthRange) {
      this._lineWidthRange.value = this._formatViewerSettingValue(this._viewerSettings.lineWidth, 1);
      const lineWidthSlider = this.shadowRoot && this.shadowRoot.getElementById("line-width-slider");
      if (lineWidthSlider) {
        lineWidthSlider.hidden = !!this._viewerSettings.renderTubes;
      }
    }
    if (this._lineWidthValue) {
      this._lineWidthValue.textContent = this._formatViewerSettingValue(this._viewerSettings.lineWidth, 1);
    }
    if (this._lineHeightRange) {
      this._lineHeightRange.value = this._formatViewerSettingValue(this._viewerSettings.lineHeight, 2);
      const lineHeightSlider = this.shadowRoot && this.shadowRoot.getElementById("line-height-slider");
      if (lineHeightSlider) {
        lineHeightSlider.hidden = !this._viewerSettings.useFixedLineHeight;
      }
    }
    if (this._lineHeightValue) {
      this._lineHeightValue.textContent = this._formatViewerSettingValue(this._viewerSettings.lineHeight, 2);
    }
    if (this._travelColorInput) {
      this._travelColorInput.value = this._viewerSettings.travelColor;
      const travelColorRow = this.shadowRoot && this.shadowRoot.getElementById("travel-color-row");
      if (travelColorRow) {
        travelColorRow.hidden = !this._viewerSettings.showTravelMoves;
      }
    }
  }

  _setStageStatus(label, copy, mode) {
    const status = this.shadowRoot && this.shadowRoot.getElementById("stage-status");
    const labelNode = this.shadowRoot && this.shadowRoot.getElementById("stage-status-label");
    const copyNode = this.shadowRoot && this.shadowRoot.getElementById("stage-status-copy");
    const spinner = this.shadowRoot && this.shadowRoot.getElementById("stage-status-spinner");
    if (!status || !labelNode || !copyNode || !spinner) {
      return;
    }

    if (mode === "hidden") {
      status.className = "stage-status hidden";
      return;
    }

    status.className = mode === "error" ? "stage-status error" : "stage-status";
    labelNode.textContent = String(label || "Loading 3D viewer").trim() || "Loading 3D viewer";
    copyNode.textContent = String(copy || "Preparing archive preview inside the render stage.").trim() || "Preparing archive preview inside the render stage.";
    spinner.hidden = mode === "error";
  }

  _buildProxyUrl(path) {
    const entryId = this._config && this._config.entry_id ? this._config.entry_id : "";
    const suffix = entryId ? `?entry_id=${encodeURIComponent(entryId)}` : "";
    return `${path}${suffix}`;
  }

  _setCaptureStatus(message, tone) {
    const node = this.shadowRoot && this.shadowRoot.getElementById("capture-status");
    if (!node) {
      return;
    }
    node.textContent = String(message || "").trim();
    node.className = tone === "error"
      ? "capture-status error"
      : tone === "success"
        ? "capture-status success"
        : "capture-status";
  }

  _focusCapturePanel(mode) {
    if (!this._capturePanel || typeof this._capturePanel.scrollIntoView !== "function") {
      return;
    }
    const shouldScroll = mode === "capture" || mode === "crop" || mode === "upload";
    if (!shouldScroll) {
      return;
    }
    try {
      this._capturePanel.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
    } catch (_error) {
      this._capturePanel.scrollIntoView();
    }
  }

  _updateCaptureHero() {
    const hero = this.shadowRoot && this.shadowRoot.getElementById("capture-hero");
    const chip = this.shadowRoot && this.shadowRoot.getElementById("capture-chip");
    const title = this.shadowRoot && this.shadowRoot.getElementById("capture-hero-title");
    if (!hero || !chip || !title || !this._capturePanel) {
      return;
    }

    let panelState = "idle";
    let heroState = "status-idle";
    let chipState = "idle";
    let chipLabel = "Waiting";
    let heroTitle = "Capture workspace";

    if (this._uploadInProgress) {
      panelState = "capture-ready";
      heroState = "status-upload";
      chipState = "upload";
      chipLabel = "Uploading";
      heroTitle = "Uploading your viewer capture";
    } else if (this._capture) {
      panelState = "capture-ready";
      heroState = "status-ready";
      chipState = "ready";
      chipLabel = "Ready";
      heroTitle = "Capture ready to use";
    } else if (this._cropMode) {
      panelState = "crop-active";
      heroState = "status-crop";
      chipState = "crop";
      chipLabel = "Crop mode";
      heroTitle = "Crop mode is active";
    }

    this._capturePanel.className = `panel capture-panel ${panelState}`;
    hero.className = `capture-hero ${heroState}`;
    chip.className = `capture-chip ${chipState}`;
    chip.textContent = chipLabel;
    title.textContent = heroTitle;
  }

  _updateCapturePanel() {
    const image = this.shadowRoot && this.shadowRoot.getElementById("capture-preview-image");
    const empty = this.shadowRoot && this.shadowRoot.getElementById("capture-empty");
    const title = this.shadowRoot && this.shadowRoot.getElementById("capture-title");
    const controls = this.shadowRoot && this.shadowRoot.getElementById("capture-controls");
    const previewWrap = image && image.parentElement instanceof HTMLElement ? image.parentElement : null;
    if (!image || !empty || !title || !previewWrap) {
      return;
    }

    if (this._capture && this._capture.objectUrl) {
      image.src = this._capture.objectUrl;
      image.hidden = false;
      empty.hidden = true;
      previewWrap.classList.add("has-image");
      title.textContent = `${this._capture.width} x ${this._capture.height} PNG ready`;
    } else {
      image.removeAttribute("src");
      image.hidden = true;
      empty.hidden = false;
      previewWrap.classList.remove("has-image");
      title.textContent = this._cropMode ? this._cropPresetLabel() : "No render captured yet";
    }

    if (controls) {
      controls.classList.toggle("visible", this._cropMode);
    }

    if (this._captureButton) {
      this._captureButton.textContent = "Capture View";
    }
    if (this._cropToggleButton) {
      this._cropToggleButton.textContent = this._cropMode ? "Capture Crop" : "Crop View";
    }

    if (this._downloadCaptureButton) {
      this._downloadCaptureButton.disabled = !this._capture;
    }
    if (this._uploadCaptureButton) {
      this._uploadCaptureButton.disabled = !this._capture || this._uploadInProgress;
    }
    this._updateCaptureHero();
    this._updateCropOverlay();
  }

  _revokeCapture() {
    if (this._capture && this._capture.objectUrl) {
      URL.revokeObjectURL(this._capture.objectUrl);
    }
    this._capture = null;
  }

  _scaledDimensions(width, height, maxDimension) {
    const safeWidth = Math.max(1, Number(width) || 1);
    const safeHeight = Math.max(1, Number(height) || 1);
    const scale = Math.min(1, maxDimension / Math.max(safeWidth, safeHeight));
    return {
      width: Math.max(1, Math.round(safeWidth * scale)),
      height: Math.max(1, Math.round(safeHeight * scale)),
    };
  }

  _canvasToBlob(canvas, mimeType, quality) {
    return new Promise((resolve, reject) => {
      canvas.toBlob((blob) => {
        if (!blob) {
          reject(new Error("Canvas export returned no data"));
          return;
        }
        resolve(blob);
      }, mimeType, quality);
    });
  }

  _blobToBase64(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error("Could not encode capture for upload"));
      reader.onload = () => {
        const result = String(reader.result || "");
        const parts = result.split(",", 2);
        resolve(parts.length === 2 ? parts[1] : result);
      };
      reader.readAsDataURL(blob);
    });
  }

  _buildCaptureFileName() {
    const archiveId = String(this._config && this._config.archive_id ? this._config.archive_id : "archive").trim();
    const rendererMode = String(this._rendererMode || "viewer").trim().toLowerCase();
    const now = new Date();
    const timestamp = now.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
    return `viewer-capture-${archiveId}-${rendererMode}-${timestamp}.png`;
  }

  _getStageElement() {
    const stage = this.shadowRoot && this.shadowRoot.getElementById("viewer-stage");
    return stage instanceof HTMLElement ? stage : null;
  }

  _getStageMetrics() {
    const stage = this._getStageElement();
    if (!stage) {
      return null;
    }
    const rect = stage.getBoundingClientRect();
    const width = Math.max(1, stage.clientWidth || Math.round(rect.width) || 1);
    const height = Math.max(1, stage.clientHeight || Math.round(rect.height) || 1);
    return { width, height, rect };
  }

  _syncViewerCanvasSize() {
    const canvas = this.shadowRoot && this.shadowRoot.getElementById("viewer-canvas");
    const metrics = this._getStageMetrics();
    if (!(canvas instanceof HTMLCanvasElement) || !metrics) {
      return;
    }
    if (canvas.width !== metrics.width) {
      canvas.width = metrics.width;
    }
    if (canvas.height !== metrics.height) {
      canvas.height = metrics.height;
    }

    const preview = this._preview;
    if (preview && typeof preview.resize === "function") {
      preview.resize();
    } else if (preview && typeof preview.setSize === "function") {
      preview.setSize(metrics.width, metrics.height);
    }
  }

  _getCropAspectRatio() {
    return Object.prototype.hasOwnProperty.call(CROP_PRESETS, this._cropAspectPreset)
      ? CROP_PRESETS[this._cropAspectPreset]
      : CROP_PRESETS.square;
  }

  _cropPresetLabel() {
    switch (this._cropAspectPreset) {
      case "free":
        return "Freeform crop";
      case "landscape4x3":
        return "Landscape 4:3 crop";
      case "landscape16x9":
        return "Landscape 16:9 crop";
      default:
        return "Square crop";
    }
  }

  _buildDefaultCropRect(width, height) {
    const safeWidth = Math.max(1, Number(width) || 1);
    const safeHeight = Math.max(1, Number(height) || 1);
    const maxWidth = safeWidth * 0.78;
    const maxHeight = safeHeight * 0.78;
    const ratio = this._getCropAspectRatio();
    let cropWidth = maxWidth;
    let cropHeight = maxHeight;

    if (ratio) {
      cropHeight = cropWidth / ratio;
      if (cropHeight > maxHeight) {
        cropHeight = maxHeight;
        cropWidth = cropHeight * ratio;
      }
    }

    return {
      x: Math.round((safeWidth - cropWidth) / 2),
      y: Math.round((safeHeight - cropHeight) / 2),
      width: Math.round(cropWidth),
      height: Math.round(cropHeight),
    };
  }

  _clampCropRect(rect, stageWidth, stageHeight) {
    const minSize = 48;
    const safeWidth = Math.max(1, Number(stageWidth) || 1);
    const safeHeight = Math.max(1, Number(stageHeight) || 1);
    const ratio = this._getCropAspectRatio();
    let width = Math.max(minSize, Math.min(Number(rect.width) || minSize, safeWidth));
    let height = Math.max(minSize, Math.min(Number(rect.height) || minSize, safeHeight));

    if (ratio) {
      height = width / ratio;
      if (height > safeHeight) {
        height = safeHeight;
        width = height * ratio;
      }
      if (height < minSize) {
        height = minSize;
        width = height * ratio;
      }
      if (width < minSize) {
        width = minSize;
        height = width / ratio;
      }
      if (width > safeWidth) {
        width = safeWidth;
        height = width / ratio;
      }
    }

    let x = Number(rect.x) || 0;
    let y = Number(rect.y) || 0;
    x = Math.min(Math.max(0, x), Math.max(0, safeWidth - width));
    y = Math.min(Math.max(0, y), Math.max(0, safeHeight - height));
    return {
      x: Math.round(x),
      y: Math.round(y),
      width: Math.round(width),
      height: Math.round(height),
    };
  }

  _ensureCropRect(reset) {
    const metrics = this._getStageMetrics();
    if (!metrics) {
      return null;
    }
    if (!this._cropRect || reset) {
      this._cropRect = this._clampCropRect(this._buildDefaultCropRect(metrics.width, metrics.height), metrics.width, metrics.height);
      return this._cropRect;
    }
    this._cropRect = this._clampCropRect(this._cropRect, metrics.width, metrics.height);
    return this._cropRect;
  }

  _updateCropOverlay() {
    const layer = this.shadowRoot && this.shadowRoot.getElementById("crop-layer");
    const box = this.shadowRoot && this.shadowRoot.getElementById("crop-box");
    const maskTop = this.shadowRoot && this.shadowRoot.getElementById("crop-mask-top");
    const maskLeft = this.shadowRoot && this.shadowRoot.getElementById("crop-mask-left");
    const maskRight = this.shadowRoot && this.shadowRoot.getElementById("crop-mask-right");
    const maskBottom = this.shadowRoot && this.shadowRoot.getElementById("crop-mask-bottom");
    if (!layer || !box || !maskTop || !maskLeft || !maskRight || !maskBottom) {
      return;
    }

    layer.classList.toggle("active", this._cropMode);
    layer.setAttribute("aria-hidden", this._cropMode ? "false" : "true");
    if (this._cropAspectSelect) {
      this._cropAspectSelect.value = this._cropAspectPreset;
    }
    if (!this._cropMode) {
      return;
    }

    const metrics = this._getStageMetrics();
    const rect = this._ensureCropRect(false);
    if (!metrics || !rect) {
      return;
    }

    box.style.left = `${rect.x}px`;
    box.style.top = `${rect.y}px`;
    box.style.width = `${rect.width}px`;
    box.style.height = `${rect.height}px`;

    maskTop.style.left = "0px";
    maskTop.style.top = "0px";
    maskTop.style.width = `${metrics.width}px`;
    maskTop.style.height = `${rect.y}px`;

    maskLeft.style.left = "0px";
    maskLeft.style.top = `${rect.y}px`;
    maskLeft.style.width = `${rect.x}px`;
    maskLeft.style.height = `${rect.height}px`;

    maskRight.style.left = `${rect.x + rect.width}px`;
    maskRight.style.top = `${rect.y}px`;
    maskRight.style.width = `${Math.max(0, metrics.width - rect.x - rect.width)}px`;
    maskRight.style.height = `${rect.height}px`;

    maskBottom.style.left = "0px";
    maskBottom.style.top = `${rect.y + rect.height}px`;
    maskBottom.style.width = `${metrics.width}px`;
    maskBottom.style.height = `${Math.max(0, metrics.height - rect.y - rect.height)}px`;
  }

  _setCropMode(enabled) {
    this._cropMode = !!enabled;
    this._cropDrag = null;
    if (this._cropMode) {
      this._ensureCropRect(!this._cropRect);
      this._setCaptureStatus("Crop mode is active.", "info");
      this._focusCapturePanel("crop");
    }
    this._updateCapturePanel();
  }

  _buildCornerRect(anchorX, anchorY, pointerX, pointerY, handle, stageWidth, stageHeight) {
    const minSize = 48;
    const ratio = this._getCropAspectRatio();
    let width = Math.max(minSize, Math.abs(pointerX - anchorX));
    let height = Math.max(minSize, Math.abs(pointerY - anchorY));

    if (ratio) {
      if (width / height > ratio) {
        height = width / ratio;
      } else {
        width = height * ratio;
      }
    }

    const x = handle.indexOf("w") >= 0 ? anchorX - width : anchorX;
    const y = handle.indexOf("n") >= 0 ? anchorY - height : anchorY;
    return this._clampCropRect({ x, y, width, height }, stageWidth, stageHeight);
  }

  _pointerPosition(event) {
    const stage = this._getStageElement();
    if (!stage) {
      return null;
    }
    const rect = stage.getBoundingClientRect();
    return {
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    };
  }

  _handleCropPointerDown(event) {
    if (!this._cropMode) {
      return;
    }
    const metrics = this._getStageMetrics();
    const rect = this._ensureCropRect(false);
    if (!metrics || !rect) {
      return;
    }
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    const position = this._pointerPosition(event);
    if (!position) {
      return;
    }

    const handle = target.dataset && target.dataset.handle ? String(target.dataset.handle) : "";
    if (handle) {
      let anchorX = rect.x;
      let anchorY = rect.y;
      if (handle === "nw") {
        anchorX = rect.x + rect.width;
        anchorY = rect.y + rect.height;
      } else if (handle === "ne") {
        anchorX = rect.x;
        anchorY = rect.y + rect.height;
      } else if (handle === "sw") {
        anchorX = rect.x + rect.width;
        anchorY = rect.y;
      } else if (handle === "se") {
        anchorX = rect.x;
        anchorY = rect.y;
      }
      this._cropDrag = {
        type: "resize",
        handle,
        anchorX,
        anchorY,
        stageWidth: metrics.width,
        stageHeight: metrics.height,
      };
    } else if (target.id === "crop-box" || target.closest("#crop-box")) {
      this._cropDrag = {
        type: "move",
        startX: position.x,
        startY: position.y,
        originX: rect.x,
        originY: rect.y,
        width: rect.width,
        height: rect.height,
        stageWidth: metrics.width,
        stageHeight: metrics.height,
      };
    }

    if (this._cropDrag) {
      event.preventDefault();
    }
  }

  _handleWindowPointerMove(event) {
    if (!this._cropDrag || !this._cropMode) {
      return;
    }
    const position = this._pointerPosition(event);
    if (!position) {
      return;
    }

    if (this._cropDrag.type === "move") {
      const nextX = this._cropDrag.originX + (position.x - this._cropDrag.startX);
      const nextY = this._cropDrag.originY + (position.y - this._cropDrag.startY);
      this._cropRect = this._clampCropRect(
        {
          x: nextX,
          y: nextY,
          width: this._cropDrag.width,
          height: this._cropDrag.height,
        },
        this._cropDrag.stageWidth,
        this._cropDrag.stageHeight
      );
    } else if (this._cropDrag.type === "resize") {
      this._cropRect = this._buildCornerRect(
        this._cropDrag.anchorX,
        this._cropDrag.anchorY,
        position.x,
        position.y,
        this._cropDrag.handle,
        this._cropDrag.stageWidth,
        this._cropDrag.stageHeight
      );
    }

    this._updateCropOverlay();
  }

  _handleWindowPointerUp() {
    if (!this._cropDrag) {
      return;
    }
    this._cropDrag = null;
  }

  _handleWindowResize() {
    this._syncViewerCanvasSize();
    if (!this._cropMode) {
      return;
    }
    this._ensureCropRect(false);
    this._updateCropOverlay();
  }

  _handleCropAspectChange(event) {
    const target = event.target;
    this._cropAspectPreset = Object.prototype.hasOwnProperty.call(CROP_PRESETS, target && target.value ? String(target.value) : "")
      ? String(target.value)
      : "square";
    if (this._cropMode) {
      this._ensureCropRect(true);
      this._updateCropOverlay();
    }
    this._updateCapturePanel();
  }

  _handleResetCrop() {
    if (!this._cropMode) {
      return;
    }
    this._ensureCropRect(true);
    this._updateCropOverlay();
    this._setCaptureStatus("Crop reset.", "info");
  }

  _handleCancelCrop() {
    this._setCropMode(false);
  }

  async _handleCropToggle() {
    try {
      if (!this._cropMode) {
        this._setCropMode(true);
        return;
      }
      await this._captureCurrentView();
    } catch (error) {
      const message = error && error.message ? error.message : String(error);
      this._setCaptureStatus(message || "Crop capture failed.", "error");
    }
  }

  async _captureCurrentView() {
    const canvas = this.shadowRoot && this.shadowRoot.getElementById("viewer-canvas");
    if (!(canvas instanceof HTMLCanvasElement)) {
      throw new Error("Viewer canvas is not available.");
    }
    const sourceWidth = canvas.width || canvas.clientWidth || 0;
    const sourceHeight = canvas.height || canvas.clientHeight || 0;
    if (sourceWidth <= 0 || sourceHeight <= 0) {
      throw new Error("The viewer has not rendered a captureable frame yet.");
    }

    const metrics = this._getStageMetrics();
    const cropRect = this._cropMode ? this._ensureCropRect(false) : null;
    const sourceX = cropRect && metrics ? Math.max(0, Math.round((cropRect.x / metrics.width) * sourceWidth)) : 0;
    const sourceY = cropRect && metrics ? Math.max(0, Math.round((cropRect.y / metrics.height) * sourceHeight)) : 0;
    const sourceCropWidth = cropRect && metrics ? Math.max(1, Math.round((cropRect.width / metrics.width) * sourceWidth)) : sourceWidth;
    const sourceCropHeight = cropRect && metrics ? Math.max(1, Math.round((cropRect.height / metrics.height) * sourceHeight)) : sourceHeight;
    const dimensions = this._scaledDimensions(sourceCropWidth, sourceCropHeight, 2048);
    const exportCanvas = document.createElement("canvas");
    exportCanvas.width = dimensions.width;
    exportCanvas.height = dimensions.height;
    const context = exportCanvas.getContext("2d");
    if (!context) {
      throw new Error("Canvas rendering is unavailable for capture.");
    }
    context.drawImage(
      canvas,
      sourceX,
      sourceY,
      sourceCropWidth,
      sourceCropHeight,
      0,
      0,
      dimensions.width,
      dimensions.height
    );
    const blob = await this._canvasToBlob(exportCanvas, "image/png");
    const cropLabel = cropRect ? this._cropPresetLabel() : "Full-frame capture";

    this._revokeCapture();
    this._capture = {
      blob,
      objectUrl: URL.createObjectURL(blob),
      width: dimensions.width,
      height: dimensions.height,
      mimeType: "image/png",
      fileName: this._buildCaptureFileName(),
      cropLabel,
    };
    this._updateCapturePanel();
    this._setCaptureStatus(`Captured ${cropLabel.toLowerCase()}.`, "success");
    this._focusCapturePanel("capture");
  }

  async _handleCapture() {
    try {
      if (this._cropMode) {
        this._setCropMode(false);
      }
      await this._captureCurrentView();
    } catch (error) {
      const message = error && error.message ? error.message : String(error);
      this._setCaptureStatus(message || "Capture failed.", "error");
    }
  }

  _downloadCapture() {
    if (!this._capture || !this._capture.objectUrl) {
      return;
    }
    const anchor = document.createElement("a");
    anchor.href = this._capture.objectUrl;
    anchor.download = this._capture.fileName;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  }

  async _uploadCapture() {
    if (!this._capture || !this._config || !this._config.archive_id) {
      return;
    }
    this._uploadInProgress = true;
    this._updateCapturePanel();
    this._setCaptureStatus("Uploading capture to the archive...", "info");
    this._focusCapturePanel("upload");

    try {
      const payload = await this._hass.callWS({
        type: "bambuddy/print_history_upload_photo",
        archive_id: Number(this._config.archive_id),
        entry_id: this._config.entry_id || undefined,
        file_name: this._capture.fileName,
        mime_type: this._capture.mimeType,
        content_base64: await this._blobToBase64(this._capture.blob),
      });
      const uploadedPhotoPath = String(payload && payload.uploaded_photo_path ? payload.uploaded_photo_path : this._capture.fileName || "").trim();
      if (uploadedPhotoPath) {
        this._capture.fileName = uploadedPhotoPath;
      }
      this._setCaptureStatus("Capture uploaded to the archive photo gallery.", "success");
    } catch (error) {
      const message = error && error.message ? error.message : String(error);
      this._setCaptureStatus(message || "Capture upload failed.", "error");
    } finally {
      this._uploadInProgress = false;
      this._updateCapturePanel();
    }
  }

  async _handleUploadCapture() {
    await this._uploadCapture();
  }

  _escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  _parseArchiveConfig(value) {
    if (!value) {
      return null;
    }
    if (typeof value === "string") {
      try {
        const parsed = JSON.parse(value);
        return parsed && typeof parsed === "object" ? parsed : null;
      } catch (_error) {
        return null;
      }
    }
    return value && typeof value === "object" ? value : null;
  }

  _normalizeHex(value) {
    const raw = String(value || "").trim().replace(/^#/, "").replace(/"/g, "");
    if (!raw) {
      return "";
    }
    const trimmed = raw.length === 8 ? raw.slice(0, 6) : raw;
    return /^[0-9a-fA-F]{6}$/.test(trimmed) ? `#${trimmed.toUpperCase()}` : "";
  }

  _normalizeColors(colors) {
    if (!Array.isArray(colors)) {
      return [];
    }
    return colors.map(this._normalizeHex.bind(this)).filter(Boolean);
  }

  _normalizeArchiveColorList(value) {
    if (Array.isArray(value)) {
      return this._normalizeColors(value);
    }
    return String(value || "")
      .split(",")
      .map(this._normalizeHex.bind(this))
      .filter(Boolean);
  }

  _archiveUsedColors() {
    const archive = this._config && this._config.archive && typeof this._config.archive === "object"
      ? this._config.archive
      : null;
    if (!archive) {
      return [];
    }

    const colors = [];
    const seen = {};
    const pushColor = (value) => {
      const color = this._normalizeHex(value);
      if (!color || seen[color]) {
        return;
      }
      seen[color] = true;
      colors.push(color);
    };

    const notes = String(archive.notes || "").trim();
    if (notes.indexOf("+>") === 0) {
      try {
        const payload = JSON.parse(notes.slice(2));
        const rows = payload && Array.isArray(payload.F) ? payload.F : [];
        rows.forEach((row) => {
          if (row && typeof row === "object") {
            pushColor(row.h || row.color);
          }
        });
      } catch (_error) {
        // Ignore malformed enrichment payloads and fall through to archive slots.
      }
    }

    const slots = Array.isArray(archive.filament_slots) ? archive.filament_slots : [];
    slots.forEach((slot) => {
      if (!slot || typeof slot !== "object") {
        return;
      }
      const usedGrams = Number(slot.used_grams != null ? slot.used_grams : slot.used_g);
      if (Number.isFinite(usedGrams) && usedGrams > 0) {
        pushColor(slot.color || slot.hex || slot.h);
      }
    });

    if (colors.length) {
      return colors;
    }
    return this._normalizeArchiveColorList(archive.filament_color);
  }

  _extractToolIdsFromGcode(gcodeText) {
    const lines = String(gcodeText || "").split("\n");
    const toolPattern = /^T(\d+)\s*$/;
    const toolIds = [];
    const seen = {};

    for (let index = 0; index < lines.length; index += 1) {
      const match = lines[index].match(toolPattern);
      if (!match) {
        continue;
      }
      const toolId = Number(match[1]);
      if (!Number.isFinite(toolId) || seen[String(toolId)]) {
        continue;
      }
      if (toolId === 1000 || toolId === 255) {
        continue;
      }
      seen[String(toolId)] = true;
      toolIds.push(toolId);
    }

    return toolIds;
  }

  _resolveInitialToolIndex(colors, gcodeText) {
    const palette = this._normalizeColors(colors);
    if (!palette.length || !/(^|\n)T1000\s*($|\n)/m.test(String(gcodeText || ""))) {
      return null;
    }

    const explicitToolIds = this._extractToolIdsFromGcode(gcodeText);
    const explicitSet = {};
    explicitToolIds.forEach((toolId) => {
      explicitSet[String(toolId)] = true;
    });

    const candidateIds = [];
    for (let index = 0; index < palette.length; index += 1) {
      if (!explicitSet[String(index)]) {
        candidateIds.push(index);
      }
    }
    if (candidateIds.length === 1) {
      return candidateIds[0];
    }

    const usedColors = this._archiveUsedColors();
    if (usedColors.length === 1) {
      const usedColor = usedColors[0];
      const matchingIndex = palette.indexOf(usedColor);
      if (matchingIndex >= 0) {
        return matchingIndex;
      }
    }

    const paletteMatches = candidateIds.filter((candidateId) => usedColors.indexOf(palette[candidateId]) >= 0);
    if (paletteMatches.length === 1) {
      return paletteMatches[0];
    }

    return null;
  }

  _singleArchiveFallbackColor() {
    const archive = this._config && this._config.archive && typeof this._config.archive === "object"
      ? this._config.archive
      : null;
    if (!archive) {
      return "";
    }

    const slots = Array.isArray(archive.filament_slots) ? archive.filament_slots : [];
    const usedSlotColors = slots.reduce((colors, slot) => {
      if (!slot || typeof slot !== "object") {
        return colors;
      }
      const color = this._normalizeHex(slot.color || slot.hex || slot.h);
      const usedGrams = Number(slot.used_grams != null ? slot.used_grams : slot.used_g);
      if (color && Number.isFinite(usedGrams) && usedGrams > 0) {
        colors.push(color);
      }
      return colors;
    }, []);

    const distinctUsedSlotColors = Array.from(new Set(usedSlotColors));
    if (distinctUsedSlotColors.length === 1) {
      return distinctUsedSlotColors[0];
    }

    const slotColors = slots
      .map((slot) => (slot && typeof slot === "object" ? this._normalizeHex(slot.color || slot.hex || slot.h) : ""))
      .filter(Boolean);
    const distinctSlotColors = Array.from(new Set(slotColors));
    if (distinctSlotColors.length === 1) {
      return distinctSlotColors[0];
    }

    const archiveColors = this._normalizeArchiveColorList(archive.filament_color);
    return archiveColors.length === 1 ? archiveColors[0] : "";
  }

  _extractFilamentColorsFromGcode(gcodeText) {
    const match = String(gcodeText || "").match(/^\s*;\s*filament_colour\s*=\s*(.+)$/im);
    if (!match || !match[1]) {
      return [];
    }
    return this._normalizeColors(match[1].split(";"));
  }

  _resolvePreviewColors(capabilities, gcodeText) {
    const toolIds = this._extractToolIdsFromGcode(gcodeText);
    if (!toolIds.length) {
      const archiveFallbackColor = this._singleArchiveFallbackColor();
      if (archiveFallbackColor) {
        return [archiveFallbackColor];
      }
    }

    const gcodeColors = this._extractFilamentColorsFromGcode(gcodeText);
    if (gcodeColors.length) {
      return gcodeColors;
    }
    const archiveColors = this._normalizeArchiveColorList(this._config && this._config.archive ? this._config.archive.filament_color : "");
    if (archiveColors.length) {
      return archiveColors;
    }
    return this._normalizeColors(capabilities.filament_colors);
  }

  _buildPreviewToolState(colors, gcodeText, initialToolIndex) {
    const palette = this._normalizeColors(colors);
    const explicitToolIds = this._extractToolIdsFromGcode(gcodeText);
    const sawInitialToolPlaceholder = /(^|\n)T1000\s*($|\n)/m.test(String(gcodeText || ""));
    const normalizedInitialTool = Number.isInteger(initialToolIndex) && initialToolIndex >= 0 ? initialToolIndex : 0;
    const orderedToolIds = explicitToolIds.slice();
    const toolMap = {};
    const previewPalette = [];

    if (sawInitialToolPlaceholder && orderedToolIds.indexOf(normalizedInitialTool) < 0) {
      orderedToolIds.unshift(normalizedInitialTool);
    }

    if (!orderedToolIds.length) {
      if (palette.length && palette[normalizedInitialTool]) {
        previewPalette.push(palette[normalizedInitialTool]);
      }
      for (let index = 0; index < Math.min(palette.length, 8); index += 1) {
        if (!previewPalette[index]) {
          previewPalette[index] = palette[index];
        }
      }
      return {
        mode: "compact",
        defaultToolIndex: 0,
        previewPalette: previewPalette.filter(Boolean),
        toolMap,
        maxKnownTool: null,
      };
    }

    for (let index = 0; index < orderedToolIds.length; index += 1) {
      const toolId = orderedToolIds[index];
      const mappedToolId = index % 8;
      toolMap[String(toolId)] = mappedToolId;
      if (palette[toolId]) {
        previewPalette[mappedToolId] = palette[toolId];
      } else if (!previewPalette[mappedToolId] && palette[index]) {
        previewPalette[mappedToolId] = palette[index];
      }
    }

    for (let index = 0; index < Math.min(palette.length, 8); index += 1) {
      if (!previewPalette[index] && palette[index]) {
        previewPalette[index] = palette[index];
      }
    }

    const defaultToolIndex = Object.prototype.hasOwnProperty.call(toolMap, String(normalizedInitialTool))
      ? toolMap[String(normalizedInitialTool)]
      : 0;

    return {
      mode: "compact",
      defaultToolIndex,
      previewPalette: previewPalette.filter(Boolean),
      toolMap,
      maxKnownTool: null,
    };
  }

  _normalizePreviewGcode(gcodeText, toolState) {
    const source = String(gcodeText || "");
    if (!source) {
      return source;
    }

    const normalizedToolState = toolState && typeof toolState === "object" ? toolState : {};
    const mode = normalizedToolState.mode === "legacy" ? "legacy" : "compact";
    const toolMap = normalizedToolState.toolMap && typeof normalizedToolState.toolMap === "object"
      ? normalizedToolState.toolMap
      : {};
    const defaultToolIndex = Number.isInteger(normalizedToolState.defaultToolIndex) && normalizedToolState.defaultToolIndex >= 0
      ? normalizedToolState.defaultToolIndex
      : 0;
    const maxKnownTool = Number.isInteger(normalizedToolState.maxKnownTool) && normalizedToolState.maxKnownTool >= 0
      ? normalizedToolState.maxKnownTool
      : null;
    const lines = source.split("\n");
    const toolPattern = /^T(\d+)\s*$/;
    let currentTool = null;
    let sawAnyTool = false;

    const normalizedLines = lines.map((line) => {
      const match = line.match(toolPattern);
      if (!match) {
        return line;
      }

      sawAnyTool = true;
      const tool = Number(match[1]);
      if (!Number.isFinite(tool)) {
        return line;
      }

      let normalizedTool = defaultToolIndex;
      if (mode === "legacy") {
        if (maxKnownTool != null) {
          if (tool >= 0 && tool <= maxKnownTool) {
            normalizedTool = tool;
          } else if (tool === 1000) {
            normalizedTool = defaultToolIndex;
          } else if (tool === 255 && currentTool != null) {
            normalizedTool = currentTool;
          } else if (currentTool != null) {
            normalizedTool = currentTool;
          }
        }
      } else if (tool === 1000) {
        normalizedTool = defaultToolIndex;
      } else if (tool === 255 && currentTool != null) {
        normalizedTool = currentTool;
      } else if (Object.prototype.hasOwnProperty.call(toolMap, String(tool))) {
        normalizedTool = toolMap[String(tool)];
      } else if (currentTool != null) {
        normalizedTool = currentTool;
      }

      currentTool = normalizedTool;
      return `T${normalizedTool}`;
    });

    if (!sawAnyTool) {
      normalizedLines.unshift(`T${defaultToolIndex}`);
    }

    return normalizedLines.join("\n");
  }

  _normalizeBuildVolume(buildVolume) {
    if (!buildVolume || typeof buildVolume !== "object") {
      return { x: 256, y: 256, z: 256 };
    }
    const x = Number(buildVolume.x || 256);
    const y = Number(buildVolume.y || 256);
    const z = Number(buildVolume.z || 256);
    return {
      x: Number.isFinite(x) && x > 0 ? x : 256,
      y: Number.isFinite(y) && y > 0 ? y : 256,
      z: Number.isFinite(z) && z > 0 ? z : 256,
    };
  }

  _extractBuildVolumeFromGcode(gcodeText) {
    const source = String(gcodeText || "");
    if (!source) {
      return null;
    }

    const bedShapeMatch = source.match(/^\s*;\s*bed_shape\s*=\s*(.+)$/im);
    const heightMatch = source.match(/^\s*;\s*(?:printable_height|max_print_height)\s*=\s*([0-9.]+)\s*$/im);
    let x = null;
    let y = null;
    let z = null;

    if (bedShapeMatch && bedShapeMatch[1]) {
      const pairs = bedShapeMatch[1].split(",").map((token) => token.trim());
      const xs = [];
      const ys = [];
      for (let index = 0; index < pairs.length; index += 1) {
        const parts = pairs[index].split("x");
        if (parts.length !== 2) {
          continue;
        }
        const parsedX = Number(parts[0]);
        const parsedY = Number(parts[1]);
        if (Number.isFinite(parsedX)) {
          xs.push(parsedX);
        }
        if (Number.isFinite(parsedY)) {
          ys.push(parsedY);
        }
      }
      if (xs.length) {
        x = Math.max.apply(null, xs);
      }
      if (ys.length) {
        y = Math.max.apply(null, ys);
      }
    }

    if (heightMatch && heightMatch[1]) {
      const parsedZ = Number(heightMatch[1]);
      if (Number.isFinite(parsedZ) && parsedZ > 0) {
        z = parsedZ;
      }
    }

    if (x == null && y == null && z == null) {
      return null;
    }
    return {
      x: Number.isFinite(x) && x > 0 ? x : 256,
      y: Number.isFinite(y) && y > 0 ? y : 256,
      z: Number.isFinite(z) && z > 0 ? z : 256,
    };
  }

  _resolveBuildVolume(capabilities, gcodeText) {
    const capabilityVolume = this._normalizeBuildVolume(capabilities && capabilities.build_volume ? capabilities.build_volume : null);
    const gcodeVolume = this._extractBuildVolumeFromGcode(gcodeText);
    return {
      x: gcodeVolume && Number.isFinite(gcodeVolume.x) && gcodeVolume.x > 0 ? gcodeVolume.x : capabilityVolume.x,
      y: gcodeVolume && Number.isFinite(gcodeVolume.y) && gcodeVolume.y > 0 ? gcodeVolume.y : capabilityVolume.y,
      z: gcodeVolume && Number.isFinite(gcodeVolume.z) && gcodeVolume.z > 0 ? gcodeVolume.z : capabilityVolume.z,
    };
  }

  _resolveNozzleDiameter(gcodeText) {
    const archive = this._config && this._config.archive && typeof this._config.archive === "object"
      ? this._config.archive
      : null;
    const archiveDiameter = archive ? Number(archive.nozzle_diameter) : NaN;
    if (Number.isFinite(archiveDiameter) && archiveDiameter > 0) {
      return archiveDiameter;
    }
    const match = String(gcodeText || "").match(/^\s*;\s*nozzle_diameter\s*=\s*([0-9.]+)\s*$/im);
    const parsed = match && match[1] ? Number(match[1]) : NaN;
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 0.4;
  }

  _applySceneManagerColors(preview) {
    const sceneManager = preview && preview.sceneManager ? preview.sceneManager : null;
    if (!sceneManager) {
      return;
    }
    if (this._viewerSettings.backgroundColor) {
      sceneManager.backgroundColor = this._viewerSettings.backgroundColor;
    }
    if (this._viewerSettings.showTravelMoves && this._viewerSettings.travelColor) {
      sceneManager.travelColor = this._viewerSettings.travelColor;
    }
    const buildVolume = sceneManager.buildVolume;
    if (buildVolume) {
      if (this._viewerSettings.gridColor && Object.prototype.hasOwnProperty.call(buildVolume, "gridColor")) {
        buildVolume.gridColor = buildVolume.gridColor && typeof buildVolume.gridColor.set === "function"
          ? buildVolume.gridColor.set(this._viewerSettings.gridColor)
          : buildVolume.gridColor;
      }
      if (this._viewerSettings.gridColor && Object.prototype.hasOwnProperty.call(buildVolume, "smallGridColor")) {
        buildVolume.smallGridColor = buildVolume.smallGridColor && typeof buildVolume.smallGridColor.set === "function"
          ? buildVolume.smallGridColor.set(this._viewerSettings.gridColor)
          : buildVolume.smallGridColor;
      }
      if (typeof buildVolume.update === "function") {
        buildVolume.update();
      }
    }
  }

  async _fetchViewerPayload() {
    return this._hass.callWS({
      type: "bambuddy/print_history_archive_viewer",
      archive_id: Number(this._config.archive_id),
      entry_id: this._config.entry_id || undefined,
      include_gcode: true,
    });
  }

  _setStatus(message, isError = false) {
    const status = this.shadowRoot && this.shadowRoot.getElementById("viewer-footnote");
    if (!status) {
      return;
    }
    status.textContent = message;
    status.className = isError ? "footnote error" : "footnote";
  }

  _setTitle(title, subtitle) {
    const titleNode = this.shadowRoot && this.shadowRoot.getElementById("viewer-title");
    const subtitleNode = this.shadowRoot && this.shadowRoot.getElementById("viewer-subtitle");
    if (titleNode) {
      titleNode.textContent = title;
    }
    if (subtitleNode) {
      const subtitleText = String(subtitle || "").trim();
      subtitleNode.textContent = subtitleText;
      subtitleNode.hidden = !subtitleText;
    }
  }

  _archiveChipMarkup() {
    const archiveId = this._config && this._config.archive_id ? String(this._config.archive_id).trim() : "";
    if (!archiveId) {
      return "";
    }
    return `<span class='chip'>Archive #${this._escapeHtml(archiveId)}</span>`;
  }

  _renderCapabilityChips(capabilities, colors) {
    const chips = this.shadowRoot && this.shadowRoot.getElementById("capability-chips");
    if (!chips) {
      return;
    }
    const buildVolume = this._effectiveBuildVolume();
    const renderAnimated = this._renderAnimated;
    const chipMarkup = [
      this._archiveChipMarkup(),
      `<span class='chip${capabilities.has_gcode ? "" : " warn"}'>G-code ${capabilities.has_gcode ? "Available" : "Unavailable"}</span>`,
      `<span class='chip${capabilities.has_model ? "" : " warn"}'>3D Model ${capabilities.has_model ? "Available" : "Unavailable"}</span>`,
      `<span class='chip'>Build ${buildVolume.x} x ${buildVolume.y} x ${buildVolume.z}</span>`,
      `<span class='chip'>${renderAnimated ? "Animated Preview" : "Static Preview"}</span>`,
    ].filter(Boolean);
    if (capabilities.has_source) {
      chipMarkup.push("<span class='chip'>Source 3MF Attached</span>");
    }
    if (colors.length) {
      chipMarkup.push(`<span class='chip'>${colors.length} Filament Color${colors.length === 1 ? "" : "s"}</span>`);
    }
    chips.innerHTML = chipMarkup.join("");
  }

  _renderOverlay(colors) {
    const overlay = this.shadowRoot && this.shadowRoot.getElementById("viewer-overlay");
    if (!overlay) {
      return;
    }
    const items = [];
    for (let index = 0; index < colors.length; index += 1) {
      const color = colors[index];
      items.push(
        `<span class='chip' title='Tool T${index}'><span style='display:inline-block;width:12px;height:12px;border-radius:999px;background:${this._escapeHtml(color)};box-shadow:inset 0 0 0 1px rgba(255,255,255,0.28);'></span>T${index}</span>`
      );
    }
    overlay.innerHTML = items.join("");
  }

  _setDownloadLink(gcodeUrl) {
    const downloadLink = this.shadowRoot && this.shadowRoot.getElementById("download-link");
    const archiveName = this._config && this._config.archive_name ? this._config.archive_name : `archive-${this._config.archive_id}`;

    if (downloadLink) {
      downloadLink.href = gcodeUrl;
      downloadLink.download = `${archiveName}.gcode`;
    }
  }

  _showFallback(message, gcodeText) {
    const panel = this.shadowRoot && this.shadowRoot.getElementById("fallback-panel");
    const copy = this.shadowRoot && this.shadowRoot.getElementById("fallback-copy");
    const snippet = this.shadowRoot && this.shadowRoot.getElementById("fallback-snippet");
    if (!panel || !copy || !snippet) {
      return;
    }
    panel.classList.add("visible");
    copy.textContent = message;
    snippet.textContent = String(gcodeText || "").split("\n").slice(0, 80).join("\n");
  }

  _hideFallback() {
    const panel = this.shadowRoot && this.shadowRoot.getElementById("fallback-panel");
    const copy = this.shadowRoot && this.shadowRoot.getElementById("fallback-copy");
    const snippet = this.shadowRoot && this.shadowRoot.getElementById("fallback-snippet");
    if (!panel || !copy || !snippet) {
      return;
    }
    panel.classList.remove("visible");
    copy.textContent = "";
    snippet.textContent = "";
  }

  async _loadViewer() {
    const token = ++this._loadToken;
    const archiveId = this._config && this._config.archive_id ? this._config.archive_id : "";
    const archiveTitle = this._config && this._config.archive_name ? this._config.archive_name : `Archive ${archiveId}`;
    const renderAnimated = this._renderAnimated;

    if (!archiveId) {
      this._setStageStatus("Viewer unavailable", "This popup cannot render because the archive ID is missing.", "error");
      this._setTitle("3D Viewer", "No archive ID was provided to the popup.");
      this._setStatus("Archive viewer could not start because archive_id is missing.", true);
      this._showFallback("Launch this popup from a print-history archive card or popup action.", "");
      return;
    }

    this._setTitle(archiveTitle, "");
    this._disposePreview();
    this._hideFallback();
    this._setStageStatus("Loading 3D viewer", "Preparing archive preview inside the render stage.");

    const gcodeUrl = this._buildProxyUrl(`/api/bambuddy/print-history/archive-viewer/${encodeURIComponent(archiveId)}/gcode`);
    this._setDownloadLink(gcodeUrl);

    try {
      this._setStageStatus("Checking archive capabilities", "Validating which viewer assets are available for this print.");
      this._setStatus("Checking archive viewer capabilities...");
      const viewerPayload = await this._fetchViewerPayload();
      if (token !== this._loadToken) {
        return;
      }
      const capabilities = viewerPayload && typeof viewerPayload.capabilities === "object"
        ? viewerPayload.capabilities
        : {};

      if (!capabilities.has_gcode) {
        this._setStageStatus("Interactive preview unavailable", "This archive does not expose extracted G-code, so the popup cannot render the interactive stage.", "error");
        this._setStatus("This archive does not expose extracted G-code, so the preview cannot be rendered here.", true);
        this._showFallback(
          capabilities.has_model
            ? "The archive still has a 3D model, but this popup does not have a reusable deep-link route for that viewer yet."
            : "This archive has neither extracted G-code nor a usable model preview path for this popup.",
          ""
        );
        return;
      }

      this._setStageStatus("Downloading G-code", "Pulling the sliced toolpath so the stage can render it.");
      this._setStatus("Downloading G-code for the viewer...");
      const gcodeText = viewerPayload && typeof viewerPayload.gcode === "string" ? viewerPayload.gcode : "";
      if (!String(gcodeText || "").trim()) {
        this._setStageStatus("Empty G-code payload", "The archive returned no renderable toolpath data.", "error");
        this._setStatus("The archive returned an empty G-code payload for this viewer.", true);
        this._showFallback("The archive G-code payload was empty.", "");
        return;
      }

      const resolvedBuildVolume = this._resolveBuildVolume(capabilities, gcodeText);
      const resolvedNozzleDiameter = this._resolveNozzleDiameter(gcodeText);
      this._resolvedBuildVolume = resolvedBuildVolume;
      this._resolvedNozzleDiameter = resolvedNozzleDiameter;
      if (this._viewerSettings.buildVolumeX == null) {
        this._viewerSettings.buildVolumeX = resolvedBuildVolume.x;
      }
      if (this._viewerSettings.buildVolumeY == null) {
        this._viewerSettings.buildVolumeY = resolvedBuildVolume.y;
      }
      if (this._viewerSettings.buildVolumeZ == null) {
        this._viewerSettings.buildVolumeZ = resolvedBuildVolume.z;
      }
      if (this._viewerSettings.extrusionWidth == null) {
        this._viewerSettings.extrusionWidth = resolvedNozzleDiameter;
      }

      const colors = this._resolvePreviewColors(capabilities, gcodeText);
      const initialToolIndex = this._resolveInitialToolIndex(colors, gcodeText);
      const toolState = this._buildPreviewToolState(colors, gcodeText, initialToolIndex);
      const previewColors = toolState.previewPalette.length ? toolState.previewPalette : colors;
      const previewGcode = this._normalizePreviewGcode(gcodeText, toolState);
      this._renderCapabilityChips(capabilities, previewColors);
      this._renderOverlay(previewColors);

      const canvas = this.shadowRoot && this.shadowRoot.getElementById("viewer-canvas");
      if (!(canvas instanceof HTMLCanvasElement)) {
        throw new Error("Viewer canvas is not available.");
      }
      this._syncViewerCanvasSize();

      this._setStageStatus("Rendering preview", "Building the interactive 3D toolpath view for this archive.");
      this._setStatus(renderAnimated ? "Rendering animated G-code preview..." : "Rendering G-code preview...");
      try {
        const GCodePreview = await import(PRINT_HISTORY_VIEWER_CDN_MODULE_URL);
        if (token !== this._loadToken) {
          return;
        }
        const preview = GCodePreview.init({
          canvas,
          buildVolume: this._viewerSettings.renderBuildVolume
            ? {
              x: this._effectiveBuildVolume().x,
              y: this._effectiveBuildVolume().y,
              z: this._effectiveBuildVolume().z,
              smallGrid: true,
            }
            : undefined,
          extrusionColor: previewColors.length ? previewColors : ["#7DD3C8", "#F59E0B", "#38BDF8", "#F97316"],
          disableGradient: !this._viewerSettings.useColorGradient,
          lineHeight: this._viewerSettings.useFixedLineHeight ? this._viewerSettings.lineHeight : undefined,
          lineWidth: !this._viewerSettings.renderTubes ? this._viewerSettings.lineWidth : undefined,
          extrusionWidth: this._viewerSettings.renderTubes ? this._effectiveTubeWidth() : undefined,
          renderTubes: this._viewerSettings.renderTubes,
          backgroundColor: this._viewerSettings.backgroundColor,
          allowDragNDrop: false,
          renderTravel: this._viewerSettings.showTravelMoves,
          travelColor: this._viewerSettings.showTravelMoves ? this._viewerSettings.travelColor : undefined,
          renderExtrusion: true,
          renderAnimated,
          RenderAnimated: renderAnimated,
        });
        this._preview = preview;
        this._rendererMode = "gcode";
        preview.processGCode(previewGcode);
        this._applySceneManagerColors(preview);
        this._totalLayers = this._resolvePreviewLayerCount(preview);
        if (!Number.isFinite(this._viewerSettings.endLayer) || this._viewerSettings.endLayer == null || this._viewerSettings.endLayer > this._totalLayers) {
          this._viewerSettings.endLayer = this._totalLayers;
        }
        this._restoreCameraState(preview, this._pendingCameraState);
        this._pendingCameraState = null;
        this._applyLayerScrubberState();
        this._updateConfigurationControls();
        this._syncLoadedSignature();
        if (renderAnimated) {
          if (typeof preview.renderAnimated === "function") {
            preview.renderAnimated();
          } else if (preview.sceneManager && typeof preview.sceneManager.renderAnimated === "function") {
            preview.sceneManager.renderAnimated();
          }
        }
        this._updateAnimateButton();
        this._setStageStatus("", "", "hidden");
        this._setStatus(
          renderAnimated
            ? "Rendered G-code preview with animated path build. Use drag, pan, and zoom inside the canvas."
            : "Rendered G-code preview. Use drag, pan, and zoom inside the canvas."
        );
      } catch (error) {
        const message = error && error.message ? error.message : String(error);
        this._setStageStatus("Interactive preview failed", "The viewer library could not load, so the popup fell back to raw G-code.", "error");
        this._setStatus("The interactive preview library could not be loaded, so the popup fell back to raw G-code.", true);
        this._showFallback(`Interactive preview failed to load: ${message}`, gcodeText);
      }
    } catch (error) {
      const message = error && error.message ? error.message : String(error);
      this._setStageStatus("Viewer load failed", message || "The popup could not load this archive preview.", "error");
      this._setStatus(message, true);
      this._showFallback(message, "");
    }
  }
}

if (!customElements.get("print-history-3d-viewer-card")) {
  customElements.define("print-history-3d-viewer-card", PrintHistory3dViewerCard);
}