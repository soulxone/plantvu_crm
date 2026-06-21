# Copyright (c) 2026, Plantvu and contributors
"""
AI best-route-by-cost — "Danczyk" plans the smartest visit order for a set of
selected map stops.

The frontend first computes a *geographically* optimal order (Google Directions
``optimizeWaypoints``) and the real drive miles. This endpoint layers BUSINESS
VALUE on top: it enriches each stop with CRM context (deal value, status, stage)
and asks the core Plantvu AI to recommend the visit order that best balances
drive cost against revenue/urgency — returning the order, a rationale, per-stop
notes, and a cost estimate.

Degrades gracefully: if the core AI engine (anthropic key) isn't present, it
returns the geo-optimal order with a computed, non-AI rationale so the feature
still works everywhere.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, cint

from crm.api import maps  # _require_crm_user, permission helpers

# US IRS standard mileage rate ($/mi) — used to turn drive miles into a $ figure.
DEFAULT_MILE_RATE = 0.67


def _get_call_claude():
    """Resolve the core Plantvu AI choke-point, or None if unavailable."""
    try:
        from plantvu.ai.client import call_claude  # type: ignore
        return call_claude
    except Exception:
        return None


def _stop_context(stop):
    """Enrich one stop ({id: 'Doctype::name', kind, label, lat, lng}) with light
    CRM business signals so the AI can weigh value against drive cost."""
    sid = stop.get("id") or ""
    doctype, _, name = sid.partition("::")
    ctx = {"value": 0, "status": "", "extra": ""}
    try:
        if doctype == "CRM Deal" and name:
            d = frappe.db.get_value(
                "CRM Deal", name,
                ["annual_revenue", "status", "probability", "close_date"],
                as_dict=True) or {}
            ctx["value"] = flt(d.get("annual_revenue"))
            ctx["status"] = d.get("status") or ""
            bits = []
            if d.get("probability"):
                bits.append(f"{cint(d['probability'])}% prob")
            if d.get("close_date"):
                bits.append(f"closes {d['close_date']}")
            ctx["extra"] = ", ".join(bits)
        elif doctype == "CRM Lead" and name:
            d = frappe.db.get_value(
                "CRM Lead", name, ["status", "annual_revenue"], as_dict=True) or {}
            ctx["status"] = d.get("status") or ""
            ctx["value"] = flt(d.get("annual_revenue"))
        elif doctype == "Customer" and name:
            ctx["status"] = "existing customer"
    except Exception:
        pass
    return ctx


_ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "order": {"type": "array", "items": {"type": "string"},
                  "description": "Stop ids in the recommended visit order"},
        "rationale": {"type": "string",
                      "description": "2-4 sentence explanation of the plan and the cost/value tradeoff"},
        "stops": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"},
            "note": {"type": "string", "description": "one short reason this stop sits where it does"},
            "priority": {"type": "string", "enum": ["high", "medium", "low"]},
        }, "required": ["id"]}},
        "deferred": {"type": "array", "items": {"type": "string"},
                     "description": "stop ids worth dropping from this trip (low value + far out of the way)"},
    },
    "required": ["order", "rationale"],
}

_ROUTE_SYSTEM = (
    "You are Danczyk, Plantvu's sales operations strategist. You plan the smartest "
    "field-visit route for a sales rep. You are given a set of stops already ordered "
    "for geographic efficiency (shortest drive), each with CRM business context. "
    "Recommend the visit order that best balances DRIVE COST against BUSINESS VALUE: "
    "keep the route efficient, but pull high-value or time-sensitive deals earlier so "
    "they aren't lost if the day runs short, and flag low-value stops that are far out "
    "of the way as candidates to defer. Be decisive and concrete. Only reorder when the "
    "business value justifies the extra drive; otherwise keep the efficient order."
)


@frappe.whitelist()
def plan_smart_route(stops, total_miles=0, mile_rate=None, home_label=None):
    """Return an AI-recommended visit order + rationale + cost for the given stops.

    ``stops`` is a JSON list (already in geo-optimal order) of
    ``{id, kind, label, lat, lng}``. ``total_miles`` is the real drive distance
    the frontend measured for that order.
    """
    maps._require_crm_user()
    if isinstance(stops, str):
        stops = json.loads(stops)
    if not stops:
        return {"error": _("No stops to plan.")}

    rate = flt(mile_rate) or DEFAULT_MILE_RATE
    miles = flt(total_miles)
    est_cost = round(miles * rate, 2)

    # enrich with business context
    enriched = []
    for s in stops:
        c = _stop_context(s)
        enriched.append({
            "id": s.get("id"), "label": s.get("label") or s.get("id"),
            "kind": s.get("kind"), "value": c["value"], "status": c["status"],
            "extra": c["extra"],
        })

    call_claude = _get_call_claude()
    ids_in = [e["id"] for e in enriched]

    if not call_claude:
        # graceful, non-AI fallback: keep geo-optimal order, computed rationale
        total_value = sum(e["value"] for e in enriched)
        return {
            "ai_used": False,
            "order": ids_in,
            "rationale": _(
                "Geo-optimal order ({n} stops, {mi} mi ≈ ${cost} at ${rate}/mi). "
                "Connect Plantvu Assist (Anthropic key) to let Danczyk re-rank by deal value."
            ).format(n=len(ids_in), mi=round(miles), cost=est_cost, rate=rate),
            "stops": [{"id": e["id"], "note": "", "priority": "medium"} for e in enriched],
            "deferred": [],
            "total_miles": round(miles, 1),
            "total_value": total_value,
            "est_cost": est_cost,
            "mile_rate": rate,
        }

    lines = []
    for i, e in enumerate(enriched, 1):
        val = f"${int(e['value']):,}" if e["value"] else "—"
        extra = f" ({e['extra']})" if e["extra"] else ""
        st = f" [{e['status']}]" if e["status"] else ""
        lines.append(f"{i}. id={e['id']} | {e['label']} | {e['kind']} | value={val}{st}{extra}")
    user = (
        f"Stops (geo-optimal order, total ~{round(miles)} mi ≈ ${est_cost} at ${rate}/mi):\n"
        + "\n".join(lines)
        + "\n\nReturn the recommended visit order (by id), a short rationale, a per-stop "
        "note + priority, and any stops worth deferring."
    )

    try:
        out = call_claude(_ROUTE_SYSTEM, user, kind="agent", output_schema=_ROUTE_SCHEMA)
        result = out.get("result") if isinstance(out, dict) else None
    except Exception:
        frappe.log_error(frappe.get_traceback(), "routing.plan_smart_route")
        result = None

    if not result or not result.get("order"):
        # AI failed → fall back to geo order, still useful
        return {
            "ai_used": False,
            "order": ids_in,
            "rationale": _("Geo-optimal order ({n} stops, {mi} mi ≈ ${cost}).").format(
                n=len(ids_in), mi=round(miles), cost=est_cost),
            "stops": [{"id": e["id"], "note": "", "priority": "medium"} for e in enriched],
            "deferred": [],
            "total_miles": round(miles, 1), "est_cost": est_cost, "mile_rate": rate,
        }

    # keep only ids we actually sent (guard against hallucinated ids), preserve AI order
    valid = set(ids_in)
    order = [i for i in result.get("order", []) if i in valid]
    for i in ids_in:  # append any the AI dropped from order (but not explicitly deferred)
        if i not in order and i not in (result.get("deferred") or []):
            order.append(i)

    return {
        "ai_used": True,
        "order": order,
        "rationale": result.get("rationale", ""),
        "stops": result.get("stops", []),
        "deferred": [i for i in (result.get("deferred") or []) if i in valid],
        "total_miles": round(miles, 1),
        "total_value": sum(e["value"] for e in enriched),
        "est_cost": est_cost,
        "mile_rate": rate,
    }
