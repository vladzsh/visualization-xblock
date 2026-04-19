# visualization-xblock

An Open edX XBlock that generates interactive educational simulations on demand
via [course-crafter-plugin][crafter] (Gemini provider). Course authors chat with
the AI directly in Studio (“Show a Moon orbiting Earth with sliders for
velocity and gravity”), review the generated HTML, and apply it to the block —
students see it rendered inside a sandboxed iframe.

Tested against the Open edX **Teak** release.

[crafter]: https://gitlab.raccoongang.com/AILab/course-crafter-ai/course-crafter-plugin

## Status

Proof of concept. Expect rough edges.

## What it does

- **Studio:** an "AI Content Assistant" chat panel (mirrors the crafter widget
  UX), a list of past messages per author × block, `Apply` to promote any AI
  message to the active simulation, and a live preview pane.
- **LMS (student view):** renders the applied simulation inside
  `<iframe sandbox="allow-scripts">`. One shared simulation per block.
- **Backend:** the Studio browser POSTs directly to `course-crafter-plugin`'s
  REST API (`/course_crafter_plugin/api/ai-content/generate/` and
  `/course_crafter_plugin/api/chat/{block_id}/`). Same origin as the xblock
  iframe so the session cookie authenticates the request. This xblock only
  persists the author-applied HTML via its own `save_applied_html` handler
  and renders it in the student view.
- **Upstream:** we contribute the `visualization` content type and the Gemini
  provider to `course-crafter-plugin` (see companion MR on the crafter repo).

## Supported models

Any model supported by Google Generative Language API (picked via the crafter
`Assistant` record). For POC we default to `gemini-2.5-flash` — free tier,
fast, sufficient for 2D simulations. `gemini-2.5-pro` and `gemini-3.1-pro`
require billing to be enabled on the API key; pro models are needed for WebGL
/ 3D content.

## Install

From inside the edx-platform virtualenv (e.g. a Tutor LMS shell):

```bash
pip install -e /path/to/course-crafter-plugin        # feat/visualization-gemini branch
pip install -e /path/to/visualization-xblock/visualization_xblock
```

Then, in site config or Django admin, add `visualization` to
`ADVANCED_COMPONENT_TYPES` so it shows up in Studio’s *Advanced Component*
picker.

## API key & per-course assistant

The Gemini key lives in the crafter `APICredentials` table, not in env vars.
One-time setup (Django admin on LMS → *Course Crafter Plugin*):

1. **APICredentials:** name `gemini-main`, provider `gemini`, `api_key` = your
   Google AI Studio key.
2. **Assistant:** pick the credentials, `model_name=gemini-2.5-flash`, leave
   `system_input` / `json_format` blank (the crafter prompt service supplies
   them), set `temperature` ≈ `0.7`.
3. **AI Content creation Assistant:** `course_id=<your course key>`,
   `assistant=<the Assistant above>`.

Once this is in place, every VisualizationXBlock instance in that course picks
up the assistant automatically.

## Development

```bash
cd visualization_xblock
python -m venv .venv && source .venv/bin/activate
pip install -e . pytest django
pytest tests/ -v
```

The test suite mocks the crafter client end-to-end — no crafter install, no
network, no API key required.

## Layout

```
visualization-xblock/
├── README.md
├── .gitignore
└── visualization_xblock/          # pip-installable project root
    ├── setup.py                   # dist name: visualization-xblock
    ├── conftest.py
    ├── visualization/             # Python package (xblock tag: visualization)
    │   ├── xblock.py              # VisualizationXBlock (save_settings + save_applied_html)
    │   └── static/{html,css,js}/  # Studio chat UI POSTs directly to crafter REST
    └── tests/
```

## Future work

- Reuse the `AIAssistantWidget` from `frontend-ai-crafter-widgets` directly.
  Blocked today because that widget is embedded in Course Authoring’s
  Problem/HTML editor modals, and Advanced Components render in an iframe that
  lives outside the widget’s DOM. Likely paths: add a dedicated Course
  Authoring editor for `visualization` blockType that reuses the widget, or
  wire a `postMessage` bridge into the iframe.
- Admin UX to configure per-course `AIContentCreator` without diving into
  Django admin.
- Streaming generation output rather than a single final HTML blob.

## License

AGPL v3.
