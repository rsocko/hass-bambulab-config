/**
 * Intake Wizard State Store
 * 
 * Unified state management for Source step (phases D & E):
 * - Browser mode (file upload tree)
 * - Server mode (folder navigation)
 * 
 * State contract (immutable):
 * {
 *   source: {
 *     mode: 'browser' | 'server',
 *     entries: [ { path, recursive, childCount } ],  // Only topmost selections
 *     excluded_items: [ path1, path2, ... ]          // Flat list, all paths
 *   },
 *   navigation: {
 *     current_path: '/models/gridfinity',
 *     expanded_folders: Set { '/models', '/models/gridfinity', ... }
 *   },
 *   metadata: {
 *     is_first_visit: true,
 *     created_at: timestamp
 *   }
 * }
 */

class IntakeWizardStore {
  constructor() {
    this.state = this._getInitialState();
    this.listeners = new Set();
  }

  _getInitialState() {
    // Try to restore from localStorage (across wizard steps)
    const cached = localStorage.getItem('intake_wizard_state');
    if (cached) {
      try {
        const restored = JSON.parse(cached);
        // Restore Set from array
        if (restored.navigation?.expanded_folders) {
          restored.navigation.expanded_folders = new Set(restored.navigation.expanded_folders);
        }
        return restored;
      } catch (e) {
        console.warn('Failed to restore cached state:', e);
      }
    }

    return {
      source: {
        mode: null,  // 'browser' or 'server', set when entering Source step
        entries: [],
        excluded_items: []
      },
      navigation: {
        current_path: '/',
        expanded_folders: new Set()
      },
      metadata: {
        is_first_visit: true,
        created_at: Date.now()
      }
    };
  }

  /**
   * Set mode: 'browser' or 'server'
   * Fired once when user chooses upload source type
   */
  setMode(mode) {
    if (!['browser', 'server'].includes(mode)) {
      throw new Error(`Invalid mode: ${mode}`);
    }
    this._update({
      source: { ...this.state.source, mode }
    });
  }

  /**
   * Get consolidated selections: only topmost entries
   */
  getSelections() {
    return this.state.source.entries;
  }

  /**
   * Get all excluded items (flat list)
   */
  getExcludedItems() {
    return this.state.source.excluded_items;
  }

  /**
   * Add selected entry (with consolidation)
   * 
   * Rules:
   * - If path is child of existing selection → don't add
   * - If path is parent → remove children, add parent
   * 
   * @param {string} path - Path to add (e.g., '/models/gridfinity')
   * @param {number} childCount - Total items under this path (for safeguard)
   */
  addSelection(path, childCount = 0) {
    const newEntries = [...this.state.source.entries];
    
    // Check for overlaps
    const existingIndex = newEntries.findIndex(e => e.path === path);
    if (existingIndex >= 0) {
      // Already selected, nothing to do
      return;
    }

    // Check if this is child of existing selection
    const isChild = newEntries.some(e => path.startsWith(e.path + '/'));
    if (isChild) {
      // Don't add child when parent already selected
      return;
    }

    // Check if this is parent of existing selections
    const childIndices = newEntries
      .map((e, i) => e.path.startsWith(path + '/') ? i : -1)
      .filter(i => i >= 0);

    if (childIndices.length > 0) {
      // Remove children, add parent
      for (let i = childIndices.length - 1; i >= 0; i--) {
        newEntries.splice(childIndices[i], 1);
      }
    }

    // Add the new entry
    newEntries.push({
      path,
      recursive: true,  // Parent selections are recursive
      childCount
    });

    this._update({
      source: { ...this.state.source, entries: newEntries }
    });
  }

  /**
   * Remove selected entry
   * Also updates expanded_folders (don't keep expanded path if not selected)
   */
  removeSelection(path) {
    const newEntries = this.state.source.entries.filter(e => e.path !== path);
    
    this._update({
      source: { ...this.state.source, entries: newEntries }
    });
  }

  /**
   * Add path to exclusion list
   * Deduplicates automatically
   */
  addExcludedItem(path) {
    const existing = this.state.source.excluded_items;
    if (existing.includes(path)) {
      return;  // Already excluded
    }

    this._update({
      source: {
        ...this.state.source,
        excluded_items: [...existing, path]
      }
    });
  }

  /**
   * Remove path from exclusion list
   */
  removeExcludedItem(path) {
    const newExcluded = this.state.source.excluded_items.filter(p => p !== path);
    
    this._update({
      source: {
        ...this.state.source,
        excluded_items: newExcluded
      }
    });
  }

  /**
   * Batch add exclusions (from pre-filtering)
   */
  addExcludedItems(paths) {
    const existing = new Set(this.state.source.excluded_items);
    paths.forEach(p => existing.add(p));

    this._update({
      source: {
        ...this.state.source,
        excluded_items: Array.from(existing)
      }
    });
  }

  /**
   * Batch clear exclusions for a folder
   * Used when removing a selection that had exclusions
   */
  clearExclusionsForPath(parentPath) {
    const newExcluded = this.state.source.excluded_items.filter(
      p => !p.startsWith(parentPath + '/')
    );

    this._update({
      source: {
        ...this.state.source,
        excluded_items: newExcluded
      }
    });
  }

  /**
   * Get excluded items under a specific path
   */
  getExcludedItemsUnderPath(parentPath) {
    return this.state.source.excluded_items.filter(
      p => p.startsWith(parentPath + '/')
    );
  }

  /**
   * Set current navigation path (breadcrumb position)
   * Triggers bilateral pane sync
   */
  setCurrentPath(path) {
    this._update({
      navigation: {
        ...this.state.navigation,
        current_path: path
      }
    });
  }

  /**
   * Get current navigation path
   */
  getCurrentPath() {
    return this.state.navigation.current_path;
  }

  /**
   * Toggle folder expanded state
   */
  toggleFolderExpanded(path) {
    const newExpanded = new Set(this.state.navigation.expanded_folders);
    if (newExpanded.has(path)) {
      newExpanded.delete(path);
    } else {
      newExpanded.add(path);
    }

    this._update({
      navigation: {
        ...this.state.navigation,
        expanded_folders: newExpanded
      }
    });
  }

  /**
   * Check if folder is expanded
   */
  isFolderExpanded(path) {
    return this.state.navigation.expanded_folders.has(path);
  }

  /**
   * Expand multiple folders at once
   */
  expandFolders(paths) {
    const newExpanded = new Set(this.state.navigation.expanded_folders);
    paths.forEach(p => newExpanded.add(p));

    this._update({
      navigation: {
        ...this.state.navigation,
        expanded_folders: newExpanded
      }
    });
  }

  /**
   * Mark that user has visited this step
   * Used for return-to-source banner logic
   */
  markVisited() {
    this._update({
      metadata: {
        ...this.state.metadata,
        is_first_visit: false
      }
    });
  }

  /**
   * Check if this is first visit to Source step
   */
  isFirstVisit() {
    return this.state.metadata.is_first_visit;
  }

  /**
   * Reset entire state (e.g., when canceling wizard)
   */
  reset() {
    this.state = this._getInitialState();
    localStorage.removeItem('intake_wizard_state');
    this._notifyListeners();
  }

  /**
   * Clear exclusions only (keep selections)
   */
  clearExclusions() {
    this._update({
      source: {
        ...this.state.source,
        excluded_items: []
      }
    });
  }

  /**
   * Get count of excluded items
   */
  getExcludedCount() {
    return this.state.source.excluded_items.length;
  }

  /**
   * Get count of excluded items under path
   */
  getExcludedCountUnderPath(parentPath) {
    return this.getExcludedItemsUnderPath(parentPath).length;
  }

  /**
   * Get summary for batch display
   * Returns: { selected_count, excluded_count, total }
   */
  getSummary() {
    const selections = this.state.source.entries;
    const excluded = this.state.source.excluded_items;

    return {
      selected_count: selections.length,
      excluded_count: excluded.length,
      total: selections.length + excluded.length
    };
  }

  /**
   * Validate state readiness for proceeding to Organize step
   * Requirements:
   * - At least one selection
   * - Mode set (browser or server)
   */
  canProceedToOrganize() {
    return this.state.source.mode && this.state.source.entries.length > 0;
  }

  /**
   * Get pre-filtered files (for display purposes)
   * Simulates what the display layer would show
   * Returns: selections with exclusions applied
   */
  getPreFilteredSnapshot() {
    return {
      selections: this.state.source.entries,
      excluded_items: this.state.source.excluded_items,
      excluded_count: this.state.source.excluded_items.length,
      mode: this.state.source.mode,
      current_path: this.state.navigation.current_path
    };
  }

  /**
   * Subscribe to state changes
   */
  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);  // Unsubscribe function
  }

  /**
   * Get full state (for debugging)
   */
  getState() {
    return JSON.parse(JSON.stringify(this.state, (key, value) => {
      if (value instanceof Set) {
        return Array.from(value);
      }
      return value;
    }));
  }

  // Private methods

  _update(partialState) {
    // Immutable merge: don't mutate directly
    this.state = {
      ...this.state,
      source: { ...this.state.source, ...partialState.source },
      navigation: { ...this.state.navigation, ...partialState.navigation },
      metadata: { ...this.state.metadata, ...partialState.metadata }
    };

    // Persist to localStorage for cross-step navigation
    localStorage.setItem('intake_wizard_state', JSON.stringify(this.getState()));

    this._notifyListeners();
  }

  _notifyListeners() {
    this.listeners.forEach(listener => {
      try {
        listener(this.state);
      } catch (e) {
        console.error('Error in state listener:', e);
      }
    });
  }
}

// Export singleton instance
window.IntakeWizardStore = window.IntakeWizardStore || new IntakeWizardStore();
export { IntakeWizardStore };
