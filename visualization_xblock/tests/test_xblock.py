"""Tests for VisualizationXBlock."""

import json
import unittest
from unittest.mock import MagicMock, patch

from web_fragments.fragment import Fragment
from xblock.fields import ScopeIds
from xblock.test.toy_runtime import ToyRuntime

from visualization import VisualizationXBlock
from visualization import gemini_client
from visualization.gemini_client import GeminiClientError, _extract_html, _extract_text


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
        return VisualizationXBlock(self.runtime, scope_ids=self.scope_ids)

    def _call_handler(self, block, handler_name, data):
        request = MagicMock()
        request.method = "POST"
        request.body = json.dumps(data).encode("utf-8")
        response = getattr(block, handler_name)(request)
        return json.loads(response.body)


class TestVisualizationHandlers(VisualizationTestBase):

    def test_save_settings_updates_fields(self):
        block = self._make_block()
        resp = self._call_handler(block, "save_settings", {
            "display_name": "Orbit demo",
            "prompt": "Show a Moon-Earth orbit",
            "model_name": "gemini-3.1-pro",
        })
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(block.display_name, "Orbit demo")
        self.assertEqual(block.prompt, "Show a Moon-Earth orbit")
        self.assertEqual(block.model_name, "gemini-3.1-pro")

    def test_save_settings_rejects_unknown_model(self):
        block = self._make_block()
        resp = self._call_handler(block, "save_settings", {
            "display_name": "x",
            "prompt": "x",
            "model_name": "gpt-5",
        })
        self.assertEqual(resp["status"], "error")

    @patch("visualization.xblock.gemini_client.generate_simulation")
    def test_generate_success_stores_html(self, mock_gen):
        mock_gen.return_value = SIMULATION_HTML
        block = self._make_block()
        resp = self._call_handler(block, "generate", {
            "prompt": "Show a Moon-Earth orbit",
            "model_name": "gemini-2.5-pro",
        })
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(resp["html"], SIMULATION_HTML)
        self.assertEqual(block.cached_html, SIMULATION_HTML)
        self.assertEqual(block.generation_status, "idle")
        self.assertEqual(block.last_error, "")
        self.assertIsNotNone(block.generated_at)
        mock_gen.assert_called_once_with("Show a Moon-Earth orbit", "gemini-2.5-pro")

    @patch("visualization.xblock.gemini_client.generate_simulation")
    def test_generate_error_sets_status(self, mock_gen):
        mock_gen.side_effect = GeminiClientError("API quota exceeded")
        block = self._make_block()
        resp = self._call_handler(block, "generate", {
            "prompt": "anything",
            "model_name": "gemini-2.5-pro",
        })
        self.assertEqual(resp["status"], "error")
        self.assertEqual(resp["message"], "API quota exceeded")
        self.assertEqual(block.generation_status, "error")
        self.assertEqual(block.last_error, "API quota exceeded")
        self.assertEqual(block.cached_html, "")


class TestVisualizationViews(VisualizationTestBase):

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
        self.assertIsInstance(frag, Fragment)
        self.assertIn('sandbox="allow-scripts"', frag.content)
        self.assertIn("srcdoc=", frag.content)
        # Raw HTML must be escaped — check it doesn't appear verbatim.
        self.assertNotIn(SIMULATION_HTML, frag.content)

    def test_studio_view_renders_form_and_model_options(self):
        block = self._make_block()
        block.prompt = "Fourier series"
        frag = block.studio_view()
        self.assertIsInstance(frag, Fragment)
        self.assertIn("Fourier series", frag.content)
        self.assertIn("gemini-2.5-pro", frag.content)
        self.assertIn("gemini-3.1-pro", frag.content)


class TestGeminiClientParser(unittest.TestCase):

    def test_extracts_from_fenced_block(self):
        raw = "Sure!\n```html\n<!DOCTYPE html><h1>ok</h1>\n```\nDone."
        self.assertEqual(_extract_html(raw), "<!DOCTYPE html><h1>ok</h1>")

    def test_fallback_to_doctype_when_no_fences(self):
        raw = "Here you go: <!DOCTYPE html><html><body>x</body></html>"
        self.assertEqual(_extract_html(raw), "<!DOCTYPE html><html><body>x</body></html>")

    def test_raises_when_no_html_found(self):
        with self.assertRaises(GeminiClientError):
            _extract_html("I cannot help with that.")

    def test_extract_text_joins_parts(self):
        payload = {
            "candidates": [
                {"content": {"parts": [{"text": "hel"}, {"text": "lo"}]}}
            ]
        }
        self.assertEqual(_extract_text(payload), "hello")

    def test_extract_text_raises_when_no_candidates(self):
        with self.assertRaises(GeminiClientError):
            _extract_text({"candidates": []})


class TestGeminiClientHTTP(unittest.TestCase):

    def _make_response(self, status=200, json_body=None, text=""):
        resp = MagicMock()
        resp.status_code = status
        resp.text = text
        if json_body is not None:
            resp.json.return_value = json_body
        else:
            resp.json.side_effect = ValueError("not json")
        return resp

    @patch("visualization.gemini_client.requests.post")
    def test_generate_simulation_happy_path(self, mock_post):
        mock_post.return_value = self._make_response(
            status=200,
            json_body={
                "candidates": [{
                    "content": {"parts": [{"text": "```html\n<!DOCTYPE html><h1>x</h1>\n```"}]}
                }]
            },
        )
        result = gemini_client.generate_simulation("demo", "gemini-2.5-pro")
        self.assertEqual(result, "<!DOCTYPE html><h1>x</h1>")

        args, kwargs = mock_post.call_args
        self.assertIn("gemini-2.5-pro:generateContent", args[0])
        self.assertEqual(kwargs["params"], {"key": "test-key"})
        self.assertEqual(
            kwargs["json"]["system_instruction"]["parts"][0]["text"],
            gemini_client.SYSTEM_PROMPT,
        )

    @patch("visualization.gemini_client.requests.post")
    def test_generate_simulation_http_error_raises(self, mock_post):
        mock_post.return_value = self._make_response(
            status=429, text="rate limited"
        )
        with self.assertRaises(GeminiClientError) as cm:
            gemini_client.generate_simulation("demo", "gemini-2.5-pro")
        self.assertIn("429", str(cm.exception))

    def test_generate_simulation_empty_prompt_raises(self):
        with self.assertRaises(GeminiClientError):
            gemini_client.generate_simulation("   ", "gemini-2.5-pro")


if __name__ == "__main__":
    unittest.main()
