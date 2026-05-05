/**
 * Organize Step Component
 * 
 * G1: Pre-filtering excluded items before grouping display
 * G2: Recursive override warning with dynamic exclusion computation
 * 
 * Responsibilities:
 * 1. Receive selections + excluded_items from Source step (via store)
 * 2. Pre-filter files (remove excluded_items from display)
 * 3. Display grouping based on pre-filtered list
 * 4. Allow recursive toggle with warning on change
 * 5. Dynamically compute subfolders to exclude when changing recursive mode
 */

class OrganizeStep extends HTMLElement {
  constructor() {
    super();
    this.store = window.IntakeWizardStore;
    this.state = {
      selections: [],
      excluded_items: [],
      pre_filtered_files: [],
      grouping_results: {},
      recursive_overrides: {},  // Map of selection path → recursive override
      pending_exclusions: {},   // Map of path → exclusions to add if confirmed
    };
    this.unsubscribe = null;
  }

  connectedCallback() {
    this.render();
    
    // Subscribe to store changes
    this.unsubscribe = this.store.subscribe((storeState) => {
      this._onStoreChange(storeState);
    });

    this.addEventListener('recursive-toggle-changed', (e) => this._onRecursiveToggleChanged(e));
    this.addEventListener('override-confirmed', (e) => this._onOverrideConfirmed(e));
    this.addEventListener('override-cancelled', (e) => this._onOverrideCancelled(e));
  }

  disconnectedCallback() {
    if (this.unsubscribe) {
      this.unsubscribe();
    }
    this.removeEventListener('recursive-toggle-changed', this._onRecursiveToggleChanged);
    this.removeEventListener('override-confirmed', this._onOverrideConfirmed);
    this.removeEventListener('override-cancelled', this._onOverrideCancelled);
  }

  _onStoreChange(storeState) {
    // G1: Pre-filter excluded items
    this.state.selections = storeState.source.entries;
    this.state.excluded_items = storeState.source.excluded_items;
    
    // Pre-filter: Remove excluded items from display
    this._prefilterExcludedItems();
    
    // Recalculate grouping based on pre-filtered list
    this._calculateGrouping();
    
    this.render();
  }

  /**
   * G1: Pre-filter excluded items
   * 
   * Simulates Phase B's _prefilter_excluded_items() logic:
   * - Create Set of excluded paths for O(1) lookup
   * - Filter files to remove excluded ones
   * - Never show removed files in Organize step
   */
  _prefilterExcludedItems() {
    const excludedSet = new Set(this.state.excluded_items);
    
    // This would come from the backend in real scenario
    // For now, we mock the filtered files
    // In real integration, this would be part of the data passed from Source
    
    // Example: if selections = ['/models'] and excluded = ['/models/bad.3mf']
    // Then pre_filtered = all files in /models except bad.3mf
    
    this.state.pre_filtered_files = this._getMockFilteredFiles(excludedSet);
  }

  /**
   * Mock function: Get filtered files
   * In real scenario, this data comes from backend via API
   */
  _getMockFilteredFiles(excludedSet) {
    // Simulate files for each selection
    const allFiles = [];
    
    for (const selection of this.state.selections) {
      // In real scenario, fetch from backend
      // For now, create mock structure
      const files = this._generateMockFilesForPath(selection.path, selection.childCount || 10);
      
      // Filter out excluded items
      const filteredFiles = files.filter(f => !excludedSet.has(f.path));
      allFiles.push(...filteredFiles);
    }
    
    return allFiles;
  }

  /**
   * Generate mock files for a path (for testing)
   */
  _generateMockFilesForPath(basePath, count) {
    const files = [];
    for (let i = 0; i < count; i++) {
      files.push({
        path: `${basePath}/model_${i}.3mf`,
        name: `model_${i}.3mf`,
        type: 'file',
        size: Math.random() * 100000
      });
    }
    return files;
  }

  /**
   * G1: Calculate grouping based on pre-filtered files
   * Groups files and prepares for display
   */
  _calculateGrouping() {
    const groups = {};
    
    for (const file of this.state.pre_filtered_files) {
      const group = this._getFileGroup(file.path);
      if (!groups[group]) {
        groups[group] = [];
      }
      groups[group].push(file);
    }
    
    this.state.grouping_results = groups;
  }

  /**
   * Determine group name for a file (simplified logic)
   */
  _getFileGroup(filePath) {
    // Extract directory name
    const parts = filePath.split('/');
    if (parts.length > 1) {
      return parts[parts.length - 2];  // Parent directory name
    }
    return 'root';
  }

  /**
   * G2: Handle recursive toggle change
   * 
   * When user changes recursive setting:
   * 1. Detect if it's different from current
   * 2. If changing to non-recursive, compute subfolders to exclude
   * 3. Show warning with count
   * 4. Store pending exclusions
   * 5. Await user confirmation
   */
  _onRecursiveToggleChanged(e) {
    const { selection_path, new_recursive_value } = e.detail;
    const current_recursive = this.store.state.source.entries.find(s => s.path === selection_path)?.recursive;
    
    if (current_recursive === new_recursive_value) {
      return;  // No change
    }

    // Compute impact
    if (!new_recursive_value && current_recursive) {
      // Changing from recursive=true to recursive=false
      // Need to exclude all subfolders
      const subfolders = this._computeSubfoldersToExclude(selection_path);
      
      if (subfolders.length > 0) {
        // Show warning and store pending exclusions
        this.state.pending_exclusions[selection_path] = subfolders;
        
        // Dispatch event to show warning modal
        this.dispatchEvent(new CustomEvent('show-recursive-warning', {
          detail: {
            selection_path,
            subfolder_count: subfolders.length,
            subfolders
          },
          bubbles: true
        }));
      } else {
        // No subfolders, just apply the change
        this._applyRecursiveOverride(selection_path, new_recursive_value);
      }
    } else if (new_recursive_value && !current_recursive) {
      // Changing from recursive=false to recursive=true
      // Remove previously excluded subfolders
      const subfolders = this.state.pending_exclusions[selection_path] || [];
      this._removeExcludedSubfolders(selection_path, subfolders);
    }
    
    this.render();
  }

  /**
   * Compute subfolders that would be excluded
   * When changing from recursive=true to recursive=false,
   * all subfolders of selection_path must be excluded
   */
  _computeSubfoldersToExclude(basePath) {
    // Find all excluded items under this path that aren't already excluded
    const subfolders = new Set();
    const excludedSet = new Set(this.state.excluded_items);
    
    for (const file of this.state.pre_filtered_files) {
      if (file.path.startsWith(basePath + '/')) {
        // This file is under the base path
        // Extract subfolder name
        const relative = file.path.substring(basePath.length + 1);
        const subfolder = basePath + '/' + relative.split('/')[0];
        
        if (!excludedSet.has(subfolder)) {
          subfolders.add(subfolder);
        }
      }
    }
    
    return Array.from(subfolders);
  }

  /**
   * User confirmed the recursive override warning
   */
  _onOverrideConfirmed(e) {
    const { selection_path } = e.detail;
    
    // Get pending exclusions
    const subfolders = this.state.pending_exclusions[selection_path];
    
    if (subfolders && subfolders.length > 0) {
      // Add all subfolders to excluded items
      this.store.addExcludedItems(subfolders);
    }
    
    // Apply the recursive override
    this._applyRecursiveOverride(selection_path, false);
    
    // Clear pending
    delete this.state.pending_exclusions[selection_path];
    
    this.render();
  }

  /**
   * User cancelled the recursive override
   */
  _onOverrideCancelled(e) {
    const { selection_path } = e.detail;
    
    // Clear pending exclusions (don't apply changes)
    delete this.state.pending_exclusions[selection_path];
    
    this.render();
  }

  /**
   * Apply the recursive override
   * In real scenario, this would update the selection's recursive flag
   */
  _applyRecursiveOverride(path, recursiveValue) {
    this.state.recursive_overrides[path] = recursiveValue;
  }

  /**
   * Remove excluded subfolders when changing back to recursive=true
   */
  _removeExcludedSubfolders(basePath, subfolders) {
    subfolders.forEach(subfolder => {
      this.store.removeExcludedItem(subfolder);
    });
  }

  /**
   * Can proceed to Validate step?
   */
  canProceedToValidate() {
    // Same as Source step validation
    return this.store.canProceedToOrganize();
  }

  /**
   * Get summary for display
   */
  getSummary() {
    return {
      total_files: this.state.pre_filtered_files.length,
      groups: Object.keys(this.state.grouping_results).length,
      excluded_count: this.state.excluded_items.length
    };
  }

  render() {
    const summary = this.getSummary();
    
    this.innerHTML = `
      <style>
        :host {
          --organize-bg: #f5f5f5;
          --organize-border: #e0e0e0;
          --organize-text: #333;
        }

        .organize-container {
          background-color: var(--organize-bg);
          border-radius: 4px;
          padding: 16px;
        }

        .organize-header {
          margin-bottom: 16px;
          border-bottom: 1px solid var(--organize-border);
          padding-bottom: 12px;
        }

        .organize-title {
          font-size: 16px;
          font-weight: 600;
          color: var(--organize-text);
          margin-bottom: 8px;
        }

        .organize-summary {
          font-size: 13px;
          color: #666;
        }

        .organize-content {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 16px;
        }

        .organize-left {
          border-right: 1px solid var(--organize-border);
          padding-right: 16px;
        }

        .organize-right {
          padding-left: 16px;
        }

        .group-header {
          font-weight: 600;
          margin-top: 12px;
          margin-bottom: 8px;
          font-size: 14px;
        }

        .group-items {
          list-style: none;
          padding: 0;
          margin: 0;
          font-size: 13px;
        }

        .group-item {
          padding: 4px 0;
          color: #666;
        }

        .recursive-toggle-container {
          background-color: white;
          border: 1px solid var(--organize-border);
          border-radius: 4px;
          padding: 12px;
          margin-top: 12px;
        }

        .recursive-toggle-label {
          font-size: 13px;
          font-weight: 500;
          margin-bottom: 8px;
        }

        .excluded-summary {
          background-color: #fff3cd;
          border-left: 4px solid #ffc107;
          padding: 12px;
          margin-top: 12px;
          border-radius: 2px;
          font-size: 13px;
        }

        .excluded-summary-title {
          font-weight: 600;
          color: #856404;
          margin-bottom: 4px;
        }

        .excluded-summary-text {
          color: #856404;
        }
      </style>

      <div class="organize-container">
        <div class="organize-header">
          <div class="organize-title">Organize Files</div>
          <div class="organize-summary">
            ${summary.total_files} files in ${summary.groups} group${summary.groups !== 1 ? 's' : ''}
            ${summary.excluded_count > 0 ? `(${summary.excluded_count} excluded)` : ''}
          </div>
        </div>

        <div class="organize-content">
          <div class="organize-left">
            <h3>File Groups</h3>
            ${this._renderGroupsPreview()}
          </div>

          <div class="organize-right">
            <h3>Settings</h3>
            ${this._renderRecursiveToggles()}
            ${this._renderExcludedSummary()}
          </div>
        </div>
      </div>
    `;
  }

  _renderGroupsPreview() {
    if (Object.keys(this.state.grouping_results).length === 0) {
      return '<p style="color: #999;">No files to organize</p>';
    }

    let html = '';
    for (const [group, files] of Object.entries(this.state.grouping_results)) {
      html += `
        <div class="group-header">${group}</div>
        <ul class="group-items">
          ${files.slice(0, 5).map(f => `
            <li class="group-item">📄 ${f.name}</li>
          `).join('')}
          ${files.length > 5 ? `<li class="group-item" style="color: #999;">... and ${files.length - 5} more</li>` : ''}
        </ul>
      `;
    }
    return html;
  }

  _renderRecursiveToggles() {
    if (this.state.selections.length === 0) {
      return '';
    }

    return `
      <div class="recursive-toggle-container">
        <div class="recursive-toggle-label">Recursive Mode</div>
        ${this.state.selections.map(selection => `
          <recursive-toggle
            path="${selection.path}"
            recursive="true"
            data-path="${selection.path}"
          />
        `).join('')}
      </div>
    `;
  }

  _renderExcludedSummary() {
    if (this.state.excluded_items.length === 0) {
      return '';
    }

    return `
      <div class="excluded-summary">
        <div class="excluded-summary-title">⚠️ ${this.state.excluded_items.length} Item${this.state.excluded_items.length !== 1 ? 's' : ''} Excluded</div>
        <div class="excluded-summary-text">
          These items will not be imported in the next step.
        </div>
      </div>
    `;
  }
}

customElements.define('organize-step', OrganizeStep);
export { OrganizeStep };
