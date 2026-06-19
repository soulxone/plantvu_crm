# Copyright (c) 2026, Plantvu and Contributors
# MIT License. See license.txt
"""Plantvu Conversation Intelligence — AI analysis of call transcripts.

P2 of the Dynamics 365 competitive plan: Plantvu's answer to Dynamics
conversation intelligence (call summary, sentiment, objections, competitor
mentions, next step) — included, via the core call_claude choke-point.

Operates on CRM Call Log. Since Call Log has no transcript field natively, a
`pv_ci_transcript` custom field holds the transcript text (pasted by a rep or
filled by a telephony/transcription integration); the linked Note is used as a
fallback. Analysis is written back to pv_ci_* fields and the call's timeline.
"""

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

# Reuse the proven core-AI bridge (lazy resolve + graceful degradation).
from crm.api.sales_ai import _get_call_claude

DT = "CRM Call Log"

_CI_SCHEMA = {
	"type": "object",
	"properties": {
		"summary": {"type": "string"},
		"sentiment": {"type": "string", "enum": ["Positive", "Neutral", "Negative", "Mixed"]},
		"objections": {"type": "array", "items": {"type": "string"}},
		"competitor_mentions": {"type": "array", "items": {"type": "string"}},
		"next_step": {"type": "string"},
	},
	# Anthropic strict json_schema: all properties required, no min/max, additionalProperties false.
	"required": ["summary", "sentiment", "objections", "competitor_mentions", "next_step"],
	"additionalProperties": False,
}

_CI_SYSTEM = (
	"You analyze a sales call transcript for a manufacturing CRM. Return a concise "
	"3-5 sentence summary, the customer's overall sentiment, any objections raised, "
	"any competitor mentions (e.g. Microsoft Dynamics, Salesforce, Amtech, Kiwiplan, "
	"or others named), and the single recommended next step. Base everything strictly "
	"on the supplied transcript; never invent quotes, names, or commitments."
)


def _check_read(name):
	if not frappe.has_permission(DT, "read", doc=name):
		raise frappe.PermissionError(_("Not permitted to read {0} {1}").format(DT, name))


def get_transcript_text(call_log):
	"""Resolve transcript text: the pv_ci_transcript field, else the linked Note."""
	doc = frappe.get_doc(DT, call_log)
	txt = (doc.get("pv_ci_transcript") or "").strip() if doc.meta.has_field("pv_ci_transcript") else ""
	if txt:
		return txt
	note = doc.get("note")
	if note and frappe.db.exists("FCRM Note", note):
		content = frappe.db.get_value("FCRM Note", note, "content") or ""
		return frappe.utils.strip_html(content).strip()
	return ""


@frappe.whitelist()
def analyze_call_log(call_log, transcript=None):
	"""Analyze a call's transcript; writes pv_ci_* fields + a timeline note."""
	_check_read(call_log)

	# If a transcript is supplied from the UI, persist it first (when writable).
	if transcript and frappe.has_permission(DT, "write", doc=call_log) \
			and frappe.get_meta(DT).has_field("pv_ci_transcript"):
		frappe.db.set_value(DT, call_log, "pv_ci_transcript", transcript, update_modified=False)

	text = (transcript or "").strip() or get_transcript_text(call_log)
	if not text:
		frappe.throw(
			_("No transcript to analyze. Paste the call transcript into the "
			  "Transcript field (or add a Note) and try again."),
			title=_("No transcript"),
		)

	call_claude = _get_call_claude()
	out = call_claude(
		_CI_SYSTEM,
		f"Analyze this call transcript:\n\n{text[:60000]}",
		kind="summarize",
		reference_doctype=DT,
		reference_name=call_log,
		output_schema=_CI_SCHEMA,
	)
	result = out["result"]

	if frappe.has_permission(DT, "write", doc=call_log):
		meta = frappe.get_meta(DT)
		patch = {}
		if meta.has_field("pv_ci_summary"):
			patch["pv_ci_summary"] = result.get("summary")
		if meta.has_field("pv_ci_sentiment"):
			patch["pv_ci_sentiment"] = result.get("sentiment")
		if meta.has_field("pv_ci_objections"):
			patch["pv_ci_objections"] = "\n".join(result.get("objections", []))
		if meta.has_field("pv_ci_competitors"):
			patch["pv_ci_competitors"] = "\n".join(result.get("competitor_mentions", []))
		if meta.has_field("pv_ci_next_step"):
			patch["pv_ci_next_step"] = result.get("next_step")
		if meta.has_field("pv_ci_analyzed_on"):
			patch["pv_ci_analyzed_on"] = frappe.utils.now()
		if patch:
			frappe.db.set_value(DT, call_log, patch, update_modified=False)

	obj = "".join(f"<li>{frappe.utils.escape_html(o)}</li>" for o in result.get("objections", []))
	comp = ", ".join(frappe.utils.escape_html(c) for c in result.get("competitor_mentions", []))
	try:
		frappe.get_doc(DT, call_log).add_comment(
			"Comment",
			f"<b>🎧 Conversation Intelligence — {frappe.utils.escape_html(result.get('sentiment',''))}</b><br>"
			f"{frappe.utils.escape_html(result.get('summary',''))}"
			+ (f"<br><i>Objections:</i><ul>{obj}</ul>" if obj else "")
			+ (f"<br><i>Competitors:</i> {comp}" if comp else "")
			+ f"<br><i>Next:</i> {frappe.utils.escape_html(result.get('next_step',''))}",
		)
	except Exception:
		frappe.log_error(title="Conversation Intelligence timeline log failed")

	return result


def install_ci_custom_fields():
	"""Add pv_ci_* fields to CRM Call Log (idempotent)."""
	fields = [
		{"fieldname": "pv_ci_section", "label": "Conversation Intelligence",
		 "fieldtype": "Section Break", "insert_after": "telephony_medium", "collapsible": 1},
		{"fieldname": "pv_ci_transcript", "label": "Transcript", "fieldtype": "Long Text",
		 "insert_after": "pv_ci_section"},
		{"fieldname": "pv_ci_summary", "label": "AI Summary", "fieldtype": "Small Text",
		 "insert_after": "pv_ci_transcript", "read_only": 1},
		{"fieldname": "pv_ci_sentiment", "label": "Sentiment", "fieldtype": "Data",
		 "insert_after": "pv_ci_summary", "read_only": 1},
		{"fieldname": "pv_ci_objections", "label": "Objections", "fieldtype": "Small Text",
		 "insert_after": "pv_ci_sentiment", "read_only": 1},
		{"fieldname": "pv_ci_competitors", "label": "Competitor Mentions", "fieldtype": "Small Text",
		 "insert_after": "pv_ci_objections", "read_only": 1},
		{"fieldname": "pv_ci_next_step", "label": "Recommended Next Step", "fieldtype": "Small Text",
		 "insert_after": "pv_ci_competitors", "read_only": 1},
		{"fieldname": "pv_ci_analyzed_on", "label": "Analyzed On", "fieldtype": "Datetime",
		 "insert_after": "pv_ci_next_step", "read_only": 1},
	]
	create_custom_fields({DT: fields}, ignore_validate=True)
	frappe.db.commit()
