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
        self.assertNotIn("record && record.thumbnail_url", self.card_content)
        self.assertIn("makerworld-profile-head' + (previewUrl ? '' : ' no-preview')", self.card_content)

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
