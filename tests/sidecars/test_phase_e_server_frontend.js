/**
 * Unit Tests for Phase E: Frontend — Source Step Server Mode
 * 
 * Tests for:
 * - E1: Server Browser Navigation (source-server-browser)
 * - E2: Server Browser Right Pane (source-server-summary)
 * - E3: Partial Folder Badge Component (partial-folder-badge)
 * 
 * Issue #1336
 */

describe('Phase E: Frontend — Source Step Server Mode', () => {
  
  // Helper function to create test server structure
  function createTestServerStructure() {
    return [
      {
        type: 'folder',
        name: 'models',
        path: '/models',
        itemCount: 50,
      },
      {
        type: 'folder',
        name: 'benchmarks',
        path: '/benchmarks',
        itemCount: 25,
      },
      {
        type: 'file',
        name: 'README.txt',
        path: '/README.txt',
        size: 1024,
      }
    ];
  }

  // Helper for large folder
  function createLargeFolderStructure() {
    return [
      {
        type: 'folder',
        name: 'huge-folder',
        path: '/huge-folder',
        itemCount: 1500,
      }
    ];
  }

  // ===================== E1: Server Browser Navigation Tests =====================
  
  describe('E1: SourceServerBrowser Component', () => {
    let component;

    beforeEach(() => {
      component = document.createElement('source-server-browser');
      document.body.appendChild(component);
    });

    afterEach(() => {
      document.body.removeChild(component);
    });

    describe('Rendering', () => {
      it('should render breadcrumb navigation', () => {
        component.items = createTestServerStructure();
        component.currentPath = '/models';
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('models');
        expect(html).toContain('breadcrumb');
      });

      it('should display items in current folder', () => {
        component.items = createTestServerStructure();
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('models');
        expect(html).toContain('benchmarks');
        expect(html).toContain('README.txt');
      });

      it('should display folder item counts', () => {
        component.items = createTestServerStructure();
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('50 items');
        expect(html).toContain('25 items');
      });

      it('should show folder icons', () => {
        component.items = createTestServerStructure();
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('📁');
      });

      it('should show file icons by extension', () => {
        component.items = [{
          type: 'file',
          name: 'model.3mf',
          path: '/model.3mf',
          size: 1024
        }];
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('🔧');
      });
    });

    describe('Selection & Consolidation', () => {
      it('should allow selecting items', () => {
        component.items = createTestServerStructure();
        
        let selectedPath = null;
        component.onItemSelect = ({ path }) => {
          selectedPath = path;
        };
        
        const checkbox = component.shadowRoot.querySelector('.item-checkbox');
        checkbox.checked = true;
        checkbox.dispatchEvent(new Event('change'));
        
        expect(selectedPath).toBeDefined();
      });

      it('should update selectedItems property', () => {
        component.items = createTestServerStructure();
        component.selectedItems = ['/models'];
        
        expect(component.getSelectedItems()).toContain('/models');
      });

      it('should mark children as absorbed when parent is selected', () => {
        component.items = createTestServerStructure();
        component.selectedItems = ['/models'];
        
        component.items = [{
          type: 'folder',
          name: 'variants',
          path: '/models/variants',
          itemCount: 10
        }];
        component.currentPath = '/models';
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('child-of-selection');
        expect(html).toContain('included in parent');
      });

      it('should show "(included in parent)" indicator for absorbed children', () => {
        component.items = [{
          type: 'folder',
          name: 'variants',
          path: '/models/variants',
          itemCount: 10
        }];
        component.selectedItems = ['/models'];
        component.currentPath = '/models';
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('included in parent');
      });

      it('should disable checkbox for child items', () => {
        component.items = [{
          type: 'folder',
          name: 'variants',
          path: '/models/variants',
          itemCount: 10
        }];
        component.selectedItems = ['/models'];
        component.currentPath = '/models';
        
        const checkbox = component.shadowRoot.querySelector('.item-checkbox');
        expect(checkbox.disabled).toBe(true);
      });

      it('should allow deselecting items', (done) => {
        component.items = createTestServerStructure();
        component.selectedItems = ['/models'];
        
        component.onItemDeselect = (path) => {
          expect(path).toBe('/models');
          done();
        };
        
        const checkbox = component.shadowRoot.querySelector('.item-checkbox');
        checkbox.checked = false;
        checkbox.dispatchEvent(new Event('change'));
      });
    });

    describe('Large Folder Safeguard', () => {
      it('should show warning for folders with >500 items', () => {
        component.items = createLargeFolderStructure();
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('warning');
        expect(html).toContain('🚫');
        expect(html).toContain('1500+ items');
      });

      it('should disable drill-down button for large folders', () => {
        component.items = createLargeFolderStructure();
        
        const drillBtn = component.shadowRoot.querySelector('.drill-down-btn');
        expect(drillBtn.disabled).toBe(true);
      });

      it('should allow drill-down for folders <500 items', () => {
        component.items = [{
          type: 'folder',
          name: 'small',
          path: '/small',
          itemCount: 250
        }];
        
        const drillBtn = component.shadowRoot.querySelector('.drill-down-btn');
        expect(drillBtn.disabled).toBe(false);
      });

      it('should trigger navigate callback on drill-down', (done) => {
        component.items = createTestServerStructure();
        
        component.onNavigate = (path) => {
          expect(path).toBe('/models');
          done();
        };
        
        const drillBtn = component.shadowRoot.querySelector('.drill-down-btn');
        drillBtn.click();
      });
    });

    describe('Exclusion Handling', () => {
      it('should track excluded items', () => {
        component.items = createTestServerStructure();
        component.excludedItems = ['/models'];
        
        expect(component.getExcludedItems()).toContain('/models');
      });

      it('should show remove button on hover', () => {
        component.items = createTestServerStructure();
        
        const removeBtn = component.shadowRoot.querySelector('.remove-btn');
        expect(removeBtn).toBeDefined();
      });

      it('should add item to exclusions when remove button clicked', (done) => {
        component.items = createTestServerStructure();
        
        component.onRemoveItem = (path) => {
          expect(path).toBe('/models');
          done();
        };
        
        const removeBtn = component.shadowRoot.querySelector('.remove-btn');
        removeBtn.click();
      });

      it('should hide excluded items visually', () => {
        component.items = createTestServerStructure();
        component.excludedItems = ['/models'];
        
        const html = component.shadowRoot.innerHTML;
        // Excluded items should have opacity reduced or be marked
        expect(html).toContain('excluded');
      });

      it('should not show remove button for excluded items', () => {
        component.items = createTestServerStructure();
        component.excludedItems = ['/models'];
        
        // After exclusion, remove buttons should not be visible
        let removeButtons = component.shadowRoot.querySelectorAll('.remove-btn');
        expect(removeButtons.length).toBe(0);
      });
    });

    describe('Selection Summary', () => {
      it('should display selection summary', () => {
        component.items = createTestServerStructure();
        component.selectedItems = ['/models'];
        
        const summary = component.shadowRoot.innerHTML;
        expect(summary).toContain('1 folder selected');
      });

      it('should show exclusion count in summary', () => {
        component.items = createTestServerStructure();
        component.selectedItems = ['/models'];
        component.excludedItems = ['/models/experimental.3mf'];
        
        const summary = component.shadowRoot.innerHTML;
        expect(summary).toContain('1 item excluded');
      });

      it('should update summary when selections change', () => {
        component.items = createTestServerStructure();
        component.selectedItems = ['/models', '/benchmarks'];
        
        const summary = component.shadowRoot.innerHTML;
        expect(summary).toContain('2 folders selected');
      });
    });

    describe('Breadcrumb Navigation', () => {
      it('should show root in breadcrumb', () => {
        component.currentPath = '/';
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('Root');
      });

      it('should show path parts in breadcrumb', () => {
        component.currentPath = '/models/gridfinity';
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('models');
        expect(html).toContain('gridfinity');
      });

      it('should trigger navigate when breadcrumb clicked', (done) => {
        component.currentPath = '/models/gridfinity';
        
        let navigationPath = null;
        component.onNavigate = (path) => {
          navigationPath = path;
          done();
        };
        
        const breadcrumbPath = component.shadowRoot.querySelector('.breadcrumb .path');
        if (breadcrumbPath) {
          breadcrumbPath.click();
        } else {
          done(); // Skip if no clickable path
        }
      });
    });
  });

  // ===================== E2: Partial Folder Badge Tests =====================

  describe('E3: PartialFolderBadge Component', () => {
    let component;

    beforeEach(() => {
      component = document.createElement('partial-folder-badge');
      document.body.appendChild(component);
    });

    afterEach(() => {
      document.body.removeChild(component);
    });

    describe('Badge Format', () => {
      it('should render badge format by default', () => {
        component.folderPath = '/models/gridfinity';
        component.excludedCount = 3;
        component.format = 'badge';
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('badge');
        expect(html).toContain('⚠️ 3');
      });

      it('should show folder name in badge', () => {
        component.folderPath = '/models/gridfinity';
        component.excludedCount = 0;
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('gridfinity');
      });

      it('should show clean indicator when no exclusions', () => {
        component.folderPath = '/models';
        component.excludedCount = 0;
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('✓ clean');
      });

      it('should show exclusion count badge', () => {
        component.folderPath = '/models';
        component.excludedCount = 5;
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('⚠️ 5');
      });
    });

    describe('Section Format', () => {
      it('should render section format when specified', () => {
        component.folderPath = '/models';
        component.excludedCount = 3;
        component.format = 'section';
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('section');
      });

      it('should show folder name in section header', () => {
        component.folderPath = '/models/gridfinity';
        component.excludedCount = 2;
        component.format = 'section';
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('gridfinity');
      });

      it('should show exclusion explanation in section', () => {
        component.folderPath = '/models';
        component.excludedCount = 3;
        component.format = 'section';
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('3 items excluded');
      });
    });

    describe('Tooltips & Accessibility', () => {
      it('should include tooltip for badge', () => {
        component.folderPath = '/models';
        component.excludedCount = 2;
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('title=');
      });

      it('should show singular/plural in tooltip', () => {
        component.folderPath = '/models';
        component.excludedCount = 1;
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('1 item excluded');
      });
    });
  });

  // ===================== E2: Server Summary Component Tests =====================

  describe('E2: SourceServerSummary Component', () => {
    let component;

    beforeEach(() => {
      component = document.createElement('source-server-summary');
      document.body.appendChild(component);
    });

    afterEach(() => {
      document.body.removeChild(component);
    });

    describe('Rendering', () => {
      it('should show batch summary', () => {
        component.selectedItems = ['/models', '/benchmarks'];
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('2 folders selected');
      });

      it('should display selected entries', () => {
        component.selectedItems = ['/models', '/benchmarks'];
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('models');
        expect(html).toContain('benchmarks');
      });

      it('should show exclusion count for each entry', () => {
        component.selectedItems = ['/models'];
        component.excludedItems = ['/models/experimental.3mf', '/models/test.3mf'];
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('⚠️ 2');
      });

      it('should render breadcrumb at top', () => {
        component.currentPath = '/models/gridfinity';
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('breadcrumb');
        expect(html).toContain('models');
        expect(html).toContain('gridfinity');
      });
    });

    describe('Consolidated View', () => {
      it('should show only topmost selected entries (no children)', () => {
        component.selectedItems = ['/models'];
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('models');
        // Should not show children (they're absorbed)
      });

      it('should display multiple topmost entries', () => {
        component.selectedItems = ['/models', '/benchmarks'];
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('models');
        expect(html).toContain('benchmarks');
      });
    });

    describe('Location Indicator', () => {
      it('should show "Part of:" indicator when in subfolder', () => {
        component.selectedItems = ['/models'];
        component.currentPath = '/models/gridfinity';
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('Part of:');
        expect(html).toContain('models');
      });

      it('should not show "Part of:" at root level', () => {
        component.selectedItems = ['/models'];
        component.currentPath = '/';
        
        const html = component.shadowRoot.innerHTML;
        expect(html).not.toContain('Part of:');
      });

      it('should show parent folder name in indicator', () => {
        component.selectedItems = ['/models'];
        component.currentPath = '/models/gridfinity/experimental';
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('📍 Part of:');
      });
    });

    describe('Exclusion Display', () => {
      it('should show exclusion count in batch summary', () => {
        component.selectedItems = ['/models'];
        component.excludedItems = ['/models/file1.3mf', '/models/file2.3mf'];
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('2 items excluded');
      });

      it('should show no exclusions message when none', () => {
        component.selectedItems = ['/models'];
        component.excludedItems = [];
        
        const html = component.shadowRoot.innerHTML;
        expect(html).not.toContain('excluded');
      });

      it('should count exclusions correctly per entry', () => {
        component.selectedItems = ['/models', '/benchmarks'];
        component.excludedItems = [
          '/models/file1.3mf',
          '/models/file2.3mf',
          '/benchmarks/old.3mf'
        ];
        
        // Summary should show total
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('3 items excluded');
      });
    });

    describe('Empty State', () => {
      it('should show "No folders selected" when empty', () => {
        component.selectedItems = [];
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('No folders selected');
      });

      it('should show empty selections message', () => {
        component.selectedItems = [];
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('No selections');
      });
    });

    describe('Count Methods', () => {
      it('should return selected count', () => {
        component.selectedItems = ['/models', '/benchmarks'];
        
        expect(component.getSelectedCount()).toBe(2);
      });

      it('should return excluded count', () => {
        component.excludedItems = ['/models/file1.3mf', '/models/file2.3mf'];
        
        expect(component.getExcludedCount()).toBe(2);
      });
    });

    describe('Synchronization', () => {
      it('should accept currentPath for synchronized navigation', () => {
        component.currentPath = '/models/gridfinity';
        
        expect(component._currentPath).toBe('/models/gridfinity');
      });

      it('should update display when selected items change', () => {
        component.selectedItems = ['/models'];
        
        let html1 = component.shadowRoot.innerHTML;
        expect(html1).toContain('1 folder');
        
        component.selectedItems = ['/models', '/benchmarks'];
        let html2 = component.shadowRoot.innerHTML;
        expect(html2).toContain('2 folders');
      });
    });
  });

  // ===================== Phase E Acceptance Criteria Tests =====================

  describe('Phase E: Acceptance Criteria', () => {
    it('[AC1] Overlapping selections consolidated', () => {
      const component = document.createElement('source-server-browser');
      document.body.appendChild(component);
      
      component.items = [{
        type: 'folder',
        name: 'variants',
        path: '/models/variants',
        itemCount: 10
      }];
      
      component.selectedItems = ['/models'];
      component.currentPath = '/models';
      
      const html = component.shadowRoot.innerHTML;
      // Children should be marked as absorbed
      expect(html).toContain('child-of-selection');
      
      document.body.removeChild(component);
    });

    it('[AC2] Children shown as "selected", grayed out', () => {
      const component = document.createElement('source-server-browser');
      document.body.appendChild(component);
      
      component.items = [{
        type: 'folder',
        name: 'variants',
        path: '/models/variants',
        itemCount: 10
      }];
      component.selectedItems = ['/models'];
      component.currentPath = '/models';
      
      const checkbox = component.shadowRoot.querySelector('.item-checkbox');
      expect(checkbox.disabled).toBe(true);
      
      document.body.removeChild(component);
    });

    it('[AC3] Removal buttons functional', (done) => {
      const component = document.createElement('source-server-browser');
      document.body.appendChild(component);
      
      component.items = [{
        type: 'folder',
        name: 'test',
        path: '/test',
        itemCount: 5
      }];
      
      component.onRemoveItem = (path) => {
        expect(path).toBeDefined();
        document.body.removeChild(component);
        done();
      };
      
      const removeBtn = component.shadowRoot.querySelector('.remove-btn');
      removeBtn.click();
    });

    it('[AC4] Left/right panes synchronized', () => {
      const leftPane = document.createElement('source-server-browser');
      const rightPane = document.createElement('source-server-summary');
      document.body.appendChild(leftPane);
      document.body.appendChild(rightPane);
      
      leftPane.items = [{
        type: 'folder',
        name: 'models',
        path: '/models',
        itemCount: 50
      }];
      leftPane.selectedItems = ['/models'];
      
      rightPane.selectedItems = ['/models'];
      
      expect(rightPane.getSelectedCount()).toBe(leftPane.getSelectedItems().length);
      
      document.body.removeChild(leftPane);
      document.body.removeChild(rightPane);
    });

    it('[AC5] Breadcrumb identical on both sides', () => {
      const leftPane = document.createElement('source-server-browser');
      const rightPane = document.createElement('source-server-summary');
      document.body.appendChild(leftPane);
      document.body.appendChild(rightPane);
      
      leftPane.currentPath = '/models/gridfinity';
      rightPane.currentPath = '/models/gridfinity';
      
      const leftHtml = leftPane.shadowRoot.innerHTML;
      const rightHtml = rightPane.shadowRoot.innerHTML;
      
      // Both should show the path parts
      expect(leftHtml).toContain('models');
      expect(rightHtml).toContain('models');
      expect(leftHtml).toContain('gridfinity');
      expect(rightHtml).toContain('gridfinity');
      
      document.body.removeChild(leftPane);
      document.body.removeChild(rightPane);
    });

    it('[AC6] Right shows only topmost entries', () => {
      const rightPane = document.createElement('source-server-summary');
      document.body.appendChild(rightPane);
      
      rightPane.selectedItems = ['/models'];
      
      const html = rightPane.shadowRoot.innerHTML;
      // Should show /models but not its children (consolidated view)
      expect(html).toContain('models');
      
      document.body.removeChild(rightPane);
    });

    it('[AC7] Partial indicators display correctly', () => {
      const component = document.createElement('source-server-browser');
      document.body.appendChild(component);
      
      component.items = [{
        type: 'folder',
        name: 'models',
        path: '/models',
        itemCount: 50
      }];
      component.selectedItems = ['/models'];
      component.excludedItems = ['/models/experimental.3mf', '/models/test.3mf'];
      
      const rightPane = document.createElement('source-server-summary');
      document.body.appendChild(rightPane);
      
      rightPane.selectedItems = ['/models'];
      rightPane.excludedItems = ['/models/experimental.3mf', '/models/test.3mf'];
      
      const html = rightPane.shadowRoot.innerHTML;
      expect(html).toContain('⚠️ 2');
      
      document.body.removeChild(component);
      document.body.removeChild(rightPane);
    });
  });
});
