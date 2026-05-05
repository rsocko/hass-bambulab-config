/**
 * Upload Handler Component
 * 
 * I1: Client-side file filtering before upload
 * 
 * Responsibilities:
 * 1. Receive files and excluded_items list from Validate step
 * 2. Filter files to exclude any in excluded_items array
 * 3. Only upload non-excluded files to sidecar
 * 4. Benefits: Saves bandwidth, no cleanup needed, deterministic flow
 * 
 * Part of Issue #1340: Phase I — End-to-End Testing & Deployment
 */

class UploadHandler extends HTMLElement {
  constructor() {
    super();
    this.store = window.IntakeWizardStore;
    this.state = {
      files: [],
      excluded_items: [],
      filtered_files: [],
      upload_progress: 0,
      uploading: false,
      uploaded: false,
      error: null,
      upload_id: null
    };
  }

  connectedCallback() {
    this.render();
  }

  /**
   * I1: Prepare files for upload by filtering excluded items
   * 
   * Algorithm:
   * - Create Set of excluded_items for O(1) lookup
   * - Filter files: only include those NOT in excluded set
   * - Return filtered list ready for upload
   */
  _prepareFilesForUpload(files, excluded_items) {
    const excludedSet = new Set(excluded_items);
    
    const filtered = files.filter(file => {
      // Check if file path is in excluded set
      return !excludedSet.has(file.path);
    });

    // Store statistics
    this.state.filtered_files = filtered;
    this.state.upload_progress = 0;

    return filtered;
  }

  /**
   * Get summary statistics
   */
  getUploadSummary() {
    const total = this.state.files.length;
    const excluded = this.state.excluded_items.length;
    const filtered = this.state.filtered_files.length;

    return {
      total_files: total,
      excluded_count: excluded,
      files_to_upload: filtered,
      files_skipped: total - filtered,
      bandwidth_saved: this._estimateBandwidthSaved(excluded)
    };
  }

  /**
   * Estimate bandwidth saved by not uploading excluded files
   * (Average 3MF file size ~2MB)
   */
  _estimateBandwidthSaved(excludedCount) {
    const avgSize = 2 * 1024 * 1024;  // 2MB in bytes
    return excludedCount * avgSize;
  }

  /**
   * I1: Start upload with excluded files already filtered out
   * 
   * In real scenario:
   * POST /api/intake/uploads/v2/browser-multipart
   * 
   * Only sends filtered_files (excluded items already removed)
   */
  async startUpload() {
    try {
      this.state.uploading = true;
      this.render();

      // Prepare files for upload
      const filesToUpload = this._prepareFilesForUpload(
        this.state.files,
        this.state.excluded_items
      );

      if (filesToUpload.length === 0) {
        throw new Error('No files to upload (all excluded)');
      }

      // Simulate upload progress
      await this._simulateUpload(filesToUpload);

      this.state.uploading = false;
      this.state.uploaded = true;
      this.render();

      // Dispatch completion event
      this.dispatchEvent(new CustomEvent('upload-complete', {
        detail: {
          upload_id: this.state.upload_id,
          files_uploaded: filesToUpload.length,
          files_excluded: this.state.excluded_items.length
        },
        bubbles: true,
        composed: true
      }));
    } catch (error) {
      this.state.uploading = false;
      this.state.error = error.message;
      this.render();

      this.dispatchEvent(new CustomEvent('upload-error', {
        detail: { error: error.message },
        bubbles: true,
        composed: true
      }));
    }
  }

  /**
   * Simulate upload with progress tracking
   * In real scenario, tracks actual multipart upload
   */
  async _simulateUpload(files) {
    return new Promise((resolve) => {
      const totalBytes = files.reduce((sum, f) => sum + (f.size || 0), 0);
      let uploadedBytes = 0;

      // Generate upload ID
      this.state.upload_id = this._generateUploadId();

      // Simulate progress
      const interval = setInterval(() => {
        uploadedBytes += Math.random() * (totalBytes / 10);
        if (uploadedBytes >= totalBytes) {
          uploadedBytes = totalBytes;
          this.state.upload_progress = 100;
          clearInterval(interval);
          resolve();
        } else {
          this.state.upload_progress = Math.floor((uploadedBytes / totalBytes) * 100);
          this.render();
        }
      }, 200);
    });
  }

  /**
   * Generate upload ID (mock)
   */
  _generateUploadId() {
    const timestamp = Date.now();
    const random = Math.floor(Math.random() * 10000);
    return `upload-${timestamp}-${random}`;
  }

  /**
   * Set files for upload
   */
  setFiles(files) {
    this.state.files = files || [];
  }

  /**
   * Set excluded items
   */
  setExcludedItems(excluded) {
    this.state.excluded_items = excluded || [];
  }

  /**
   * Load from store (Phase F)
   */
  loadFromStore() {
    const excluded = this.store.getExcludedItems();
    this.setExcludedItems(excluded);
  }

  render() {
    if (this.state.uploading) {
      this.innerHTML = `
        <style>
          :host {
            --upload-bg: #f5f5f5;
            --upload-text: #333;
            --primary: #2196f3;
          }

          .upload-container {
            background-color: var(--upload-bg);
            border-radius: 4px;
            padding: 20px;
            text-align: center;
          }

          .upload-title {
            font-size: 1.2em;
            font-weight: bold;
            color: var(--upload-text);
            margin-bottom: 16px;
          }

          .progress-bar {
            width: 100%;
            height: 8px;
            background-color: #e0e0e0;
            border-radius: 4px;
            overflow: hidden;
            margin: 16px 0;
          }

          .progress-fill {
            height: 100%;
            background-color: var(--primary);
            width: ${this.state.upload_progress}%;
            transition: width 0.3s ease;
          }

          .progress-text {
            font-size: 0.9em;
            color: #666;
            margin-top: 8px;
          }

          .file-info {
            font-size: 0.85em;
            color: #999;
            margin-top: 12px;
            padding: 8px;
            background-color: white;
            border-radius: 4px;
          }
        </style>

        <div class="upload-container">
          <div class="upload-title">Uploading Files</div>
          <div class="progress-bar">
            <div class="progress-fill"></div>
          </div>
          <div class="progress-text">${this.state.upload_progress}% complete</div>
          <div class="file-info">
            ${this.state.filtered_files.length} file(s) uploading
            ${this.state.excluded_items.length > 0 ? `(${this.state.excluded_items.length} excluded)` : ''}
          </div>
        </div>
      `;
      return;
    }

    if (this.state.uploaded) {
      const summary = this.getUploadSummary();

      this.innerHTML = `
        <style>
          :host {
            --upload-bg: #f0f8f0;
            --success: #2cbb2c;
            --upload-text: #333;
          }

          .upload-container {
            background-color: var(--upload-bg);
            border: 2px solid var(--success);
            border-radius: 4px;
            padding: 20px;
          }

          .upload-title {
            font-size: 1.3em;
            font-weight: bold;
            color: var(--success);
            margin-bottom: 16px;
          }

          .upload-summary {
            background-color: white;
            border-radius: 4px;
            padding: 12px;
            margin: 12px 0;
            font-size: 0.95em;
            color: var(--upload-text);
          }

          .summary-item {
            display: flex;
            justify-content: space-between;
            padding: 6px 0;
            border-bottom: 1px solid #eee;
          }

          .summary-item:last-child {
            border-bottom: none;
          }

          .summary-label {
            font-weight: 500;
          }

          .summary-value {
            color: #666;
          }

          .upload-id {
            font-family: monospace;
            font-size: 0.85em;
            background-color: #f5f5f5;
            padding: 4px 8px;
            border-radius: 2px;
            margin-top: 8px;
          }

          .upload-actions {
            display: flex;
            gap: 12px;
            margin-top: 16px;
          }

          .action-button {
            flex: 1;
            padding: 10px 16px;
            border: none;
            border-radius: 4px;
            font-weight: bold;
            cursor: pointer;
            font-size: 0.95em;
          }

          .action-button.primary {
            background-color: var(--success);
            color: white;
          }

          .action-button.primary:hover {
            background-color: #22aa22;
          }
        </style>

        <div class="upload-container">
          <div class="upload-title">✓ Upload Complete</div>
          
          <div class="upload-summary">
            <div class="summary-item">
              <span class="summary-label">Files uploaded:</span>
              <span class="summary-value">${summary.files_to_upload}</span>
            </div>
            ${summary.excluded_count > 0 ? `
            <div class="summary-item">
              <span class="summary-label">Files excluded:</span>
              <span class="summary-value">${summary.excluded_count}</span>
            </div>
            ` : ''}
            <div class="summary-item">
              <span class="summary-label">Upload ID:</span>
              <span class="summary-value upload-id">${this.state.upload_id}</span>
            </div>
          </div>

          <div class="upload-actions">
            <button class="action-button primary" onclick="this.getRootNode().host.onCompleteClicked()">
              Done
            </button>
          </div>
        </div>
      `;
      return;
    }

    if (this.state.error) {
      this.innerHTML = `
        <style>
          :host {
            --error-bg: #fee;
            --error: #f44336;
            --error-text: #c33;
          }

          .upload-container {
            background-color: var(--error-bg);
            border: 2px solid var(--error);
            border-radius: 4px;
            padding: 20px;
          }

          .upload-title {
            font-size: 1.2em;
            font-weight: bold;
            color: var(--error-text);
            margin-bottom: 12px;
          }

          .error-detail {
            background-color: white;
            border-radius: 4px;
            padding: 12px;
            color: var(--error-text);
            font-size: 0.9em;
            margin-bottom: 16px;
          }

          .action-button {
            width: 100%;
            padding: 10px 16px;
            border: 1px solid var(--error);
            background-color: white;
            color: var(--error-text);
            border-radius: 4px;
            font-weight: bold;
            cursor: pointer;
          }

          .action-button:hover {
            background-color: #f9f9f9;
          }
        </style>

        <div class="upload-container">
          <div class="upload-title">✗ Upload Failed</div>
          <div class="error-detail">${this._escapeHtml(this.state.error)}</div>
          <button class="action-button" onclick="this.getRootNode().host.onRetryClicked()">
            Retry
          </button>
        </div>
      `;
      return;
    }

    // Ready to upload
    const summary = this.getUploadSummary();

    this.innerHTML = `
      <style>
        :host {
          --upload-bg: #f5f5f5;
          --upload-border: #e0e0e0;
          --upload-text: #333;
          --primary: #2196f3;
        }

        .upload-container {
          background-color: var(--upload-bg);
          border-radius: 4px;
          padding: 20px;
        }

        .upload-title {
          font-size: 1.2em;
          font-weight: bold;
          color: var(--upload-text);
          margin-bottom: 16px;
        }

        .upload-summary {
          background-color: white;
          border: 1px solid var(--upload-border);
          border-radius: 4px;
          padding: 12px;
          margin-bottom: 16px;
          font-size: 0.95em;
        }

        .summary-item {
          display: flex;
          justify-content: space-between;
          padding: 6px 0;
          border-bottom: 1px solid #eee;
        }

        .summary-item:last-child {
          border-bottom: none;
        }

        .summary-label {
          font-weight: 500;
          color: var(--upload-text);
        }

        .summary-value {
          color: #666;
        }

        .action-button {
          width: 100%;
          padding: 12px 16px;
          border: none;
          background-color: var(--primary);
          color: white;
          border-radius: 4px;
          font-weight: bold;
          font-size: 1em;
          cursor: pointer;
        }

        .action-button:hover {
          background-color: #1976d2;
        }

        .action-button:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
      </style>

      <div class="upload-container">
        <div class="upload-title">Ready to Upload</div>
        
        <div class="upload-summary">
          <div class="summary-item">
            <span class="summary-label">Files to upload:</span>
            <span class="summary-value">${summary.files_to_upload}</span>
          </div>
          ${summary.excluded_count > 0 ? `
          <div class="summary-item">
            <span class="summary-label">Files excluded:</span>
            <span class="summary-value">${summary.excluded_count}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">Bandwidth saved:</span>
            <span class="summary-value">${this._formatBytes(summary.bandwidth_saved)}</span>
          </div>
          ` : ''}
        </div>

        <button class="action-button" onclick="this.getRootNode().host.startUpload()">
          Start Upload
        </button>
      </div>
    `;
  }

  /**
   * Format bytes as human-readable
   */
  _formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  }

  /**
   * Escape HTML to prevent XSS
   */
  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  onCompleteClicked() {
    this.dispatchEvent(new CustomEvent('upload-wizard-complete', {
      bubbles: true,
      composed: true
    }));
  }

  onRetryClicked() {
    this.state.error = null;
    this.render();
  }
}

// Register custom element
if (!customElements.get('upload-handler')) {
  customElements.define('upload-handler', UploadHandler);
}

export { UploadHandler };
