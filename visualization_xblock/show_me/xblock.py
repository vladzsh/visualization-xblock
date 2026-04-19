"""ShowMeXBlock — Gemini-powered interactive simulation for Open edX."""

import datetime
import html
import logging

from importlib.resources import files

from web_fragments.fragment import Fragment
from xblock.core import XBlock
from xblock.fields import DateTime, Scope, String

from show_me import gemini_client
from show_me.gemini_client import GeminiClientError

log = logging.getLogger(__name__)

STATUS_IDLE = "idle"
STATUS_GENERATING = "generating"
STATUS_ERROR = "error"

MODEL_CHOICES = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-3.1-pro",
]


class ShowMeXBlock(XBlock):
    """Render an LLM-generated interactive simulation in a sandboxed iframe."""

    display_name = String(
        display_name="Display Name",
        default="Show Me Simulation",
        scope=Scope.settings,
        help="Component title shown to students.",
    )
    prompt = String(
        display_name="Simulation prompt",
        default="",
        scope=Scope.settings,
        help="What the simulation should show. Describe the phenomenon and controls.",
    )
    model_name = String(
        display_name="Gemini model",
        default="gemini-2.5-flash",
        scope=Scope.settings,
        values=MODEL_CHOICES,
        help=(
            "gemini-2.5-flash (free tier, default) for most 2D simulations; "
            "gemini-2.5-pro requires billing; gemini-3.1-pro adds WebGL/3D."
        ),
    )
    cached_html = String(
        default="",
        scope=Scope.settings,
        help="Generated simulation HTML (shared across students of the block).",
    )
    generated_at = DateTime(
        default=None,
        scope=Scope.settings,
        help="Timestamp of the last successful generation.",
    )
    generation_status = String(
        default=STATUS_IDLE,
        scope=Scope.settings,
        help="One of: idle | generating | error.",
    )
    last_error = String(
        default="",
        scope=Scope.settings,
        help="Last generation error message, surfaced in Studio.",
    )

    def resource_string(self, path):
        return files(__package__).joinpath(path).read_text(encoding="utf-8")

    @XBlock.json_handler
    def save_settings(self, data, suffix=""):
        """Persist Studio-edited fields without generating."""
        self.display_name = data.get("display_name", self.display_name)
        self.prompt = data.get("prompt", self.prompt)

        model_name = data.get("model_name", self.model_name)
        if model_name not in MODEL_CHOICES:
            return {"status": "error", "message": f"Unknown model: {model_name}"}
        self.model_name = model_name

        return {"status": "ok"}

    @XBlock.json_handler
    def generate(self, data, suffix=""):
        """Call Gemini and cache the resulting HTML on the block."""
        prompt = data.get("prompt", self.prompt)
        model_name = data.get("model_name", self.model_name)

        if model_name not in MODEL_CHOICES:
            self.generation_status = STATUS_ERROR
            self.last_error = f"Unknown model: {model_name}"
            return {"status": "error", "message": self.last_error}

        self.prompt = prompt
        self.model_name = model_name
        self.generation_status = STATUS_GENERATING

        try:
            rendered_html = gemini_client.generate_simulation(prompt, model_name)
        except GeminiClientError as exc:
            log.warning("ShowMe Gemini generation failed: %s", exc)
            self.generation_status = STATUS_ERROR
            self.last_error = str(exc)
            return {"status": "error", "message": str(exc)}

        self.cached_html = rendered_html
        self.generated_at = datetime.datetime.now(datetime.timezone.utc)
        self.generation_status = STATUS_IDLE
        self.last_error = ""
        return {
            "status": "ok",
            "html": rendered_html,
            "generated_at": self.generated_at.isoformat(),
        }

    def student_view(self, context=None):
        template = self.resource_string("static/html/student.html")
        has_html = bool(self.cached_html)
        iframe_html = ""
        placeholder_display = "block"
        iframe_display = "none"
        if has_html:
            srcdoc = html.escape(self.cached_html, quote=True)
            iframe_html = (
                f'<iframe class="show-me-frame" sandbox="allow-scripts" '
                f'srcdoc="{srcdoc}" '
                f'style="width:100%;height:600px;border:0" '
                f'title="{html.escape(self.display_name or "Simulation", quote=True)}">'
                f"</iframe>"
            )
            placeholder_display = "none"
            iframe_display = "block"

        rendered = template.format(
            display_name=html.escape(self.display_name or "", quote=True),
            iframe_html=iframe_html,
            placeholder_display=placeholder_display,
            iframe_display=iframe_display,
        )
        frag = Fragment(rendered)
        frag.add_css(self.resource_string("static/css/show_me.css"))
        frag.add_javascript(self.resource_string("static/js/src/student.js"))
        frag.initialize_js("ShowMeXBlock")
        return frag

    def studio_view(self, context=None):
        template = self.resource_string("static/html/studio.html")
        preview_srcdoc = html.escape(self.cached_html, quote=True) if self.cached_html else ""
        generated_at_str = self.generated_at.isoformat() if self.generated_at else ""

        model_options = "".join(
            f'<option value="{m}"{" selected" if m == self.model_name else ""}>{m}</option>'
            for m in MODEL_CHOICES
        )

        rendered = template.format(
            display_name=html.escape(self.display_name or "", quote=True),
            prompt=html.escape(self.prompt or ""),
            model_options=model_options,
            preview_srcdoc=preview_srcdoc,
            preview_display="block" if preview_srcdoc else "none",
            status=self.generation_status,
            last_error=html.escape(self.last_error or ""),
            error_display="block" if self.last_error else "none",
            generated_at=generated_at_str,
        )
        frag = Fragment(rendered)
        frag.add_css(self.resource_string("static/css/show_me.css"))
        frag.add_javascript(self.resource_string("static/js/src/studio.js"))
        frag.initialize_js("ShowMeStudio")
        return frag
