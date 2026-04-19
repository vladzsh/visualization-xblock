"""VisualizationXBlock — renders a Gemini-generated interactive simulation.

Content generation and chat history are not implemented here: the Studio
browser POSTs directly to ``course-crafter-plugin``'s REST API (same origin,
same session cookie). This xblock only persists the resulting HTML and
renders it in the student view inside a sandboxed iframe.
"""

import datetime
import html
import logging

from importlib.resources import files

from web_fragments.fragment import Fragment
from xblock.core import XBlock
from xblock.fields import DateTime, Scope, String

log = logging.getLogger(__name__)


class VisualizationXBlock(XBlock):
    """AI-generated interactive simulation rendered in a sandboxed iframe."""

    display_name = String(
        display_name="Display Name",
        default="Visualization",
        scope=Scope.settings,
        help="Component title shown to students.",
    )
    prompt = String(
        display_name="Last applied prompt",
        default="",
        scope=Scope.settings,
        help="The prompt that produced the currently applied simulation (informational).",
    )
    cached_html = String(
        default="",
        scope=Scope.settings,
        help="Currently-applied simulation HTML (shared across students).",
    )
    generated_at = DateTime(
        default=None,
        scope=Scope.settings,
        help="When ``cached_html`` was last updated.",
    )

    def resource_string(self, path):
        return files(__package__).joinpath(path).read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Usage-key helpers (resolved server-side for the Studio template)
    # ------------------------------------------------------------------
    def _course_id(self):
        try:
            return str(self.scope_ids.usage_id.context_key)
        except Exception:
            return ""

    def _block_id(self):
        try:
            return str(self.scope_ids.usage_id)
        except Exception:
            return ""

    def _sequential_id(self):
        """Walk the xblock tree up to the sequential container.

        Our block lives inside a vertical, which lives inside a sequential.
        Crafter's ``build_prompt`` needs the sequential id to fetch
        ``sequential.display_name`` for the learning context.
        """
        try:
            vertical = self.get_parent()
            sequential = vertical.get_parent() if vertical is not None else None
            if sequential is not None:
                return str(sequential.scope_ids.usage_id)
        except Exception:
            pass
        return ""

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    @XBlock.json_handler
    def save_settings(self, data, suffix=""):
        """Persist Studio-edited display name."""
        self.display_name = data.get("display_name", self.display_name)
        return {"status": "ok"}

    @XBlock.json_handler
    def save_applied_html(self, data, suffix=""):
        """Promote a generated HTML payload (chosen in Studio) to the applied simulation."""
        html_payload = data.get("html") or ""
        if not html_payload:
            return {"status": "error", "message": "No HTML to apply."}
        self.cached_html = html_payload
        self.prompt = data.get("prompt", self.prompt)
        self.generated_at = datetime.datetime.now(datetime.timezone.utc)
        return {
            "status": "ok",
            "generated_at": self.generated_at.isoformat(),
        }

    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------
    def student_view(self, context=None):
        template = self.resource_string("static/html/student.html")
        has_html = bool(self.cached_html)
        iframe_html = ""
        placeholder_display = "block"
        iframe_display = "none"
        if has_html:
            srcdoc = html.escape(self.cached_html, quote=True)
            iframe_html = (
                f'<iframe class="visualization-frame" sandbox="allow-scripts" '
                f'srcdoc="{srcdoc}" '
                f'style="width:100%;height:600px;border:0" '
                f'title="{html.escape(self.display_name or "Visualization", quote=True)}">'
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
        frag.add_css(self.resource_string("static/css/visualization.css"))
        frag.add_javascript(self.resource_string("static/js/src/student.js"))
        frag.initialize_js("VisualizationXBlock")
        return frag

    def _lms_root_url(self):
        try:
            from django.conf import settings
            return (getattr(settings, "LMS_ROOT_URL", "") or "").rstrip("/")
        except Exception:
            return ""

    def studio_view(self, context=None):
        template = self.resource_string("static/html/studio.html")
        preview_srcdoc = (
            html.escape(self.cached_html, quote=True) if self.cached_html else ""
        )
        generated_at_str = self.generated_at.isoformat() if self.generated_at else ""

        rendered = template.format(
            display_name=html.escape(self.display_name or "", quote=True),
            preview_srcdoc=preview_srcdoc,
            preview_display="block" if preview_srcdoc else "none",
            generated_at=generated_at_str,
            applied_prompt=html.escape(self.prompt or ""),
            course_id=html.escape(self._course_id(), quote=True),
            block_id=html.escape(self._block_id(), quote=True),
            sequential_id=html.escape(self._sequential_id(), quote=True),
            lms_root_url=html.escape(self._lms_root_url(), quote=True),
        )
        frag = Fragment(rendered)
        frag.add_css(self.resource_string("static/css/visualization.css"))
        frag.add_javascript(self.resource_string("static/js/src/studio.js"))
        frag.initialize_js("VisualizationStudio")
        return frag
