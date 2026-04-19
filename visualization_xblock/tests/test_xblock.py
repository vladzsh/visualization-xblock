"""Tests for VisualizationXBlock."""

import json
import unittest
from unittest.mock import MagicMock

from web_fragments.fragment import Fragment
from xblock.fields import ScopeIds
from xblock.test.toy_runtime import ToyRuntime

from visualization import VisualizationXBlock


SIMULATION_HTML = "<!DOCTYPE html><html><body><h1>sim</h1></body></html>"


class VisualizationTestBase(unittest.TestCase):
    def setUp(self):
        self.runtime = ToyRuntime()
        self.scope_ids = ScopeIds(
            user_id="test_user",
            block_type="visualization",
            def_id="def_id",
            usage_id="usage_id",
        )

    def _make_block(self):
        block = VisualizationXBlock(self.runtime, scope_ids=self.scope_ids)
        # ToyRuntime has no real opaque keys — stub the helpers.
        block._course_id = lambda: "course-v1:edx+1+1"
        block._block_id = lambda: "block-v1:edx+1+1+type@visualization+block@abc"
        block._sequential_id = lambda: "block-v1:edx+1+1+type@sequential+block@seq"
        return block

    def _call_handler(self, block, handler_name, data):
        request = MagicMock()
        request.method = "POST"
        request.body = json.dumps(data).encode("utf-8")
        response = getattr(block, handler_name)(request)
        return json.loads(response.body)


class TestSaveSettings(VisualizationTestBase):
    def test_updates_display_name(self):
        block = self._make_block()
        resp = self._call_handler(block, "save_settings", {"display_name": "Orbits"})
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(block.display_name, "Orbits")


class TestSaveAppliedHtml(VisualizationTestBase):
    def test_persists_html_and_timestamp(self):
        block = self._make_block()
        resp = self._call_handler(block, "save_applied_html", {
            "html": SIMULATION_HTML,
            "prompt": "Orbit sim",
        })
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(block.cached_html, SIMULATION_HTML)
        self.assertEqual(block.prompt, "Orbit sim")
        self.assertIsNotNone(block.generated_at)
        self.assertIn("generated_at", resp)

    def test_rejects_empty_payload(self):
        block = self._make_block()
        resp = self._call_handler(block, "save_applied_html", {"html": ""})
        self.assertEqual(resp["status"], "error")


class TestViews(VisualizationTestBase):
    def test_student_view_placeholder_when_empty(self):
        block = self._make_block()
        frag = block.student_view()
        self.assertIsInstance(frag, Fragment)
        self.assertIn("not been generated", frag.content)
        self.assertNotIn("<iframe", frag.content)

    def test_student_view_renders_sandboxed_iframe(self):
        block = self._make_block()
        block.cached_html = SIMULATION_HTML
        frag = block.student_view()
        self.assertIn('sandbox="allow-scripts"', frag.content)
        self.assertIn("srcdoc=", frag.content)
        self.assertNotIn(SIMULATION_HTML, frag.content)  # escaped

    def test_studio_view_carries_data_attrs_and_chat_scaffold(self):
        block = self._make_block()
        frag = block.studio_view()
        self.assertIn("AI Content Assistant", frag.content)
        self.assertIn("visualization-messages", frag.content)
        self.assertIn("visualization-clear-history", frag.content)
        self.assertIn("visualization-send", frag.content)
        self.assertIn('data-course-id="course-v1:edx+1+1"', frag.content)
        self.assertIn("data-sequential-id=\"block-v1:edx+1+1+type@sequential+block@seq\"", frag.content)


if __name__ == "__main__":
    unittest.main()
