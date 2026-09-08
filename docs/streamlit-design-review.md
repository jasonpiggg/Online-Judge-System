# Streamlit final interface review

The native Streamlit interface follows the existing React white-and-blue design direction. Changes are confined to Streamlit pages, its browser bridge, and acceptance tests. React source, shared renderers, REST contracts, permissions, and publication gates are unchanged.

## Design and navigation

- A 1200px workspace, 880px reading surface, 800px account page and 440px login form share the same typography and spacing system.
- Desktop navigation aligns with the content; the fixed header has an opaque background and a clear gap before the brand row. Mobile retains the native navigation drawer.
- Task tabs scroll horizontally on desktop and become a selector on mobile. Returning to a root page clears selection while retaining the last detail route. Forty tasks remain bounded; closing is disabled without an active task.
- Library, submission, resource, draft and task listings use aligned rows. The vertical workspace has statement, editor and result panels, a compact editor toolbar and a save/submit footer.
- Evaluation completion is distinguished from acceptance. Verdict, score and available case counts are grouped; timestamps use Beijing time. Private details remain unavailable.
- Assistant/history and authoring list tabs use explicit open state for deferred rendering. Existing task polling stops at terminal states; opening a panel does not create a paid model request.

## Feature comparison with React

| Capability | Streamlit coverage | Verification |
| --- | --- | --- |
| Authentication, registration, deep links, account isolation | Cookie bridge, password confirmation, UTF-8 boundary, logout and identity restoration | Auth tests and browser registration/account flows |
| Editing and evaluation | Local Monaco, Markdown/math, samples/copy, language/font controls, import/export, autosave, conflict resolution, result detail, source restoration and rejudge | Browser editor, submission, import and two-tab flows |
| AI problem generation | Requirement/reference input, workflow v2, generation stages, cost details, final draft, failed candidate recovery and archive | Deterministic generation/recovery browser flows |
| AI assisted authoring | Scoped revision, test design, full review, complete generation, candidate Diff and explicit adoption with revision guards | Scoped review browser flow and backend workflow tests |
| Draft lifecycle | Incomplete saves, JSON import/export, versions, assets, basic/full verification, publication gates and archive | AppTest, browser publish/revision flows and backend tests |
| AI solving assistant | Quick prompts, source/submission context, full-solution option, streaming, restored history, cancellation, candidates, Diff, download, adoption and undo | Assistant stream/history/stale/undo/cancel browser flows |
| Administration/resources | Language registration, model settings, roles, audit, public logs, problem management and reset confirmation | Resource/admin/permission tests |

Feature equivalence means the same supported workflows and API capabilities, not identical widgets. Streamlit uses native controls and a vertical layout. Its stale-code guard intentionally requires copying a fragment or asking again when the source has changed, rather than allowing an old answer to overwrite newer code. Both interfaces still require reviewing generated content and passing the existing publication checks.

## State and request safety

Python and browser draft equivalence ignore only empty form defaults. Literal whitespace, zero, false and list ordering remain meaningful. Multiline case inputs synchronize on blur into the same payload used by save and browser backup. Invalid attachment JSON remains editable. Version conflicts never silently overwrite either copy.

AI authoring and assistant retries retain an idempotency key until a response succeeds or the request changes. No automatic model retry was added. Browser restoration uses persistent component state so responsive reruns cannot consume a one-shot restoration signal.

## Acceptance evidence and limits

`web/streamlit/e2e/design.spec.ts` checks login and thirteen page surfaces at 1440, 1024, 390 and 320px, document/content overflow, mobile controls, header alignment, sticky navigation, task activation, forty tasks and multiline backup recovery. `parity.spec.ts` exercises the functional workflows listed above, including failure, cancellation, deleted problems, private logs and concurrent edits. Code/data areas may scroll locally.

Local verification includes the full Python suite, Ruff, mypy, React unit tests/build, Streamlit bridge unit tests/build, ESLint and Playwright. CI runs both React and Streamlit browser suites. Browser AI tests use the isolated deterministic provider fixture; they verify UI behavior and API integration without charging a live model. They do not certify output quality for every external provider. Ten environment-dependent Python tests are skipped locally and are reported as skipped, not passed.

Representative isolated-fixture screenshots are retained for review:

- [Desktop library and aligned header](screenshots/streamlit-final/library-desktop.png)
- [320px library](screenshots/streamlit-final/library-mobile.png)
- [Editor panel and pinned section navigation](screenshots/streamlit-final/editor-desktop.png)

The complete screenshot set is generated in Playwright output directories. No user database, real credentials, model configuration, logs or temporary traces are committed.
