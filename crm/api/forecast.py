# Copyright (c) 2026, Plantvu and Contributors
# MIT License. See license.txt
"""Plantvu Weighted Pipeline Forecast — P2 of the Dynamics 365 competitive plan.

Plantvu's answer to Dynamics forecasting: weighted pipeline (deal_value x
probability), best/likely/commit scenarios, gap-to-quota, and an AI narrative —
all over the deals the user is permitted to see (org-hierarchy scoped via
frappe.get_list). Values are normalized to the base/company currency using each
deal's exchange_rate.
"""

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from crm.api.sales_ai import _get_call_claude

COMMIT_THRESHOLD = 75  # probability >= this counts as "commit"


def _status_map():
	"""status name -> (type, probability)."""
	out = {}
	for s in frappe.get_all("CRM Deal Status", fields=["name", "type", "probability"]):
		out[s.name] = (s.get("type"), s.get("probability") or 0)
	return out


def _base_value(d):
	val = d.get("deal_value") or d.get("expected_deal_value") or 0
	rate = d.get("exchange_rate") or 1
	try:
		return float(val) * float(rate or 1)
	except Exception:
		return 0.0


@frappe.whitelist()
def get_forecast(from_date=None, to_date=None, owner=None):
	"""Weighted pipeline forecast over permitted, open deals.

	Returns scenarios (pipeline/likely/best/commit), won-this-period, and
	breakdowns by owner, stage, and close-month, plus quota/gap if quotas exist.
	"""
	filters = {}
	if owner:
		filters["deal_owner"] = owner
	if from_date and to_date:
		filters["expected_closure_date"] = ["between", [from_date, to_date]]

	deals = frappe.get_list(
		"CRM Deal",
		filters=filters,
		fields=["name", "deal_value", "expected_deal_value", "exchange_rate",
				"probability", "status", "deal_owner", "expected_closure_date",
				"organization", "currency", "pv_forecast_included"],
		limit_page_length=0,
	)

	smap = _status_map()
	pipeline = likely = best = commit = won = 0.0
	by_owner, by_stage, by_month = {}, {}, {}
	open_count = won_count = 0

	for d in deals:
		stype, sprob = smap.get(d.get("status"), (None, 0))
		base = _base_value(d)
		if stype == "Won":
			won += base
			won_count += 1
			continue
		if stype == "Lost":
			continue
		if d.get("pv_forecast_included") == 0:  # explicitly excluded by a rep (NULL/1 = included)
			continue
		# open deal
		open_count += 1
		prob = d.get("probability")
		if prob in (None, 0):
			prob = sprob
		w = base * (float(prob or 0) / 100.0)
		pipeline += base
		likely += w
		best += base
		if (prob or 0) >= COMMIT_THRESHOLD:
			commit += base
		o = d.get("deal_owner") or "Unassigned"
		by_owner[o] = by_owner.get(o, 0) + w
		st = d.get("status") or "Unknown"
		by_stage[st] = by_stage.get(st, 0) + w
		mo = str(d.get("expected_closure_date") or "")[:7] or "Unscheduled"
		by_month[mo] = by_month.get(mo, 0) + w

	# quota / gap (sum quotas matching the period window owners, best-effort)
	quota = 0.0
	for q in frappe.get_all("CRM Forecast Quota",
							filters={"forecast_owner": owner} if owner else {},
							fields=["quota_amount"]):
		quota += float(q.get("quota_amount") or 0)

	def rows(dct):
		return sorted(({"key": k, "value": round(v, 2)} for k, v in dct.items()),
					  key=lambda r: -r["value"])

	return {
		"scenarios": {
			"pipeline": round(pipeline, 2),
			"likely": round(likely, 2),
			"best": round(best, 2),
			"commit": round(commit, 2),
			"won": round(won, 2),
		},
		"counts": {"open": open_count, "won": won_count},
		"quota": round(quota, 2),
		"gap_to_quota": round(quota - (likely + won), 2) if quota else None,
		"by_owner": rows(by_owner),
		"by_stage": rows(by_stage),
		"by_month": sorted(({"key": k, "value": round(v, 2)} for k, v in by_month.items()),
						   key=lambda r: r["key"]),
		"currency": frappe.defaults.get_global_default("currency") or "USD",
	}


@frappe.whitelist()
def get_forecast_narrative(from_date=None, to_date=None, owner=None):
	"""AI narrative over the current forecast: strengths, risks, recommended focus."""
	# FCRM Settings is a Single doctype (no tab table) -> use meta.has_field, not has_column.
	if frappe.get_meta("FCRM Settings").has_field("pv_enable_ai_forecast_narrative"):
		val = frappe.db.get_single_value("FCRM Settings", "pv_enable_ai_forecast_narrative")
		if val is not None and not val:  # unset -> default enabled; explicit 0 -> off
			return {"narrative": _("AI forecast narrative is turned off in CRM Settings.")}
	data = get_forecast(from_date, to_date, owner)
	call_claude = _get_call_claude()
	import json
	out = call_claude(
		"You are a sales forecasting analyst for a manufacturing CRM. Given the "
		"weighted-pipeline figures and breakdowns, write a tight 3-5 sentence "
		"narrative: how healthy the forecast is vs. quota, where the strength is, "
		"the biggest risks (concentration, thin commit, slipping months), and the "
		"single highest-leverage focus this period. Base it strictly on the numbers.",
		json.dumps(data),
		kind="agent",
		max_tokens=900,
	)
	return {"narrative": out["result"], "data": data}


def install_forecast_custom_fields():
	"""pv_forecast_included on CRM Deal + pv_enable_ai_forecast_narrative on FCRM Settings."""
	create_custom_fields({
		"CRM Deal": [{
			"fieldname": "pv_forecast_included", "label": "Include in Forecast",
			"fieldtype": "Check", "default": "1", "insert_after": "probability",
		}],
		"FCRM Settings": [{
			"fieldname": "pv_enable_ai_forecast_narrative", "label": "Enable AI Forecast Narrative",
			"fieldtype": "Check", "default": "1", "insert_after": "update_timestamp_on_new_communication",
		}],
	}, ignore_validate=True)
	frappe.db.commit()
