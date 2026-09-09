# List filter and presentation audit

- Library: standard difficulties include Unrated; custom labels remain available. Tag options and per-tag counts come from all visible problems before filtering or pagination. Multiple tags use OR; other filters use AND. URL state survives refresh and task navigation.
- Submission lists (personal and administrator): lifecycle state is separate from verdict. The shared verdict catalog includes partial, compile/runtime failures, resource limits, empty/incomplete results, and private details. Legacy outcome parameters remain supported. Verdict filtering classifies authorized visible metadata before pagination and total counting, in batches of 500 without loading source code. It scans matching history when a verdict is requested; ordinary unfiltered queries retain SQL pagination.
- Authoring center: existing include-archived controls cover both active and archived drafts/tasks; these lists have no enum dropdown that excludes terminal states.
- User administration: username/ID search is server-side before pagination; role editing covers user/admin/banned. The target-user selector intentionally addresses the current displayed page, not a query filter.
- Audit logs: user/problem ID conditions are applied server-side before pagination. Resource problem search runs on the full visible problem set. Public-log lookup is an ID lookup, not an enum filter.
- Test-case result options are collected from all authorized cases before case pagination. No hidden case details are used to populate options.
- Presentation: browser icons share a blue code-symbol SVG. User-facing timestamps use Beijing time to minute precision, including profile, audit tables, authoring versions and the alternate Web entry. Raw logs, code and downloads are unchanged.

Full-pass and partial-pass filters use authorized scores for both roles (success with score=counts>0, or 0<score<counts). Detailed failure filters continue to use visible case metadata; private case results are not inferred. Score filters use SQL pagination and counting.

Workflow follow-up: generation and per-draft AI instruction inputs clear only after task acceptance; original draft requirements remain saved. Failed requests retain input and the idempotency key. Navigation guards consider only connected controls in the current editable page/object; read-only submission pages and list/search controls cannot inherit another page's dirty state.

Validation includes backend verdict/permission/pagination regression tests, desktop/mobile tag selection, counts, refresh, task return, combined search and clearing; favicon and profile timestamp browser checks; frontend builds/lint, Ruff and mypy. Role-parity browser regressions cover passed filtering, clean submission navigation, real dirty-draft confirmation, save clearing and account switching; mock generation checks preserve the original requirement while clearing send inputs.
