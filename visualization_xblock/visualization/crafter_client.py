"""Adapter from VisualizationXBlock to course-crafter-plugin.

Imports crafter's services/models at call-time so the xblock remains
installable in environments where crafter is not present (unit tests, early
Tutor setups). If crafter is missing, handlers surface a ``CrafterNotInstalledError``
so the Studio UI can show actionable guidance instead of crashing.
"""

import logging

log = logging.getLogger(__name__)

VISUALIZATION_BLOCK_TYPE = "visualization"


class CrafterError(Exception):
    """Base class for crafter integration failures."""


class CrafterNotInstalledError(CrafterError):
    """Raised when course-crafter-plugin is not importable from this Python env."""


class CrafterNotConfiguredError(CrafterError):
    """Raised when the target course has no AIContentCreator assigned."""


def _import_crafter():
    try:
        from course_crafter_plugin.clients import generate_text_content
        from course_crafter_plugin.models.assistants import AIContentCreator
        from course_crafter_plugin.services.content_service import XBlockContentService
        from course_crafter_plugin.services.prompt_service import AIPromptService
        from course_crafter_chat.services import (
            get_or_create_conversation,
            save_assistant_message,
            save_user_message,
        )
        from course_crafter_chat.models import Conversation
    except ImportError as exc:
        raise CrafterNotInstalledError(
            "course-crafter-plugin is not installed in this environment. "
            "Install it alongside visualization-xblock to enable AI generation."
        ) from exc
    return {
        "generate_text_content": generate_text_content,
        "AIContentCreator": AIContentCreator,
        "XBlockContentService": XBlockContentService,
        "AIPromptService": AIPromptService,
        "get_or_create_conversation": get_or_create_conversation,
        "save_assistant_message": save_assistant_message,
        "save_user_message": save_user_message,
        "Conversation": Conversation,
    }


def _empty_context():
    """Minimal learning-context stub for prompt building.

    We skip ``platform_service.get_learning_context`` (which requires the
    sequential usage_id) because it's not trivially reachable from an
    Advanced Component and the visualization prompt does not actually rely on
    course metadata.
    """
    return {
        "course_name": "",
        "course_description": "",
        "sequential_name": "",
    }


def generate_visualization_html(course_id, block_id, prompt, user, current_content=""):
    """Generate an interactive simulation via crafter's Gemini provider.

    Parameters
    ----------
    course_id : str
        Course key, e.g. ``"course-v1:edx+1+1"``.
    block_id : str
        Usage key for this xblock instance; used as the conversation location.
    prompt : str
        Author-provided request to the model.
    user : User
        The Studio author making the request (for chat history & auth context).
    current_content : str
        Previously cached HTML, if any — enables edit-mode detection in
        crafter's prompt service.

    Returns the generated HTML string.

    Raises ``CrafterNotInstalledError``, ``CrafterNotConfiguredError``, or
    ``CrafterError`` subclass / ``ValueError`` for generation failures.
    """
    mods = _import_crafter()

    try:
        creator = mods["AIContentCreator"].objects.get(course_id=course_id)
    except mods["AIContentCreator"].DoesNotExist as exc:
        raise CrafterNotConfiguredError(
            f"No AIContentCreator is assigned to course '{course_id}'. "
            "Open Django admin → course_crafter_plugin → AI Content creation "
            "Assistants and add one for this course."
        ) from exc

    conversation = mods["get_or_create_conversation"](user, block_id)
    mods["save_user_message"](conversation, prompt)

    prompt_service = mods["AIPromptService"]()
    content_service = mods["XBlockContentService"]()

    prompt_config = prompt_service.build_prompt(
        xblock_type=VISUALIZATION_BLOCK_TYPE,
        prompt=prompt,
        content=current_content or "",
        context=_empty_context(),
    )

    ai_response = mods["generate_text_content"](
        assistant=creator.assistant,
        developer=prompt_config.developer,
        user=prompt_config.user,
        text_format=prompt_config.text_format,
    )
    if not ai_response:
        raise ValueError("AI service returned an empty response.")

    content = content_service.parse_content(
        xblock_type=VISUALIZATION_BLOCK_TYPE,
        ai_response=ai_response,
    )
    mods["save_assistant_message"](conversation, content)
    return content


def get_chat_messages(block_id, user):
    """Return list of ``{role, content, created_at}`` for the user's conversation on this block."""
    mods = _import_crafter()
    conv = mods["Conversation"].objects.filter(user=user, location_id=block_id).first()
    if not conv:
        return []
    return [
        {
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at.isoformat(),
        }
        for m in conv.messages.order_by("created_at")
    ]


def clear_chat(block_id, user):
    """Delete the user's conversation for this block. Returns number of messages removed."""
    mods = _import_crafter()
    conv = mods["Conversation"].objects.filter(user=user, location_id=block_id).first()
    if not conv:
        return 0
    count = conv.messages.count()
    conv.delete()
    return count
