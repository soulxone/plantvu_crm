# Copyright (c) 2026, Plantvu and contributors
"""Battle Cards — competitor intelligence tied to the CRM map.

Enter a competitor with an ADDRESS (geocoded so it places inside coverage rings /
zones), then optionally "Create battle card" to AI-generate the talk track via the
core Plantvu AI choke-point (Danczyk). Cards are saved per rep/manager and listed
for competitors inside a selected ring/zone — to get a new rep up to speed fast.

Flag-gated: crm.battle_cards (Control-Plane). Degrades gracefully when the AI
engine isn't configured (you can still save competitors + write cards by hand).
"""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime, flt

from crm.api import maps        # _require_crm_user, _haversine_mi, _point_in_polygon
from crm.api import enrichment  # _server_key


def _bc_on():
    try:
        from plantvu.control.features import is_on
        return is_on("crm.battle_cards", True)
    except Exception:
        return True


def _guard():
    maps._require_crm_user()
    if not _bc_on():
        frappe.throw(_("Battle Cards are turned off in the Control-Plane."))


def _get_call_claude():
    try:
        from plantvu.ai.client import call_claude  # type: ignore
        return call_claude
    except Exception:
        return None


def _geocode(parts, key):
    """Geocode an address string to (lat, lng) via Google Geocoding (server key)."""
    addr = ", ".join([p for p in parts if p])
    if not addr or not key:
        return None, None
    import requests
    try:
        r = requests.get("https://maps.googleapis.com/maps/api/geocode/json",
                         params={"address": addr, "key": key}, timeout=12).json()
        res = r.get("results") or []
        if res:
            loc = res[0]["geometry"]["location"]
            return loc.get("lat"), loc.get("lng")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "battlecards.geocode")
    return None, None


# ── CRUD ─────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def save_battlecard(payload):
    """Create or update a Battle Card. Geocodes the entered address to lat/lng."""
    _guard()
    data = json.loads(payload) if isinstance(payload, str) else dict(payload)
    name = data.get("name")
    doc = frappe.get_doc("CRM Battle Card", name) if name and frappe.db.exists("CRM Battle Card", name) \
        else frappe.new_doc("CRM Battle Card")
    for f in ("competitor_name", "website", "industry", "territory", "shared_scope",
              "address_line1", "address_line2", "city", "state", "pincode", "country",
              "overview", "how_we_win", "watch_outs", "proof_points", "notes"):
        if f in data:
            doc.set(f, data.get(f))
    if not doc.owner_user:
        doc.owner_user = frappe.session.user
    # geocode the address so the competitor places on the map / inside rings+zones
    lat, lng = _geocode([doc.address_line1, doc.city, doc.state, doc.pincode, doc.country],
                        enrichment._server_key())
    if lat is not None:
        doc.latitude, doc.longitude = lat, lng
    doc.save(ignore_permissions=False)
    frappe.db.commit()
    return {"name": doc.name, "latitude": doc.latitude, "longitude": doc.longitude,
            "geocoded": lat is not None}


_CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "overview": {"type": "string", "description": "2-3 sentences: who this competitor is"},
        "how_we_win": {"type": "string", "description": "bullet talk-track of where we beat them"},
        "watch_outs": {"type": "string", "description": "where they are strong + objections to expect"},
        "proof_points": {"type": "string", "description": "concrete proof points / discovery questions"},
    },
    "required": ["overview", "how_we_win", "watch_outs", "proof_points"],
}

_CARD_SYSTEM = (
    "You are Danczyk, a Plantvu sales strategist. Produce a concise, practical competitive "
    "BATTLE CARD a sales rep can use in the field against the named competitor. Be specific and "
    "honest; if you are unsure of a fact, frame it as a discovery question rather than asserting it. "
    "Plantvu sells a unified manufacturing platform (CRM + projects + quality + corrugated MES + "
    "portal + AI). Tailor 'how we win' to that where relevant, but keep it credible."
)


@frappe.whitelist()
def generate_battlecard(name):
    """AI-generate the battle-card content for a saved competitor (Danczyk)."""
    _guard()
    doc = frappe.get_doc("CRM Battle Card", name)
    call_claude = _get_call_claude()
    if not call_claude:
        return {"error": _("Plantvu Assist (AI) isn't configured — fill the card in manually.")}
    loc = ", ".join([p for p in (doc.city, doc.state) if p])
    user = (f"Competitor: {doc.competitor_name}\n"
            f"Website: {doc.website or 'unknown'}\n"
            f"Industry/segment: {doc.industry or 'unknown'}\n"
            f"Location: {loc or 'unknown'}\n\n"
            "Write the battle card sections.")
    try:
        out = call_claude(_CARD_SYSTEM, user, kind="agent",
                          reference_doctype="CRM Battle Card", reference_name=name,
                          output_schema=_CARD_SCHEMA)
        res = out.get("result") if isinstance(out, dict) else None
    except Exception:
        frappe.log_error(frappe.get_traceback(), "battlecards.generate")
        return {"error": _("AI generation failed — try again or fill in manually.")}
    if not res:
        return {"error": _("No content generated.")}
    doc.overview = res.get("overview")
    doc.how_we_win = res.get("how_we_win")
    doc.watch_outs = res.get("watch_outs")
    doc.proof_points = res.get("proof_points")
    doc.ai_generated = 1
    doc.last_generated = now_datetime()
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"name": name, "data": res}


@frappe.whitelist()
def get_battlecard(name):
    _guard()
    d = frappe.get_doc("CRM Battle Card", name)
    return {k: d.get(k) for k in
            ("name", "competitor_name", "website", "industry", "territory", "shared_scope",
             "address_line1", "address_line2", "city", "state", "pincode", "country",
             "latitude", "longitude", "overview", "how_we_win", "watch_outs", "proof_points",
             "ai_generated", "last_generated", "notes", "owner_user")}


def _visible_filter():
    """Respect shared_scope: Just Me -> only owner; Team/Everyone -> all readable."""
    user = frappe.session.user
    return ["`tabCRM Battle Card`.shared_scope != 'Just Me' OR `tabCRM Battle Card`.owner_user = %(u)s",
            {"u": user}]


@frappe.whitelist()
def list_battlecards():
    """All battle cards the user may see (sharing-aware)."""
    _guard()
    user = frappe.session.user
    rows = frappe.get_all("CRM Battle Card",
        filters=None, or_filters=[["shared_scope", "!=", "Just Me"], ["owner_user", "=", user]],
        fields=["name", "competitor_name", "industry", "city", "state", "latitude", "longitude",
                "ai_generated", "shared_scope", "owner_user"],
        order_by="competitor_name asc", limit_page_length=0)
    return rows


@frappe.whitelist()
def list_in_area(scope_type, scope):
    """Battle cards whose competitor location falls inside a ring or zone."""
    _guard()
    scope = json.loads(scope) if isinstance(scope, str) else scope
    cards = list_battlecards()
    out = []
    for c in cards:
        if c.get("latitude") is None or c.get("longitude") is None:
            continue
        lat, lng = flt(c["latitude"]), flt(c["longitude"])
        if scope_type == "ring":
            if maps._haversine_mi(flt(scope["lat"]), flt(scope["lng"]), lat, lng) <= flt(scope["radius_mi"]):
                out.append(c)
        elif scope_type == "zone":
            if maps._point_in_polygon(lat, lng, scope.get("points") or []):
                out.append(c)
    return out


@frappe.whitelist()
def delete_battlecard(name):
    _guard()
    frappe.delete_doc("CRM Battle Card", name)
    frappe.db.commit()
    return {"deleted": name}
