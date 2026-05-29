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

    def test_profile_render_failures_show_inline_status_error(self):
        self.assertIn(
            "Some MakerWorld profile details could not be rendered from this capture. You can continue with metadata import, or capture metadata again.",
            self.card_content,
        )
        self.assertIn(
            "(profileRenderError ? '<div class=\"status error\">' + escapeHtml(profileRenderError) + '</div>' : '')",
            self.card_content,
        )


if __name__ == "__main__":
    unittest.main()
