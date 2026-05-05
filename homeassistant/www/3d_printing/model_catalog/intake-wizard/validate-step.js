/**
 * Validate Step Component
 * 
 * H1: Display validation checks including exclusion summary
 * 
 * Responsibilities:
 * 1. Receive validation response from backend
 * 2. Display ordered checklist of validation checks
 * 3. Show exclusion summary check (always present, always passes)
 * 4. Allow user to proceed or return to previous steps
 */

class ValidateStep extends HTMLElement {
  constructor() {
    super();
    this.store = window.IntakeWizardStore;
    this.state = {
      validation_state: null,
      checks: [],
      excluded_count: 0,
      total_files: 0,
      remaining_files: 0,
      loading: false,
      error: null
    };
    this.validationResponse = null;
  }

  connectedCallback() {
    this.render();
    this._loadValidation();
  }

  /**
   * Load validation response from backend
   * 
   * In real scenario:
   * POST /api/intake/items/{item_id}/validate
   * 
   * Response includes checks with:
   * - source_access
   * - supported_types
   * - duplicate_scan
   * - commit_ready
   * - excluded_items_summary (NEW - H1)
   */
  async _loadValidation() {
    try {
      this.state.loading = true;
      this.render();

      // In real scenario, make API call
      // For now, mock the response based on store state
      const mockResponse = this._buildMockValidationResponse();
      
      this.validationResponse = mockResponse;
      this.state.checks = mockResponse.checks;
      this.state.validation_state = mockResponse.validation_state;
      this.state.excluded_count = mockResponse.excluded_items_summary.excluded_count;
      this.state.total_files = mockResponse.excluded_items_summary.total_files;
      this.state.remaining_files = mockResponse.excluded_items_summary.remaining_files;

      this.state.loading = false;
      this.render();
    } catch (error) {
      this.state.error = error.message;
      this.state.loading = false;
      this.render();
    }
  }

  /**
   * Build mock validation response
   * 
   * In real scenario, this comes from backend
   * Includes H1: excluded_items_summary check
   */
  _buildMockValidationResponse() {
    const excluded = this.store.getExcludedItems();
    const excluded_count = excluded.length;
    const total_files = 10;  // Mock value
    const remaining_files = Math.max(0, total_files - excluded_count);

    return {
      validation_state: 'ready',
      excluded_items_summary: {
        excluded_count,
        total_files,
        remaining_files
      },
      checks: [
        {
          key: 'source_access',
          label: 'Selected sources are present and readable',
          passed: true,
          detail: `Resolved ${total_files} file(s) for validation.`
        },
        {
          key: 'supported_types',
          label: 'All files use supported types',
          passed: true,
          detail: 'All .3mf files are supported.'
        },
        {
          key: 'duplicate_scan',
          label: 'No duplicate files found',
          passed: true,
          detail: 'No file hashes match existing Working items.'
        },
        {
          key: 'excluded_items_summary',
          label: 'Exclusion summary',
          passed: true,  // H1: Always passes (informational)
          detail: this._buildExclusionSummaryMessage(excluded_count, remaining_files)
        },
        {
          key: 'commit_ready',
          label: 'Ready for upload',
          passed: remaining_files > 0,
          detail: remaining_files > 0 
            ? `Commit will import ${remaining_files} item(s).`
            : 'No items to import (all excluded).'
        }
      ]
    };
  }

  /**
   * H1: Build exclusion summary message
   * 
   * Message format:
   * - "No items excluded" if count = 0
   * - "N files excluded from selected sources. Proceeding with M remaining items." if count > 0
   */
  _buildExclusionSummaryMessage(excluded_count, remaining_files) {
    if (excluded_count === 0) {
      return 'No items excluded from selected sources.';
    }

    const fileText = excluded_count === 1 ? 'file' : 'files';
    return `${excluded_count} ${fileText} excluded from selected sources. Proceeding with ${remaining_files} remaining items.`;
  }

  /**
   * Check if can proceed to Upload
   * 
   * Requirements:
   * - All checks passed (or informational checks don't block)
   * - At least one file to import (remaining_files > 0)
   */
  canProceedToUpload() {
    if (!this.validationResponse) return false;

    // H1: excluded_items_summary doesn't block (always passes)
    // commit_ready check determines if we can proceed
    const commitReadyCheck = this.state.checks.find(c => c.key === 'commit_ready');
    return commitReadyCheck?.passed ?? false;
  }

  /**
   * Get validation summary
   */
  getSummary() {
    return {
      state: this.state.validation_state,
      checks_passed: this.state.checks.filter(c => c.passed).length,
      total_checks: this.state.checks.length,
      excluded_count: this.state.excluded_count,
      remaining_files: this.state.remaining_files
    };
  }

  /**
   * Handle back button (return to Organize step)
   */
  onBackClicked() {
    this.dispatchEvent(new CustomEvent('validate-back', {
      bubbles: true,
      composed: true
    }));
  }

  /**
   * Handle proceed button (go to Upload)
   */
  onProceedClicked() {
    if (!this.canProceedToUpload()) {
      return;  // Button disabled
    }

    this.dispatchEvent(new CustomEvent('validate-proceed', {
      detail: {
        validation_state: this.state.validation_state,
        excluded_count: this.state.excluded_count,
        remaining_files: this.state.remaining_files
      },
      bubbles: true,
      composed: true
    }));
  }

  render() {
    if (this.state.loading) {
      this.innerHTML = `
        <style>
          :host {
            --validate-bg: #f5f5f5;
            --validate-text: #333;
          }
          .validate-container {
            background-color: var(--validate-bg);
            border-radius: 4px;
            padding: 16px;
            text-align: center;
          }
          .loading-spinner {
            display: inline-block;
            width: 24px;
            height: 24px;
            border: 3px solid rgba(0, 0, 0, 0.1);
            border-radius: 50%;
            border-top-color: #333;
            animation: spin 0.6s linear infinite;
          }
          @keyframes spin {
            to { transform: rotate(360deg); }
          }
          .loading-text {
            margin-top: 12px;
            color: var(--validate-text);
          }
        </style>
        <div class="validate-container">
          <div class="loading-spinner"></div>
          <div class="loading-text">Validating selections...</div>
        </div>
      `;
      return;
    }

    if (this.state.error) {
      this.innerHTML = `
        <style>
          :host {
            --error-bg: #fee;
            --error-text: #c33;
          }
          .validate-container {
            background-color: var(--error-bg);
            border-radius: 4px;
            padding: 16px;
          }
          .error-message {
            color: var(--error-text);
            font-weight: bold;
            margin-bottom: 8px;
          }
          .error-detail {
            font-size: 0.9em;
            color: var(--error-text);
          }
        </style>
        <div class="validate-container">
          <div class="error-message">Validation Error</div>
          <div class="error-detail">${this.state.error}</div>
        </div>
      `;
      return;
    }

    // Main validation display
    const checksHTML = this.state.checks
      .map(check => this._renderCheckItem(check))
      .join('');

    const canProceed = this.canProceedToUpload();

    this.innerHTML = `
      <style>
        :host {
          --validate-bg: #f5f5f5;
          --validate-border: #e0e0e0;
          --validate-text: #333;
          --success: #2cbb2c;
          --warning: #ff9800;
          --error: #f44336;
        }

        .validate-container {
          background-color: var(--validate-bg);
          border-radius: 4px;
          padding: 20px;
        }

        .validate-header {
          margin-bottom: 20px;
          border-bottom: 1px solid var(--validate-border);
          padding-bottom: 16px;
        }

        .validate-title {
          font-size: 1.4em;
          font-weight: bold;
          color: var(--validate-text);
          margin-bottom: 8px;
        }

        .validate-status {
          font-size: 0.95em;
          color: #666;
        }

        .validate-status.ready {
          color: var(--success);
          font-weight: bold;
        }

        .validate-status.warning {
          color: var(--warning);
          font-weight: bold;
        }

        .validate-checklist {
          margin: 20px 0;
        }

        .check-item {
          display: flex;
          align-items: flex-start;
          padding: 12px;
          margin-bottom: 8px;
          background-color: white;
          border: 1px solid var(--validate-border);
          border-radius: 4px;
          border-left: 4px solid transparent;
        }

        .check-item.passed {
          border-left-color: var(--success);
          background-color: #f0f8f0;
        }

        .check-item.failed {
          border-left-color: var(--error);
          background-color: #fff0f0;
        }

        .check-item.informational {
          border-left-color: var(--warning);
          background-color: #fffbf0;
        }

        .check-icon {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 24px;
          height: 24px;
          border-radius: 50%;
          margin-right: 12px;
          flex-shrink: 0;
          font-weight: bold;
          font-size: 0.9em;
        }

        .check-item.passed .check-icon {
          background-color: var(--success);
          color: white;
        }

        .check-item.failed .check-icon {
          background-color: var(--error);
          color: white;
        }

        .check-item.informational .check-icon {
          background-color: var(--warning);
          color: white;
        }

        .check-content {
          flex: 1;
        }

        .check-label {
          font-weight: bold;
          color: var(--validate-text);
          margin-bottom: 4px;
        }

        .check-detail {
          font-size: 0.9em;
          color: #666;
        }

        .validate-actions {
          display: flex;
          gap: 12px;
          margin-top: 20px;
          border-top: 1px solid var(--validate-border);
          padding-top: 16px;
        }

        .action-button {
          padding: 10px 16px;
          border: none;
          border-radius: 4px;
          font-weight: bold;
          cursor: pointer;
          font-size: 1em;
          transition: all 0.2s ease;
        }

        .action-button.back {
          background-color: white;
          color: #333;
          border: 1px solid var(--validate-border);
        }

        .action-button.back:hover:not(:disabled) {
          background-color: #f9f9f9;
          border-color: #999;
        }

        .action-button.proceed {
          background-color: var(--success);
          color: white;
          flex: 1;
        }

        .action-button.proceed:hover:not(:disabled) {
          background-color: #22aa22;
        }

        .action-button:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .info-box {
          background-color: #e3f2fd;
          border: 1px solid #90caf9;
          border-radius: 4px;
          padding: 12px;
          margin-top: 16px;
          font-size: 0.9em;
          color: #1565c0;
        }
      </style>

      <div class="validate-container">
        <div class="validate-header">
          <div class="validate-title">Validate Selections</div>
          <div class="validate-status ${this.state.validation_state === 'ready' ? 'ready' : 'warning'}">
            ${this._getStatusMessage()}
          </div>
        </div>

        <div class="validate-checklist">
          ${checksHTML}
        </div>

        <div class="validate-actions">
          <button class="action-button back" onclick="this.getRootNode().host.onBackClicked()">
            Back to Organize
          </button>
          <button 
            class="action-button proceed" 
            onclick="this.getRootNode().host.onProceedClicked()"
            ${canProceed ? '' : 'disabled'}
          >
            Proceed to Upload
          </button>
        </div>

        ${this.state.excluded_count > 0 ? `
          <div class="info-box">
            <strong>Exclusions Applied:</strong> ${this.state.excluded_count} item(s) excluded. 
            You can return to the Organize step to adjust exclusions if needed.
          </div>
        ` : ''}
      </div>
    `;
  }

  /**
   * Render individual check item
   * 
   * H1: excluded_items_summary check shows:
   * - Key: excluded_items_summary
   * - Always passes (informational only)
   * - Shows count of excluded items
   */
  _renderCheckItem(check) {
    const iconMap = {
      '✓': 'passed',
      '✗': 'failed',
      'ℹ': 'informational'
    };

    const icon = check.passed ? '✓' : (check.key === 'excluded_items_summary' ? 'ℹ' : '✗');
    const checkType = check.key === 'excluded_items_summary' ? 'informational' : (check.passed ? 'passed' : 'failed');

    return `
      <div class="check-item ${checkType}">
        <div class="check-icon">${icon}</div>
        <div class="check-content">
          <div class="check-label">${this._escapeHtml(check.label)}</div>
          <div class="check-detail">${this._escapeHtml(check.detail)}</div>
        </div>
      </div>
    `;
  }

  /**
   * Get status message based on validation state
   */
  _getStatusMessage() {
    if (this.state.validation_state === 'ready') {
      return '✓ All checks passed. Ready to proceed.';
    }
    return '⚠ Review checks below. Some items may need attention.';
  }

  /**
   * Escape HTML to prevent XSS
   */
  _escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}

// Register custom element
if (!customElements.get('validate-step')) {
  customElements.define('validate-step', ValidateStep);
}

export { ValidateStep };
