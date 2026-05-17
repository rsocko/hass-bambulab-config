# Issue #1490: Entity Types Frontend Implementation Guide

## Overview
This guide describes how to extend the existing model catalog browse card to support Ideas and Working Groups as first-class catalog citizens (US-9, US-10).

## Backend API Contract
The sidecar now exposes:
- **POST** `/api/local/models` - Create entities with `entity_type: "idea" | "working_group" | "model"`
- **PUT** `/api/local/models/{id}/promote` - Promote entities between types
- All list/detail endpoints now include `entity_type` in responses

## Phase 2.1 Frontend: Core Filtering & UI Elements

### 1. Toolbar Chips (Show ideas / Show working groups)

**Location**: model-catalog-browser-card.js, filter toolbar area

```javascript
// Add to filter state tracking:
_filterState = {
  showModels: true,      // default: show only models
  showIdeas: false,      // new chip: toggle to show ideas
  showWorkingGroups: false, // new chip: toggle to show working groups
  // ... existing filters
};

// Filter logic (update _applyFilters method):
_applyFilters(models) {
  let filtered = models;
  
  // Entity type filter
  filtered = filtered.filter(model => {
    const entityType = model.entity_type || 'model';
    if (this._filterState.showIdeas && entityType === 'idea') return true;
    if (this._filterState.showWorkingGroups && entityType === 'working_group') return true;
    if (entityType === 'model') return true;  // always show models by default
    return false;
  });
  
  // ... apply other existing filters
  return filtered;
}

// Render chips in toolbar:
_renderFilterChips() {
  return html`
    <!-- existing chips -->
    ${this._filterState.showIdeas ? 
      html`<span class="filter-chip idea" @click="${() => this._toggleFilter('showIdeas')}">
        💡 Show ideas (${this._countEntitiesOfType('idea')})
      </span>` : ''}
    
    ${this._filterState.showWorkingGroups ? 
      html`<span class="filter-chip working-group" @click="${() => this._toggleFilter('showWorkingGroups')}">
        🧰 Show working groups (${this._countEntitiesOfType('working_group')})
      </span>` : ''}
  `;
}
```

### 2. Add Idea Quick-Add Button

**Location**: model-catalog-browser-card.js, header action buttons

```javascript
_renderHeaderActions() {
  return html`
    <!-- Existing "+ Add Model" button -->
    <button class="action-btn add-idea-btn" @click="${this._onCreateIdea}">
      + Add Idea
    </button>
  `;
}

async _onCreateIdea() {
  // Open minimal idea creation form
  const title = prompt("Idea title:");
  if (!title) return;
  
  const localModelId = this._generateUniqueId('idea');
  
  const response = await fetch(
    `${this._getSidecarUrl()}/api/local/models`,
    {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        local_model_id: localModelId,
        model_name: title,
        entity_type: 'idea',
        tags: []
      })
    }
  );
  
  if (response.ok) {
    this._refreshModelList();
  } else {
    alert('Failed to create idea');
  }
}
```

### 3. Entity Type Badges on Cards

**Location**: model-catalog-browser-card.js, card rendering

```javascript
_renderModelCard(model) {
  const entityType = model.entity_type || 'model';
  
  return html`
    <article class="model-card" data-entity-type="${entityType}">
      <!-- existing card content -->
      
      <!-- Add entity type pill -->
      ${entityType !== 'model' ? html`
        <span class="entity-type-pill ${entityType}">
          ${entityType === 'idea' ? '💡 Idea' : 
            entityType === 'working_group' ? '🧰 Working Group' : ''}
        </span>
      ` : ''}
      
      <!-- existing card footer -->
    </article>
  `;
}

// CSS for pills:
.entity-type-pill {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  margin: 0 4px 4px 0;
  
  &.idea {
    background: #fff3cd;
    color: #856404;
    border: 1px solid #ffeeba;
  }
  
  &.working_group {
    background: #d1ecf1;
    color: #0c5460;
    border: 1px solid #bee5eb;
  }
}
```

### 4. Promote Actions in Popup

**Location**: model-catalog-browser-card.js, detail popup overflow menu

```javascript
_renderPopupActions(modelRef) {
  const model = this._findModel(modelRef);
  if (!model) return '';
  
  const entityType = model.entity_type || 'model';
  const promotePath = this._getPromotionPath(entityType);
  
  return html`
    <!-- existing actions -->
    
    ${promotePath.includes('model') ? html`
      <button class="popup-action" @click="${() => this._onPromote(modelRef, entityType, 'model')}">
        📤 Promote to Model
      </button>
    ` : ''}
    
    ${promotePath.includes('working_group') ? html`
      <button class="popup-action" @click="${() => this._onPromote(modelRef, entityType, 'working_group')}">
        📤 Promote to Working Group
      </button>
    ` : ''}
  `;
}

_getPromotionPath(fromType) {
  const paths = {
    'idea': ['model', 'working_group'],
    'working_group': ['model'],
    'model': []
  };
  return paths[fromType] || [];
}

async _onPromote(modelRef, fromType, toType) {
  if (!confirm(`Promote ${modelRef} from ${fromType} to ${toType}?`)) {
    return;
  }
  
  const response = await fetch(
    `${this._getSidecarUrl()}/api/local/models/${encodeURIComponent(modelRef)}/promote`,
    {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        from_entity_type: fromType,
        to_entity_type: toType
      })
    }
  );
  
  if (response.ok) {
    this._refreshModelList();
    this._showNotification(`Promoted to ${toType}`, 'success');
  } else {
    this._showNotification('Promotion failed', 'error');
  }
}
```

## Phase 2.2 Frontend: Membership Plumbing

Once Phase 2 (Projects/Collections) is complete, extend the above to support:
- Rendering Ideas/WGs inline in Project views (no separate section)
- Candidate state tracking for Ideas in evaluating Projects
- Multi-select + bulk "Add to Project" from Catalog grid

## Testing Checklist

- [ ] Create idea via "Add Idea" button
- [ ] Filter catalog by showing ideas (chip appears)
- [ ] Filter catalog by showing working groups (chip appears)
- [ ] Entity type badges show correctly on all entity types
- [ ] Promote Idea → Model works
- [ ] Promote Idea → Working Group works
- [ ] Promote Working Group → Model works
- [ ] Promoted entity updates card type immediately
- [ ] Default catalog view hides Ideas and Working Groups
- [ ] Toggle chips correctly filter the view

## Dependencies

- Backend migration #25 applied
- Sidecar promote endpoints live
- model-catalog-browser-card.js updated

## References

- [Catalog Redesign 2026-05](../../catalog-redesign-2026-05.md#59-entity-types)
- [Design Mockups](../../design/mockups/catalog-redesign-mockups.html)
