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


if __name__ == "__main__":
    unittest.main()