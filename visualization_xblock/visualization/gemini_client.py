"""Thin REST adapter over the Gemini generateContent endpoint.

Uses ``requests`` directly instead of ``google-generativeai`` to avoid dragging
protobuf / grpcio / google-auth into the Open edX Python environment, where
they conflict with platform-pinned dependencies.
"""

import os
import re

import requests

SYSTEM_PROMPT = """\
You are generating an interactive educational simulation for an Open edX course.

REQUIREMENTS:
1. Output ONE self-contained HTML file.
2. ALL CSS must be inline in a <style> block.
3. ALL JavaScript must be inline in a <script> block.
4. External libraries allowed only via CDN (Chart.js, three.js, KaTeX).
5. The simulation MUST be interactive - include UI controls (sliders, buttons, inputs) that change behavior in real time without page reload.
6. Label all controls clearly.
7. Use semantic HTML (<main>, <section>, <label>).
8. Ensure output is safe to render inside a sandboxed iframe (no top-level navigation, no localStorage without fallback).

OUTPUT FORMAT:
Return ONLY the HTML file content inside a ```html fenced block. No additional prose.
"""

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
REQUEST_TIMEOUT = 120

_HTML_FENCE = re.compile(r"```html\s*(.+?)\s*```", re.DOTALL)


class GeminiClientError(Exception):
    """Raised when Gemini generation fails or returns an unusable payload."""


def _get_api_key():
    try:
        from django.conf import settings
        key = getattr(settings, "GEMINI_API_KEY", None)
        if key:
            return key
    except ImportError:
        pass
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise GeminiClientError(
            "GEMINI_API_KEY is not configured. Set Django setting GEMINI_API_KEY "
            "or the environment variable of the same name."
        )
    return key


def _extract_html(response_text):
    """Pull the HTML payload out of a Gemini response.

    Gemini wraps the HTML in ```html ... ``` fences almost always; fall back
    to slicing from the first ``<!DOCTYPE`` marker if the fences are missing.
    """
    match = _HTML_FENCE.search(response_text)
    if match:
        return match.group(1).strip()
    doctype_idx = response_text.find("<!DOCTYPE")
    if doctype_idx >= 0:
        return response_text[doctype_idx:].strip()
    raise GeminiClientError("No HTML block found in Gemini response.")


def _extract_text(payload):
    """Concatenate text parts from a generateContent response JSON."""
    try:
        candidates = payload["candidates"]
    except (KeyError, TypeError):
        raise GeminiClientError(
            f"Gemini response missing 'candidates': {payload!r}"
        )
    if not candidates:
        raise GeminiClientError("Gemini returned zero candidates.")

    parts = candidates[0].get("content", {}).get("parts", [])
    texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
    text = "".join(texts).strip()
    if not text:
        raise GeminiClientError("Gemini returned an empty text payload.")
    return text


def generate_simulation(prompt, model_name):
    """Call Gemini generateContent and return the extracted simulation HTML."""
    if not prompt or not prompt.strip():
        raise GeminiClientError("Prompt is empty — cannot generate a simulation.")

    api_key = _get_api_key()
    url = f"{GEMINI_API_BASE}/models/{model_name}:generateContent"
    body = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [
            {"role": "user", "parts": [{"text": f"USER REQUEST:\n{prompt}"}]}
        ],
    }

    try:
        response = requests.post(
            url,
            params={"key": api_key},
            json=body,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise GeminiClientError(f"Gemini API call failed: {exc}") from exc

    if response.status_code >= 400:
        raise GeminiClientError(
            f"Gemini API returned {response.status_code}: {response.text[:500]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise GeminiClientError(f"Gemini returned non-JSON response: {exc}") from exc

    text = _extract_text(payload)
    return _extract_html(text)
