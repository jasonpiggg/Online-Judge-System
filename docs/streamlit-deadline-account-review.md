# Streamlit task limits and account improvements

## Scope and design

Streamlit only; the React application is unchanged. Preserve the programming workspace's blue/white visual language: accent #2563eb, ink #1d293d, muted #617087, surface #f5f8fe, border #e3eaf3, white canvas. Keep system Chinese typography and monospace code. Align statement content with the workspace edge, preserve the existing 1200px page container, and preserve readable paragraph spacing and semantic list markers.

The navigation layout is: count → first/previous → nearby pages → next/last → page jump. Both ends of each nonempty paginated list expose the same URL-backed state; empty lists show one contextual message without pagination. Always show first/last numbered pages plus the current page and up to two neighbors in each direction, with ellipses for gaps; show every page when at most five exist. Three groups span the available content width and wrap when needed. Native controls wrap on narrow screens and preserve keyboard focus. Existing components and tokens are reused; there is no Figma source in this repository.

## Execution contract

All assistant and authoring operations inherit the shared task runner. Its effective budget is `min(240, configured timeout)` seconds, including time since task creation. The default is now 240 seconds. Legacy larger environment overrides remain parseable but cannot increase the effective limit. Stage calls, concurrency waits, verification and repair stay inside that budget. Expired queued work does not start a provider call. Cancellation unwinds the existing provider transport and subprocess cleanup; observed usage and usable partial results survive failure.

This is a bounded execution policy, not a guarantee that an external provider will successfully solve every request. Provider failures, cancellation cleanup, database availability and process/event-loop outages cannot be made into successful model answers by a timeout setting. No paid benchmark or real provider call was performed. Existing provider/model/pricing configuration is preserved instead of assigning an unverified model identifier to arbitrary endpoints.

## Account and interaction changes

Password changes require the authenticated identity and current password, share the login attempt limiter, validate bcrypt's UTF-8 byte limit, update with a compare-and-swap guard, and revoke other sessions transactionally. The current session remains valid. Password fields clear after submission and are never logged.

Unauthenticated navigation is hidden. Password fields use Streamlit's single reveal button; the redundant checkbox and Edge reveal are removed. Clear-all closes navigation tabs without cancelling background work; dirty state prompts before clearing, and local draft backups remain available.

## Automated design review

- Frictionless: nearby pages, direct jump, paired pagers, account password update, and clear-all tabs reduce repeated navigation.
- Quality craft: full-width statements, in-bounds semantic lists, native accessible controls, wrapped mobile layout, and reduced-motion support.
- Trustworthy: AI timing is derived from persisted timestamps, terminal failure is explicit, and existing AI verification/cost disclosures remain.

Validation includes password/session security tests, task cancellation and expired-queue tests, AppTest paired-page navigation, full Python tests, Ruff, mypy, and Streamlit browser checks at 1440, 1024, 390 and 320 pixels. Final results are recorded in the PR. Chromium is visually checked; Edge's proprietary reveal pseudo-element is suppressed in CSS but not executed in an Edge browser test.
