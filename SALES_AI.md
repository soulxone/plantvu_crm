# Plantvu Sales AI (`crm/api/sales_ai.py`)

Claude-native sales assistance inside the CRM — Plantvu's answer to Microsoft
Dynamics 365 Sales' AI agents, **included** rather than metered by Copilot
Credits, and able to reason over operational data (jobs, quality, history) a
standalone CRM can't see.

Every model call goes through the core choke-point
`plantvu.ai.client.call_claude`, so guardrails, model/effort selection, daily
token caps, and the `PV Agent Run` audit trail are shared platform-wide. When
the core `plantvu` app (or its API key) is absent, every endpoint degrades with
a clear message instead of a stack trace.

## Endpoints (whitelisted, permission-checked)

| Method | Purpose | Counters in Dynamics |
|---|---|---|
| `crm.api.sales_ai.score_record(doctype, name)` | 0–100 fit/intent score + tier + reasons + next action, written back to `pv_ai_*` | Predictive lead/opportunity scoring |
| `crm.api.sales_ai.qualify_lead(name)` | BANT verdict + competitor talking points + recommended action + draft email | **Sales Qualification Agent** (their flagship) |
| `crm.api.sales_ai.compose_email(doctype, name, instruction, tone)` | Copilot-style draft email/reply (returns text, never sends) | Copilot in Outlook |
| `crm.api.sales_ai.summarize_thread(doctype, name)` | Thread digest, sentiment, objections, next step | Conversation intelligence (partial) |

`score_record` and `qualify_lead` use a JSON output schema (structured/parsed);
`compose_email` and `summarize_thread` return prose.

## Custom fields (CRM Lead + CRM Deal)

`pv_ai_score` (Int), `pv_ai_tier` (Data), `pv_ai_summary` (Small Text),
`pv_ai_next_action` (Small Text), `pv_ai_scored_on` (Datetime), under a
collapsible **Plantvu Sales AI** section. Installed idempotently via
`install_sales_ai_custom_fields()`, wired into `after_install`
(`crm/install.py`) and the patch `add_sales_ai_custom_fields`.

## Safety / design

- **Add-in clean:** lives entirely in `crm.api.sales_ai`; no core edits; the AI
  brain stays in the `plantvu` core app and is resolved lazily.
- **Grounded prompts:** every system prompt instructs "use only supplied facts,
  never fabricate." Email/qualification drafts are returned for human review and
  **never auto-sent**.
- **Permission-gated:** read checked before any call; write-back only when the
  user has write permission and the fields exist.
- **No secrets:** API key lives in site config, read only inside core
  `call_claude`.

## Tests

`crm/tests/test_sales_ai.py` mocks the core choke-point (offline, no tokens):
field install, context building (no column leakage), score write-back, schema
forwarding, prose vs structured, and unsupported-doctype rejection.

```bash
bench --site <site> run-tests --module crm.tests.test_sales_ai
```

## Next (P2/P3)

Sales sequences/cadences, conversation intelligence over Call Log, weighted
pipeline forecast view, guided selling, Outlook/Teams/LinkedIn bridges — see
`docs/25-plantvu-vs-dynamics-competitive-plan.md`.
