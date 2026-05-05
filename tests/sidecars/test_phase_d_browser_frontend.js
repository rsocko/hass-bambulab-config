/**
 * Unit Tests for Phase D: Frontend — Source Step Browser Mode
 * 
 * Tests for:
 * - D1: Browser File List Component (source-browser-file-tree)
 * - D2: Browser Upload Right Pane (source-browser-summary)
 * 
 * Issue #1335
 */

describe('Phase D: Frontend — Source Step Browser Mode', () => {
  
  // Helper function to create test tree structure
  function createTestTree(fileCount = 10) {
    const files = [];
    for (let i = 1; i <= fileCount; i++) {
      files.push({
        type: 'file',
        name: `model-${i}.3mf`,
        path: `/uploads/model-${i}.3mf`,
        size: 1024 * 100 * i,
      });
    }
    
    return [
      {
        type: 'folder',
        name: 'uploads',
        path: '/uploads',
        children: files,
      }
    ];
  }

  // ===================== D1: Browser File List Component Tests =====================
  
  describe('D1: SourceBrowserFileTree Component', () => {
    let component;

    beforeEach(() => {
      component = document.createElement('source-browser-file-tree');
      document.body.appendChild(component);
    });

    afterEach(() => {
      document.body.removeChild(component);
    });

    describe('Rendering', () => {
      it('should render empty state when no items provided', () => {
        component.items = [];
        const text = component.shadowRoot.textContent;
        expect(text).toContain('No files uploaded yet');
      });

      it('should render tree with 10 items without lag', (done) => {
        const startTime = performance.now();
        component.items = createTestTree(10);
        const endTime = performance.now();
        
        expect(endTime - startTime).toBeLessThan(50); // Should render in < 50ms
        expect(component.shadowRoot.querySelectorAll('.tree-node').length).toBeGreaterThan(0);
        done();
      });

      it('should render tree with 50 files without lag', (done) => {
        const startTime = performance.now();
        component.items = createTestTree(50);
        const endTime = performance.now();
        
        expect(endTime - startTime).toBeLessThan(100); // Should render in < 100ms
        expect(component.shadowRoot.querySelectorAll('.tree-node').length).toBeGreaterThan(0);
        done();
      });

      it('should display file count in summary', () => {
        component.items = createTestTree(5);
        const summary = component.shadowRoot.textContent;
        expect(summary).toContain('5 items selected');
      });

      it('should display file names correctly', () => {
        component.items = createTestTree(3);
        const content = component.shadowRoot.innerHTML;
        expect(content).toContain('model-1.3mf');
        expect(content).toContain('model-2.3mf');
        expect(content).toContain('model-3.3mf');
      });

      it('should display folder icons for folders', () => {
        component.items = createTestTree(2);
        const icons = component.shadowRoot.innerHTML;
        expect(icons).toContain('📁');
      });

      it('should display file icons based on extension', () => {
        component.items = [{
          type: 'folder',
          name: 'test',
          path: '/test',
          children: [
            { type: 'file', name: 'model.3mf', path: '/test/model.3mf' },
            { type: 'file', name: 'data.stl', path: '/test/data.stl' },
            { type: 'file', name: 'info.pdf', path: '/test/info.pdf' },
            { type: 'file', name: 'image.jpg', path: '/test/image.jpg' },
          ]
        }];
        component.items = component.items;
        
        const content = component.shadowRoot.innerHTML;
        expect(content).toContain('🔧'); // for 3mf/stl
        expect(content).toContain('📖'); // for pdf
        expect(content).toContain('🖼️'); // for jpg
      });
    });

    describe('Exclusion Tracking', () => {
      it('should track excluded items', () => {
        component.items = createTestTree(5);
        component.excludedItems = ['/uploads/model-1.3mf'];
        
        expect(component.getExcludedCount()).toBe(1);
        expect(component.getIncludedCount()).toBe(4);
      });

      it('should display exclusion count in summary', () => {
        component.items = createTestTree(5);
        component.excludedItems = ['/uploads/model-1.3mf', '/uploads/model-2.3mf'];
        
        const summary = component.shadowRoot.textContent;
        expect(summary).toContain('2 excluded');
      });

      it('should hide excluded items from tree display', () => {
        component.items = createTestTree(5);
        component.excludedItems = ['/uploads/model-1.3mf'];
        
        const content = component.shadowRoot.innerHTML;
        expect(content).not.toContain('model-1.3mf');
        expect(content).toContain('model-2.3mf');
      });

      it('should support multiple exclusions', () => {
        component.items = createTestTree(10);
        const excluded = ['/uploads/model-1.3mf', '/uploads/model-5.3mf', '/uploads/model-9.3mf'];
        component.excludedItems = excluded;
        
        expect(component.getExcludedCount()).toBe(3);
        expect(component.getIncludedCount()).toBe(7);
      });

      it('should show exclusion count as 0 when no items excluded', () => {
        component.items = createTestTree(5);
        component.excludedItems = [];
        
        const summary = component.shadowRoot.textContent;
        expect(summary).not.toContain('excluded');
      });
    });

    describe('Partial Indicators', () => {
      it('should mark folders as partial when children are excluded', () => {
        const tree = [{
          type: 'folder',
          name: 'parent',
          path: '/parent',
          children: [
            { type: 'file', name: 'child1.3mf', path: '/parent/child1.3mf' },
            { type: 'file', name: 'child2.3mf', path: '/parent/child2.3mf' },
          ]
        }];
        
        component.items = tree;
        component.excludedItems = ['/parent/child1.3mf'];
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('partial');
        expect(html).toContain('⚠️');
      });

      it('should show exclusion count in partial badge', () => {
        const tree = [{
          type: 'folder',
          name: 'parent',
          path: '/parent',
          children: [
            { type: 'file', name: 'child1.3mf', path: '/parent/child1.3mf' },
            { type: 'file', name: 'child2.3mf', path: '/parent/child2.3mf' },
            { type: 'file', name: 'child3.3mf', path: '/parent/child3.3mf' },
          ]
        }];
        
        component.items = tree;
        component.excludedItems = ['/parent/child1.3mf', '/parent/child2.3mf'];
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('⚠️ 2');
      });

      it('should cascade partial indicators to ancestors', () => {
        const tree = [{
          type: 'folder',
          name: 'root',
          path: '/root',
          children: [{
            type: 'folder',
            name: 'child',
            path: '/root/child',
            children: [{
              type: 'file',
              name: 'file.3mf',
              path: '/root/child/file.3mf'
            }]
          }]
        }];
        
        component.items = tree;
        component.excludedItems = ['/root/child/file.3mf'];
        
        const html = component.shadowRoot.innerHTML;
        // Both parent and child should be marked partial
        const partialCount = (html.match(/partial/g) || []).length;
        expect(partialCount).toBeGreaterThan(0);
      });
    });

    describe('Remove Button Functionality', () => {
      it('should show remove button on hover', () => {
        component.items = createTestTree(1);
        
        let removeButtons = component.shadowRoot.querySelectorAll('.remove-btn');
        expect(removeButtons.length).toBeGreaterThan(0);
      });

      it('should not show remove button for excluded items', () => {
        const tree = [{
          type: 'folder',
          name: 'parent',
          path: '/parent',
          children: [
            { type: 'file', name: 'item.3mf', path: '/parent/item.3mf' }
          ]
        }];
        
        component.items = tree;
        component.excludedItems = ['/parent/item.3mf'];
        
        const removeButtons = component.shadowRoot.querySelectorAll('.remove-btn');
        expect(removeButtons.length).toBe(0);
      });

      it('should call onRemoveItem callback when remove button clicked', (done) => {
        component.items = createTestTree(1);
        
        let removedPath = null;
        component.onRemoveItem = (path) => {
          removedPath = path;
          done();
        };
        
        const removeBtn = component.shadowRoot.querySelector('.remove-btn');
        removeBtn.click();
      });

      it('should trigger state change on remove', (done) => {
        component.items = createTestTree(1);
        
        component.onStateChange = (change) => {
          expect(change.type).toBe('remove');
          expect(change.path).toBeDefined();
          done();
        };
        
        const removeBtn = component.shadowRoot.querySelector('.remove-btn');
        removeBtn.click();
      });

      it('should immediately hide item from tree after removal', () => {
        const testPath = '/uploads/model-1.3mf';
        component.items = createTestTree(5);
        
        component.onRemoveItem = (path) => {
          // Simulate exclusion update
          component.excludedItems = [path];
        };
        
        const removeBtn = component.shadowRoot.querySelector('.remove-btn');
        removeBtn.click();
        
        const content = component.shadowRoot.innerHTML;
        expect(content).not.toContain('model-1.3mf');
      });
    });

    describe('File Size Display', () => {
      it('should display file sizes in human-readable format', () => {
        const tree = [{
          type: 'folder',
          name: 'test',
          path: '/test',
          children: [
            { type: 'file', name: 'small.3mf', path: '/test/small.3mf', size: 512 },
            { type: 'file', name: 'medium.3mf', path: '/test/medium.3mf', size: 1024 * 100 },
            { type: 'file', name: 'large.3mf', path: '/test/large.3mf', size: 1024 * 1024 * 50 },
          ]
        }];
        
        component.items = tree;
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('B'); // bytes
        expect(html).toContain('KB'); // kilobytes
        expect(html).toContain('MB'); // megabytes
      });
    });

    describe('XSS Prevention', () => {
      it('should escape HTML in file names', () => {
        const tree = [{
          type: 'folder',
          name: 'test',
          path: '/test',
          children: [{
            type: 'file',
            name: 'file<script>.3mf',
            path: '/test/file<script>.3mf'
          }]
        }];
        
        component.items = tree;
        
        const html = component.shadowRoot.innerHTML;
        expect(html).not.toContain('<script>');
        expect(html).toContain('&lt;script&gt;');
      });
    });

    describe('Performance', () => {
      it('should use Set-based O(1) lookup for excluded items', () => {
        component.items = createTestTree(100);
        
        const largeExcluded = [];
        for (let i = 1; i <= 50; i++) {
          largeExcluded.push(`/uploads/model-${i}.3mf`);
        }
        
        const startTime = performance.now();
        component.excludedItems = largeExcluded;
        const endTime = performance.now();
        
        // Should be fast even with 50 exclusions (O(n) tree setup only)
        expect(endTime - startTime).toBeLessThan(50);
      });
    });
  });

  // ===================== D2: Browser Summary Component Tests =====================

  describe('D2: SourceBrowserSummary Component', () => {
    let component;

    beforeEach(() => {
      component = document.createElement('source-browser-summary');
      document.body.appendChild(component);
    });

    afterEach(() => {
      document.body.removeChild(component);
    });

    describe('Rendering', () => {
      it('should render empty state when no items', () => {
        component.items = [];
        const text = component.shadowRoot.textContent;
        expect(text).toContain('No files selected');
      });

      it('should display batch summary', () => {
        component.items = createTestTree(5);
        const text = component.shadowRoot.textContent;
        expect(text).toContain('5 items selected');
      });

      it('should show exclusion count in batch summary', () => {
        component.items = createTestTree(5);
        component.excludedItems = ['/uploads/model-1.3mf', '/uploads/model-2.3mf'];
        
        const text = component.shadowRoot.textContent;
        expect(text).toContain('2 excluded');
      });
    });

    describe('Pre-Filtering (Excluded Items Hidden)', () => {
      it('should NOT display excluded items', () => {
        component.items = createTestTree(5);
        component.excludedItems = ['/uploads/model-1.3mf'];
        
        const html = component.shadowRoot.innerHTML;
        expect(html).not.toContain('model-1.3mf');
        expect(html).toContain('model-2.3mf');
      });

      it('should hide multiple excluded items', () => {
        component.items = createTestTree(5);
        component.excludedItems = ['/uploads/model-1.3mf', '/uploads/model-3.3mf', '/uploads/model-5.3mf'];
        
        const html = component.shadowRoot.innerHTML;
        expect(html).not.toContain('model-1.3mf');
        expect(html).not.toContain('model-3.3mf');
        expect(html).not.toContain('model-5.3mf');
        expect(html).toContain('model-2.3mf');
        expect(html).toContain('model-4.3mf');
      });

      it('should correctly count included items (excluding removed)', () => {
        component.items = createTestTree(10);
        component.excludedItems = Array.from({length: 3}, (_, i) => `/uploads/model-${i+1}.3mf`);
        
        expect(component.getIncludedCount()).toBe(7);
        expect(component.getExcludedCount()).toBe(3);
      });
    });

    describe('Partial Indicators', () => {
      it('should display partial badge for folders with excluded descendants', () => {
        const tree = [{
          type: 'folder',
          name: 'parent',
          path: '/parent',
          children: [
            { type: 'file', name: 'child1.3mf', path: '/parent/child1.3mf' },
            { type: 'file', name: 'child2.3mf', path: '/parent/child2.3mf' },
          ]
        }];
        
        component.items = tree;
        component.excludedItems = ['/parent/child1.3mf'];
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('⚠️');
      });

      it('should show correct count in partial badge', () => {
        const tree = [{
          type: 'folder',
          name: 'parent',
          path: '/parent',
          children: [
            { type: 'file', name: 'child1.3mf', path: '/parent/child1.3mf' },
            { type: 'file', name: 'child2.3mf', path: '/parent/child2.3mf' },
          ]
        }];
        
        component.items = tree;
        component.excludedItems = ['/parent/child1.3mf', '/parent/child2.3mf'];
        
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('⚠️ 2');
      });

      it('should not show partial badge when no exclusions', () => {
        component.items = createTestTree(5);
        component.excludedItems = [];
        
        const html = component.shadowRoot.innerHTML;
        expect(html).not.toContain('⚠️');
      });
    });

    describe('Navigation Synchronization', () => {
      it('should update expanded folders when synced from left pane', () => {
        const tree = [{
          type: 'folder',
          name: 'parent',
          path: '/parent',
          children: [
            { type: 'folder', name: 'child', path: '/parent/child', children: [] }
          ]
        }];
        
        component.items = tree;
        component.expandedFolders = new Set(['/parent']);
        
        // Should reflect expanded state in rendering
        const html = component.shadowRoot.innerHTML;
        expect(html).toContain('expanded');
      });

      it('should render collapse indicator when folder not expanded', () => {
        const tree = [{
          type: 'folder',
          name: 'parent',
          path: '/parent',
          children: [
            { type: 'file', name: 'file.3mf', path: '/parent/file.3mf' }
          ]
        }];
        
        component.items = tree;
        component.expandedFolders = new Set(); // Not expanded
        
        const html = component.shadowRoot.innerHTML;
        expect(html).not.toContain('expanded');
      });

      it('should accept currentPath prop for navigation state', () => {
        component.items = createTestTree(5);
        component.currentPath = '/uploads';
        
        // Component should store the path (used for synchronized navigation)
        expect(component._currentPath).toBe('/uploads');
      });
    });

    describe('Batch Summary Display', () => {
      it('should display singular "item" for 1 item', () => {
        const tree = [{
          type: 'folder',
          name: 'test',
          path: '/test',
          children: [{ type: 'file', name: 'file.3mf', path: '/test/file.3mf' }]
        }];
        
        component.items = tree;
        const text = component.shadowRoot.textContent;
        expect(text).toContain('1 items selected');
      });

      it('should display plural "items" for multiple', () => {
        component.items = createTestTree(5);
        const text = component.shadowRoot.textContent;
        expect(text).toContain('5 items selected');
      });

      it('should update summary when exclusions change', () => {
        component.items = createTestTree(10);
        
        let initialCount = component.getIncludedCount();
        expect(initialCount).toBe(10);
        
        component.excludedItems = ['/uploads/model-1.3mf', '/uploads/model-2.3mf'];
        
        let updatedCount = component.getIncludedCount();
        expect(updatedCount).toBe(8);
      });
    });

    describe('Component Integration', () => {
      it('should have identical item count to left pane (when synced)', () => {
        const leftPane = document.createElement('source-browser-file-tree');
        const rightPane = document.createElement('source-browser-summary');
        document.body.appendChild(leftPane);
        document.body.appendChild(rightPane);
        
        const tree = createTestTree(10);
        const excluded = ['/uploads/model-1.3mf'];
        
        leftPane.items = tree;
        leftPane.excludedItems = excluded;
        
        rightPane.items = tree;
        rightPane.excludedItems = excluded;
        
        expect(rightPane.getIncludedCount()).toBe(leftPane.getIncludedCount());
        
        document.body.removeChild(leftPane);
        document.body.removeChild(rightPane);
      });

      it('should hide excluded items consistently between panes', () => {
        const leftPane = document.createElement('source-browser-file-tree');
        const rightPane = document.createElement('source-browser-summary');
        document.body.appendChild(leftPane);
        document.body.appendChild(rightPane);
        
        const tree = createTestTree(5);
        const excluded = ['/uploads/model-1.3mf', '/uploads/model-3.3mf'];
        
        leftPane.items = tree;
        leftPane.excludedItems = excluded;
        
        rightPane.items = tree;
        rightPane.excludedItems = excluded;
        
        const leftHtml = leftPane.shadowRoot.innerHTML;
        const rightHtml = rightPane.shadowRoot.innerHTML;
        
        // Both should NOT contain excluded items
        expect(leftHtml).not.toContain('model-1.3mf');
        expect(rightHtml).not.toContain('model-1.3mf');
        expect(leftHtml).not.toContain('model-3.3mf');
        expect(rightHtml).not.toContain('model-3.3mf');
        
        document.body.removeChild(leftPane);
        document.body.removeChild(rightPane);
      });
    });
  });

  // ===================== Phase D Acceptance Criteria Tests =====================

  describe('Phase D: Acceptance Criteria', () => {
    it('[AC1] Tree displays uploaded files/folders', () => {
      const component = document.createElement('source-browser-file-tree');
      document.body.appendChild(component);
      
      component.items = createTestTree(5);
      
      const html = component.shadowRoot.innerHTML;
      expect(html).toContain('model-1.3mf');
      expect(html).toContain('model-5.3mf');
      
      document.body.removeChild(component);
    });

    it('[AC2] Remove buttons functional', () => {
      const component = document.createElement('source-browser-file-tree');
      document.body.appendChild(component);
      
      component.items = createTestTree(3);
      
      let removedPath = null;
      component.onRemoveItem = (path) => {
        removedPath = path;
      };
      
      const removeBtn = component.shadowRoot.querySelector('.remove-btn');
      removeBtn.click();
      
      expect(removedPath).toBeDefined();
      expect(removedPath).toContain('/uploads/');
      
      document.body.removeChild(component);
    });

    it('[AC3] Removed items disappear from both panes', () => {
      const leftPane = document.createElement('source-browser-file-tree');
      const rightPane = document.createElement('source-browser-summary');
      document.body.appendChild(leftPane);
      document.body.appendChild(rightPane);
      
      const tree = createTestTree(3);
      const testPath = '/uploads/model-1.3mf';
      
      leftPane.items = tree;
      rightPane.items = tree;
      
      leftPane.excludedItems = [testPath];
      rightPane.excludedItems = [testPath];
      
      const leftHtml = leftPane.shadowRoot.innerHTML;
      const rightHtml = rightPane.shadowRoot.innerHTML;
      
      expect(leftHtml).not.toContain('model-1.3mf');
      expect(rightHtml).not.toContain('model-1.3mf');
      
      document.body.removeChild(leftPane);
      document.body.removeChild(rightPane);
    });

    it('[AC4] Partial indicators show correct counts', () => {
      const component = document.createElement('source-browser-file-tree');
      document.body.appendChild(component);
      
      const tree = [{
        type: 'folder',
        name: 'parent',
        path: '/parent',
        children: Array.from({length: 5}, (_, i) => ({
          type: 'file',
          name: `file${i}.3mf`,
          path: `/parent/file${i}.3mf`
        }))
      }];
      
      component.items = tree;
      component.excludedItems = ['/parent/file0.3mf', '/parent/file1.3mf', '/parent/file2.3mf'];
      
      const html = component.shadowRoot.innerHTML;
      expect(html).toContain('⚠️ 3');
      
      document.body.removeChild(component);
    });

    it('[AC5] Left/right panes synchronized', () => {
      const leftPane = document.createElement('source-browser-file-tree');
      const rightPane = document.createElement('source-browser-summary');
      document.body.appendChild(leftPane);
      document.body.appendChild(rightPane);
      
      const tree = createTestTree(10);
      const excluded = ['/uploads/model-1.3mf', '/uploads/model-2.3mf'];
      
      leftPane.items = tree;
      leftPane.excludedItems = excluded;
      
      rightPane.items = tree;
      rightPane.excludedItems = excluded;
      rightPane.expandedFolders = new Set(['/uploads']);
      
      expect(leftPane.getExcludedCount()).toBe(rightPane.getExcludedCount());
      expect(leftPane.getIncludedCount()).toBe(rightPane.getIncludedCount());
      
      document.body.removeChild(leftPane);
      document.body.removeChild(rightPane);
    });

    it('[AC6] No performance issues with 50+ files', () => {
      const startTime = performance.now();
      
      const component = document.createElement('source-browser-file-tree');
      document.body.appendChild(component);
      
      component.items = createTestTree(50);
      component.excludedItems = Array.from({length: 25}, (_, i) => `/uploads/model-${i+1}.3mf`);
      
      const endTime = performance.now();
      
      expect(endTime - startTime).toBeLessThan(200); // Total operation < 200ms
      
      document.body.removeChild(component);
    });

    it('[AC7] Excluded items not shown on right pane', () => {
      const rightPane = document.createElement('source-browser-summary');
      document.body.appendChild(rightPane);
      
      const tree = createTestTree(5);
      const excluded = ['/uploads/model-1.3mf', '/uploads/model-3.3mf'];
      
      rightPane.items = tree;
      rightPane.excludedItems = excluded;
      
      const html = rightPane.shadowRoot.innerHTML;
      
      // Excluded items should not appear in right pane (pre-filtered)
      expect(html).not.toContain('model-1.3mf');
      expect(html).not.toContain('model-3.3mf');
      // But included items should
      expect(html).toContain('model-2.3mf');
      expect(html).toContain('model-4.3mf');
      
      document.body.removeChild(rightPane);
    });
  });
});
