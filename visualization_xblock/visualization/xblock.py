"""VisualizationXBlock — AI-crafter-backed interactive simulations for Open edX."""

import datetime
import html
import logging

from importlib.resources import files

from web_fragments.fragment import Fragment
from xblock.core import XBlock
from xblock.fields import DateTime, Scope, String

from visualization import crafter_client
from visualization.crafter_client import (
    CrafterError,
    CrafterNotConfiguredError,
    CrafterNotInstalledError,
)

log = logging.getLogger(__name__)

STATUS_IDLE = "idle"
STATUS_GENERATING = "generating"
STATUS_ERROR = "error"


class VisualizationXBlock(XBlock):
    """Render an AI-generated interactive simulation in a sandboxed iframe.

    Generation is delegated to course-crafter-plugin (Gemini provider). Per-block
    state keeps only the applied HTML plus status metadata; chat history lives
    in crafter's ``Conversation`` model keyed on ``(user, usage_id)``.
    """

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
    generation_status = String(
        default=STATUS_IDLE,
        scope=Scope.settings,
        help="One of: idle | generating | error.",
    )
    last_error = String(
        default="",
        scope=Scope.settings,
        help="Last error message, surfaced in Studio.",
    )

    def resource_string(self, path):
        return files(__package__).joinpath(path).read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Usage-key helpers
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

    def _current_user(self):
        """Resolve the real Django user for the request, or ``None``.

        Tries, in order:
        1. ``crum.get_current_user()`` — request-scoped middleware, works in
           both LMS and CMS/Studio.
        2. The xblock ``user`` runtime service (LMS student contexts). We look
           up the Django ``User`` by id because the service only exposes an
           ``XBlockUser`` wrapper, not the ORM instance crafter's chat models
           expect.
        """
        try:
            from crum import get_current_user
            user = get_current_user()
            if user is not None and getattr(user, "is_authenticated", False):
                return user
        except ImportError:
            pass
        except Exception:
            pass

        try:
            user_service = self.runtime.service(self, "user")
            current = user_service.get_current_user()
            opt_attrs = getattr(current, "opt_attrs", {}) or {}
            user_id = opt_attrs.get("edx-platform.user_id")
            if user_id:
                from django.contrib.auth import get_user_model
                return get_user_model().objects.filter(pk=user_id).first()
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    @XBlock.json_handler
    def save_settings(self, data, suffix=""):
        """Persist Studio-edited display name."""
        self.display_name = data.get("display_name", self.display_name)
        return {"status": "ok"}

    @XBlock.json_handler
    def send_message(self, data, suffix=""):
        """Send a chat message to crafter, stream back the generated HTML.

        The AI response is NOT automatically applied — the author reviews it
        in Studio and clicks Apply to promote it to ``cached_html``.
        """
        prompt_text = (data.get("prompt") or "").strip()
        if not prompt_text:
            return {"status": "error", "message": "Prompt is empty."}

        user = self._current_user()
        if user is None:
            return {"status": "error", "message": "No authenticated user in context."}

        self.generation_status = STATUS_GENERATING
        try:
            generated_html = crafter_client.generate_visualization_html(
                course_id=self._course_id(),
                block_id=self._block_id(),
                prompt=prompt_text,
                user=user,
                current_content=self.cached_html,
            )
        except CrafterNotInstalledError as exc:
            self.generation_status = STATUS_ERROR
            self.last_error = str(exc)
            return {"status": "error", "message": str(exc), "code": "crafter_not_installed"}
        except CrafterNotConfiguredError as exc:
            self.generation_status = STATUS_ERROR
            self.last_error = str(exc)
            return {"status": "error", "message": str(exc), "code": "crafter_not_configured"}
        except (CrafterError, ValueError) as exc:
            log.warning("Visualization generation failed: %s", exc)
            self.generation_status = STATUS_ERROR
            self.last_error = str(exc)
            return {"status": "error", "message": str(exc)}
        except Exception as exc:
            log.exception("Unexpected error during visualization generation")
            self.generation_status = STATUS_ERROR
            self.last_error = str(exc)
            return {"status": "error", "message": str(exc)}

        self.generation_status = STATUS_IDLE
        self.last_error = ""
        return {
            "status": "ok",
            "html": generated_html,
            "prompt": prompt_text,
        }

    @XBlock.json_handler
    def apply_message(self, data, suffix=""):
        """Promote a generated HTML payload to the applied simulation."""
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

    @XBlock.json_handler
    def get_chat_history(self, data, suffix=""):
        """Return the conversation log for this (user, block)."""
        user = self._current_user()
        if user is None:
            return {"status": "error", "message": "No authenticated user in context."}
        try:
            messages = crafter_client.get_chat_messages(self._block_id(), user)
        except CrafterNotInstalledError as exc:
            return {"status": "error", "message": str(exc), "code": "crafter_not_installed"}
        return {"status": "ok", "messages": messages}

    @XBlock.json_handler
    def clear_chat_history(self, data, suffix=""):
        """Delete all messages for this (user, block)."""
        user = self._current_user()
        if user is None:
            return {"status": "error", "message": "No authenticated user in context."}
        try:
            deleted = crafter_client.clear_chat(self._block_id(), user)
        except CrafterNotInstalledError as exc:
            return {"status": "error", "message": str(exc), "code": "crafter_not_installed"}
        return {"status": "ok", "deleted": deleted}

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
            status=self.generation_status,
            last_error=html.escape(self.last_error or ""),
            error_display="block" if self.last_error else "none",
            generated_at=generated_at_str,
            applied_prompt=html.escape(self.prompt or ""),
        )
        frag = Fragment(rendered)
        frag.add_css(self.resource_string("static/css/visualization.css"))
        frag.add_javascript(self.resource_string("static/js/src/studio.js"))
        frag.initialize_js("VisualizationStudio")
        return frag
