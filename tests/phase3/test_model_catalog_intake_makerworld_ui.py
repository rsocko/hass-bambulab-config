import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CARD_JS = ROOT / "homeassistant" / "www" / "3d_printing" / "model_catalog" / "model-catalog-intake-home-card.js"


class TestModelCatalogIntakeMakerWorldUi(unittest.TestCase):
    def setUp(self):
        self.assertTrue(CARD_JS.exists(), f"Card JS not found: {CARD_JS}")
        self.card_content = CARD_JS.read_text(encoding="utf-8")

    def test_profile_markup_uses_safe_render_helper(self):
        self.assertIn("_makerworldProfileCardsMarkup(fileManifest, selectedInstanceIds, instanceDetailsById, record, snapshot)", self.card_content)
        self.assertIn("var profileCardsResult = this._makerworldProfileCardsMarkup(", self.card_content)
        self.assertIn("var profileRenderError = profileCardsResult.error;", self.card_content)

    def test_profile_preview_does_not_fallback_to_design_thumbnail(self):
        self.assertIn("_makerworldProfilePreviewUrl(entry, details, modelInfo)", self.card_content)
        helper_start = self.card_content.index("_makerworldProfilePreviewUrl(entry, details, modelInfo) {")
        helper_end = self.card_content.index("_renderMakerWorldTagEditor()", helper_start)
        helper_body = self.card_content[helper_start:helper_end]
        self.assertNotIn("record && record.thumbnail_url", helper_body)
        self.assertIn("makerworld-profile-head' + (previewUrl ? '' : ' no-preview')", self.card_content)
        self.assertIn("This profile does not expose a distinct preview image.", self.card_content)
        self.assertIn("makerworld-profile-thumb-placeholder", self.card_content)

    def test_designer_chip_uses_broader_identity_resolution(self):
        self.assertIn("_makerworldUserIdentity(", self.card_content)
        self.assertIn("snapshot.designCreator,", self.card_content)
        self.assertIn("modelInfo.creator,", self.card_content)
        self.assertIn('makerworld-designer-badge', self.card_content)

    def test_profile_cards_use_metric_row_icons_and_hide_profile_owner_ids(self):
        self.assertIn("_makerworldProfileMetricMarkup('time', 'Print time', predictionLabel)", self.card_content)
        self.assertIn("_makerworldProfileMetricMarkup('plates', 'Plates'", self.card_content)
        self.assertIn("_makerworldProfileMetricMarkup('prints', 'Prints'", self.card_content)
        self.assertIn('makerworld-metric-row', self.card_content)
        self.assertNotIn('Profile user #', self.card_content)
        self.assertNotIn("<span class=\"chip\">' + escapeHtml(entry.is_default ? 'Default' : 'Profile') + '</span>'", self.card_content)

    def test_tag_draft_input_does_not_rerender_on_each_keystroke(self):
        self.assertIn("if (action === 'makerworld-tag-draft') {\n      this._makerworldTagDraft = String(target.value || '');\n      return;", self.card_content)
        self.assertIn("<button class=\"add-chip\" type=\"button\" data-action=\"add-makerworld-tag\">+ Tag</button>", self.card_content)

    def test_profile_render_failures_show_inline_status_error(self):
        self.assertIn(
            "Some MakerWorld profile details could not be rendered from this capture. You can continue with metadata import, or capture metadata again.",
            self.card_content,
        )
        self.assertIn(
            "(profileRenderError ? '<div class=\"status error\">' + escapeHtml(profileRenderError) + '</div>' : '')",
            self.card_content,
        )

    def test_link_only_fallback_is_presented_as_retryable_degraded_state(self):
        self.assertIn("var linkOnlyFallback = captureMode === 'link_only';", self.card_content)
        self.assertIn(
            "Metadata capture was unavailable, so this URL was saved as a link-only fallback. Retry Capture Metadata after fixing MakerWorld auth or API availability.",
            self.card_content,
        )
        self.assertIn(
            "No MakerWorld metadata or downloadable profile manifest is attached yet. Keep this saved URL as provenance-only, or retry metadata capture later.",
            self.card_content,
        )


if __name__ == "__main__":
    unittest.main()
