/**
 * Pane Synchronization Utility
 * 
 * Keeps left pane (file tree) and right pane (summary) in sync:
 * - Current navigation path (breadcrumb)
 * - Expanded folder state
 * - Selected entries
 * - Exclusion indicators
 * 
 * Works by:
 * 1. Store broadcasts state changes
 * 2. Components memoized to prevent jank
 * 3. Bilateral sync: left path change → right pane updates, vice versa
 */

class PaneSynchronizer {
  constructor(store) {
    this.store = store;
    this.leftPane = null;
    this.rightPane = null;
    this.unsubscribe = null;
  }

  /**
   * Register panes for synchronization
   * @param {HTMLElement} leftPane - Left pane element (file tree)
   * @param {HTMLElement} rightPane - Right pane element (summary)
   */
  registerPanes(leftPane, rightPane) {
    this.leftPane = leftPane;
    this.rightPane = rightPane;

    // Subscribe to store changes
    this.unsubscribe = this.store.subscribe((state) => {
      this._onStateChange(state);
    });
  }

  /**
   * Unregister panes and clean up subscriptions
   */
  unregister() {
    if (this.unsubscribe) {
      this.unsubscribe();
      this.unsubscribe = null;
    }
    this.leftPane = null;
    this.rightPane = null;
  }

  /**
   * Sync navigation: left pane path changed, update right pane
   * @param {string} newPath - New navigation path from left pane
   */
  syncNavigationFromLeft(newPath) {
    this.store.setCurrentPath(newPath);
    // Store change triggers _onStateChange, which updates both panes
  }

  /**
   * Sync navigation: right pane breadcrumb clicked, update left pane
   * @param {string} newPath - New navigation path from right pane
   */
  syncNavigationFromRight(newPath) {
    this.store.setCurrentPath(newPath);
    // Same as left, store change handles sync
  }

  /**
   * Sync selections: left pane item selected, update right pane
   * @param {string} path - Path selected
   * @param {number} childCount - Number of items under this path
   */
  syncSelectionFromLeft(path, childCount = 0) {
    this.store.addSelection(path, childCount);
    // Store broadcasts, _onStateChange updates right pane
  }

  /**
   * Sync exclusion: item excluded on left pane, update right pane
   * @param {string} path - Path to exclude
   */
  syncExclusionFromLeft(path) {
    this.store.addExcludedItem(path);
    // Store broadcasts, partial indicator badge updated
  }

  /**
   * Get left pane current path
   */
  getLeftPath() {
    return this.leftPane?.getAttribute('data-current-path') || '/';
  }

  /**
   * Get right pane current path
   */
  getRightPath() {
    return this.rightPane?.getAttribute('data-current-path') || '/';
  }

  /**
   * Verify panes are synchronized (for testing)
   * Returns: { synchronized: boolean, details: string }
   */
  verifySynchronized() {
    const leftPath = this.getLeftPath();
    const rightPath = this.getRightPath();
    const pathMatch = leftPath === rightPath;

    const leftSelected = this.leftPane?.getAttribute('data-selected-count') || '0';
    const rightSelected = this.rightPane?.getAttribute('data-selected-count') || '0';
    const selectionMatch = leftSelected === rightSelected;

    return {
      synchronized: pathMatch && selectionMatch,
      leftPath,
      rightPath,
      pathMatch,
      leftSelected,
      rightSelected,
      selectionMatch
    };
  }

  // Private methods

  _onStateChange(state) {
    if (!this.leftPane || !this.rightPane) {
      return;  // Not registered
    }

    const currentPath = state.navigation.current_path;
    const selections = state.source.entries;
    const excluded = state.source.excluded_items;

    // Update left pane
    if (this.leftPane) {
      this._updateLeftPane(currentPath, selections, excluded);
    }

    // Update right pane
    if (this.rightPane) {
      this._updateRightPane(currentPath, selections, excluded);
    }
  }

  _updateLeftPane(currentPath, selections, excluded) {
    // Update breadcrumb
    this.leftPane.setAttribute('data-current-path', currentPath);

    // Update batch summary
    this.leftPane.setAttribute('data-selected-count', selections.length);
    this.leftPane.setAttribute('data-excluded-count', excluded.length);

    // Dispatch custom event so component can re-render
    this.leftPane.dispatchEvent(new CustomEvent('intake-state-changed', {
      detail: {
        currentPath,
        selections,
        excluded,
        excludedCount: excluded.length
      },
      bubbles: true
    }));
  }

  _updateRightPane(currentPath, selections, excluded) {
    // Update breadcrumb (synchronized)
    this.rightPane.setAttribute('data-current-path', currentPath);

    // Update batch summary
    this.rightPane.setAttribute('data-selected-count', selections.length);
    this.rightPane.setAttribute('data-excluded-count', excluded.length);

    // For server mode, show "Part of:" indicator if navigated into subfolder
    this._updatePartOfIndicator(currentPath, selections);

    // Dispatch custom event
    this.rightPane.dispatchEvent(new CustomEvent('intake-state-changed', {
      detail: {
        currentPath,
        selections,
        excluded,
        excludedCount: excluded.length
      },
      bubbles: true
    }));
  }

  /**
   * Update "Part of: parent/path" indicator
   * Shown when user navigates to subfolder of selected entry
   */
  _updatePartOfIndicator(currentPath, selections) {
    let partOfParent = null;

    // Find if current path is child of any selection
    for (const selection of selections) {
      if (currentPath.startsWith(selection.path + '/')) {
        partOfParent = selection.path;
        break;
      }
    }

    if (partOfParent) {
      this.rightPane.setAttribute('data-part-of', partOfParent);
    } else {
      this.rightPane.removeAttribute('data-part-of');
    }
  }

  /**
   * Cascade partial indicator updates
   * When exclusions change, update badge counts on parent folders
   */
  cascadePartialIndicators(excluded) {
    if (!this.leftPane) return;

    // Collect all parent folders with excluded items
    const parentFolders = new Set();
    excluded.forEach(path => {
      let current = path;
      while (current && current !== '/') {
        const parent = current.substring(0, current.lastIndexOf('/')) || '/';
        parentFolders.add(parent);
        current = parent;
      }
    });

    // Dispatch event so left pane component can update badges
    this.leftPane.dispatchEvent(new CustomEvent('partial-indicators-changed', {
      detail: {
        parentFolders: Array.from(parentFolders),
        excludedItems: excluded
      },
      bubbles: true
    }));
  }
}

export { PaneSynchronizer };
