# Copyright (c) 2026, Plantvu and Contributors
# MIT License. See license.txt
"""Plantvu Sales Sequences / Cadences — P2 of the Dynamics 365 competitive plan.

Plantvu's answer to Dynamics sequences / sales accelerator: multi-step, multi-day
outreach playbooks (Email -> wait -> Task -> Call) that reps enroll Leads/Deals
into. A scheduler runner executes due steps; AI can draft email-step copy via the
core call_claude choke-point. Drafts/sends are explicit; the runner never invents
content. Add-in clean (no core edits).

Execution model: an enrollment has current_step_index (the NEXT step to run) and
next_run (when). enroll() sets next_run = now + steps[0].wait_days. The */5 runner
executes the current step, advances the pointer, and sets next_run from the next
step's wait_days, or marks the enrollment Completed.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime, add_to_date
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from crm.api.sales_ai import _get_call_claude

ENR = "CRM Sequence Enrollment"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _target(enr_doc):
	"""(doctype, name) for the enrollment's linked Lead or Deal."""
	if enr_doc.get("lead"):
		return "CRM Lead", enr_doc.lead
	return "CRM Deal", enr_doc.deal


def _require_target_write(doctype, name):
	if doctype not in ("CRM Lead", "CRM Deal"):
		frappe.throw(_("Sequences attach to a Lead or Deal."))
	if not frappe.has_permission(doctype, "write", doc=name):
		raise frappe.PermissionError(_("Not permitted to manage sequences on {0} {1}").format(doctype, name))


def _recipient_email(doctype, name):
	return frappe.db.get_value(doctype, name, "email")


def _first_next_run(seq_doc):
	if not seq_doc.steps:
		return None
	return add_to_date(now_datetime(), days=int(seq_doc.steps[0].wait_days or 0))


def _log_line(enr, text):
	stamp = now_datetime().strftime("%Y-%m-%d %H:%M")
	enr.execution_log = ((enr.execution_log or "") + f"[{stamp}] {text}\n")[-8000:]


# --------------------------------------------------------------------------- #
# enrollment lifecycle (rep-facing)
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def enroll_record(doctype, record_name, sequence_name):
	"""Enroll a Lead/Deal into a Sequence."""
	_require_target_write(doctype, record_name)
	if not frappe.db.get_value("CRM Sequence", sequence_name, "enabled"):
		frappe.throw(_("Sequence {0} is not enabled.").format(sequence_name))
	# avoid duplicate active enrollment in the same sequence
	field = "lead" if doctype == "CRM Lead" else "deal"
	existing = frappe.db.exists(ENR, {field: record_name, "sequence": sequence_name, "status": "Active"})
	if existing:
		frappe.throw(_("Already enrolled in this sequence (active)."))

	seq = frappe.get_doc("CRM Sequence", sequence_name)
	enr = frappe.new_doc(ENR)
	enr.update({
		"sequence": sequence_name,
		field: record_name,
		"status": "Active" if seq.steps else "Completed",
		"current_step_index": 0,
		"next_run": _first_next_run(seq),
		"enrolled_on": now_datetime(),
		"enrolled_by": frappe.session.user,
	})
	_log_line(enr, f"Enrolled by {frappe.session.user}.")
	enr.insert(ignore_permissions=True)
	return {"enrollment": enr.name, "status": enr.status, "next_run": str(enr.next_run or "")}


def _set_status(enrollment, status, recompute=False):
	enr = frappe.get_doc(ENR, enrollment)
	dt, dn = _target(enr)
	_require_target_write(dt, dn)
	enr.status = status
	if status == "Abandoned":
		enr.next_run = None
	if recompute and status == "Active":
		seq = frappe.get_doc("CRM Sequence", enr.sequence)
		idx = int(enr.current_step_index or 0)
		enr.next_run = (add_to_date(now_datetime(), days=int(seq.steps[idx].wait_days or 0))
						if idx < len(seq.steps) else None)
		if enr.next_run is None:
			enr.status = "Completed"
	_log_line(enr, f"Status -> {enr.status} by {frappe.session.user}.")
	enr.save(ignore_permissions=True)
	return {"enrollment": enr.name, "status": enr.status, "next_run": str(enr.next_run or "")}


@frappe.whitelist()
def unenroll_record(enrollment):
	return _set_status(enrollment, "Abandoned")


@frappe.whitelist()
def pause_enrollment(enrollment):
	return _set_status(enrollment, "Paused")


@frappe.whitelist()
def resume_enrollment(enrollment):
	return _set_status(enrollment, "Active", recompute=True)


@frappe.whitelist()
def get_active_enrollments(doctype, name):
	"""Enrollments for a Lead/Deal, for the inline panel."""
	field = "lead" if doctype == "CRM Lead" else "deal"
	rows = frappe.get_all(
		ENR, filters={field: name},
		fields=["name", "sequence", "status", "current_step_index", "next_run"],
		order_by="creation desc",
	)
	return rows


# --------------------------------------------------------------------------- #
# step execution (scheduler + manual)
# --------------------------------------------------------------------------- #
def _execute_current(enr):
	"""Execute the enrollment's current step, then advance. Resilient: failures
	are logged and the step marked, never crashing the batch."""
	seq = frappe.get_doc("CRM Sequence", enr.sequence)
	steps = seq.steps
	idx = int(enr.current_step_index or 0)
	if idx >= len(steps):
		enr.status = "Completed"
		enr.next_run = None
		enr.save(ignore_permissions=True)
		return {"done": True}

	step = steps[idx]
	dt, dn = _target(enr)
	try:
		if step.action_type == "Email":
			_send_email(dt, dn, step, enr)
		else:  # Task or Call -> create a CRM Task reminder
			_create_task(dt, dn, step, enr)
		_log_line(enr, f"Step {idx + 1} ({step.action_type}) executed.")
	except Exception as e:
		_log_line(enr, f"Step {idx + 1} ({step.action_type}) ERROR: {str(e)[:150]}")
		frappe.log_error(title="CRM Sequence step failed")

	enr.last_executed_on = now_datetime()
	enr.last_executed_step = idx
	enr.current_step_index = idx + 1
	if enr.current_step_index < len(steps):
		enr.next_run = add_to_date(now_datetime(), days=int(steps[enr.current_step_index].wait_days or 0))
	else:
		enr.status = "Completed"
		enr.next_run = None
		_log_line(enr, "Sequence completed.")
	enr.save(ignore_permissions=True)
	return {"step": idx, "status": enr.status}


def _send_email(dt, dn, step, enr):
	email = _recipient_email(dt, dn)
	if not email:
		_log_line(enr, f"Step {step.idx}: no email on {dt} {dn} — skipped.")
		return
	target = frappe.get_doc(dt, dn)
	ctx = {"doc": target}
	subject = frappe.render_template(step.subject or "Following up", ctx)
	body = frappe.render_template(step.email_body or "", ctx)
	frappe.sendmail(
		recipients=[email],
		subject=subject,
		message=body,
		reference_doctype=dt,
		reference_name=dn,
	)


def _create_task(dt, dn, step, enr):
	title = step.task_title or (f"{step.action_type} — sequence {enr.sequence}")
	frappe.get_doc({
		"doctype": "CRM Task",
		"title": title,
		"description": step.task_description or "",
		"priority": step.task_priority or "Low",
		"status": "Backlog",
		"reference_doctype": dt,
		"reference_docname": dn,
	}).insert(ignore_permissions=True)


@frappe.whitelist()
def execute_step(enrollment):
	"""Manually run the current due step now (rep-triggered)."""
	enr = frappe.get_doc(ENR, enrollment)
	dt, dn = _target(enr)
	_require_target_write(dt, dn)
	if enr.status != "Active":
		frappe.throw(_("Enrollment is not active."))
	return _execute_current(enr)


def run_due_sequence_steps():
	"""Scheduler (*/5): execute due steps for active enrollments (batched)."""
	due = frappe.get_all(
		ENR,
		filters={"status": "Active", "next_run": ["<=", now_datetime()]},
		pluck="name",
		limit=50,
		order_by="next_run asc",
	)
	for name in due:
		try:
			_execute_current(frappe.get_doc(ENR, name))
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Sequence runner failed for {name}")


def abandon_stale_enrollments():
	"""Daily janitor: abandon enrollments stuck active > 180 days."""
	cutoff = add_to_date(now_datetime(), days=-180)
	for name in frappe.get_all(ENR, filters={"status": "Active", "enrolled_on": ["<", cutoff]}, pluck="name"):
		frappe.db.set_value(ENR, name, {"status": "Abandoned", "next_run": None})
	frappe.db.commit()


# --------------------------------------------------------------------------- #
# AI draft for an email step (rep-triggered only — never in the runner)
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def draft_email_for_step(doctype, record_name, instruction=None):
	"""Draft outreach email copy for a sequence email step, given a Lead/Deal."""
	if not frappe.has_permission(doctype, "read", doc=record_name):
		raise frappe.PermissionError()
	call_claude = _get_call_claude()
	target = frappe.get_doc(doctype, record_name)
	ctx = []
	for f in ("lead_name", "first_name", "organization", "organization_name", "industry", "status"):
		if target.get(f):
			ctx.append(f"{frappe.unscrub(f)}: {target.get(f)}")
	out = call_claude(
		"You draft a short, warm sales-cadence outreach email for a manufacturing CRM. "
		"Return a 'Subject:' line, a blank line, then a body under 150 words. Use ONLY "
		"the supplied facts; no placeholders, no invented commitments.",
		f"Record:\n" + "\n".join(ctx) + (f"\n\nInstruction: {instruction}" if instruction else ""),
		kind="draft_reply",
		reference_doctype=doctype,
		reference_name=record_name,
	)
	return {"draft": out["result"]}


# --------------------------------------------------------------------------- #
# authoring / listing (frontend)
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def list_sequences(only_enabled=False):
	filters = {"enabled": 1} if frappe.parse_json(only_enabled) else {}
	seqs = frappe.get_all("CRM Sequence", filters=filters,
						  fields=["name", "sequence_name", "enabled", "description"],
						  order_by="modified desc")
	for s in seqs:
		s["step_count"] = frappe.db.count("CRM Sequence Step", {"parent": s.name})
	return seqs


@frappe.whitelist()
def get_sequence_details(sequence_name):
	doc = frappe.get_doc("CRM Sequence", sequence_name)
	return {
		"name": doc.name, "sequence_name": doc.sequence_name,
		"enabled": doc.enabled, "description": doc.description,
		"steps": [{"action_type": s.action_type, "wait_days": s.wait_days,
				   "subject": s.subject, "email_body": s.email_body,
				   "task_title": s.task_title, "task_description": s.task_description,
				   "task_priority": s.task_priority} for s in doc.steps],
	}


@frappe.whitelist()
def save_sequence(sequence_name, steps, description=None, enabled=1, name=None):
	"""Create or update a sequence with its steps (frontend authoring)."""
	if not (frappe.has_permission("CRM Sequence", "create")
			or frappe.has_permission("CRM Sequence", "write")):
		raise frappe.PermissionError()
	steps = frappe.parse_json(steps)
	doc = frappe.get_doc("CRM Sequence", name) if name and frappe.db.exists("CRM Sequence", name) \
		else frappe.new_doc("CRM Sequence")
	doc.sequence_name = sequence_name
	doc.description = description
	doc.enabled = 1 if frappe.parse_json(enabled) else 0
	doc.set("steps", [])
	for s in steps:
		doc.append("steps", {
			"action_type": s.get("action_type") or "Email",
			"wait_days": s.get("wait_days") or 0,
			"subject": s.get("subject"), "email_body": s.get("email_body"),
			"task_title": s.get("task_title"), "task_description": s.get("task_description"),
			"task_priority": s.get("task_priority") or "Low",
		})
	doc.save(ignore_permissions=True)
	return {"name": doc.name}


# --------------------------------------------------------------------------- #
# doc_event handlers (lightweight)
# --------------------------------------------------------------------------- #
def clear_sequence_cache(doc, method=None):
	frappe.cache().delete_value("crm_sequences")


def on_enrollment_insert(doc, method=None):
	pass


def on_enrollment_update(doc, method=None):
	pass


# --------------------------------------------------------------------------- #
# install
# --------------------------------------------------------------------------- #
def install_sequence_custom_fields():
	"""Inline enrollment section on Lead/Deal (chained after the Sales-AI section)."""
	common = [
		{"fieldname": "pv_sequence_section", "label": "Sales Sequences",
		 "fieldtype": "Section Break", "insert_after": "pv_ai_next_action", "collapsible": 1},
		{"fieldname": "pv_active_sequences", "label": "Active Sequences", "fieldtype": "Small Text",
		 "insert_after": "pv_sequence_section", "read_only": 1},
	]
	create_custom_fields({"CRM Lead": common, "CRM Deal": common}, ignore_validate=True)
	frappe.db.commit()
