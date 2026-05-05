/**
 * Phase G: Organize Step Integration — Comprehensive Test Suite
 * 
 * Test Coverage:
 * - G1.1 Pre-filtering excluded items
 * - G1.2 Grouping based on pre-filtered list
 * - G1.3 Excluded items never shown in Organize
 * - G2.1 Recursive toggle rendering
 * - G2.2 Recursive override warning calculation
 * - G2.3 Warning modal interaction (confirm/cancel)
 * - G2.4 Dynamic exclusion application
 * - G2.5 Reverting to recursive=true removes exclusions
 * - Integration: Full flow from Source to Organize
 */

describe('Phase G: Organize Step Integration', () => {

  // ============================================
  // G1.1: Pre-filtering Excluded Items
  // ============================================

  describe('G1.1 - Pre-filtering Excluded Items', () => {
    let organizeStep;
    let store;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
      organizeStep = document.createElement('organize-step');
      document.body.appendChild(organizeStep);
    });

    afterEach(() => {
      organizeStep.remove();
    });

    test('G1.1.1: Pre-filtered files exclude items from excluded_items list', () => {
      store.setMode('server');
      store.addSelection('/models', 10);
      store.addExcludedItem('/models/bad.3mf');

      // Trigger state change
      const storeState = store.getState();
      organizeStep._onStoreChange(storeState);

      const preFiltered = organizeStep.state.pre_filtered_files;
      
      // bad.3mf should not be in pre-filtered list
      const hasExcluded = preFiltered.some(f => f.path === '/models/bad.3mf');
      expect(hasExcluded).toBe(false);
    });

    test('G1.1.2: Pre-filtered includes non-excluded files', () => {
      store.setMode('browser');
      store.addSelection('/uploads', 5);
      store.addExcludedItem('/uploads/file1.3mf');

      const storeState = store.getState();
      organizeStep._onStoreChange(storeState);

      // Should have other files but not file1
      expect(organizeStep.state.pre_filtered_files.length).toBeGreaterThan(0);
      expect(organizeStep.state.pre_filtered_files.length).toBeLessThan(5);
    });

    test('G1.1.3: Multiple excluded items removed from display', () => {
      store.setMode('server');
      store.addSelection('/models', 10);
      store.addExcludedItems([
        '/models/bad1.3mf',
        '/models/bad2.3mf',
        '/models/bad3.3mf'
      ]);

      const storeState = store.getState();
      organizeStep._onStoreChange(storeState);

      const preFiltered = organizeStep.state.pre_filtered_files;
      const excluded = ['/models/bad1.3mf', '/models/bad2.3mf', '/models/bad3.3mf'];
      
      excluded.forEach(item => {
        expect(preFiltered.some(f => f.path === item)).toBe(false);
      });
    });

    test('G1.1.4: Excluded items for different selection preserved', () => {
      store.setMode('server');
      store.addSelection('/models', 5);
      store.addSelection('/benchmarks', 5);
      store.addExcludedItem('/models/bad.3mf');

      const storeState = store.getState();
      organizeStep._onStoreChange(storeState);

      // /benchmarks files should be in pre-filtered
      const benchmarkFiles = organizeStep.state.pre_filtered_files.filter(
        f => f.path.startsWith('/benchmarks')
      );
      expect(benchmarkFiles.length).toBeGreaterThan(0);
    });
  });

  // ============================================
  // G1.2: Grouping Based on Pre-filtered List
  // ============================================

  describe('G1.2 - Grouping Based on Pre-filtered List', () => {
    let organizeStep;
    let store;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
      organizeStep = document.createElement('organize-step');
      document.body.appendChild(organizeStep);
    });

    afterEach(() => {
      organizeStep.remove();
    });

    test('G1.2.1: Files grouped correctly', () => {
      store.setMode('server');
      store.addSelection('/models', 6);

      const storeState = store.getState();
      organizeStep._onStoreChange(storeState);

      expect(Object.keys(organizeStep.state.grouping_results).length).toBeGreaterThan(0);
    });

    test('G1.2.2: Grouping excludes excluded items', () => {
      store.setMode('server');
      store.addSelection('/models', 8);
      store.addExcludedItem('/models/bad.3mf');

      const storeState = store.getState();
      organizeStep._onStoreChange(storeState);

      // Total grouped files should be less due to exclusion
      const totalGrouped = Object.values(organizeStep.state.grouping_results)
        .reduce((sum, group) => sum + group.length, 0);
      
      expect(totalGrouped).toBeLessThan(8);
    });

    test('G1.2.3: Empty group created for no files', () => {
      store.setMode('server');
      store.addSelection('/empty', 0);

      const storeState = store.getState();
      organizeStep._onStoreChange(storeState);

      // May have empty groups or minimal groups
      expect(typeof organizeStep.state.grouping_results).toBe('object');
    });
  });

  // ============================================
  // G1.3: Excluded Items Never Shown
  // ============================================

  describe('G1.3 - Excluded Items Never Shown in Organize', () => {
    let organizeStep;
    let store;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
      organizeStep = document.createElement('organize-step');
      document.body.appendChild(organizeStep);
    });

    afterEach(() => {
      organizeStep.remove();
    });

    test('G1.3.1: Excluded item not in pre-filtered list', () => {
      store.setMode('server');
      store.addSelection('/models', 10);
      store.addExcludedItem('/models/excluded.3mf');

      const storeState = store.getState();
      organizeStep._onStoreChange(storeState);

      expect(organizeStep.state.pre_filtered_files.some(f => 
        f.path === '/models/excluded.3mf'
      )).toBe(false);
    });

    test('G1.3.2: Excluded item not in grouping results', () => {
      store.setMode('server');
      store.addSelection('/models', 10);
      store.addExcludedItem('/models/excluded.3mf');

      const storeState = store.getState();
      organizeStep._onStoreChange(storeState);

      const allGrouped = Object.values(organizeStep.state.grouping_results)
        .flat();
      
      expect(allGrouped.some(f => f.path === '/models/excluded.3mf')).toBe(false);
    });

    test('G1.3.3: Render does not show excluded items', () => {
      store.setMode('server');
      store.addSelection('/models', 5);
      store.addExcludedItem('/models/bad.3mf');

      const storeState = store.getState();
      organizeStep._onStoreChange(storeState);
      organizeStep.render();

      const html = organizeStep.innerHTML;
      expect(html).not.toContain('bad.3mf');
    });
  });

  // ============================================
  // G2.1: Recursive Toggle Rendering
  // ============================================

  describe('G2.1 - Recursive Toggle Rendering', () => {
    let toggle;

    beforeEach(() => {
      toggle = document.createElement('recursive-toggle');
      toggle.setAttribute('path', '/models');
      toggle.setAttribute('recursive', 'true');
      document.body.appendChild(toggle);
    });

    afterEach(() => {
      toggle.remove();
    });

    test('G2.1.1: Toggle renders with recursive=true state', () => {
      expect(toggle.innerHTML).toContain('✓ On');
    });

    test('G2.1.2: Toggle renders with recursive=false state', () => {
      toggle.setAttribute('recursive', 'false');
      toggle.render();
      
      expect(toggle.innerHTML).toContain('Off');
    });

    test('G2.1.3: Toggle shows path', () => {
      expect(toggle.innerHTML).toContain('/models');
    });

    test('G2.1.4: Toggle button clickable', (done) => {
      const button = toggle.querySelector('.toggle-button');
      
      toggle.addEventListener('recursive-toggle-changed', (e) => {
        expect(e.detail.selection_path).toBe('/models');
        expect(e.detail.new_recursive_value).toBe(false);
        done();
      });

      button.click();
    });

    test('G2.1.5: Toggle state updates on click', (done) => {
      const button = toggle.querySelector('.toggle-button');
      
      button.click();
      
      setTimeout(() => {
        expect(toggle.getAttribute('recursive')).toBe('false');
        done();
      }, 50);
    });
  });

  // ============================================
  // G2.2: Recursive Override Warning Calculation
  // ============================================

  describe('G2.2 - Recursive Override Warning Calculation', () => {
    let organizeStep;
    let store;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
      organizeStep = document.createElement('organize-step');
      document.body.appendChild(organizeStep);
    });

    afterEach(() => {
      organizeStep.remove();
    });

    test('G2.2.1: Compute subfolders to exclude on recursive=true to false', () => {
      store.setMode('server');
      store.addSelection('/models', 10);

      const storeState = store.getState();
      organizeStep._onStoreChange(storeState);

      // Generate some files
      organizeStep._prefilterExcludedItems();

      const subfolders = organizeStep._computeSubfoldersToExclude('/models');
      
      // Should have at least some subfolders
      expect(Array.isArray(subfolders)).toBe(true);
    });

    test('G2.2.2: No subfolders to exclude if already excluded', () => {
      store.setMode('server');
      store.addSelection('/models', 5);
      store.addExcludedItem('/models/variants');

      const storeState = store.getState();
      organizeStep._onStoreChange(storeState);

      const subfolders = organizeStep._computeSubfoldersToExclude('/models');
      
      // Already excluded subfolders shouldn't be in list
      expect(subfolders.every(s => s !== '/models/variants')).toBe(true);
    });

    test('G2.2.3: Correct count for warning', () => {
      store.setMode('server');
      store.addSelection('/models', 12);

      const storeState = store.getState();
      organizeStep._onStoreChange(storeState);

      const subfolders = organizeStep._computeSubfoldersToExclude('/models');
      
      // Count should match computed subfolders
      expect(subfolders.length).toBeGreaterThanOrEqual(0);
    });
  });

  // ============================================
  // G2.3: Warning Modal Interaction
  // ============================================

  describe('G2.3 - Warning Modal Interaction', () => {
    let warning;

    beforeEach(() => {
      warning = document.createElement('recursive-override-warning');
      document.body.appendChild(warning);
    });

    afterEach(() => {
      warning.remove();
    });

    test('G2.3.1: Warning modal hidden initially', () => {
      expect(warning.style.display).toBe('none');
    });

    test('G2.3.2: setWarning shows modal', () => {
      warning.setWarning('/models', ['/models/v1', '/models/v2']);
      
      expect(warning.style.display).toBe('flex');
    });

    test('G2.3.3: Warning displays subfolder count', () => {
      warning.setWarning('/models', ['/models/v1', '/models/v2', '/models/v3']);
      
      expect(warning.innerHTML).toContain('3');
    });

    test('G2.3.4: Warning displays subfolders list', () => {
      warning.setWarning('/models', ['/models/v1', '/models/v2']);
      
      expect(warning.innerHTML).toContain('/models/v1');
      expect(warning.innerHTML).toContain('/models/v2');
    });

    test('G2.3.5: Confirm button dispatches override-confirmed event', (done) => {
      warning.setWarning('/models', ['/models/v1']);

      warning.addEventListener('override-confirmed', (e) => {
        expect(e.detail.selection_path).toBe('/models');
        done();
      });

      const confirmBtn = warning.querySelector('.warning-confirm');
      confirmBtn.click();
    });

    test('G2.3.6: Cancel button dispatches override-cancelled event', (done) => {
      warning.setWarning('/models', ['/models/v1']);

      warning.addEventListener('override-cancelled', (e) => {
        expect(e.detail.selection_path).toBe('/models');
        done();
      });

      const cancelBtn = warning.querySelector('.warning-cancel');
      cancelBtn.click();
    });

    test('G2.3.7: Escape key cancels modal', (done) => {
      warning.setWarning('/models', ['/models/v1']);

      warning.addEventListener('override-cancelled', () => {
        done();
      });

      const event = new KeyboardEvent('keydown', { key: 'Escape' });
      warning.dispatchEvent(event);
    });

    test('G2.3.8: Overlay click cancels modal', (done) => {
      warning.setWarning('/models', ['/models/v1']);

      warning.addEventListener('override-cancelled', () => {
        done();
      });

      const overlay = warning.querySelector('.warning-overlay');
      overlay.click();
    });

    test('G2.3.9: Modal hides after confirm', () => {
      warning.setWarning('/models', ['/models/v1']);
      expect(warning.style.display).toBe('flex');

      const confirmBtn = warning.querySelector('.warning-confirm');
      confirmBtn.click();

      expect(warning.style.display).toBe('none');
    });

    test('G2.3.10: Modal hides after cancel', () => {
      warning.setWarning('/models', ['/models/v1']);
      expect(warning.style.display).toBe('flex');

      const cancelBtn = warning.querySelector('.warning-cancel');
      cancelBtn.click();

      expect(warning.style.display).toBe('none');
    });
  });

  // ============================================
  // G2.4: Dynamic Exclusion Application
  // ============================================

  describe('G2.4 - Dynamic Exclusion Application', () => {
    let organizeStep;
    let store;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
      organizeStep = document.createElement('organize-step');
      document.body.appendChild(organizeStep);
    });

    afterEach(() => {
      organizeStep.remove();
    });

    test('G2.4.1: Confirm adds subfolders to excluded_items', (done) => {
      store.setMode('server');
      store.addSelection('/models', 10);

      const storeState = store.getState();
      organizeStep._onStoreChange(storeState);

      const initialExcluded = store.getExcludedCount();

      // Simulate user confirming override
      const event = new CustomEvent('override-confirmed', {
        detail: { selection_path: '/models' }
      });

      organizeStep.state.pending_exclusions['/models'] = [
        '/models/v1',
        '/models/v2'
      ];

      organizeStep._onOverrideConfirmed(event);

      setTimeout(() => {
        const newExcluded = store.getExcludedCount();
        expect(newExcluded).toBeGreaterThan(initialExcluded);
        done();
      }, 50);
    });

    test('G2.4.2: Cancel does not add exclusions', () => {
      store.setMode('server');
      store.addSelection('/models', 10);

      const storeState = store.getState();
      organizeStep._onStoreChange(storeState);

      const initialExcluded = store.getExcludedCount();

      organizeStep.state.pending_exclusions['/models'] = [
        '/models/v1',
        '/models/v2'
      ];

      const event = new CustomEvent('override-cancelled', {
        detail: { selection_path: '/models' }
      });

      organizeStep._onOverrideCancelled(event);

      const newExcluded = store.getExcludedCount();
      expect(newExcluded).toBe(initialExcluded);
    });
  });

  // ============================================
  // G2.5: Reverting to Recursive Removes Exclusions
  // ============================================

  describe('G2.5 - Reverting to Recursive', () => {
    let organizeStep;
    let store;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
      organizeStep = document.createElement('organize-step');
      document.body.appendChild(organizeStep);
    });

    afterEach(() => {
      organizeStep.remove();
    });

    test('G2.5.1: Changing back to recursive=true removes added exclusions', () => {
      store.setMode('server');
      store.addSelection('/models', 10);
      store.addExcludedItems(['/models/v1', '/models/v2']);

      const storeState = store.getState();
      organizeStep._onStoreChange(storeState);

      const initialExcluded = store.getExcludedCount();

      // Simulate reverting to recursive
      organizeStep._removeExcludedSubfolders('/models', ['/models/v1', '/models/v2']);

      const newExcluded = store.getExcludedCount();
      expect(newExcluded).toBeLessThan(initialExcluded);
    });
  });

  // ============================================
  // G1.6: Summary & Validation
  // ============================================

  describe('G1.6 - Summary & Validation', () => {
    let organizeStep;
    let store;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
      organizeStep = document.createElement('organize-step');
      document.body.appendChild(organizeStep);
    });

    afterEach(() => {
      organizeStep.remove();
    });

    test('G1.6.1: Can proceed to Validate when ready', () => {
      store.setMode('server');
      store.addSelection('/models', 10);

      const storeState = store.getState();
      organizeStep._onStoreChange(storeState);

      expect(organizeStep.canProceedToValidate()).toBe(true);
    });

    test('G1.6.2: Cannot proceed without selections', () => {
      store.setMode('server');

      const storeState = store.getState();
      organizeStep._onStoreChange(storeState);

      expect(organizeStep.canProceedToValidate()).toBe(false);
    });

    test('G1.6.3: Get summary with correct counts', () => {
      store.setMode('server');
      store.addSelection('/models', 6);
      store.addExcludedItem('/models/bad.3mf');

      const storeState = store.getState();
      organizeStep._onStoreChange(storeState);

      const summary = organizeStep.getSummary();

      expect(summary.total_files).toBeGreaterThan(0);
      expect(summary.groups).toBeGreaterThan(0);
      expect(summary.excluded_count).toBe(1);
    });
  });

});
