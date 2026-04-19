# visualization-xblock

An Open edX XBlock that generates interactive educational simulations on demand
via the Google Gemini API. Course authors write a natural-language prompt in
Studio (“Show a Moon orbiting Earth with sliders for velocity and gravity”),
Gemini returns a single self-contained HTML page, and students see it rendered
inside a sandboxed iframe.

Tested against the Open edX **Teak** release.

## Status

Proof of concept. Expect rough edges. See `docs/POC.md` in the project wiki
for the background and open questions.

## What it does

- **Studio:** textarea for the prompt, dropdown for the Gemini model, a
  *Generate* button, and a preview pane.
- **LMS (student view):** renders the cached simulation inside
  `<iframe sandbox="allow-scripts">`. One shared simulation per block.
- **Backend:** thin wrapper around Gemini’s REST
  `generateContent` endpoint. No `google-generativeai` SDK, so no protobuf
  / grpcio conflicts with the edX Python environment.

## Supported models

| Model             | Notes                                               |
|-------------------|-----------------------------------------------------|
| `gemini-2.5-flash`| Free tier. Default. Good enough for most 2D sims.   |
| `gemini-2.5-pro`  | Higher quality. **Requires billing** on the key.    |
| `gemini-3.1-pro`  | WebGL / 3D support. Requires billing.               |

## Install

From inside the edx-platform virtualenv (e.g. a Tutor LMS shell):

```bash
pip install -e /path/to/visualization-xblock/visualization_xblock
```

Then add `show_me` to `ADVANCED_COMPONENT_TYPES` (site config or Django admin)
so it shows up in Studio’s *Advanced Component* picker.

> The XBlock tag is intentionally kept as `show_me` — renaming it would orphan
> any blocks already authored in Studio.

## API key

The XBlock reads the Gemini API key from, in order of preference:

1. `django.conf.settings.GEMINI_API_KEY`
2. `os.environ["GEMINI_API_KEY"]`

For Tutor dev, the quickest option is to set the env var on the LMS and CMS
containers via a `docker-compose.override.yml` in the Tutor env. A proper
Tutor plugin that pipes the value through the settings chain is left as an
exercise (and is the recommended path for any non-POC deployment).

## Development

```bash
cd visualization_xblock
python -m venv .venv && source .venv/bin/activate
pip install -e . pytest django
pytest tests/ -v
```

All 15 tests mock the Gemini HTTP call, so no API key is required to run them.

## Layout

```
visualization-xblock/
├── README.md
├── .gitignore
└── visualization_xblock/          # pip-installable project root
    ├── setup.py                   # dist name: visualization-xblock
    ├── conftest.py
    ├── show_me/                   # Python package (xblock tag: show_me)
    │   ├── xblock.py              # ShowMeXBlock
    │   ├── gemini_client.py       # REST adapter over generateContent
    │   └── static/{html,css,js}/
    └── tests/
```

## License

AGPL v3.
