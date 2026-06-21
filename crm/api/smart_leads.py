# Copyright (c) 2026, Plantvu and contributors
"""Smart Leads — territory-scoped prospecting off the CRM map.

Select a coverage RING (plant center + radius) or a ZONE (polygon); we search
Google Places for prospect businesses inside that area, dedupe against existing
Leads/Customers/Organizations, and (on confirm) create them as CRM Leads flagged
``custom_smart_lead`` + source "Smart Lead" + a "Smart Lead" tag so they stand
out on the map and lead list.

Server-side Places calls use the dedicated google_maps_server_key (the browser
key is referrer-restricted). Flag-gated: crm.smart_leads.
"""

import json
import math

import frappe
from frappe import _
from frappe.utils import cint, flt

from crm.api import maps        # _require_manager, _haversine_mi, _point_in_polygon
from crm.api import enrichment  # _server_key


def _sl_on():
    try:
        from plantvu.control.features import is_on
        return is_on("crm.smart_leads", True)
    except Exception:
        return True


def _guard():
    maps._require_manager()
    if not _sl_on():
        frappe.throw(_("Smart Leads is turned off in the Control-Plane."))


def _norm(name):
    """Canonical company name for dedup (lower, strip punctuation + common suffixes)."""
    s = (name or "").lower()
    for ch in ",.&'\"-/()":
        s = s.replace(ch, " ")
    toks = [t for t in s.split() if t not in ("inc", "llc", "corp", "co", "company",
                                              "ltd", "the", "incorporated", "group")]
    return " ".join(toks).strip()


def _places_nearby(lat, lng, radius_m, key, keyword=None):
    import requests
    params = {"location": f"{lat},{lng}", "radius": min(int(radius_m), 50000), "key": key}
    if keyword:
        params["keyword"] = keyword
    try:
        r = requests.get("https://maps.googleapis.com/maps/api/place/nearbysearch/json",
                         params=params, timeout=15).json()
        return r.get("results") or []
    except Exception:
        frappe.log_error(frappe.get_traceback(), "smart_leads.nearby")
        return []


def _existing_names():
    """Set of normalized names already in the CRM (Leads/Customers/Organizations)."""
    names = set()
    try:
        for r in frappe.get_all("CRM Lead", fields=["lead_name", "organization"], limit_page_length=0):
            names.add(_norm(r.get("organization") or r.get("lead_name")))
    except Exception:
        pass
    for dt, field in (("Customer", "customer_name"), ("CRM Organization", "organization_name")):
        try:
            for r in frappe.get_all(dt, fields=[field], limit_page_length=0):
                names.add(_norm(r.get(field)))
        except Exception:
            pass
    names.discard("")
    return names


def _in_scope(scope_type, scope, lat, lng):
    if scope_type == "ring":
        return maps._haversine_mi(flt(scope["lat"]), flt(scope["lng"]), lat, lng) <= flt(scope["radius_mi"])
    if scope_type == "zone":
        return maps._point_in_polygon(lat, lng, scope.get("points") or [])
    return False


def _center_radius(scope_type, scope):
    if scope_type == "ring":
        return flt(scope["lat"]), flt(scope["lng"]), flt(scope["radius_mi"]) * 1609.34
    pts = scope.get("points") or []
    lats = [p[0] for p in pts]; lngs = [p[1] for p in pts]
    clat, clng = sum(lats) / len(lats), sum(lngs) / len(lngs)
    rad = max(maps._haversine_mi(clat, clng, p[0], p[1]) for p in pts) * 1609.34
    return clat, clng, min(rad, 50000)


@frappe.whitelist()
def discover(scope_type, scope, keyword=None, limit=40):
    """Find prospect businesses inside a ring/zone (no writes). Returns candidates."""
    _guard()
    key = enrichment._server_key()
    if not key:
        frappe.throw(_("Set a Google Maps Server Key in CRM Settings → Map first."))
    scope = json.loads(scope) if isinstance(scope, str) else scope
    clat, clng, radius_m = _center_radius(scope_type, scope)
    raw = _places_nearby(clat, clng, radius_m, key, keyword)
    existing = _existing_names()
    seen, fresh = set(), []
    for r in raw:
        loc = (r.get("geometry") or {}).get("location") or {}
        lat, lng = loc.get("lat"), loc.get("lng")
        if lat is None or not _in_scope(scope_type, scope, lat, lng):
            continue
        nm = _norm(r.get("name"))
        if not nm or nm in existing or nm in seen:
            continue
        seen.add(nm)
        fresh.append({
            "place_id": r.get("place_id"), "name": r.get("name"),
            "address": r.get("vicinity") or "", "lat": lat, "lng": lng,
            "category": ", ".join((r.get("types") or [])[:3]).replace("_", " "),
            "rating": r.get("rating"), "reviews": r.get("user_ratings_total"),
        })
        if len(fresh) >= cint(limit):
            break
    return {"candidates": fresh, "found": len(raw), "fresh": len(fresh)}


@frappe.whitelist()
def create_leads(candidates, assign_rep=None):
    """Create the chosen candidates as CRM Leads tagged Smart Lead."""
    _guard()
    candidates = json.loads(candidates) if isinstance(candidates, str) else candidates
    meta = frappe.get_meta("CRM Lead")
    existing = _existing_names()
    created = []
    for c in candidates:
        if _norm(c.get("name")) in existing:
            continue
        doc = frappe.new_doc("CRM Lead")
        doc.lead_name = c.get("name")
        if meta.has_field("organization"):
            doc.organization = c.get("name")
        if meta.has_field("source"):
            doc.source = "Smart Lead"
        if meta.has_field("custom_smart_lead"):
            doc.custom_smart_lead = 1
        if meta.has_field("custom_place_id") and c.get("place_id"):
            doc.custom_place_id = c.get("place_id")
        if assign_rep and meta.has_field("lead_owner"):
            doc.lead_owner = assign_rep
        # stash the discovered address into the map address fields if present
        af = maps._lead_addr_fields(meta)
        if af.get("address_line1") and c.get("address"):
            doc.set(af["address_line1"], c.get("address"))
        try:
            doc.insert(ignore_permissions=False)
            try:
                from frappe.desk.doctype.tag.tag import add_tag
                add_tag("Smart Lead", "CRM Lead", doc.name)
            except Exception:
                pass
            created.append(doc.name)
            existing.add(_norm(c.get("name")))
        except Exception:
            frappe.log_error(frappe.get_traceback(), "smart_leads.create")
    frappe.db.commit()
    return {"created": created, "count": len(created)}
