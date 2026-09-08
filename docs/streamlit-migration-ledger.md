# Streamlit migration ledger

This ledger is the acceptance checklist for the native Streamlit entry. React remains in `web/` and uses the same REST APIs.

| React surface / scenario | Streamlit entry and equivalent interaction | Evidence |
| --- | --- | --- |
| Login, registration, confirmation, rate limit, disabled account, deep links | `frontend/account.py` auth form plus local auth bridge; HttpOnly cookie and `/api/auth/me` restore | `tests/test_streamlit_auth.py`; `parity.spec.ts` registration/reload |
| Library search, difficulty/progress filters, guide, pagination | `frontend/library.py` native controls and URL query state | AppTest + responsive Playwright |
| Problem statement, samples, limits, tags, custom levels | `frontend/workspace.py` safe Markdown component and native metadata | workspace browser flow |
| Monaco editor, font size, language, import/export, autosave, revision conflict | `frontend/components.py` local bundled Monaco bridge and `source_editor` | autosave/reload + two-tab conflict Playwright |
| Submission, polling, score/verdict, diagnostics, case filters, source restore | `frontend/records.py` fragments and paginated detail | submission detail browser flow; backend regression |
| Assistant streaming, history, cancel, candidates, Diff, stale guard, undo | `frontend/assistant.py` conversation REST client and local Diff/Markdown controls | assistant browser flow; parity AppTest |
| Draft fields, JSON import/export, revisions, archive, basic/full verify, publish | `frontend/forms.py`, `frontend/authoring.py` | draft/revision/verification AppTest and browser flow |
| AI task stages, usage/cost, source/result, recovery and archive | `frontend/authoring.py::task_page` | isolated mock task browser flow |
| Resources, language registration, public logs, problem import/delete/visibility | `frontend/resources.py`, `frontend/admin.py` | resource and permission browser flows |
| Admin users, roles, submissions, audit, reset confirmation | `frontend/admin.py` guarded sections | backend permission tests and admin browser flow |
| Task tabs, back/close/origin, URL filters/pages, scroll and account isolation | `frontend/navigation.py` plus `state` bridge | navigation/account browser flows |
| Markdown/math/highlighting/copy/Diff/mobile/reduced motion | local `web/streamlit/entry.tsx` bundle and scoped CSS | no-CDN and 1440/1024/390/320 checks |

Known intentional compatibility notes are recorded in `docs/experiment-compatibility.md`: the unique-admin guard, safe language command policy, deleted-problem rejudge guard, and the authenticated language API extension.
