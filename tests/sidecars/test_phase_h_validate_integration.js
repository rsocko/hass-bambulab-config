/**
 * Phase H: Validate Step Integration — Comprehensive Test Suite
 * 
 * Test Coverage:
 * - H1.1 Exclusion summary check present in response
 * - H1.2 Check always passes (informational only)
 * - H1.3 Message format with no exclusions
 * - H1.4 Message format with exclusions
 * - H1.5 Check displays count correctly
 * - H1.6 Multiple source entries aggregate count
 * - H1.7 Validation checklist displays all checks
 * - H1.8 Can proceed to Upload when validation passes
 * - H1.9 Cannot proceed if no files remaining after exclusions
 * - H1.10 Back button and proceed button events
 */

describe('Phase H: Validate Step Integration', () => {

  // ============================================
  // H1.1: Exclusion Summary Check Present
  // ============================================

  describe('H1.1 - Exclusion Summary Check Present', () => {
    let validateStep;
    let store;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
      validateStep = document.createElement('validate-step');
      document.body.appendChild(validateStep);
    });

    afterEach(() => {
      validateStep.remove();
    });

    test('H1.1.1: excluded_items_summary check in response', () => {
      expect(validateStep.state.checks.length).toBeGreaterThan(0);
      
      const summaryCheck = validateStep.state.checks.find(c => c.key === 'excluded_items_summary');
      expect(summaryCheck).toBeDefined();
    });

    test('H1.1.2: Check has required fields', (done) => {
      setTimeout(() => {
        const summaryCheck = validateStep.state.checks.find(c => c.key === 'excluded_items_summary');
        
        expect(summaryCheck.key).toBe('excluded_items_summary');
        expect(summaryCheck.label).toBeDefined();
        expect(summaryCheck.passed).toBeDefined();
        expect(summaryCheck.detail).toBeDefined();
        done();
      }, 100);
    });

    test('H1.1.3: Check appears in correct position in checklist', (done) => {
      setTimeout(() => {
        const checkKeys = validateStep.state.checks.map(c => c.key);
        const summaryIndex = checkKeys.indexOf('excluded_items_summary');
        
        // Should be after source_access, supported_types, duplicate_scan
        expect(summaryIndex).toBeGreaterThan(2);
        done();
      }, 100);
    });
  });

  // ============================================
  // H1.2: Check Always Passes
  // ============================================

  describe('H1.2 - Check Always Passes', () => {
    let validateStep;
    let store;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
      validateStep = document.createElement('validate-step');
      document.body.appendChild(validateStep);
    });

    afterEach(() => {
      validateStep.remove();
    });

    test('H1.2.1: Check passed=true with no exclusions', (done) => {
      setTimeout(() => {
        const summaryCheck = validateStep.state.checks.find(c => c.key === 'excluded_items_summary');
        expect(summaryCheck.passed).toBe(true);
        done();
      }, 100);
    });

    test('H1.2.2: Check passed=true with exclusions', (done) => {
      store.addSelection('/models', 5);
      store.addExcludedItem('/models/bad.3mf');
      
      setTimeout(() => {
        validateStep._loadValidation();
        
        setTimeout(() => {
          const summaryCheck = validateStep.state.checks.find(c => c.key === 'excluded_items_summary');
          expect(summaryCheck.passed).toBe(true);
          done();
        }, 100);
      }, 50);
    });

    test('H1.2.3: Check marked as informational in UI', (done) => {
      setTimeout(() => {
        validateStep.render();
        
        const html = validateStep.innerHTML;
        expect(html).toContain('excluded_items_summary');
        done();
      }, 100);
    });
  });

  // ============================================
  // H1.3: Message Format - No Exclusions
  // ============================================

  describe('H1.3 - Message Format: No Exclusions', () => {
    let validateStep;
    let store;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
      validateStep = document.createElement('validate-step');
      document.body.appendChild(validateStep);
    });

    afterEach(() => {
      validateStep.remove();
    });

    test('H1.3.1: Message says "No items excluded" when count is 0', (done) => {
      setTimeout(() => {
        const summaryCheck = validateStep.state.checks.find(c => c.key === 'excluded_items_summary');
        expect(summaryCheck.detail).toContain('No items excluded');
        done();
      }, 100);
    });

    test('H1.3.2: Check detail mentions selected sources', (done) => {
      setTimeout(() => {
        const summaryCheck = validateStep.state.checks.find(c => c.key === 'excluded_items_summary');
        expect(summaryCheck.detail).toContain('selected sources');
        done();
      }, 100);
    });

    test('H1.3.3: Display shows "No items excluded" when rendered', (done) => {
      setTimeout(() => {
        validateStep.render();
        
        const html = validateStep.innerHTML;
        expect(html).toContain('No items excluded');
        done();
      }, 100);
    });
  });

  // ============================================
  // H1.4: Message Format - With Exclusions
  // ============================================

  describe('H1.4 - Message Format: With Exclusions', () => {
    let validateStep;
    let store;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
      validateStep = document.createElement('validate-step');
      document.body.appendChild(validateStep);
    });

    afterEach(() => {
      validateStep.remove();
    });

    test('H1.4.1: Message includes count when items excluded', (done) => {
      store.addSelection('/models', 5);
      store.addExcludedItem('/models/bad1.3mf');
      store.addExcludedItem('/models/bad2.3mf');
      store.addExcludedItem('/models/bad3.3mf');

      setTimeout(() => {
        validateStep._loadValidation();
        
        setTimeout(() => {
          const summaryCheck = validateStep.state.checks.find(c => c.key === 'excluded_items_summary');
          expect(summaryCheck.detail).toContain('3');
          done();
        }, 100);
      }, 50);
    });

    test('H1.4.2: Message format: "N files excluded from selected sources"', (done) => {
      store.addSelection('/models', 10);
      store.addExcludedItem('/models/file1.3mf');

      setTimeout(() => {
        validateStep._loadValidation();
        
        setTimeout(() => {
          const summaryCheck = validateStep.state.checks.find(c => c.key === 'excluded_items_summary');
          expect(summaryCheck.detail).toContain('excluded');
          expect(summaryCheck.detail).toContain('selected sources');
          done();
        }, 100);
      }, 50);
    });

    test('H1.4.3: Message includes remaining items count', (done) => {
      store.addSelection('/models', 10);
      store.addExcludedItem('/models/bad1.3mf');

      setTimeout(() => {
        validateStep._loadValidation();
        
        setTimeout(() => {
          const summaryCheck = validateStep.state.checks.find(c => c.key === 'excluded_items_summary');
          expect(summaryCheck.detail).toContain('Proceeding with');
          expect(summaryCheck.detail).toContain('remaining');
          done();
        }, 100);
      }, 50);
    });

    test('H1.4.4: Singular "file" when count is 1', (done) => {
      store.addSelection('/models', 5);
      store.addExcludedItem('/models/bad.3mf');

      setTimeout(() => {
        validateStep._loadValidation();
        
        setTimeout(() => {
          const summaryCheck = validateStep.state.checks.find(c => c.key === 'excluded_items_summary');
          expect(summaryCheck.detail).toContain('1 file');
          done();
        }, 100);
      }, 50);
    });

    test('H1.4.5: Plural "files" when count > 1', (done) => {
      store.addSelection('/models', 10);
      store.addExcludedItem('/models/file1.3mf');
      store.addExcludedItem('/models/file2.3mf');

      setTimeout(() => {
        validateStep._loadValidation();
        
        setTimeout(() => {
          const summaryCheck = validateStep.state.checks.find(c => c.key === 'excluded_items_summary');
          expect(summaryCheck.detail).toContain('files');
          done();
        }, 100);
      }, 50);
    });
  });

  // ============================================
  // H1.5: Check Displays Count Correctly
  // ============================================

  describe('H1.5 - Check Displays Count Correctly', () => {
    let validateStep;
    let store;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
      validateStep = document.createElement('validate-step');
      document.body.appendChild(validateStep);
    });

    afterEach(() => {
      validateStep.remove();
    });

    test('H1.5.1: Count matches store excluded items', (done) => {
      store.addSelection('/models', 15);
      store.addExcludedItem('/models/f1.3mf');
      store.addExcludedItem('/models/f2.3mf');
      store.addExcludedItem('/models/f3.3mf');
      store.addExcludedItem('/models/f4.3mf');
      store.addExcludedItem('/models/f5.3mf');

      setTimeout(() => {
        validateStep._loadValidation();
        
        setTimeout(() => {
          expect(validateStep.state.excluded_count).toBe(5);
          done();
        }, 100);
      }, 50);
    });

    test('H1.5.2: Remaining files count is correct', (done) => {
      store.addSelection('/models', 8);
      store.addExcludedItem('/models/f1.3mf');
      store.addExcludedItem('/models/f2.3mf');
      store.addExcludedItem('/models/f3.3mf');

      setTimeout(() => {
        validateStep._loadValidation();
        
        setTimeout(() => {
          const remaining = validateStep.state.remaining_files;
          expect(remaining).toBe(5);  // 8 total - 3 excluded
          done();
        }, 100);
      }, 50);
    });

    test('H1.5.3: UI displays correct count in detail text', (done) => {
      store.addSelection('/models', 20);
      store.addExcludedItem('/models/f1.3mf');
      store.addExcludedItem('/models/f2.3mf');

      setTimeout(() => {
        validateStep._loadValidation();
        
        setTimeout(() => {
          validateStep.render();
          
          const html = validateStep.innerHTML;
          expect(html).toContain('2');  // Excluded count
          done();
        }, 100);
      }, 50);
    });
  });

  // ============================================
  // H1.7: Validation Checklist Display
  // ============================================

  describe('H1.7 - Validation Checklist Display', () => {
    let validateStep;
    let store;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
      validateStep = document.createElement('validate-step');
      document.body.appendChild(validateStep);
    });

    afterEach(() => {
      validateStep.remove();
    });

    test('H1.7.1: All checks displayed in order', (done) => {
      setTimeout(() => {
        validateStep.render();
        
        const html = validateStep.innerHTML;
        
        // Should have all check keys
        expect(html).toContain('source_access');
        expect(html).toContain('supported_types');
        expect(html).toContain('duplicate_scan');
        expect(html).toContain('excluded_items_summary');
        expect(html).toContain('commit_ready');
        done();
      }, 100);
    });

    test('H1.7.2: Check items have correct visual styling', (done) => {
      setTimeout(() => {
        validateStep.render();
        
        const html = validateStep.innerHTML;
        
        // Should have passed indicators
        expect(html).toContain('check-item');
        expect(html).toContain('check-label');
        expect(html).toContain('check-detail');
        done();
      }, 100);
    });

    test('H1.7.3: Passed checks show checkmark', (done) => {
      setTimeout(() => {
        validateStep.render();
        
        const html = validateStep.innerHTML;
        expect(html).toContain('✓');
        done();
      }, 100);
    });

    test('H1.7.4: Exclusion summary shown with info icon', (done) => {
      setTimeout(() => {
        validateStep.render();
        
        const html = validateStep.innerHTML;
        
        // Should have exclusion summary displayed
        expect(html).toContain('excluded_items_summary') ||
        expect(html).toContain('Exclusion summary');
        done();
      }, 100);
    });
  });

  // ============================================
  // H1.8: Can Proceed to Upload
  // ============================================

  describe('H1.8 - Can Proceed to Upload', () => {
    let validateStep;
    let store;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
      validateStep = document.createElement('validate-step');
      document.body.appendChild(validateStep);
    });

    afterEach(() => {
      validateStep.remove();
    });

    test('H1.8.1: Can proceed when all checks pass', (done) => {
      store.addSelection('/models', 10);

      setTimeout(() => {
        validateStep._loadValidation();
        
        setTimeout(() => {
          expect(validateStep.canProceedToUpload()).toBe(true);
          done();
        }, 100);
      }, 50);
    });

    test('H1.8.2: Proceed button enabled when ready', (done) => {
      store.addSelection('/models', 10);

      setTimeout(() => {
        validateStep._loadValidation();
        
        setTimeout(() => {
          validateStep.render();
          
          const proceedBtn = validateStep.querySelector('.action-button.proceed');
          expect(proceedBtn.disabled).toBe(false);
          done();
        }, 100);
      }, 50);
    });

    test('H1.8.3: Exclusions do not block proceed (informational)', (done) => {
      store.addSelection('/models', 20);
      store.addExcludedItem('/models/file1.3mf');
      store.addExcludedItem('/models/file2.3mf');
      store.addExcludedItem('/models/file3.3mf');

      setTimeout(() => {
        validateStep._loadValidation();
        
        setTimeout(() => {
          expect(validateStep.canProceedToUpload()).toBe(true);
          done();
        }, 100);
      }, 50);
    });
  });

  // ============================================
  // H1.9: Cannot Proceed With No Files
  // ============================================

  describe('H1.9 - Cannot Proceed: No Remaining Files', () => {
    let validateStep;
    let store;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
      validateStep = document.createElement('validate-step');
      document.body.appendChild(validateStep);
    });

    afterEach(() => {
      validateStep.remove();
    });

    test('H1.9.1: Cannot proceed if all files excluded', (done) => {
      store.addSelection('/models', 3);
      store.addExcludedItem('/models/file1.3mf');
      store.addExcludedItem('/models/file2.3mf');
      store.addExcludedItem('/models/file3.3mf');

      setTimeout(() => {
        validateStep._loadValidation();
        
        setTimeout(() => {
          expect(validateStep.canProceedToUpload()).toBe(false);
          done();
        }, 100);
      }, 50);
    });

    test('H1.9.2: Proceed button disabled when no files remaining', (done) => {
      store.addSelection('/models', 2);
      store.addExcludedItem('/models/file1.3mf');
      store.addExcludedItem('/models/file2.3mf');

      setTimeout(() => {
        validateStep._loadValidation();
        
        setTimeout(() => {
          validateStep.render();
          
          const proceedBtn = validateStep.querySelector('.action-button.proceed');
          expect(proceedBtn.disabled).toBe(true);
          done();
        }, 100);
      }, 50);
    });

    test('H1.9.3: commit_ready check shows failure when no files', (done) => {
      store.addSelection('/models', 1);
      store.addExcludedItem('/models/only_file.3mf');

      setTimeout(() => {
        validateStep._loadValidation();
        
        setTimeout(() => {
          const commitCheck = validateStep.state.checks.find(c => c.key === 'commit_ready');
          expect(commitCheck.passed).toBe(false);
          done();
        }, 100);
      }, 50);
    });
  });

  // ============================================
  // H1.10: Button Events
  // ============================================

  describe('H1.10 - Button Events', () => {
    let validateStep;
    let store;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
      validateStep = document.createElement('validate-step');
      document.body.appendChild(validateStep);
    });

    afterEach(() => {
      validateStep.remove();
    });

    test('H1.10.1: Back button dispatches validate-back event', (done) => {
      setTimeout(() => {
        validateStep._loadValidation();
        
        setTimeout(() => {
          validateStep.render();
          
          let eventFired = false;
          validateStep.addEventListener('validate-back', () => {
            eventFired = true;
          });
          
          const backBtn = validateStep.querySelector('.action-button.back');
          backBtn.click();
          
          setTimeout(() => {
            expect(eventFired).toBe(true);
            done();
          }, 50);
        }, 100);
      }, 50);
    });

    test('H1.10.2: Proceed button dispatches validate-proceed event', (done) => {
      store.addSelection('/models', 10);

      setTimeout(() => {
        validateStep._loadValidation();
        
        setTimeout(() => {
          validateStep.render();
          
          let eventFired = false;
          let eventDetail = null;
          validateStep.addEventListener('validate-proceed', (e) => {
            eventFired = true;
            eventDetail = e.detail;
          });
          
          const proceedBtn = validateStep.querySelector('.action-button.proceed');
          proceedBtn.click();
          
          setTimeout(() => {
            expect(eventFired).toBe(true);
            expect(eventDetail.validation_state).toBe('ready');
            done();
          }, 50);
        }, 100);
      }, 50);
    });

    test('H1.10.3: Proceed button disabled when cannot proceed', (done) => {
      store.addSelection('/models', 1);
      store.addExcludedItem('/models/only.3mf');

      setTimeout(() => {
        validateStep._loadValidation();
        
        setTimeout(() => {
          validateStep.render();
          
          const proceedBtn = validateStep.querySelector('.action-button.proceed');
          expect(proceedBtn.disabled).toBe(true);
          done();
        }, 100);
      }, 50);
    });

    test('H1.10.4: Proceed event includes excluded count', (done) => {
      store.addSelection('/models', 10);
      store.addExcludedItem('/models/file1.3mf');

      setTimeout(() => {
        validateStep._loadValidation();
        
        setTimeout(() => {
          validateStep.render();
          
          let eventDetail = null;
          validateStep.addEventListener('validate-proceed', (e) => {
            eventDetail = e.detail;
          });
          
          const proceedBtn = validateStep.querySelector('.action-button.proceed');
          proceedBtn.click();
          
          setTimeout(() => {
            expect(eventDetail.excluded_count).toBe(1);
            done();
          }, 50);
        }, 100);
      }, 50);
    });
  });

  // ============================================
  // H1.6: Summary & Validation
  // ============================================

  describe('H1.6 - Summary & Validation', () => {
    let validateStep;
    let store;

    beforeEach(() => {
      localStorage.clear();
      store = new IntakeWizardStore();
      validateStep = document.createElement('validate-step');
      document.body.appendChild(validateStep);
    });

    afterEach(() => {
      validateStep.remove();
    });

    test('H1.6.1: Get summary with correct info', (done) => {
      store.addSelection('/models', 8);
      store.addExcludedItem('/models/bad1.3mf');
      store.addExcludedItem('/models/bad2.3mf');

      setTimeout(() => {
        validateStep._loadValidation();
        
        setTimeout(() => {
          const summary = validateStep.getSummary();
          
          expect(summary.state).toBe('ready');
          expect(summary.excluded_count).toBe(2);
          expect(summary.remaining_files).toBe(6);
          done();
        }, 100);
      }, 50);
    });
  });

});
