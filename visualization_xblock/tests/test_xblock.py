"""Tests for VisualizationXBlock (crafter-backed)."""

import json
import unittest
from unittest.mock import MagicMock, patch

from web_fragments.fragment import Fragment
from xblock.fields import ScopeIds
from xblock.test.toy_runtime import ToyRuntime

from visualization import VisualizationXBlock
from visualization.crafter_client import (
    CrafterError,
    CrafterNotConfiguredError,
    CrafterNotInstalledError,
)


SIMULATION_HTML = "<!DOCTYPE html><html><body><h1>sim</h1></body></html>"


FAKE_COURSE_ID = "course-v1:edx+1+1"
FAKE_BLOCK_ID = "block-v1:edx+1+1+type@visualization+block@abc"


class VisualizationTestBase(unittest.TestCase):
    def setUp(self):
        self.runtime = ToyRuntime()
        self.scope_ids = ScopeIds(
            user_id="test_user",
            block_type="visualization",
            def_id="def_id",
            usage_id="usage_id",
        )
        self.mock_user = MagicMock(name="django_user")

    def _make_block(self):
        block = VisualizationXBlock(self.runtime, scope_ids=self.scope_ids)
        # ToyRuntime doesn't supply real usage keys / user services; stub ours.
        block._current_user = lambda: self.mock_user
        block._course_id = lambda: FAKE_COURSE_ID
        block._block_id = lambda: FAKE_BLOCK_ID
        return block

    def _call_handler(self, block, handler_name, data):
        request = MagicMock()
        request.method = "POST"
        request.body = json.dumps(data).encode("utf-8")
        response = getattr(block, handler_name)(request)
        return json.loads(response.body)


class TestSaveSettings(VisualizationTestBase):
    def test_save_settings_updates_display_name(self):
        block = self._make_block()
        resp = self._call_handler(block, "save_settings", {"display_name": "Orbits"})
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(block.display_name, "Orbits")


class TestSendMessage(VisualizationTestBase):
    @patch("visualization.xblock.crafter_client.generate_visualization_html")
    def test_send_message_happy_path(self, mock_gen):
        mock_gen.return_value = SIMULATION_HTML
        block = self._make_block()
        resp = self._call_handler(block, "send_message", {"prompt": "Orbit sim"})
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(resp["html"], SIMULATION_HTML)
        self.assertEqual(block.generation_status, "idle")
        # send_message does NOT auto-apply
        self.assertEqual(block.cached_html, "")
        mock_gen.assert_called_once_with(
            course_id=FAKE_COURSE_ID,
            block_id=FAKE_BLOCK_ID,
            prompt="Orbit sim",
            user=self.mock_user,
            current_content="",
        )

    def test_send_message_rejects_empty_prompt(self):
        block = self._make_block()
        resp = self._call_handler(block, "send_message", {"prompt": "   "})
        self.assertEqual(resp["status"], "error")

    @patch("visualization.xblock.crafter_client.generate_visualization_html")
    def test_send_message_reports_not_configured(self, mock_gen):
        mock_gen.side_effect = CrafterNotConfiguredError("no creator for course")
        block = self._make_block()
        resp = self._call_handler(block, "send_message", {"prompt": "x"})
        self.assertEqual(resp["status"], "error")
        self.assertEqual(resp["code"], "crafter_not_configured")
        self.assertEqual(block.generation_status, "error")
        self.assertIn("no creator", block.last_error)

    @patch("visualization.xblock.crafter_client.generate_visualization_html")
    def test_send_message_reports_not_installed(self, mock_gen):
        mock_gen.side_effect = CrafterNotInstalledError("crafter missing")
        block = self._make_block()
        resp = self._call_handler(block, "send_message", {"prompt": "x"})
        self.assertEqual(resp["code"], "crafter_not_installed")

    @patch("visualization.xblock.crafter_client.generate_visualization_html")
    def test_send_message_reports_generic_error(self, mock_gen):
        mock_gen.side_effect = ValueError("API timeout")
        block = self._make_block()
        resp = self._call_handler(block, "send_message", {"prompt": "x"})
        self.assertEqual(resp["status"], "error")
        self.assertEqual(resp["message"], "API timeout")
        self.assertEqual(block.generation_status, "error")


class TestApplyMessage(VisualizationTestBase):
    def test_apply_message_updates_cached_html(self):
        block = self._make_block()
        resp = self._call_handler(block, "apply_message", {
            "html": SIMULATION_HTML,
            "prompt": "Orbit sim",
        })
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(block.cached_html, SIMULATION_HTML)
        self.assertEqual(block.prompt, "Orbit sim")
        self.assertIsNotNone(block.generated_at)

    def test_apply_message_rejects_empty_payload(self):
        block = self._make_block()
        resp = self._call_handler(block, "apply_message", {"html": ""})
        self.assertEqual(resp["status"], "error")


class TestChatHistory(VisualizationTestBase):
    @patch("visualization.xblock.crafter_client.get_chat_messages")
    def test_get_chat_history_returns_messages(self, mock_get):
        mock_get.return_value = [
            {"role": "user", "content": "hi", "created_at": "2026-01-01T00:00:00+00:00"},
        ]
        block = self._make_block()
        resp = self._call_handler(block, "get_chat_history", {})
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(len(resp["messages"]), 1)
        mock_get.assert_called_once_with(FAKE_BLOCK_ID, self.mock_user)

    @patch("visualization.xblock.crafter_client.clear_chat")
    def test_clear_chat_history(self, mock_clear):
        mock_clear.return_value = 3
        block = self._make_block()
        resp = self._call_handler(block, "clear_chat_history", {})
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(resp["deleted"], 3)


class TestViews(VisualizationTestBase):
    def test_student_view_without_html_shows_placeholder(self):
        block = self._make_block()
        frag = block.student_view()
        self.assertIsInstance(frag, Fragment)
        self.assertIn("not been generated", frag.content)
        self.assertNotIn("<iframe", frag.content)

    def test_student_view_renders_iframe_with_srcdoc(self):
        block = self._make_block()
        block.cached_html = SIMULATION_HTML
        frag = block.student_view()
        self.assertIn('sandbox="allow-scripts"', frag.content)
        self.assertIn("srcdoc=", frag.content)
        self.assertNotIn(SIMULATION_HTML, frag.content)  # escaped

    def test_studio_view_has_chat_scaffolding(self):
        block = self._make_block()
        frag = block.studio_view()
        self.assertIn("AI Content Assistant", frag.content)
        self.assertIn("visualization-messages", frag.content)
        self.assertIn("visualization-clear-history", frag.content)
        self.assertIn("visualization-send", frag.content)


if __name__ == "__main__":
    unittest.main()
