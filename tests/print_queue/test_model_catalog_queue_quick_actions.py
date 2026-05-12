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
        self.assertIn("var queueButtonQueued = !!(queueStateInfo && this._isUnifiedQueueActiveState(queueStateInfo.state));", self.card_content)
        self.assertIn("queueButtonQueued ? 'queue-clear' : 'queue-add'", self.card_content)
        self.assertIn("queueButtonQueued ? 'Dequeue' : 'Add to backlog'", self.card_content)

    def test_both_cards_import_shared_queue_add_helper(self):
        self.assertIn("import { addUnifiedQueueEntry } from '../common/unified-queue-api-client.js?v=1';", self.card_content)
        self.assertIn("import { addUnifiedQueueEntry } from '../common/unified-queue-api-client.js?v=1';", self.queue_card_content)


if __name__ == "__main__":
    unittest.main()