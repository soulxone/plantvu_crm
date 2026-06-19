# Copyright (c) 2026, Plantvu and Contributors
# MIT License. See license.txt
"""Plantvu Sales AI — Claude-native sales assistance inside the CRM.

This is Plantvu's answer to Microsoft Dynamics 365 Sales' AI agents
(Sales Qualification Agent, predictive scoring, Copilot email drafting) — but
included rather than metered by Copilot Credits, and able to reason over the
operational data (jobs, quality, history) a standalone CRM can't see.

Every model call goes through the *core* Plantvu choke-point
``plantvu.ai.client.call_claude`` so guardrails, model selection, token caps,
and the ``PV Agent Run`` audit trail are shared with the rest of the platform.
When the core ``plantvu`` app (or its AI config) is absent, every endpoint
degrades cleanly with a clear, actionable message instead of a stack trace.

Endpoints (all permission-checked against the underlying record):
    - score_record(doctype, name)        -> AI fit/intent score, written back
    - qualify_lead(name)                 -> Sales Qualification Agent
    - compose_email(doctype, name, ...)  -> Copilot-style draft (never auto-sends)
    - summarize_thread(doctype, name)    -> recent-communication digest

Custom fields are installed on CRM Lead / CRM Deal by
``install_sales_ai_custom_fields`` (wired into after_install + a patch).
"""

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

SUPPORTED = ("CRM Lead", "CRM Deal")

# Fields we send to the model as context, per doctype. Kept explicit so we never
# leak unexpected columns and so the prompt stays small and cache-friendly.
_CONTEXT_FIELDS = {
	"CRM Lead": [
		"lead_name", "first_name", "last_name", "job_title", "organization",
		"industry", "website", "email", "mobile_no", "phone", "status", "source",
		"no_of_employees", "annual_revenue", "territory", "lead_owner",
	],
	"CRM Deal": [
		"organization", "organization_name", "industry", "website", "email",
		"mobile_no", "status", "source", "deal_value", "expected_deal_value",
		"expected_closure_date", "probability", "next_step", "no_of_employees",
		"annual_revenue", "territory", "deal_owner", "lead_name",
	],
}


# --------------------------------------------------------------------------- #
# Core bridge + guards
# --------------------------------------------------------------------------- #
def _get_call_claude():
	"""Resolve the core Plantvu AI choke-point, or raise a clean error.

	plantvu_crm is an add-in: the AI brain lives in the core ``plantvu`` app and
	is shared platform-wide. We resolve it lazily so the CRM still installs and
	runs on benches where core AI isn't present."""
	try:
		from plantvu.ai.client import call_claude  # type: ignore
	except Exception:
		frappe.throw(
			_("Plantvu Assist (the AI engine) isn't available on this site. "
			  "Install the Plantvu core app and set an Anthropic API key to "
			  "enable Sales AI."),
			title=_("Sales AI unavailable"),
		)
	return call_claude


def _check_read(doctype, name):
	if doctype not in SUPPORTED:
		frappe.throw(_("Sales AI supports {0}.").format(", ".join(SUPPORTED)))
	if not frappe.has_permission(doctype, "read", doc=name):
		raise frappe.PermissionError(_("Not permitted to read {0} {1}").format(doctype, name))


def _record_context(doctype, name):
	"""Build a compact, human-readable context block for the model from the
	whitelisted fields, skipping empties."""
	doc = frappe.get_doc(doctype, name)
	lines = []
	for f in _CONTEXT_FIELDS.get(doctype, []):
		val = doc.get(f)
		if val in (None, "", 0):
			continue
		label = frappe.unscrub(f)
		lines.append(f"- {label}: {val}")
	# Linked operational context — this is Plantvu's edge over a standalone CRM.
	lines.append(f"- Record type: {doctype}")
	return doc, "\n".join(lines) if lines else "- (no details captured yet)"


def _recent_communications(doctype, name, limit=8):
	"""Pull the last few emails/comments on the record for context."""
	rows = frappe.get_all(
		"Communication",
		filters={"reference_doctype": doctype, "reference_name": name},
		fields=["communication_date", "sender", "subject", "content"],
		order_by="creation desc",
		limit=limit,
	)
	out = []
	for r in reversed(rows):
		body = frappe.utils.strip_html(r.get("content") or "")[:600]
		out.append(f"[{r.get('communication_date')}] {r.get('sender')} — "
				   f"{r.get('subject') or '(no subject)'}\n{body}")
	return "\n\n".join(out)


def _log(doctype, name, html):
	"""Add an AI note to the record's activity timeline (best-effort)."""
	try:
		frappe.get_doc(doctype, name).add_comment("Comment", html)
	except Exception:
		frappe.log_error(title="Sales AI timeline log failed")


# --------------------------------------------------------------------------- #
# 1) AI Lead / Deal scoring  (counters Dynamics predictive scoring)
# --------------------------------------------------------------------------- #
_SCORE_SCHEMA = {
	"type": "object",
	"properties": {
		"score": {"type": "integer", "minimum": 0, "maximum": 100},
		"tier": {"type": "string", "enum": ["Hot", "Warm", "Cool", "Cold"]},
		"summary": {"type": "string"},
		"reasons": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
		"risks": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
		"next_action": {"type": "string"},
	},
	"required": ["score", "tier", "summary", "reasons", "next_action"],
	"additionalProperties": False,
}

_SCORE_SYSTEM = (
	"You are Plantvu's sales scoring engine for a manufacturing CRM. Given a "
	"lead or deal, return a 0-100 fit/intent score, a tier, a one-line summary, "
	"up to 5 concrete reasons, key risks, and the single best next action. "
	"Plantvu sells an all-in-one manufacturing operating system (CRM + ERP + "
	"quality + shop-floor). Reward manufacturers (esp. corrugated/packaging), "
	"clear budget/authority/need/timeline signals, and operational fit. Be "
	"calibrated and honest — do not inflate scores. Base everything strictly on "
	"the supplied facts; never invent details."
)


@frappe.whitelist()
def score_record(doctype, name):
	"""AI fit/intent score for a Lead/Deal; written back to pv_ai_* fields."""
	_check_read(doctype, name)
	call_claude = _get_call_claude()
	doc, ctx = _record_context(doctype, name)

	out = call_claude(
		_SCORE_SYSTEM,
		f"Score this {doctype}:\n\n{ctx}",
		kind="agent",  # core PV Agent Run allows: ask/summarize/extract_action_items/draft_reply/automation/agent
		reference_doctype=doctype,
		reference_name=name,
		output_schema=_SCORE_SCHEMA,
	)
	result = out["result"]

	# Write back only if the custom fields exist and the user can write.
	if frappe.has_permission(doctype, "write", doc=name):
		meta = frappe.get_meta(doctype)
		patch = {}
		if meta.has_field("pv_ai_score"):
			patch["pv_ai_score"] = result.get("score")
		if meta.has_field("pv_ai_tier"):
			patch["pv_ai_tier"] = result.get("tier")
		if meta.has_field("pv_ai_summary"):
			patch["pv_ai_summary"] = result.get("summary")
		if meta.has_field("pv_ai_next_action"):
			patch["pv_ai_next_action"] = result.get("next_action")
		if meta.has_field("pv_ai_scored_on"):
			patch["pv_ai_scored_on"] = frappe.utils.now()
		if patch:
			frappe.db.set_value(doctype, name, patch, update_modified=False)

	reasons = "".join(f"<li>{frappe.utils.escape_html(r)}</li>" for r in result.get("reasons", []))
	_log(doctype, name,
		 f"<b>🤖 Plantvu Sales AI — score {result.get('score')}/100 "
		 f"({result.get('tier')})</b><br>{frappe.utils.escape_html(result.get('summary',''))}"
		 f"<ul>{reasons}</ul>"
		 f"<i>Next:</i> {frappe.utils.escape_html(result.get('next_action',''))}")
	return result


# --------------------------------------------------------------------------- #
# 2) Sales Qualification Agent  (counters Dynamics Sales Qualification Agent)
# --------------------------------------------------------------------------- #
_QUALIFY_SCHEMA = {
	"type": "object",
	"properties": {
		"qualification": {
			"type": "object",
			"properties": {
				"budget": {"type": "string"},
				"authority": {"type": "string"},
				"need": {"type": "string"},
				"timeline": {"type": "string"},
				"verdict": {"type": "string", "enum": ["Qualified", "Nurture", "Disqualify"]},
			},
			"required": ["budget", "authority", "need", "timeline", "verdict"],
			"additionalProperties": False,
		},
		"competitor_talking_points": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
		"recommended_next_action": {"type": "string"},
		"draft_email": {
			"type": "object",
			"properties": {"subject": {"type": "string"}, "body": {"type": "string"}},
			"required": ["subject", "body"],
			"additionalProperties": False,
		},
	},
	"required": ["qualification", "recommended_next_action", "draft_email"],
	"additionalProperties": False,
}

_QUALIFY_SYSTEM = (
	"You are Plantvu's Sales Qualification Agent for a manufacturing CRM. Given a "
	"lead and its recent activity, do four things: (1) assess BANT — budget, "
	"authority, need, timeline — and give a verdict (Qualified / Nurture / "
	"Disqualify); (2) give up to 5 talking points for positioning Plantvu's "
	"all-in-one manufacturing platform vs. a standalone CRM like Microsoft "
	"Dynamics 365 (one platform vs CRM+ERP integration; AI included vs Copilot "
	"Credits; faster, lower TCO; manufacturing depth); (3) recommend the single "
	"best next action; (4) draft a short, warm, specific outreach email (subject "
	"+ body) the rep can send after a quick edit. Use ONLY the supplied facts; "
	"never fabricate names, numbers, or commitments. Keep the email under 150 words."
)


@frappe.whitelist()
def qualify_lead(name):
	"""Autonomously research/qualify a lead and draft outreach. Never auto-sends."""
	_check_read("CRM Lead", name)
	call_claude = _get_call_claude()
	doc, ctx = _record_context("CRM Lead", name)
	comms = _recent_communications("CRM Lead", name)
	user = f"Qualify this lead:\n\n{ctx}"
	if comms:
		user += f"\n\nRecent activity:\n{comms}"

	out = call_claude(
		_QUALIFY_SYSTEM, user,
		kind="agent",
		reference_doctype="CRM Lead",
		reference_name=name,
		output_schema=_QUALIFY_SCHEMA,
	)
	result = out["result"]
	q = result.get("qualification", {})
	tp = "".join(f"<li>{frappe.utils.escape_html(p)}</li>"
				 for p in result.get("competitor_talking_points", []))
	_log("CRM Lead", name,
		 f"<b>🤖 Sales Qualification Agent — {frappe.utils.escape_html(q.get('verdict','?'))}</b><br>"
		 f"<b>Budget:</b> {frappe.utils.escape_html(q.get('budget',''))}<br>"
		 f"<b>Authority:</b> {frappe.utils.escape_html(q.get('authority',''))}<br>"
		 f"<b>Need:</b> {frappe.utils.escape_html(q.get('need',''))}<br>"
		 f"<b>Timeline:</b> {frappe.utils.escape_html(q.get('timeline',''))}<br>"
		 f"<i>Talking points:</i><ul>{tp}</ul>"
		 f"<i>Next:</i> {frappe.utils.escape_html(result.get('recommended_next_action',''))}")
	return result


# --------------------------------------------------------------------------- #
# 3) Email / reply composer  (counters Copilot in Outlook)
# --------------------------------------------------------------------------- #
_COMPOSE_SYSTEM = (
	"You are Plantvu's sales email assistant for a manufacturing CRM. Write a "
	"clear, friendly, concise business email for a salesperson based on the "
	"record context, recent thread, and the rep's instruction. Return the email "
	"as: a 'Subject:' line, a blank line, then the body. Keep it under 180 "
	"words, no placeholder brackets, ready to send after a quick read. Use ONLY "
	"supplied facts; never invent commitments, prices, or dates."
)


@frappe.whitelist()
def compose_email(doctype, name, instruction, tone="professional"):
	"""Copilot-style draft email/reply. Returns text; never sends."""
	_check_read(doctype, name)
	call_claude = _get_call_claude()
	doc, ctx = _record_context(doctype, name)
	comms = _recent_communications(doctype, name)
	user = (f"Record context:\n{ctx}\n\n"
			f"Tone: {tone}\n"
			f"Rep instruction: {instruction}")
	if comms:
		user += f"\n\nRecent thread:\n{comms}"

	out = call_claude(
		_COMPOSE_SYSTEM, user,
		kind="draft_reply",
		reference_doctype=doctype,
		reference_name=name,
	)
	return {"draft": out["result"]}


@frappe.whitelist()
def summarize_thread(doctype, name):
	"""Summarize recent communications + suggest next steps."""
	_check_read(doctype, name)
	call_claude = _get_call_claude()
	comms = _recent_communications(doctype, name, limit=12)
	if not comms:
		return {"summary": _("No communications to summarize yet.")}
	out = call_claude(
		"You summarize a sales conversation thread for a manufacturing CRM. "
		"Give a 3-5 bullet summary, the customer's apparent sentiment, any "
		"objections or competitor mentions, and the recommended next step. "
		"Base everything strictly on the supplied messages.",
		f"Thread for {doctype} {name}:\n\n{comms}",
		kind="summarize",
		reference_doctype=doctype,
		reference_name=name,
	)
	return {"summary": out["result"]}


# --------------------------------------------------------------------------- #
# Install — custom fields on Lead/Deal
# --------------------------------------------------------------------------- #
def install_sales_ai_custom_fields():
	"""Add the pv_ai_* score fields to CRM Lead and CRM Deal (idempotent)."""
	common = [
		{"fieldname": "pv_sales_ai_section", "label": "Plantvu Sales AI",
		 "fieldtype": "Section Break", "insert_after": "status", "collapsible": 1},
		{"fieldname": "pv_ai_score", "label": "AI Score", "fieldtype": "Int",
		 "insert_after": "pv_sales_ai_section", "read_only": 1, "in_list_view": 0},
		{"fieldname": "pv_ai_tier", "label": "AI Tier", "fieldtype": "Data",
		 "insert_after": "pv_ai_score", "read_only": 1},
		{"fieldname": "pv_ai_col", "fieldtype": "Column Break", "insert_after": "pv_ai_tier"},
		{"fieldname": "pv_ai_scored_on", "label": "AI Scored On", "fieldtype": "Datetime",
		 "insert_after": "pv_ai_col", "read_only": 1},
		{"fieldname": "pv_ai_summary", "label": "AI Summary", "fieldtype": "Small Text",
		 "insert_after": "pv_ai_scored_on", "read_only": 1},
		{"fieldname": "pv_ai_next_action", "label": "AI Next Action", "fieldtype": "Small Text",
		 "insert_after": "pv_ai_summary", "read_only": 1},
	]
	create_custom_fields({"CRM Lead": common, "CRM Deal": common}, ignore_validate=True)
	frappe.db.commit()
