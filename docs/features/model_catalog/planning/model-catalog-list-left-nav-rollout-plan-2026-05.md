# Model Catalog List UI Left Navigation Rollout Plan (2026-05)

Status: Proposed for implementation
Owner: Model Catalog UI
Scope: Model Catalog List UI only (not workspace-level tab shell)
Related design docs:
- ../design/catalog-redesign-2026-05.md
- ../design/catalog-redesign-2026-05-updates.md
- ../design/mockups/catalog-redesign-mockups.html
- ../design/mockups/collections-and-projects-nav.html

## 1) Intended UX Outcome

Left navigation is the intended direction for the Model Catalog List UI.

Target information architecture:
- Left nav is the primary browse context (Favorites, Frequents, Recents, Projects, Collections, Tags).
- Top toolbar is for global actions and display controls (search, sort, view mode, create/import, refresh).
- Main content shows frequents rail plus model results for the active left-nav context.

Target interaction model:
- Selecting left-nav nodes pivots context.
- Toolbar controls refine and operate on the current context.
- Chips represent active filters, not long-term navigation hierarchy.

## 2) Top Toolbar vs Left Nav Responsibilities

### Left nav owns
- Favorites pivot
- Frequents pivot
- Recently added pivot
- Recently printed pivot
- Projects section (Active, Backlog, Completed collapsed)
- Collections section (tree in Phase 2)
- Tags section (quick shortcuts in Phase 1, expanded in Phase 2)

### Top toolbar owns
- Search
- Sort
- View mode
- Add Model / Add Idea / Import
- Refresh
- Pagination and density controls

### Control migration map

Move to left nav:
- Favorites only
- Frequents only
- Collection text filter (replace with collection nav selection)
- Tag text filter (replace with tag nav selection)
- Show ideas (move to entity-type section)

Remain in top toolbar:
- Search
- Sort
- View mode picker
- Create/import actions
- Refresh

Remove or de-emphasize as redundant:
- Segmented scope toggle once left nav is active and stable
- Always-visible Creator free-text field (phase to advanced/search syntax)
- Has other files as always-visible chip (move to Advanced filter popover)

Rationale:
- Left nav represents location in the catalog hierarchy.
- Toolbar represents actions and transient refinements against that location.
- This split improves discoverability and reduces top-row overload.

## 3) Layout Behavior and Responsiveness

### Desktop
- Two-column shell in the custom card:
  - Left nav fixed width (248-280px)
  - Main content flexible width
- Left nav default expanded
- Optional collapse to compact icon rail

### Tablet
- Left nav becomes a drawer
- Drawer toggle always visible near page title/search
- Active context shown in main header

### Mobile
- Left nav drawer/overlay only
- Primary row includes nav toggle + active context + search
- Secondary filter chips become horizontal scroller

### Home Assistant main sidebar behavior
- Keep user-controlled.
- Do not auto-collapse the HA main sidebar from this card.

### Accessibility and discoverability
- Nav toggle uses aria-expanded and clear aria-label
- Tree sections support keyboard navigation
- Active node has persistent visual state
- Focus management on open/close and context pivot
- Browse toggle remains visible on tablet/mobile

## 4) Dependency and Roadmap Sequencing

Recommendation: implement left nav now in a constrained Phase 1, then deepen in Phase 2.

### Phase 1 (safe to ship now)
- Introduce left-nav shell and state model
- Add quick pivots (Favorites/Frequents/Recent Added/Recent Printed)
- Add basic Projects list (flat)
- Add tag shortcuts (lightweight)
- Keep existing chips as compatibility bridge
- Keep search/sort/view in top toolbar

### Phase 2 (depends on Collections/Projects maturity)
- Add full Collections tree navigation
- Add richer Project lifecycle sections and counts
- Add advanced tag/facet behavior
- Remove redundant top controls permanently

### Risks if too early
- Incorrect counts if nav is derived from page-local data
- Temporary collection behavior may churn without stable tree API
- User confusion if old and new navigation are both primary

### Risks if waiting too long
- Toolbar complexity remains high
- IA divergence from design docs/mockups increases
- Larger migration blast radius later

## 5) Concrete Implementation Plan

## Files likely to change (Phase 1)
- homeassistant/www/3d_printing/model_catalog/model-catalog-browser-card.js
- homeassistant/packages/3d_printing/model_catalog/rest_commands/model_catalog_list_projects.yaml (validate usage and payload assumptions)
- homeassistant/packages/3d_printing/common/dashboards/_resources.yaml (version bump required when JS changes)

Optional/possible (Phase 2):
- sidecars/model_catalog/app/routers/models.py (facets/tree endpoints)
- sidecars/model_catalog/app/routers/working.py (project/facet enrichments)
- homeassistant/packages/3d_printing/model_catalog/rest_commands/*.yaml (new tree/facet commands)

### Data/state changes needed
- New UI state:
  - nav_selected_key
  - nav_collapsed (desktop)
  - nav_drawer_open (tablet/mobile)
  - nav_data cache (quick pivots/projects/tags)
- Persistable preference (phase 1.5 or phase 2):
  - nav collapse state
  - frequents rail visibility state

### Migration strategy (avoid churn)
- Introduce left nav behind an internal config switch in the card
- Keep legacy chips during transition as compatibility bridge
- De-emphasize moved controls before removing them
- Remove segmented scope toggle only after stabilization cycle

### Acceptance criteria by phase

Phase 1 acceptance:
- Desktop shows stable left nav + main content layout
- Tablet/mobile nav drawer is discoverable and accessible
- Search/sort/view/actions continue to work without regressions
- Projects section loads and pivots results context
- Legacy controls still available where required for compatibility

Phase 2 acceptance:
- Collections tree and project sections are complete with accurate counts
- Redundant toolbar controls removed
- Context pivots remain stable across pagination/refresh
- Keyboard and screen-reader behavior validated for nav tree/drawer

## 6) Decision Summary (Recommended Path)

Go now with scoped left-nav foundation.

Implement first:
- Left-nav skeleton and context pivots
- Toolbar simplification to global controls
- Compatibility bridge for legacy chips

Defer:
- Full Collections tree and advanced project drilldowns
- Hard removal of all moved controls until phase 2 stabilization

---

## GitHub Issue Pack (12 prefilled links)

Use these links to create prefilled issues in this repository.

1. Phase 1 left-nav shell and layout
- https://github.com/rsocko/hass-bambulab-config/issues/new?title=Model%20Catalog%20List%20UI%3A%20Phase%201%20left-nav%20shell%20and%20layout&body=%23%20Summary%0AImplement%20the%20left-navigation%20shell%20for%20Model%20Catalog%20List%20UI%20with%20desktop%20split-layout%20and%20responsive%20drawer%20modes.%0A%0A%23%23%20Scope%0A-%20Add%20left-nav%20container%20and%20main-content%20container%20in%20model-catalog-browser-card%0A-%20Add%20state%20for%20nav%20selection%2C%20collapse%2C%20and%20drawer%20open%0A-%20Render%20placeholder%20sections%20for%20quick%20pivots%2C%20projects%2C%20and%20tags%0A%0A%23%23%20Files%0A-%20homeassistant%2Fwww%2F3d_printing%2Fmodel_catalog%2Fmodel-catalog-browser-card.js%0A%0A%23%23%20Acceptance%20Criteria%0A-%20Desktop%20renders%20left-nav%20and%20main%20content%20with%20stable%20layout%0A-%20Tablet%2Fmobile%20switch%20to%20drawer%20navigation%0A-%20No%20regression%20to%20existing%20results%20rendering%20or%20pagination%0A%0A%23%23%20References%0A-%20docs%2Ffeatures%2Fmodel_catalog%2Fplanning%2Fmodel-catalog-list-left-nav-rollout-plan-2026-05.md

2. Control migration map implementation
- https://github.com/rsocko/hass-bambulab-config/issues/new?title=Model%20Catalog%20List%20UI%3A%20migrate%20top%20controls%20to%20left-nav%20contexts&body=%23%20Summary%0AImplement%20control%20responsibility%20split%20by%20moving%20context%20pivots%20to%20left-nav%20and%20keeping%20global%20actions%20in%20top%20toolbar.%0A%0A%23%23%20Move%20to%20left-nav%0A-%20Favorites%20only%0A-%20Frequents%20only%0A-%20Collection%20filter%20(from%20text%20input%20to%20nav%20selection)%0A-%20Tag%20filter%20(from%20text%20input%20to%20nav%20selection)%0A-%20Show%20ideas%20(entity-type%20section)%0A%0A%23%23%20Keep%20in%20toolbar%0A-%20Search%2C%20Sort%2C%20View%20mode%2C%20Create%2FImport%2C%20Refresh%0A%0A%23%23%20Acceptance%20Criteria%0A-%20Migrated%20controls%20work%20through%20left-nav%20state%0A-%20Toolbar%20retains%20only%20global%20controls%0A-%20Compatibility%20fallback%20exists%20during%20transition%0A%0A%23%23%20References%0A-%20docs%2Ffeatures%2Fmodel_catalog%2Fplanning%2Fmodel-catalog-list-left-nav-rollout-plan-2026-05.md

3. Responsive nav drawer + behavior
- https://github.com/rsocko/hass-bambulab-config/issues/new?title=Model%20Catalog%20List%20UI%3A%20responsive%20left-nav%20drawer%20%28tablet%2Fmobile%29&body=%23%20Summary%0AAdd%20responsive%20behavior%20for%20left-nav%20as%20a%20drawer%20on%20tablet%2Fmobile%20with%20clear%20toggle%20and%20active-context%20display.%0A%0A%23%23%20Scope%0A-%20Desktop%3A%20persistent%20left-nav%20%28collapsible%29%0A-%20Tablet%3A%20drawer%20mode%20with%20visible%20toggle%0A-%20Mobile%3A%20drawer%2Foverlay%20mode%20with%20compact%20header%0A%0A%23%23%20Acceptance%20Criteria%0A-%20Toggle%20present%20and%20operational%20on%20tablet%2Fmobile%0A-%20Drawer%20can%20open%2Fclose%20without%20layout%20jank%0A-%20Main%20content%20remains%20fully%20usable%20across%20breakpoints%0A%0A%23%23%20References%0A-%20docs%2Ffeatures%2Fmodel_catalog%2Fplanning%2Fmodel-catalog-list-left-nav-rollout-plan-2026-05.md

4. Accessibility and keyboard navigation
- https://github.com/rsocko/hass-bambulab-config/issues/new?title=Model%20Catalog%20List%20UI%3A%20left-nav%20accessibility%20and%20keyboard%20support&body=%23%20Summary%0AImplement%20accessibility%20for%20left-nav%20including%20aria%20labels%2C%20aria-expanded%2C%20active%20state%20announcements%2C%20and%20keyboard%20navigation.%0A%0A%23%23%20Scope%0A-%20Nav%20toggle%20ARIA%20%28label%2C%20expanded%29%0A-%20Keyboard%20navigation%20for%20nav%20sections%20and%20tree%20nodes%0A-%20Focus%20management%20on%20drawer%20open%2Fclose%20and%20pivot%0A-%20Visible%20active-node%20indication%0A%0A%23%23%20Acceptance%20Criteria%0A-%20Keyboard-only%20navigation%20is%20practical%0A-%20Focus%20is%20not%20lost%20during%20mode%20changes%0A-%20No%20critical%20accessibility%20regressions%20in%20card%20controls%0A%0A%23%23%20References%0A-%20docs%2Ffeatures%2Fmodel_catalog%2Fplanning%2Fmodel-catalog-list-left-nav-rollout-plan-2026-05.md

5. Projects section data wiring
- https://github.com/rsocko/hass-bambulab-config/issues/new?title=Model%20Catalog%20List%20UI%3A%20wire%20Projects%20section%20in%20left-nav&body=%23%20Summary%0AWire%20the%20left-nav%20Projects%20section%20using%20existing%20sidecar%20projects%20API%20through%20HA%20rest_command.%0A%0A%23%23%20Scope%0A-%20Use%20model_catalog_list_projects%20for%20project%20list%20loading%0A-%20Render%20flat%20project%20list%20for%20Phase%201%0A-%20Allow%20project%20selection%20to%20pivot%20results%20context%0A%0A%23%23%20Files%0A-%20homeassistant%2Fwww%2F3d_printing%2Fmodel_catalog%2Fmodel-catalog-browser-card.js%0A-%20homeassistant%2Fpackages%2F3d_printing%2Fmodel_catalog%2Frest_commands%2Fmodel_catalog_list_projects.yaml%20%28verify%20contract%29%0A%0A%23%23%20Acceptance%20Criteria%0A-%20Projects%20load%20and%20display%20in%20left-nav%0A-%20Project%20click%20updates%20active%20context%20and%20results%0A-%20Error%2Fempty%20states%20are%20handled%20cleanly%0A%0A%23%23%20References%0A-%20docs%2Ffeatures%2Fmodel_catalog%2Fplanning%2Fmodel-catalog-list-left-nav-rollout-plan-2026-05.md

6. Temporary compatibility bridge
- https://github.com/rsocko/hass-bambulab-config/issues/new?title=Model%20Catalog%20List%20UI%3A%20legacy-control%20compatibility%20bridge%20during%20nav%20migration&body=%23%20Summary%0AProvide%20a%20compatibility%20bridge%20so%20legacy%20chips%2Fcontrols%20remain%20usable%20while%20new%20left-nav%20flows%20are%20introduced.%0A%0A%23%23%20Scope%0A-%20Keep%20legacy%20chips%20temporarily%20where%20needed%0A-%20Sync%20legacy%20actions%20to%20new%20left-nav%20state%0A-%20Add%20de-emphasis%20styling%20to%20legacy%20controls%20after%20new%20flow%20is%20stable%0A%0A%23%23%20Acceptance%20Criteria%0A-%20No%20functional%20loss%20for%20existing%20operators%0A-%20State%20remains%20consistent%20between%20legacy%20and%20new%20controls%0A-%20Migration%20can%20be%20completed%20without%20UI%20churn%0A%0A%23%23%20References%0A-%20docs%2Ffeatures%2Fmodel_catalog%2Fplanning%2Fmodel-catalog-list-left-nav-rollout-plan-2026-05.md

7. Remove segmented scope toggle after stabilization
- https://github.com/rsocko/hass-bambulab-config/issues/new?title=Model%20Catalog%20List%20UI%3A%20retire%20segmented%20scope%20toggle%20after%20left-nav%20stabilization&body=%23%20Summary%0ARemove%20the%20top%20segmented%20scope%20toggle%20once%20left-nav%20is%20the%20primary%20and%20stable%20navigation%20surface.%0A%0A%23%23%20Scope%0A-%20Delete%20or%20hide%20the%20segmented%20scope%20toggle%20for%20Models%2FCollections%2FWorking%0A-%20Ensure%20equivalent%20pivots%20exist%20through%20left-nav%20and%20workspace-level%20shell%0A-%20Update%20UI%20copy%20and%20help%20text%0A%0A%23%23%20Acceptance%20Criteria%0A-%20No%20duplicate%20navigation%20surfaces%20for%20the%20same%20context%0A-%20Navigation%20to%20all%20supported%20contexts%20still%20works%0A-%20No%20regressions%20in%20working%20or%20collections%20flows%0A%0A%23%23%20References%0A-%20docs%2Ffeatures%2Fmodel_catalog%2Fplanning%2Fmodel-catalog-list-left-nav-rollout-plan-2026-05.md

8. Collections tree API and contract (Phase 2 backend)
- https://github.com/rsocko/hass-bambulab-config/issues/new?title=Model%20Catalog%20Phase%202%3A%20add%20Collections%20tree%2Ffacet%20API%20for%20left-nav&body=%23%20Summary%0AAdd%20backend%20support%20for%20Collections%20tree%20and%20faceted%20counts%20required%20by%20left-nav%20Phase%202.%0A%0A%23%23%20Scope%0A-%20Define%20and%20implement%20collections%20tree%20endpoint%28s%29%0A-%20Return%20stable%20counts%20for%20nodes%20and%20optionally%20visibility%20scopes%0A-%20Document%20response%20shape%20and%20pagination%2Fcaching%20rules%0A%0A%23%23%20Likely%20files%0A-%20sidecars%2Fmodel_catalog%2Fapp%2Frouters%2Fmodels.py%0A-%20sidecars%2Fmodel_catalog%2Fapp%2Fservices%2F%2A%20%28as%20needed%29%0A%0A%23%23%20Acceptance%20Criteria%0A-%20Collections%20tree%20API%20is%20stable%20and%20documented%0A-%20Counts%20are%20consistent%20with%20search%20results%20contract%0A-%20Performance%20is%20acceptable%20for%20left-nav%20interactive%20use%0A%0A%23%23%20References%0A-%20docs%2Ffeatures%2Fmodel_catalog%2Fplanning%2Fmodel-catalog-list-left-nav-rollout-plan-2026-05.md

9. HA rest_commands for new tree/facet endpoints
- https://github.com/rsocko/hass-bambulab-config/issues/new?title=Model%20Catalog%20Phase%202%3A%20add%20HA%20rest_commands%20for%20Collections%20tree%20and%20tag%20facets&body=%23%20Summary%0AExpose%20new%20sidecar%20Collections%20tree%20and%20tag%20facet%20endpoints%20through%20Home%20Assistant%20rest_command%20wrappers.%0A%0A%23%23%20Scope%0A-%20Add%20new%20rest_command%20YAML%20definitions%0A-%20Align%20templating%20with%20existing%20model_catalog%20command%20patterns%0A-%20Validate%20query%20parameter%20passthrough%20and%20defaults%0A%0A%23%23%20Files%0A-%20homeassistant%2Fpackages%2F3d_printing%2Fmodel_catalog%2Frest_commands%2F%2A.yaml%0A%0A%23%23%20Acceptance%20Criteria%0A-%20Commands%20are%20available%20and%20return%20expected%20payload%20shapes%0A-%20Error%20handling%20is%20consistent%20with%20existing%20commands%0A-%20No%20regression%20to%20existing%20rest_command%20workflows%0A%0A%23%23%20References%0A-%20docs%2Ffeatures%2Fmodel_catalog%2Fplanning%2Fmodel-catalog-list-left-nav-rollout-plan-2026-05.md

10. Phase 2 toolbar cleanup and redundancy removal
- https://github.com/rsocko/hass-bambulab-config/issues/new?title=Model%20Catalog%20Phase%202%3A%20finalize%20toolbar%20cleanup%20and%20remove%20redundant%20filters&body=%23%20Summary%0AComplete%20toolbar%20cleanup%20after%20left-nav%20and%20backend%20facets%20are%20stable%2C%20removing%20redundant%20top-row%20filters.%0A%0A%23%23%20Scope%0A-%20Remove%20redundant%20collection%2Ftag%2Ffavorites%2Ffrequents%20top%20filters%0A-%20Move%20rare%20controls%20%28for%20example%20Has%20other%20files%29%20to%20Advanced%20filter%20popover%0A-%20Keep%20toolbar%20focused%20on%20search%2C%20sort%2C%20view%2C%20actions%0A%0A%23%23%20Acceptance%20Criteria%0A-%20Toolbar%20is%20visibly%20simpler%20without%20functional%20loss%0A-%20All%20removed%20controls%20have%20equivalent%20left-nav%20or%20advanced%20paths%0A-%20Regression%20tests%20pass%20for%20core%20browse%20workflows%0A%0A%23%23%20References%0A-%20docs%2Ffeatures%2Fmodel_catalog%2Fplanning%2Fmodel-catalog-list-left-nav-rollout-plan-2026-05.md

11. Docs and mockup alignment with shipped IA
- https://github.com/rsocko/hass-bambulab-config/issues/new?title=Model%20Catalog%20docs%3A%20align%20redesign%20docs%20and%20mockups%20to%20shipped%20left-nav%20IA&body=%23%20Summary%0AUpdate%20design%20docs%20and%20mockups%20so%20they%20match%20the%20implemented%20left-nav%20IA%2C%20responsiveness%2C%20and%20control%20ownership.%0A%0A%23%23%20Scope%0A-%20Update%20catalog-redesign-2026-05.md%20with%20final%20control%20mapping%0A-%20Update%20catalog-redesign-2026-05-updates.md%20for%20implementation%20status%0A-%20Update%20mockups%20for%20left-nav%20behavior%20and%20toolbar%20separation%0A-%20Add%20or%20update%20planning%20cross-links%0A%0A%23%23%20Acceptance%20Criteria%0A-%20No%20major%20discrepancies%20between%20docs%2C%20mockups%2C%20and%20shipped%20UI%0A-%20Planning%20doc%20and%20issue%20tracking%20references%20are%20consistent%0A%0A%23%23%20References%0A-%20docs%2Ffeatures%2Fmodel_catalog%2Fplanning%2Fmodel-catalog-list-left-nav-rollout-plan-2026-05.md

12. Resource version bump + validation checklist
- https://github.com/rsocko/hass-bambulab-config/issues/new?title=Model%20Catalog%20UI%20release%3A%20resource%20cache-bust%20version%20bump%20and%20validation&body=%23%20Summary%0AEnsure%20all%20Model%20Catalog%20JS%20changes%20include%20resource%20version%20bump%20and%20validation%20before%20sync%2Fdeploy.%0A%0A%23%23%20Scope%0A-%20Increment%20model-catalog-browser-card.js%20resource%20version%20in%20_resources.yaml%0A-%20Run%20Lovelace%20resource%20cache-bust%20validation%20task%0A-%20Capture%20validation%20notes%20for%20desktop%2Ftablet%2Fmobile%20smoke%20checks%0A%0A%23%23%20Files%0A-%20homeassistant%2Fpackages%2F3d_printing%2Fcommon%2Fdashboards%2F_resources.yaml%0A%0A%23%23%20Acceptance%20Criteria%0A-%20Resource%20manifest%20reflects%20updated%20version%20for%20changed%20JS%0A-%20Validate%20Before%20Sync%20task%20passes%0A-%20Post-deploy%20hard-refresh%20guidance%20is%20recorded%0A%0A%23%23%20References%0A-%20docs%2Ffeatures%2Fmodel_catalog%2Fplanning%2Fmodel-catalog-list-left-nav-rollout-plan-2026-05.md
