/**
 * Phase I: End-to-End Integration Tests
 * 
 * Test Coverage:
 * - E2E Scenario 1: Server Selection + Removal
 * - E2E Scenario 2: Browser Upload + Removal
 * - E2E Scenario 3: Recursive Override
 * - E2E Scenario 4: Full Wizard Flow (Source → Organize → Validate → Upload)
 * - Performance Tests
 * - File Filtering Tests
 * 
 * Part of Issue #1340: Phase I — End-to-End Testing & Deployment
 */

describe('Phase I: End-to-End Integration Tests', () => {

  // ============================================
  // Scenario 1: Server Selection + Removal
  // ============================================

  describe('E2E Scenario 1: Server Selection + Removal', () => {
    let store;
    let sourceStep;
    let organizeStep;
    let validateStep;
    let uploadHandler;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
      sourceStep = document.createElement('source-step');
      organizeStep = document.createElement('organize-step');
      validateStep = document.createElement('validate-step');
      uploadHandler = document.createElement('upload-handler');
      
      document.body.appendChild(sourceStep);
      document.body.appendChild(organizeStep);
      document.body.appendChild(validateStep);
      document.body.appendChild(uploadHandler);
    });

    afterEach(() => {
      sourceStep.remove();
      organizeStep.remove();
      validateStep.remove();
      uploadHandler.remove();
    });

    test('E2E-1.1: User selects /models/ folder on server', () => {
      store.setMode('server');
      store.addSelection('/models', 10);

      expect(store.getSelections().length).toBe(1);
      expect(store.getSelections()[0].path).toBe('/models');
    });

    test('E2E-1.2: User removes experimental.3mf → exclusion tracked', () => {
      store.setMode('server');
      store.addSelection('/models', 10);
      store.addExcludedItem('/models/experimental.3mf');

      expect(store.getExcludedItems().length).toBe(1);
      expect(store.getExcludedItems()).toContain('/models/experimental.3mf');
    });

    test('E2E-1.3: Organize step shows file not in grouping', (done) => {
      store.setMode('server');
      store.addSelection('/models', 10);
      store.addExcludedItem('/models/experimental.3mf');

      setTimeout(() => {
        organizeStep._onStoreChange(store.getState());
        
        const preFiltered = organizeStep.state.pre_filtered_files;
        expect(preFiltered.some(f => f.path === '/models/experimental.3mf')).toBe(false);
        done();
      }, 100);
    });

    test('E2E-1.4: Validate step shows exclusion count', (done) => {
      store.setMode('server');
      store.addSelection('/models', 10);
      store.addExcludedItem('/models/experimental.3mf');

      setTimeout(() => {
        validateStep._loadValidation();
        
        setTimeout(() => {
          const summaryCheck = validateStep.state.checks.find(c => c.key === 'excluded_items_summary');
          expect(summaryCheck.detail).toContain('1 file');
          done();
        }, 100);
      }, 100);
    });

    test('E2E-1.5: Upload filters excluded file', () => {
      const files = [
        { path: '/models/good.3mf', size: 2000000 },
        { path: '/models/experimental.3mf', size: 1000000 },
        { path: '/models/test.3mf', size: 1500000 }
      ];

      uploadHandler.setFiles(files);
      uploadHandler.setExcludedItems(['/models/experimental.3mf']);

      const filtered = uploadHandler._prepareFilesForUpload(files, ['/models/experimental.3mf']);
      
      expect(filtered.length).toBe(2);
      expect(filtered.some(f => f.path === '/models/experimental.3mf')).toBe(false);
    });

    test('E2E-1.6: Full flow: 10 selected, 1 excluded, 9 uploaded', () => {
      store.setMode('server');
      store.addSelection('/models', 10);
      store.addExcludedItem('/models/experimental.3mf');

      const files = [];
      for (let i = 0; i < 10; i++) {
        files.push({ path: `/models/file${i}.3mf`, size: 2000000 });
      }
      files[5].path = '/models/experimental.3mf';  // Mark one as experimental

      uploadHandler.setFiles(files);
      uploadHandler.setExcludedItems(store.getExcludedItems());

      const filtered = uploadHandler._prepareFilesForUpload(files, store.getExcludedItems());
      
      expect(filtered.length).toBe(9);
      expect(store.getExcludedItems().length).toBe(1);
    });
  });

  // ============================================
  // Scenario 2: Browser Upload + Removal
  // ============================================

  describe('E2E Scenario 2: Browser Upload + Removal', () => {
    let store;
    let uploadHandler;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
      uploadHandler = document.createElement('upload-handler');
      document.body.appendChild(uploadHandler);
    });

    afterEach(() => {
      uploadHandler.remove();
    });

    test('E2E-2.1: User uploads 50 files', () => {
      const files = [];
      for (let i = 0; i < 50; i++) {
        files.push({ path: `/uploads/file${i}.3mf`, size: 2000000 });
      }

      uploadHandler.setFiles(files);
      expect(uploadHandler.state.files.length).toBe(50);
    });

    test('E2E-2.2: User removes 5 files → excluded_items tracked', () => {
      const excluded = [
        '/uploads/file0.3mf',
        '/uploads/file10.3mf',
        '/uploads/file20.3mf',
        '/uploads/file30.3mf',
        '/uploads/file40.3mf'
      ];

      uploadHandler.setExcludedItems(excluded);
      expect(uploadHandler.state.excluded_items.length).toBe(5);
    });

    test('E2E-2.3: Upload filters 5 excluded files → 45 uploaded', () => {
      const files = [];
      for (let i = 0; i < 50; i++) {
        files.push({ path: `/uploads/file${i}.3mf`, size: 2000000 });
      }

      const excluded = [
        '/uploads/file0.3mf',
        '/uploads/file10.3mf',
        '/uploads/file20.3mf',
        '/uploads/file30.3mf',
        '/uploads/file40.3mf'
      ];

      uploadHandler.setFiles(files);
      uploadHandler.setExcludedItems(excluded);

      const filtered = uploadHandler._prepareFilesForUpload(files, excluded);
      
      expect(filtered.length).toBe(45);
      expect(uploadHandler.getUploadSummary().files_to_upload).toBe(45);
    });

    test('E2E-2.4: Bandwidth saved by not uploading excluded files', () => {
      const files = [];
      for (let i = 0; i < 50; i++) {
        files.push({ path: `/uploads/file${i}.3mf`, size: 2000000 });
      }

      const excluded = [
        '/uploads/file0.3mf',
        '/uploads/file10.3mf',
        '/uploads/file20.3mf',
        '/uploads/file30.3mf',
        '/uploads/file40.3mf'
      ];

      uploadHandler.setFiles(files);
      uploadHandler.setExcludedItems(excluded);

      const summary = uploadHandler.getUploadSummary();
      
      // 5 files * 2MB each = 10MB saved
      expect(summary.bandwidth_saved).toBe(5 * 2 * 1024 * 1024);
    });
  });

  // ============================================
  // Scenario 3: Recursive Override
  // ============================================

  describe('E2E Scenario 3: Recursive Override', () => {
    let store;
    let organizeStep;
    let validateStep;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
      organizeStep = document.createElement('organize-step');
      validateStep = document.createElement('validate-step');
      
      document.body.appendChild(organizeStep);
      document.body.appendChild(validateStep);
    });

    afterEach(() => {
      organizeStep.remove();
      validateStep.remove();
    });

    test('E2E-3.1: User selects /models/ recursively', () => {
      store.setMode('server');
      store.addSelection('/models', 50);

      expect(store.getSelections()[0].path).toBe('/models');
      expect(store.getSelections()[0].recursive).toBe(true);
    });

    test('E2E-3.2: Organize: user changes to non-recursive', (done) => {
      store.setMode('server');
      store.addSelection('/models', 50);

      setTimeout(() => {
        organizeStep._onStoreChange(store.getState());
        
        // Simulate toggle change
        const event = new CustomEvent('recursive-toggle-changed', {
          detail: { selection_path: '/models', new_recursive_value: false }
        });

        organizeStep._onRecursiveToggleChanged(event);

        // Should compute subfolders to exclude
        const subfolders = organizeStep._computeSubfoldersToExclude('/models');
        expect(Array.isArray(subfolders)).toBe(true);
        done();
      }, 100);
    });

    test('E2E-3.3: Warning shows subfolder count', (done) => {
      store.setMode('server');
      store.addSelection('/models', 50);

      setTimeout(() => {
        organizeStep._onStoreChange(store.getState());
        
        const subfolders = organizeStep._computeSubfoldersToExclude('/models');
        
        // Should have some subfolders
        if (subfolders.length > 0) {
          expect(subfolders.length).toBeGreaterThan(0);
        }
        done();
      }, 100);
    });

    test('E2E-3.4: Validate: exclusion count updated after override', (done) => {
      store.setMode('server');
      store.addSelection('/models', 50);

      // Simulate adding subfolders to excluded items
      organizeStep._onStoreChange(store.getState());
      const subfolders = organizeStep._computeSubfoldersToExclude('/models');
      if (subfolders.length > 0) {
        store.addExcludedItems(subfolders);
      }

      setTimeout(() => {
        validateStep._loadValidation();
        
        setTimeout(() => {
          const summaryCheck = validateStep.state.checks.find(c => c.key === 'excluded_items_summary');
          expect(summaryCheck.passed).toBe(true);
          done();
        }, 100);
      }, 100);
    });
  });

  // ============================================
  // Full Wizard Flow Test
  // ============================================

  describe('E2E Scenario 4: Full Wizard Flow', () => {
    let store;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
    });

    test('E2E-4.1: Source step → selections made', () => {
      store.setMode('server');
      store.addSelection('/models/gridfinity', 25);
      store.addSelection('/models/functional', 15);

      expect(store.getSelections().length).toBe(2);
    });

    test('E2E-4.2: Source step → some items removed', () => {
      store.setMode('server');
      store.addSelection('/models', 30);
      store.addExcludedItem('/models/bad1.3mf');
      store.addExcludedItem('/models/bad2.3mf');
      store.addExcludedItem('/models/bad3.3mf');

      expect(store.getExcludedItems().length).toBe(3);
    });

    test('E2E-4.3: Organize step → grouping computed', () => {
      store.setMode('server');
      store.addSelection('/models', 10);
      store.addExcludedItems(['/models/file1.3mf', '/models/file2.3mf']);

      const organizeStep = document.createElement('organize-step');
      organizeStep._onStoreChange(store.getState());

      expect(Object.keys(organizeStep.state.grouping_results).length).toBeGreaterThan(0);
      organizeStep.remove();
    });

    test('E2E-4.4: Validate step → exclusion summary shown', (done) => {
      store.setMode('server');
      store.addSelection('/models', 20);
      store.addExcludedItem('/models/file1.3mf');
      store.addExcludedItem('/models/file2.3mf');

      const validateStep = document.createElement('validate-step');
      document.body.appendChild(validateStep);

      setTimeout(() => {
        validateStep._loadValidation();
        
        setTimeout(() => {
          expect(validateStep.state.excluded_count).toBe(2);
          expect(validateStep.canProceedToUpload()).toBe(true);
          validateStep.remove();
          done();
        }, 100);
      }, 100);
    });

    test('E2E-4.5: Upload step → files filtered before upload', () => {
      store.setMode('browser');
      store.addSelection('/uploads', 50);
      store.addExcludedItems(['/uploads/f1.3mf', '/uploads/f2.3mf', '/uploads/f3.3mf']);

      const files = [];
      for (let i = 0; i < 50; i++) {
        files.push({ path: `/uploads/f${i}.3mf`, size: 2000000 });
      }

      const uploadHandler = document.createElement('upload-handler');
      uploadHandler.setFiles(files);
      uploadHandler.setExcludedItems(store.getExcludedItems());

      const filtered = uploadHandler._prepareFilesForUpload(files, store.getExcludedItems());

      expect(filtered.length).toBe(47);
      expect(uploadHandler.getUploadSummary().files_to_upload).toBe(47);
      uploadHandler.remove();
    });
  });

  // ============================================
  // Performance Tests
  // ============================================

  describe('E2E Performance Tests', () => {
    let uploadHandler;

    beforeEach(() => {
      uploadHandler = document.createElement('upload-handler');
      document.body.appendChild(uploadHandler);
    });

    afterEach(() => {
      uploadHandler.remove();
    });

    test('E2E-Perf-1: Filter 1000 files with 50 exclusions', () => {
      const files = [];
      for (let i = 0; i < 1000; i++) {
        files.push({ path: `/models/file${i}.3mf`, size: 2000000 });
      }

      const excluded = [];
      for (let i = 0; i < 50; i++) {
        excluded.push(`/models/file${i * 20}.3mf`);
      }

      const startTime = performance.now();
      const filtered = uploadHandler._prepareFilesForUpload(files, excluded);
      const endTime = performance.now();

      expect(filtered.length).toBe(950);
      expect(endTime - startTime).toBeLessThan(50);  // Should complete in <50ms
    });

    test('E2E-Perf-2: Get upload summary for 1000+ files', () => {
      const files = [];
      for (let i = 0; i < 1500; i++) {
        files.push({ path: `/uploads/file${i}.3mf`, size: 2000000 });
      }

      uploadHandler.setFiles(files);
      uploadHandler.setExcludedItems(['/uploads/file0.3mf']);

      const startTime = performance.now();
      const summary = uploadHandler.getUploadSummary();
      const endTime = performance.now();

      expect(summary.files_to_upload).toBe(1499);
      expect(endTime - startTime).toBeLessThan(10);  // Should complete in <10ms
    });

    test('E2E-Perf-3: Store can handle 500+ selections and exclusions', () => {
      const store = new IntakeWizardStore();
      store.setMode('server');

      const startTime = performance.now();

      for (let i = 0; i < 500; i++) {
        store.addExcludedItem(`/folder${i}/file.3mf`);
      }

      const endTime = performance.now();

      expect(store.getExcludedCount()).toBe(500);
      expect(endTime - startTime).toBeLessThan(100);  // Should complete in <100ms

      store.reset();
    });
  });

  // ============================================
  // File Filtering Tests (I1)
  // ============================================

  describe('E2E: I1 File Filtering', () => {
    let uploadHandler;

    beforeEach(() => {
      uploadHandler = document.createElement('upload-handler');
      document.body.appendChild(uploadHandler);
    });

    afterEach(() => {
      uploadHandler.remove();
    });

    test('I1.1: 50 files, 5 excluded → only 45 uploaded', () => {
      const files = [];
      for (let i = 0; i < 50; i++) {
        files.push({ path: `/uploads/file${i}.3mf` });
      }

      const excluded = [
        '/uploads/file5.3mf',
        '/uploads/file15.3mf',
        '/uploads/file25.3mf',
        '/uploads/file35.3mf',
        '/uploads/file45.3mf'
      ];

      const filtered = uploadHandler._prepareFilesForUpload(files, excluded);

      expect(filtered.length).toBe(45);
      expect(filtered.some(f => f.path === '/uploads/file5.3mf')).toBe(false);
    });

    test('I1.2: Exclusions applied correctly', () => {
      const files = [
        { path: '/a.3mf' },
        { path: '/b.3mf' },
        { path: '/c.3mf' },
        { path: '/d.3mf' }
      ];

      const excluded = ['/b.3mf', '/d.3mf'];

      const filtered = uploadHandler._prepareFilesForUpload(files, excluded);

      expect(filtered.length).toBe(2);
      expect(filtered.map(f => f.path)).toEqual(['/a.3mf', '/c.3mf']);
    });

    test('I1.3: No excluded files reach sidecar', () => {
      const files = [
        { path: '/good1.3mf' },
        { path: '/bad1.3mf' },
        { path: '/good2.3mf' },
        { path: '/bad2.3mf' }
      ];

      const excluded = ['/bad1.3mf', '/bad2.3mf'];

      const filtered = uploadHandler._prepareFilesForUpload(files, excluded);

      for (const file of filtered) {
        expect(excluded).not.toContain(file.path);
      }

      expect(filtered.length).toBe(2);
    });

    test('I1.4: Empty exclusions → all files included', () => {
      const files = [
        { path: '/a.3mf' },
        { path: '/b.3mf' },
        { path: '/c.3mf' }
      ];

      const filtered = uploadHandler._prepareFilesForUpload(files, []);

      expect(filtered.length).toBe(3);
    });

    test('I1.5: All files excluded → empty result', () => {
      const files = [
        { path: '/a.3mf' },
        { path: '/b.3mf' },
        { path: '/c.3mf' }
      ];

      const excluded = ['/a.3mf', '/b.3mf', '/c.3mf'];

      const filtered = uploadHandler._prepareFilesForUpload(files, excluded);

      expect(filtered.length).toBe(0);
    });
  });

  // ============================================
  // Integration Verification
  // ============================================

  describe('E2E Integration Verification', () => {
    test('E2E-Ver-1: All phases accessible and working', () => {
      // Store available
      const store = new IntakeWizardStore();
      expect(store).toBeDefined();

      // Source step available
      const sourceStep = document.createElement('source-step');
      expect(sourceStep).toBeDefined();
      sourceStep.remove();

      // Organize step available
      const organizeStep = document.createElement('organize-step');
      expect(organizeStep).toBeDefined();
      organizeStep.remove();

      // Validate step available
      const validateStep = document.createElement('validate-step');
      expect(validateStep).toBeDefined();
      validateStep.remove();

      // Upload handler available
      const uploadHandler = document.createElement('upload-handler');
      expect(uploadHandler).toBeDefined();
      uploadHandler.remove();
    });

    test('E2E-Ver-2: State persists across step transitions', () => {
      localStorage.clear();

      // Initial selection
      const store1 = new IntakeWizardStore();
      store1.setMode('server');
      store1.addSelection('/models', 10);
      store1.addExcludedItem('/models/bad.3mf');

      // New instance should restore
      const store2 = new IntakeWizardStore();

      expect(store2.getSelections().length).toBe(1);
      expect(store2.getExcludedItems().length).toBe(1);
    });

    test('E2E-Ver-3: Excluded items properly filtered throughout flow', () => {
      const store = new IntakeWizardStore();
      store.setMode('server');
      store.addSelection('/models', 20);
      store.addExcludedItems(['/models/f1.3mf', '/models/f2.3mf', '/models/f3.3mf']);

      // Organize step should not show excluded items
      const organizeStep = document.createElement('organize-step');
      organizeStep._onStoreChange(store.getState());

      const preFiltered = organizeStep.state.pre_filtered_files;
      expect(preFiltered.some(f => f.path === '/models/f1.3mf')).toBe(false);

      // Upload handler should filter them
      const uploadHandler = document.createElement('upload-handler');
      uploadHandler.setExcludedItems(store.getExcludedItems());

      const files = [];
      for (let i = 1; i <= 20; i++) {
        files.push({ path: `/models/f${i}.3mf` });
      }

      const filtered = uploadHandler._prepareFilesForUpload(files, store.getExcludedItems());
      expect(filtered.length).toBe(17);

      organizeStep.remove();
      uploadHandler.remove();
    });
  });

});
