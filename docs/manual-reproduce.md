# Manual reproduce — VisualizationXBlock + course-crafter-plugin (Gemini)

End-to-end smoke scenario for a Tutor dev environment. Runs in ~20 minutes the
first time. Assumes `~/rg/ai-lab/edx` is the Tutor root.

## 0. Preconditions

- Tutor dev environment is already set up and `tutor dev start -d` works.
- Google AI Studio key with access to `gemini-2.5-flash` (free tier is fine).
  Create one at https://aistudio.google.com/apikey.
- The two repos checked out locally. Paths inside the container map to
  `/openedx/edx_plugins/` because `~/rg/ai-lab/edx/edx_plugins` is mounted in.
  - `edx_plugins/course-crafter-plugin/` on branch `feat/visualization-gemini`
    (or `main` after merge).
  - `edx_plugins/visualization-xblock/` (symlink or checkout).

## 1. Install both plugins into LMS & CMS

From a host shell:

```bash
tutor dev run lms pip install -e /openedx/edx_plugins/course-crafter-plugin
tutor dev run lms pip install -e /openedx/edx_plugins/visualization-xblock/visualization_xblock
tutor dev run cms pip install -e /openedx/edx_plugins/course-crafter-plugin
tutor dev run cms pip install -e /openedx/edx_plugins/visualization-xblock/visualization_xblock
```

Expected: no dependency resolver errors involving `xblock` / `web-fragments` /
`requests`. Crafter will downgrade/upgrade `openai`, `typing-extensions` —
that's pre-existing and fine.

## 2. Run migrations

```bash
tutor dev run lms ./manage.py lms migrate course_crafter_plugin
tutor dev run lms ./manage.py lms migrate course_crafter_chat
```

Expected: `0003_apicredentials_provider_gemini` applies.

## 3. Restart services

```bash
tutor dev restart lms cms
```

Wait ~30s for both containers to come back.

## 4. Seed crafter data via Django admin

Open http://local.openedx.io:8000/admin/ and sign in as `edx`
(default Tutor superuser).

**APICredentials** (`/admin/course_crafter_plugin/apicredentials/add/`):

| Field    | Value           |
|----------|-----------------|
| Name     | `gemini-main`   |
| Provider | `gemini`        |
| Api key  | `AIza…`         |

**Assistant** (`/admin/course_crafter_plugin/assistant/add/`):

| Field          | Value                                              |
|----------------|----------------------------------------------------|
| Credentials    | `gemini-main`                                      |
| Name           | `visualization-assistant`                          |
| Temperature    | `0.7`                                              |
| Model name     | `gemini-2.5-flash`                                 |
| System input   | *(leave blank — prompt_service supplies it)*       |
| Json format    | *(leave blank)*                                    |

**AI Content creation Assistant** (`/admin/course_crafter_plugin/aicontentcreator/add/`):

| Field      | Value                     |
|------------|---------------------------|
| Course id  | `course-v1:edx+1+1` (or your test course) |
| Assistant  | `visualization-assistant` |

## 5. Enable the Advanced Component

Studio → your course → Settings → Advanced Settings → **Advanced Module List**,
add `visualization`:

```json
["visualization"]
```

Save.

## 6. Add a Visualization block to a unit

1. Studio → your course → a unit.
2. *Add new component* → **Advanced** → **Visualization**.
3. Click **Edit** on the newly added component.

The edit modal should load the Studio view of the xblock with:

- *Display name* field (default `Visualization`).
- *AI Content Assistant* panel with an empty message list, a `0 message(s)`
  counter, and a *Clear History* button.
- A prompt textarea + *Send* button.
- A *Save settings* button at the bottom.

## 7. First generation

In the prompt textarea, enter:

```
Create an interactive simulation of the Moon orbiting Earth.
Include a slider for initial velocity (0–3000 m/s) and a slider for
gravitational strength. Draw the orbit on a Canvas.
```

Press **Send** (or Enter). Expected:

- Status flips to `Status: generating`.
- User message appears immediately in the chat.
- 5–20 seconds later, an AI message with a `<pre>`-clipped HTML snippet
  appears, status returns to `idle`.

## 8. Apply + preview

Click **Apply** under the AI message. Expected:

- *Applied simulation* preview iframe appears at the bottom of the modal with
  the simulation rendered and controls interactive.
- `Last applied at` shows a UTC ISO timestamp.

Click **Save settings** (any pending display-name change persists). Close the
modal.

## 9. View as a student in LMS

Publish the unit, then open http://apps.local.openedx.io:2000/learning/course/course-v1:edx+1+1/
(adjust course id). Expected: the same simulation renders inside a sandboxed
iframe (`sandbox="allow-scripts"`), controls respond.

## 10. Chat history persists

Re-open the component's Edit modal. Expected: all prior messages are loaded
(from `course_crafter_chat.Conversation`), counter shows the correct total.

Click **Clear History**. Expected: list empties and counter goes to `0`. Close
and reopen — still empty.

## 11. Edit mode

Add a second message in chat, e.g.:

```
Add a second slider for moon mass (0.1–5 × current mass).
```

Expected: since `cached_html` is non-empty, crafter's prompt service detects
edit mode and preserves the existing structure. The new AI message should be
a *minimally-modified* version of the previous HTML, not a rewrite.

## 12. Error-path checks

The xblock's Studio JS calls crafter's REST API directly, so errors come
straight from crafter's view (DRF 400s) — shown in the red "Last error" bar
above the Save button.

**a. No AIContentCreator for course.** Temporarily delete the
`AIContentCreator` row in Django admin, then Send. Expected:
`Generation failed: Missing AI Content creation Assistant for this course.`.

**b. Invalid API key.** Edit `APICredentials.api_key` to `"invalid"`, Send.
Expected message contains `AI Content creation failed:` plus Google's
key-invalid payload.

**c. Quota exhausted (pro models on free tier).** Set `Assistant.model_name`
to `gemini-2.5-pro` and Send. Expected: error contains `429` and
`Quota exceeded for metric …` — the exact path we hit in the earlier curl
POC, now proving the provider dispatcher routes through `clients/gemini.py`.

## 13. Restore

Revert the API key, model name, and re-add the `AIContentCreator` for the
course.

## Done

If every step above passes, the integration works end-to-end:
- xblock Studio JS POSTs to `/course_crafter_plugin/api/ai-content/generate/`
- crafter's prompt service picks the new `_build_visualization_prompt`
- crafter's client dispatcher routes to `clients/gemini.py`
- content_service's non-sanitizing parser returns raw HTML
- xblock's `save_applied_html` handler persists the author-chosen result
- student view renders it in a sandboxed iframe
- chat history survives across sessions via `course_crafter_chat.Conversation`
