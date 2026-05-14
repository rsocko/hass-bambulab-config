import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CARD_JS = ROOT / "homeassistant" / "www" / "3d_printing" / "model_catalog" / "model-catalog-browser-card.js"


class TestModelCatalogQueueQuickActions(unittest.TestCase):
    def setUp(self):
        self.assertTrue(CARD_JS.exists(), f"Card JS not found: {CARD_JS}")
        self.card_content = CARD_JS.read_text(encoding="utf-8")

        queue_card = ROOT / "homeassistant" / "www" / "3d_printing" / "print_queue" / "unified-queue-board-card.js"
        self.assertTrue(queue_card.exists(), f"Queue card JS not found: {queue_card}")
        self.queue_card_content = queue_card.read_text(encoding="utf-8")

    def test_quick_add_creates_backlog_entry(self):
        self.assertIn('if (action === "queue-add") {', self.card_content)
        self.assertIn('await this._addUnifiedQueueEntryForModel(modelRef, { state: "backlog" });', self.card_content)

    def test_quick_action_uses_dedicated_queue_add_action(self):
        # Quick button always shows Add to backlog (never toggles to dequeue)
        self.assertIn("var queueButton = ''", self.card_content)
        self.assertIn("data-action=\"queue-add\"", self.card_content)
        self.assertNotIn("queueButtonQueued ? 'queue-clear' : 'queue-add'", self.card_content)
        self.assertIn("Add to backlog", self.card_content)

    def test_both_cards_import_shared_queue_add_helper(self):
        self.assertIn("import { addUnifiedQueueEntry } from '../common/unified-queue-api-client.js?v=1';", self.card_content)
        self.assertIn("import { addUnifiedQueueEntry } from '../common/unified-queue-api-client.js?v=1';", self.queue_card_content)

    def test_queue_button_shows_count_badge(self):
        # Queue button renders count badge when entries exist
        self.assertIn("var queueEntryCount = queueStateInfo && queueStateInfo.count", self.card_content)
        self.assertIn('<span class="queue-count-badge">', self.card_content)

    def test_re_add_button_in_advanced_menu(self):
        # Re-add button added to advanced menu for manual re-queuing
        self.assertIn('data-action="queue-re-add"', self.card_content)
        self.assertIn('>Re-add<', self.card_content)

    def test_queue_add_shows_confirmation_on_duplicate(self):
        # Confirm dialog when adding same model >1 time
        self.assertIn('This model already has', self.card_content)
        self.assertIn('queue entr', self.card_content)


if __name__ == "__main__":
    unittest.main()