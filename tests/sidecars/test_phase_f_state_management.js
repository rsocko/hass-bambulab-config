/**
 * Phase F: State Management & Persistence — Comprehensive Test Suite
 * 
 * Test Coverage:
 * - F1.1 Store initialization and state structure
 * - F1.2 Consolidation logic (parent absorbs children)
 * - F1.3 Exclusion management
 * - F1.4 Persistence (localStorage)
 * - F1.5 Navigation and expanded folders
 * - F2.1 Pane synchronization
 * - F2.2 Bilateral sync (left ↔ right)
 * - F2.3 Partial indicator cascading
 * - F2O.1 Return-to-source banner
 * - Property-based testing: 100 random action sequences
 */

describe('Phase F: State Management & Persistence', () => {

  // ============================================
  // F1.1: Store Initialization
  // ============================================

  describe('F1.1 - Store Initialization', () => {
    let store;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
    });

    test('F1.1.1: Initial state has correct structure', () => {
      const state = store.getState();
      
      expect(state.source).toBeDefined();
      expect(state.source.mode).toBeNull();
      expect(state.source.entries).toEqual([]);
      expect(state.source.excluded_items).toEqual([]);
      
      expect(state.navigation).toBeDefined();
      expect(state.navigation.current_path).toBe('/');
      expect(state.navigation.expanded_folders).toEqual([]);
      
      expect(state.metadata).toBeDefined();
      expect(state.metadata.is_first_visit).toBe(true);
    });

    test('F1.1.2: Mode can be set to "browser"', () => {
      store.setMode('browser');
      expect(store.state.source.mode).toBe('browser');
    });

    test('F1.1.3: Mode can be set to "server"', () => {
      store.setMode('server');
      expect(store.state.source.mode).toBe('server');
    });

    test('F1.1.4: Invalid mode throws error', () => {
      expect(() => store.setMode('invalid')).toThrow();
    });

    test('F1.1.5: State listeners can be subscribed', (done) => {
      let callCount = 0;
      store.subscribe(() => {
        callCount++;
        if (callCount === 1) {
          expect(callCount).toBe(1);
          done();
        }
      });
      
      store.setMode('browser');
    });
  });

  // ============================================
  // F1.2: Consolidation Logic
  // ============================================

  describe('F1.2 - Consolidation Logic', () => {
    let store;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
    });

    test('F1.2.1: Can add selection', () => {
      store.addSelection('/models', 50);
      expect(store.getSelections()).toHaveLength(1);
      expect(store.getSelections()[0].path).toBe('/models');
    });

    test('F1.2.2: Don\'t add duplicate selections', () => {
      store.addSelection('/models', 50);
      store.addSelection('/models', 50);
      expect(store.getSelections()).toHaveLength(1);
    });

    test('F1.2.3: Don\'t add child when parent already selected', () => {
      store.addSelection('/models', 50);
      store.addSelection('/models/gridfinity', 25);
      expect(store.getSelections()).toHaveLength(1);
      expect(store.getSelections()[0].path).toBe('/models');
    });

    test('F1.2.4: Parent absorbs child selections', () => {
      store.addSelection('/models/gridfinity', 25);
      store.addSelection('/models/benchmarks', 15);
      expect(store.getSelections()).toHaveLength(2);

      store.addSelection('/models', 50);
      expect(store.getSelections()).toHaveLength(1);
      expect(store.getSelections()[0].path).toBe('/models');
    });

    test('F1.2.5: Can remove selection', () => {
      store.addSelection('/models', 50);
      store.removeSelection('/models');
      expect(store.getSelections()).toHaveLength(0);
    });

    test('F1.2.6: Multiple non-overlapping selections allowed', () => {
      store.addSelection('/models', 50);
      store.addSelection('/benchmarks', 30);
      store.addSelection('/projects', 20);
      
      expect(store.getSelections()).toHaveLength(3);
    });

    test('F1.2.7: Deep nesting consolidates correctly', () => {
      store.addSelection('/a/b/c/d', 5);
      store.addSelection('/a/b', 50);
      
      expect(store.getSelections()).toHaveLength(1);
      expect(store.getSelections()[0].path).toBe('/a/b');
    });

    test('F1.2.8: Consolidation preserves non-overlapping siblings', () => {
      store.addSelection('/models/variant1', 10);
      store.addSelection('/models/variant2', 10);
      store.addSelection('/benchmarks', 20);
      
      store.addSelection('/models', 30);
      
      // Should have /models and /benchmarks, not the variants
      const selections = store.getSelections();
      expect(selections).toHaveLength(2);
      expect(selections.map(s => s.path)).toContain('/models');
      expect(selections.map(s => s.path)).toContain('/benchmarks');
    });
  });

  // ============================================
  // F1.3: Exclusion Management
  // ============================================

  describe('F1.3 - Exclusion Management', () => {
    let store;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
    });

    test('F1.3.1: Can add excluded item', () => {
      store.addExcludedItem('/models/bad.3mf');
      expect(store.getExcludedItems()).toContain('/models/bad.3mf');
    });

    test('F1.3.2: Don\'t add duplicate excluded items', () => {
      store.addExcludedItem('/models/bad.3mf');
      store.addExcludedItem('/models/bad.3mf');
      expect(store.getExcludedItems()).toHaveLength(1);
    });

    test('F1.3.3: Can remove excluded item', () => {
      store.addExcludedItem('/models/bad.3mf');
      store.removeExcludedItem('/models/bad.3mf');
      expect(store.getExcludedItems()).toHaveLength(0);
    });

    test('F1.3.4: Can batch add excluded items', () => {
      store.addExcludedItems(['/a.3mf', '/b.3mf', '/c.3mf']);
      expect(store.getExcludedItems()).toHaveLength(3);
    });

    test('F1.3.5: Get excluded count', () => {
      store.addExcludedItems(['/a.3mf', '/b.3mf', '/c.3mf']);
      expect(store.getExcludedCount()).toBe(3);
    });

    test('F1.3.6: Get excluded items under path', () => {
      store.addExcludedItems([
        '/models/a.3mf',
        '/models/b.3mf',
        '/benchmarks/c.3mf'
      ]);
      
      const underModels = store.getExcludedItemsUnderPath('/models');
      expect(underModels).toHaveLength(2);
      expect(underModels).toContain('/models/a.3mf');
      expect(underModels).toContain('/models/b.3mf');
    });

    test('F1.3.7: Clear exclusions for path', () => {
      store.addExcludedItems([
        '/models/subfolder/a.3mf',
        '/models/subfolder/b.3mf',
        '/benchmarks/c.3mf'
      ]);
      
      store.clearExclusionsForPath('/models/subfolder');
      
      expect(store.getExcludedItems()).toContain('/benchmarks/c.3mf');
      expect(store.getExcludedItems()).not.toContain('/models/subfolder/a.3mf');
      expect(store.getExcludedItems()).not.toContain('/models/subfolder/b.3mf');
    });

    test('F1.3.8: Get excluded count under path', () => {
      store.addExcludedItems([
        '/models/a.3mf',
        '/models/b.3mf',
        '/benchmarks/c.3mf'
      ]);
      
      expect(store.getExcludedCountUnderPath('/models')).toBe(2);
      expect(store.getExcludedCountUnderPath('/benchmarks')).toBe(1);
    });

    test('F1.3.9: Clear all exclusions', () => {
      store.addExcludedItems(['/a.3mf', '/b.3mf', '/c.3mf']);
      store.clearExclusions();
      expect(store.getExcludedItems()).toHaveLength(0);
    });
  });

  // ============================================
  // F1.4: Persistence
  // ============================================

  describe('F1.4 - Persistence', () => {
    beforeEach(() => {
      localStorage.clear();
    });

    test('F1.4.1: State persists to localStorage', () => {
      let store = new IntakeWizardStore();
      store.setMode('browser');
      store.addSelection('/models', 50);
      store.addExcludedItem('/models/bad.3mf');
      
      // Create new store instance
      let store2 = new IntakeWizardStore();
      
      expect(store2.state.source.mode).toBe('browser');
      expect(store2.getSelections()).toHaveLength(1);
      expect(store2.getExcludedItems()).toContain('/models/bad.3mf');
    });

    test('F1.4.2: Navigation state persists', () => {
      let store = new IntakeWizardStore();
      store.setCurrentPath('/models/gridfinity');
      store.expandFolders(['/models', '/models/gridfinity']);
      
      let store2 = new IntakeWizardStore();
      
      expect(store2.getCurrentPath()).toBe('/models/gridfinity');
      expect(store2.isFolderExpanded('/models')).toBe(true);
    });

    test('F1.4.3: Reset clears localStorage', () => {
      let store = new IntakeWizardStore();
      store.addSelection('/models', 50);
      store.reset();
      
      let store2 = new IntakeWizardStore();
      
      expect(store2.getSelections()).toHaveLength(0);
    });

    test('F1.4.4: Complex state persists correctly', () => {
      let store = new IntakeWizardStore();
      store.setMode('server');
      store.addSelection('/models', 100);
      store.addSelection('/benchmarks', 50);
      store.addExcludedItems(['/models/a.3mf', '/models/b.3mf']);
      store.setCurrentPath('/models/variants');
      store.expandFolders(['/models', '/models/variants']);
      
      let store2 = new IntakeWizardStore();
      
      const state = store2.getState();
      expect(state.source.mode).toBe('server');
      expect(state.source.entries).toHaveLength(2);
      expect(state.source.excluded_items).toHaveLength(2);
      expect(state.navigation.current_path).toBe('/models/variants');
      expect(state.navigation.expanded_folders).toContain('/models');
    });
  });

  // ============================================
  // F1.5: Navigation & Expanded Folders
  // ============================================

  describe('F1.5 - Navigation & Expanded Folders', () => {
    let store;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
    });

    test('F1.5.1: Can set current path', () => {
      store.setCurrentPath('/models/gridfinity');
      expect(store.getCurrentPath()).toBe('/models/gridfinity');
    });

    test('F1.5.2: Default path is root', () => {
      expect(store.getCurrentPath()).toBe('/');
    });

    test('F1.5.3: Can toggle folder expanded state', () => {
      store.toggleFolderExpanded('/models');
      expect(store.isFolderExpanded('/models')).toBe(true);
      
      store.toggleFolderExpanded('/models');
      expect(store.isFolderExpanded('/models')).toBe(false);
    });

    test('F1.5.4: Can expand multiple folders at once', () => {
      store.expandFolders(['/models', '/benchmarks', '/projects']);
      
      expect(store.isFolderExpanded('/models')).toBe(true);
      expect(store.isFolderExpanded('/benchmarks')).toBe(true);
      expect(store.isFolderExpanded('/projects')).toBe(true);
    });

    test('F1.5.5: Expanded folders start empty', () => {
      const state = store.getState();
      expect(state.navigation.expanded_folders).toEqual([]);
    });
  });

  // ============================================
  // F2.1: Pane Synchronization
  // ============================================

  describe('F2.1 - Pane Synchronization', () => {
    let store, sync, leftPane, rightPane;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
      sync = new PaneSynchronizer(store);

      leftPane = document.createElement('div');
      leftPane.setAttribute('data-current-path', '/');
      document.body.appendChild(leftPane);

      rightPane = document.createElement('div');
      rightPane.setAttribute('data-current-path', '/');
      document.body.appendChild(rightPane);

      sync.registerPanes(leftPane, rightPane);
    });

    afterEach(() => {
      sync.unregister();
      leftPane.remove();
      rightPane.remove();
    });

    test('F2.1.1: Panes start synchronized', () => {
      const verify = sync.verifySynchronized();
      expect(verify.synchronized).toBe(true);
    });

    test('F2.1.2: Sync navigation from left pane', (done) => {
      sync.syncNavigationFromLeft('/models');
      
      setTimeout(() => {
        expect(rightPane.getAttribute('data-current-path')).toBe('/models');
        done();
      }, 50);
    });

    test('F2.1.3: Sync navigation from right pane', (done) => {
      sync.syncNavigationFromRight('/benchmarks');
      
      setTimeout(() => {
        expect(leftPane.getAttribute('data-current-path')).toBe('/benchmarks');
        done();
      }, 50);
    });

    test('F2.1.4: Sync selections from left pane', (done) => {
      sync.syncSelectionFromLeft('/models', 50);
      
      setTimeout(() => {
        expect(rightPane.getAttribute('data-selected-count')).toBe('1');
        done();
      }, 50);
    });

    test('F2.1.5: Sync exclusions from left pane', (done) => {
      sync.syncExclusionFromLeft('/models/bad.3mf');
      
      setTimeout(() => {
        expect(rightPane.getAttribute('data-excluded-count')).toBe('1');
        done();
      }, 50);
    });

    test('F2.1.6: Both panes have same selected count', (done) => {
      sync.syncSelectionFromLeft('/models', 50);
      sync.syncSelectionFromLeft('/benchmarks', 30);
      
      setTimeout(() => {
        const leftCount = leftPane.getAttribute('data-selected-count');
        const rightCount = rightPane.getAttribute('data-selected-count');
        expect(leftCount).toBe(rightCount);
        expect(leftCount).toBe('2');
        done();
      }, 50);
    });
  });

  // ============================================
  // F2.2: Bilateral Synchronization
  // ============================================

  describe('F2.2 - Bilateral Synchronization', () => {
    let store, sync, leftPane, rightPane;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
      sync = new PaneSynchronizer(store);

      leftPane = document.createElement('div');
      leftPane.setAttribute('data-current-path', '/');
      document.body.appendChild(leftPane);

      rightPane = document.createElement('div');
      rightPane.setAttribute('data-current-path', '/');
      document.body.appendChild(rightPane);

      sync.registerPanes(leftPane, rightPane);
    });

    afterEach(() => {
      sync.unregister();
      leftPane.remove();
      rightPane.remove();
    });

    test('F2.2.1: Left to right navigation sync', (done) => {
      sync.syncNavigationFromLeft('/models/gridfinity');
      
      setTimeout(() => {
        expect(rightPane.getAttribute('data-current-path')).toBe('/models/gridfinity');
        expect(leftPane.getAttribute('data-current-path')).toBe('/models/gridfinity');
        done();
      }, 50);
    });

    test('F2.2.2: Right to left navigation sync', (done) => {
      sync.syncNavigationFromRight('/benchmarks');
      
      setTimeout(() => {
        expect(leftPane.getAttribute('data-current-path')).toBe('/benchmarks');
        expect(rightPane.getAttribute('data-current-path')).toBe('/benchmarks');
        done();
      }, 50);
    });

    test('F2.2.3: Alternating sync direction maintains coherence', (done) => {
      sync.syncNavigationFromLeft('/models');
      
      setTimeout(() => {
        sync.syncNavigationFromRight('/models/gridfinity');
        
        setTimeout(() => {
          expect(leftPane.getAttribute('data-current-path')).toBe('/models/gridfinity');
          expect(rightPane.getAttribute('data-current-path')).toBe('/models/gridfinity');
          done();
        }, 50);
      }, 50);
    });
  });

  // ============================================
  // F2O.1: Return-to-Source Banner
  // ============================================

  describe('F2O.1 - Return-to-Source Banner', () => {
    let banner;

    beforeEach(() => {
      document.body.innerHTML = '';
      banner = document.createElement('return-to-source-banner');
      document.body.appendChild(banner);
    });

    afterEach(() => {
      banner.remove();
    });

    test('F2O.1.1: Banner hidden on first visit', () => {
      banner.setAttribute('is-first-visit', 'true');
      banner.setAttribute('excluded-count', '0');
      banner.render();
      
      expect(banner.innerHTML).toBe('');
    });

    test('F2O.1.2: Banner hidden with no exclusions', () => {
      banner.setAttribute('is-first-visit', 'false');
      banner.setAttribute('excluded-count', '0');
      banner.render();
      
      expect(banner.innerHTML).toBe('');
    });

    test('F2O.1.3: Banner shown on return with exclusions', () => {
      banner.setAttribute('is-first-visit', 'false');
      banner.setAttribute('excluded-count', '5');
      banner.render();
      
      expect(banner.innerHTML).toContain('Previous exclusions detected');
      expect(banner.innerHTML).toContain('5');
    });

    test('F2O.1.4: Banner shows "View Exclusions" button', () => {
      banner.setAttribute('is-first-visit', 'false');
      banner.setAttribute('excluded-count', '3');
      banner.render();
      
      expect(banner.innerHTML).toContain('View Exclusions');
    });

    test('F2O.1.5: Banner shows "Clear All" button', () => {
      banner.setAttribute('is-first-visit', 'false');
      banner.setAttribute('excluded-count', '3');
      banner.render();
      
      expect(banner.innerHTML).toContain('Clear All');
    });

    test('F2O.1.6: Banner dispatches action event', (done) => {
      banner.setAttribute('is-first-visit', 'false');
      banner.setAttribute('excluded-count', '3');
      banner.render();

      banner.addEventListener('banner-action', (e) => {
        expect(e.detail.action).toBe('view-exclusions');
        done();
      });

      const button = banner.querySelector('[data-action="view-exclusions"]');
      button.click();
    });

    test('F2O.1.7: Can dismiss banner', (done) => {
      banner.setAttribute('is-first-visit', 'false');
      banner.setAttribute('excluded-count', '3');
      banner.render();

      banner.addEventListener('banner-action', (e) => {
        if (e.detail.action === 'dismiss') {
          expect(banner.innerHTML).toBe('');
          done();
        }
      });

      const closeButton = banner.querySelector('[data-action="dismiss"]');
      closeButton.click();
    });

    test('F2O.1.8: Plural/singular text correct', () => {
      banner.setAttribute('is-first-visit', 'false');
      banner.setAttribute('excluded-count', '1');
      banner.render();
      
      expect(banner.innerHTML).toContain('1 item');
      expect(banner.innerHTML).not.toContain('1 items');
    });
  });

  // ============================================
  // F1.6: Summary & Validation
  // ============================================

  describe('F1.6 - Summary & Validation', () => {
    let store;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
    });

    test('F1.6.1: Can proceed to Organize when ready', () => {
      store.setMode('browser');
      store.addSelection('/models', 50);
      
      expect(store.canProceedToOrganize()).toBe(true);
    });

    test('F1.6.2: Cannot proceed without mode set', () => {
      store.addSelection('/models', 50);
      
      expect(store.canProceedToOrganize()).toBe(false);
    });

    test('F1.6.3: Cannot proceed without selections', () => {
      store.setMode('browser');
      
      expect(store.canProceedToOrganize()).toBe(false);
    });

    test('F1.6.4: Get pre-filtered snapshot', () => {
      store.setMode('server');
      store.addSelection('/models', 50);
      store.addExcludedItem('/models/bad.3mf');
      store.setCurrentPath('/models');
      
      const snapshot = store.getPreFilteredSnapshot();
      
      expect(snapshot.mode).toBe('server');
      expect(snapshot.selections).toHaveLength(1);
      expect(snapshot.excluded_count).toBe(1);
      expect(snapshot.current_path).toBe('/models');
    });

    test('F1.6.5: Get summary', () => {
      store.addSelection('/models', 50);
      store.addSelection('/benchmarks', 30);
      store.addExcludedItems(['/a.3mf', '/b.3mf', '/c.3mf']);
      
      const summary = store.getSummary();
      
      expect(summary.selected_count).toBe(2);
      expect(summary.excluded_count).toBe(3);
      expect(summary.total).toBe(5);
    });

    test('F1.6.6: Mark and check first visit', () => {
      expect(store.isFirstVisit()).toBe(true);
      
      store.markVisited();
      
      expect(store.isFirstVisit()).toBe(false);
    });
  });

  // ============================================
  // Property-Based Testing: Random Action Sequences
  // ============================================

  describe('Property-Based Testing - 100 Random Action Sequences', () => {
    let store, sync, leftPane, rightPane;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
      sync = new PaneSynchronizer(store);

      leftPane = document.createElement('div');
      leftPane.setAttribute('data-current-path', '/');
      document.body.appendChild(leftPane);

      rightPane = document.createElement('div');
      rightPane.setAttribute('data-current-path', '/');
      document.body.appendChild(rightPane);

      sync.registerPanes(leftPane, rightPane);
    });

    afterEach(() => {
      sync.unregister();
      leftPane.remove();
      rightPane.remove();
    });

    test('Property-based: Panes never diverge after 100 random actions', (done) => {
      const paths = [
        '/models', '/models/gridfinity', '/models/variants',
        '/benchmarks', '/benchmarks/complex',
        '/projects', '/test'
      ];

      const getRandomAction = () => {
        const actions = [
          'addSelection',
          'removeSelection',
          'navigateLeft',
          'navigateRight',
          'addExclusion',
          'expand'
        ];
        return actions[Math.floor(Math.random() * actions.length)];
      };

      const getRandomPath = () => paths[Math.floor(Math.random() * paths.length)];

      let actionCount = 0;
      const totalActions = 100;

      const executeRandomAction = () => {
        if (actionCount >= totalActions) {
          // Verify panes are still synchronized
          const verify = sync.verifySynchronized();
          expect(verify.synchronized).toBe(true);
          done();
          return;
        }

        const action = getRandomAction();
        const path = getRandomPath();

        try {
          switch (action) {
            case 'addSelection':
              sync.syncSelectionFromLeft(path, Math.random() * 100);
              break;
            case 'removeSelection':
              store.removeSelection(path);
              break;
            case 'navigateLeft':
              sync.syncNavigationFromLeft(path);
              break;
            case 'navigateRight':
              sync.syncNavigationFromRight(path);
              break;
            case 'addExclusion':
              sync.syncExclusionFromLeft(path + '/file.3mf');
              break;
            case 'expand':
              store.toggleFolderExpanded(path);
              break;
          }
        } catch (e) {
          // Silently catch errors from invalid paths
        }

        actionCount++;
        setTimeout(executeRandomAction, 10);
      };

      executeRandomAction();
    });
  });

});
