import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CARD_JS = ROOT / "homeassistant" / "www" / "3d_printing" / "model_catalog" / "model-catalog-browser-card.js"


class TestModelCatalogTagFilterUi(unittest.TestCase):
    def setUp(self):
        self.assertTrue(CARD_JS.exists(), f"Card JS not found: {CARD_JS}")
        self.card_content = CARD_JS.read_text(encoding="utf-8")

    def test_default_filters_include_multi_tag_state(self):
        self.assertIn("tags: []", self.card_content)

    def test_selected_filter_strip_is_rendered(self):
        self.assertIn("_renderSelectedFilterStrip()", self.card_content)
        self.assertIn('Selected filters', self.card_content)
        self.assertIn('data-action="clear-selected-tag"', self.card_content)
        self.assertIn('data-action="clear-collection-filter"', self.card_content)

    def test_search_request_sends_combined_tags(self):
        self.assertIn('var activeTags = this._activeTagFilters();', self.card_content)
        self.assertIn('tags: activeTags.join(",")', self.card_content)

    def test_left_nav_tags_toggle_additively(self):
        self.assertIn('var contextTags = this._activeTagFilters();', self.card_content)
        self.assertIn('contextTags = contextTags.concat([nextTag]);', self.card_content)
        self.assertIn('contextTags = contextTags.filter(function (value) {', self.card_content)

    def test_working_files_not_in_top_scope_pivot(self):
        self.assertIn('this._renderOptionToggle("models")', self.card_content)
        self.assertIn('this._renderOptionToggle("collections")', self.card_content)
        self.assertNotIn('this._renderOptionToggle("working")', self.card_content)
        self.assertIn('includeWorkingInModels = this._browserScope === "models"', self.card_content)

    def test_selected_left_nav_filters_show_remove_glyph(self):
        self.assertIn('left-nav-item-count dismiss', self.card_content)
        self.assertIn("if (isActive && isFacetFilterItem)", self.card_content)

    def test_collection_or_tag_filters_keep_all_models_quick_pivot_selected(self):
        self.assertIn('if (this._selectedCollectionKey() || this._activeTagFilters().length) {', self.card_content)
        self.assertIn('return "all-models";', self.card_content)

    def test_recent_pivots_use_real_filter_flags(self):
        self.assertIn('recent_added_only: false', self.card_content)
        self.assertIn('recent_printed_only: false', self.card_content)
        self.assertIn('this._filters.recent_added_only = contextRecentAdded;', self.card_content)
        self.assertIn('this._filters.recent_printed_only = contextRecentPrinted;', self.card_content)
        self.assertIn('recent_added_only: !!this._filters.recent_added_only,', self.card_content)
        self.assertIn('recent_printed_only: !!this._filters.recent_printed_only,', self.card_content)
        self.assertIn('this._filters.sort = "added";', self.card_content)
        self.assertIn('this._filters.sort = "recent";', self.card_content)

    def test_working_files_render_through_mixed_entry_pipeline(self):
        self.assertIn("_currentDisplayEntries()", self.card_content)
        self.assertIn("_renderCatalogEntryCard(entry)", self.card_content)
        self.assertIn("_buildMixedCatalogEntries(", self.card_content)
        self.assertIn("_sortMixedCatalogEntries(", self.card_content)

    def test_collapsed_left_nav_uses_section_triggers_for_facets(self):
        self.assertIn("_renderCollapsedFacetSectionTrigger(", self.card_content)
        self.assertIn('data-action="expand-left-nav-section"', self.card_content)
        self.assertIn("this._leftNavAutoCollapsePending = true;", self.card_content)

    def test_type_toggles_include_icons_and_section_separators(self):
        self.assertIn("_leftNavTypeIcon(typeKey)", self.card_content)
        self.assertIn('left-nav-type-icon', self.card_content)
        self.assertIn('.left-nav-section + .left-nav-section{padding-top:10px;border-top:1px solid rgba(148,163,184,0.14);}', self.card_content)

    def test_type_counts_use_server_aggregate(self):
        self.assertIn('var counts = { model: 0, idea: 0 };', self.card_content)
        self.assertIn('return this._serverEntityTypeCounts;', self.card_content)

    def test_sort_picker_uses_explicit_recent_labels(self):
        self.assertIn('<option value="added"', self.card_content)
        self.assertIn('>Recently added</option>', self.card_content)
        self.assertIn('>Recently printed</option>', self.card_content)

    def test_advanced_filters_menu_owns_secondary_toolbar_filters(self):
        self.assertIn('_renderAdvancedFiltersMenu()', self.card_content)
        self.assertIn('advanced-filter-menu', self.card_content)
        self.assertIn('Advanced</span>', self.card_content)
        self.assertIn('search-only-filter-row', self.card_content)

    def test_multi_select_bulk_delete_is_soft_delete_with_two_stage_confirmation(self):
        self.assertIn('data-action="bulk-delete-models"', self.card_content)
        self.assertIn('await this._bulkDeleteSelectedModels();', self.card_content)
        self.assertIn('window.confirm(confirmLines.join("\\n"))', self.card_content)
        self.assertIn('window.prompt("Type DELETE to remove "', self.card_content)
        self.assertIn('This moves them to Deleted. They are kept indefinitely until you restore or purge them.', self.card_content)
        self.assertIn('Stored model files/assets stay on disk unless you purge from Deleted.', self.card_content)

    def test_deleted_model_lifecycle_has_restore_and_purge_ui(self):
        self.assertIn('show_deleted: false', self.card_content)
        self.assertIn('data-action="toggle-show-deleted-filter"', self.card_content)
        self.assertIn('/api/local/deleted-models?', self.card_content)
        self.assertIn('data-action="bulk-restore-models"', self.card_content)
        self.assertIn('data-action="bulk-purge-models"', self.card_content)
        self.assertIn('/restore', self.card_content)
        self.assertIn('/purge', self.card_content)
        self.assertIn('window.prompt("Type PURGE to permanently delete "', self.card_content)


if __name__ == "__main__":
    unittest.main()