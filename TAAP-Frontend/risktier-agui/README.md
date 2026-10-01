# Risk Tier Agent — AGUI components (React)

React implementation of the four Level 2/AGUI panels from the Risk Tier
Agent architecture: three built from the reorganized HTML prototype
(`agui_reorg/`), plus a fourth — Run Console — added to trigger a run and
show live sub-agent status. Each panel is an independent component with
its own data fetch, its own local state, and its own scoped CSS — matching
how Spider's Workbench will actually host them (mounted separately, not as
pages of one app).

## Run it

```
npm install
npm run dev       # local dev server with hot reload
npm run build     # production build, output in dist/
npm run preview   # serve the production build locally
```

`App.tsx` is a **local dev/demo shell only** — it is not part of what ships
to Spider. It tabs between each panel alone and a combined view (labeled
"All three, as Spider would mount them") so you can confirm every panel
truly works standalone before it's embedded anywhere. In the real
Workbench, Spider's own shell decides layout and placement.

## Structure

```
src/
  types/testCase.ts            Shared data shapes (TestCase, Factor, ExclusionStatement, AuditEntry...)
  data/mockTests.ts            Async "fetch" functions standing in for the real agent endpoints
  data/mockAuditLog.ts
  lib/aguiEvents.ts            Cross-panel signal: agui:navigate-to-signoff
  lib/runStatusBus.ts          Mock run-status stream: RUN_STARTED / per-agent status / RUN_FINISHED
  components/
    RunConsole/                AGUI Panel — Run Console (trigger a run, watch sub-agent status)
    TestSelectionReport/       AGUI Panel — Test Selection & Risk Report
    ExclusionSignoffQueue/     AGUI Panel — Exclusion Sign-off
    ExecutionAuditLog/         AGUI Panel — Execution Audit Log
  App.tsx                      Local dev shell (not shipped)
```

## Design decisions worth knowing about

**State management.** Each panel that has related pieces of state changing
together uses `useReducer` (`TestSelectionReport`: filter + search +
selected test + list/detail view; `ExclusionSignoffQueue`: queue + modal +
submit status). `ExecutionAuditLog` is read-only, so plain `useState` is
enough there — no need for a heavier state library anywhere in this build.

**Data layer.** `fetchAllTests()`, `fetchPendingExclusions()`, and
`fetchAuditLog()` in `src/data/` are written as `Promise`-returning
functions on purpose, so swapping in a real
`fetch("/agui/risk-tier/...")` call — or wrapping them in TanStack Query
once there's a real backend worth caching against, or pointing them at
MSW-mocked responses for testing — is a change at the call site, not a
component rewrite.

**No router.** None of the three panels use React Router. Each is meant to
be mounted on its own wherever Spider puts it, not navigated to as a
"page." The tab switcher in `App.tsx` is plain `useState`, since it only
exists for local development.

**Cross-panel communication.** `TestSelectionReport` and
`ExclusionSignoffQueue` never import each other or share state, but a user
can click through from a test's exclusion detail to its sign-off entry.
That's handled by `src/lib/aguiEvents.ts`, a thin typed wrapper around a
`CustomEvent` on `window`. It's a placeholder for whatever cross-panel
signal Spider's AGUI host contract actually provides — worth confirming
with the platform team — but it keeps the two components decoupled either
way, since neither one imports the other's internals.

**Responsive layout via CSS container queries, not `@media`.** Every panel
uses `container-type: inline-size` and `@container` breakpoints instead of
viewport-based `@media` breakpoints. This matters specifically because
Spider decides how wide a slot each panel gets — a full page, one of
several panels side by side, a narrow sidebar — independent of the
browser window's size. `TestSelectionReport`'s test table collapses into
stacked cards below ~720px of *panel* width (not window width), which is
what keeps it readable when, say, three panels end up sharing one screen.

**TypeScript.** Used throughout given the nested shapes involved (a test
case's `factors` array, its optional `exclusion` statement, etc.) — the
type errors it catches here are exactly the class of bug that's easy to
miss by eye in a shape this nested.

**Run Console — a structured trigger, not an open-ended chatbot.** The
only input it takes is a release ID; "sending" it just starts the Master
Orchestrator's existing pipeline (BR-ORC-01). No natural-language
understanding is involved, and none of the other three panels' scope
changed to support it. It's styled as a chat thread because that's a
natural way to show a running log of status updates, not because it
answers arbitrary questions — see the Run Console architecture addendum
for the reasoning behind that scope choice.

**How the other three panels learn a run happened.** `runStatusBus.ts`
mocks the status stream Run Console would really receive from the
Orchestrator via the AGUI Gateway (most likely SSE, matching how AGUI
already streams agent state to the browser). `startRun()` fires a scripted
timeline of `AgentStatus` events — Agents 1–4 in parallel, then Agent 5,
then Agent 6, then a ledger write — matching the release pipeline's real
sequencing. TestSelectionReport listens for Agent 5 finishing,
ExclusionSignoffQueue for Agent 6, and ExecutionAuditLog for the ledger
write (it aggregates all agents' decisions, so it refreshes on the
pipeline's last step, not on any one agent). Each panel calls `onAgentFinished`
directly from `runStatusBus.ts` — none of them import RunConsole or each
other, so the "independently mounted panels" principle holds even with
this new cross-cutting signal. A brief background-flash animation (see
each panel's own `.css`) is the only visual proof-of-refresh added; the
mock data itself doesn't change, since the point of this pass is to prove
the wiring, not to fabricate new results.

## Next steps

- Point the functions in `src/data/` at real endpoints once the
  Risk-Based Test Selection & Scoring Agent and the Exclusion Risk &
  Governance Agent expose them (Section 6, Agent Card & Endpoint Design).
- Confirm with the Spider platform team how cross-panel signals are meant
  to travel in production, and adjust `src/lib/aguiEvents.ts` accordingly.
- Replace `src/lib/runStatusBus.ts`'s scripted timeline with a real
  subscription to the Orchestrator's status stream through the AGUI
  Gateway once that endpoint exists — the event shapes (`AgentStatusDetail`,
  `RunLifecycleDetail`) are written to match what that stream should emit.
- Bring in MSW for local development against more realistic mocked
  network conditions (latency, errors) once there's a real API shape to
  mock against.
