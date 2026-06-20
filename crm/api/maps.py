# Copyright (c) 2026, Plantvu and contributors
# For license information, please see license.txt
"""
Plantvu CRM — Map API.

Powers the in-CRM map for Leads + Customers (CRM Organizations) + Deals, the
per-sales-rep "my customers" travel view, and the admin map configuration.

Records are scoped to the logged-in rep unless the user is a manager (Sales
Manager / System Manager), who may view everyone or filter by rep. The Google
Maps key is served from FCRM Settings so it is never hard-coded in the SPA; it
must be HTTP-referrer-restricted in Google Cloud (the key is public by design
when used with the Maps JavaScript / Extended Component Library).
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt

GEO_CACHE_KEY = "crm_map_geocode_cache"

KINDS = {
	"lead": {"label": "Lead", "color": "#FF9800"},
	"organization": {"label": "Customer", "color": "#0B9E92"},
	"deal": {"label": "Deal", "color": "#3F51B5"},
	"contact": {"label": "Contact", "color": "#9C27B0"},
}


# ── permission helpers ──────────────────────────────────────────────────────

def _is_manager():
	roles = set(frappe.get_roles())
	return bool(roles & {"System Manager", "Sales Manager", "Sales Master Manager"})


def _require_crm_user():
	if frappe.session.user == "Guest":
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _settings():
	return frappe.get_cached_doc("FCRM Settings")


def _api_key():
	s = _settings()
	# Password fieldtype — read decrypted via get_password
	try:
		return s.get_password("google_maps_api_key", raise_exception=False) or ""
	except Exception:
		return getattr(s, "google_maps_api_key", "") or ""


# ── geocoding ───────────────────────────────────────────────────────────────

def _has(meta, fieldname):
	try:
		return bool(meta.has_field(fieldname))
	except Exception:
		return False


def _addr_str(addr):
	parts = [
		addr.get("address_line1"),
		addr.get("address_line2"),
		addr.get("city"),
		" ".join(p for p in [addr.get("state"), addr.get("pincode")] if p),
		addr.get("country"),
	]
	return ", ".join(p.strip() for p in parts if p and str(p).strip())


def _address_for(link_doctype, link_name):
	"""Primary linked Address one-line string (Dynamic Link pattern)."""
	try:
		links = frappe.get_all(
			"Dynamic Link",
			filters={"parenttype": "Address", "link_doctype": link_doctype, "link_name": link_name},
			fields=["parent"],
			limit=5,
		)
	except Exception:
		return ""
	best = ""
	for link in links:
		addr = frappe.db.get_value(
			"Address", link.parent,
			["address_line1", "address_line2", "city", "state", "pincode",
			 "country", "is_primary_address"], as_dict=True)
		if not addr:
			continue
		line = _addr_str(addr)
		if not line:
			continue
		if addr.get("is_primary_address"):
			return line
		best = best or line
	return best


# ── record collectors ───────────────────────────────────────────────────────

def _lead_addr_fields(meta):
	out = {}
	cand = {
		"address_line1": ["custom_address_line1", "custom_address", "address_line1"],
		"address_line2": ["custom_address_line2", "address_line2"],
		"city": ["custom_city", "city"],
		"state": ["custom_state", "state"],
		"pincode": ["custom_pincode", "pincode"],
		"country": ["custom_country", "country"],
	}
	for key, names in cand.items():
		for n in names:
			if _has(meta, n):
				out[key] = n
				break
	return out


def _collect_leads(rep, limit):
	if not frappe.db.exists("DocType", "CRM Lead"):
		return []
	meta = frappe.get_meta("CRM Lead")
	af = _lead_addr_fields(meta)
	fields = ["name", "lead_name", "organization", "status", "lead_owner"]
	fields = [f for f in fields if f == "name" or _has(meta, f)]
	if _has(meta, "territory"):
		fields.append("territory")
	fields += list(af.values())
	filters = {}
	if _has(meta, "converted"):
		filters["converted"] = 0
	if rep:
		filters["lead_owner"] = rep
	out = []
	for r in frappe.get_all("CRM Lead", fields=fields, filters=filters, limit=limit):
		addr = _addr_str({k: r.get(v) for k, v in af.items()}) if af else ""
		if not addr and r.get("organization"):
			addr = r.get("organization")
		out.append({
			"id": f"CRM Lead::{r.name}",
			"kind": "lead",
			"label": r.get("organization") or r.get("lead_name") or r.name,
			"sublabel": r.get("lead_name") or "",
			"address": addr,
			"status": r.get("status") or "New",
			"owner": r.get("lead_owner") or "",
			"territory": r.get("territory") or "",
			"route": f"/crm/leads/{r.name}",
		})
	return out


def _collect_organizations(rep, limit):
	if not frappe.db.exists("DocType", "CRM Organization"):
		return []
	meta = frappe.get_meta("CRM Organization")
	fields = ["name", "organization_name"]
	for f in ("territory", "industry", "address"):
		if _has(meta, f):
			fields.append(f)
	owner_field = "owner"  # CRM Organization has no rep owner; use document owner
	if _has(meta, owner_field):
		fields.append(owner_field)
	rows = frappe.get_all("CRM Organization", fields=fields, limit=limit)
	addr_cache = {}
	out = []
	for r in rows:
		o = r.get("owner") or ""
		if rep and o != rep:
			continue
		addr = ""
		if r.get("address"):
			if r.address not in addr_cache:
				ad = frappe.db.get_value(
					"Address", r.address,
					["address_line1", "address_line2", "city", "state", "pincode", "country"],
					as_dict=True)
				addr_cache[r.address] = _addr_str(ad) if ad else ""
			addr = addr_cache[r.address]
		if not addr:
			addr = _address_for("CRM Organization", r.name)
		out.append({
			"id": f"CRM Organization::{r.name}",
			"kind": "organization",
			"label": r.get("organization_name") or r.name,
			"sublabel": r.get("industry") or "",
			"address": addr,
			"status": "Customer",
			"owner": o,
			"territory": r.get("territory") or "",
			"route": f"/crm/organizations/{r.name}",
		})
	return out


def _collect_deals(rep, limit):
	if not frappe.db.exists("DocType", "CRM Deal"):
		return []
	meta = frappe.get_meta("CRM Deal")
	fields = ["name", "organization", "deal_owner", "status"]
	fields = [f for f in fields if f == "name" or _has(meta, f)]
	if _has(meta, "territory"):
		fields.append("territory")
	filters = {}
	if rep:
		filters["deal_owner"] = rep
	rows = frappe.get_all("CRM Deal", fields=fields, filters=filters, limit=limit)
	org_addr = {}
	out = []
	for r in rows:
		org = r.get("organization")
		addr = ""
		if org:
			if org not in org_addr:
				a = ""
				link = frappe.db.get_value("CRM Organization", org, "address")
				if link:
					ad = frappe.db.get_value(
						"Address", link,
						["address_line1", "address_line2", "city", "state", "pincode", "country"],
						as_dict=True)
					a = _addr_str(ad) if ad else ""
				org_addr[org] = a
			addr = org_addr[org]
		out.append({
			"id": f"CRM Deal::{r.name}",
			"kind": "deal",
			"label": org or r.name,
			"sublabel": r.get("status") or "",
			"address": addr,
			"status": r.get("status") or "Open",
			"owner": r.get("deal_owner") or "",
			"territory": r.get("territory") or "",
			"route": f"/crm/deals/{r.name}",
		})
	return out


# ── whitelisted endpoints ───────────────────────────────────────────────────

@frappe.whitelist()
def get_map_settings():
	"""Key, map id, home base, manager flag, and rep list for the map page."""
	_require_crm_user()
	s = _settings()
	is_mgr = _is_manager()
	reps = get_sales_reps() if is_mgr else []
	return {
		"api_key": _api_key(),
		"map_id": getattr(s, "google_maps_map_id", "") or "",
		"home": {
			"address": getattr(s, "map_home_address", "") or "",
			"lat": flt(getattr(s, "map_home_latitude", 0)) or None,
			"lng": flt(getattr(s, "map_home_longitude", 0)) or None,
		},
		"is_manager": is_mgr,
		"current_user": frappe.session.user,
		"kinds": KINDS,
		"reps": reps,
	}


@frappe.whitelist()
def get_sales_reps():
	_require_crm_user()
	ids = set()
	for dt, field in (("CRM Lead", "lead_owner"), ("CRM Deal", "deal_owner")):
		if not frappe.db.exists("DocType", dt):
			continue
		try:
			for row in frappe.get_all(dt, fields=[field], filters={field: ["is", "set"]}, distinct=True):
				if row.get(field):
					ids.add(row[field])
		except Exception:
			pass
	out = []
	for rep in sorted(ids):
		name = frappe.db.get_value("User", rep, "full_name") or rep
		out.append({"id": rep, "name": name})
	return out


@frappe.whitelist()
def get_map_records(rep=None, kinds=None):
	"""Typed map records. Non-managers are always scoped to their own records."""
	_require_crm_user()
	if isinstance(kinds, str):
		kinds = [k.strip() for k in kinds.replace("[", "").replace("]", "").replace('"', "").split(",") if k.strip()]
	wanted = set(kinds) if kinds else {"lead", "organization", "deal"}

	# enforce per-rep scoping for non-managers
	if not _is_manager():
		rep = frappe.session.user
	rep = (rep or "").strip() or None

	limit = 5000
	records = []
	if "lead" in wanted:
		records += _collect_leads(rep, limit)
	if "organization" in wanted:
		records += _collect_organizations(rep, limit)
	if "deal" in wanted:
		records += _collect_deals(rep, limit)

	cache = frappe.cache().get_value(GEO_CACHE_KEY) or {}
	mapped = 0
	for r in records:
		coords = cache.get((r.get("address") or "").strip())
		if coords:
			r["lat"], r["lng"] = coords.get("lat"), coords.get("lng")
			mapped += 1
		else:
			r["lat"], r["lng"] = None, None

	return {
		"records": records,
		"total": len(records),
		"mapped": mapped,
		"pending_geocode": sum(1 for r in records if r["lat"] is None and r.get("address")),
		"scoped_to": rep,
	}


@frappe.whitelist()
def save_geocodes(resolved):
	"""Persist browser-resolved coordinates to the shared cache (no Google call).

	The SPA geocodes in the browser under the referrer-restricted key, then posts
	``{address: {lat, lng}}`` here so coords survive reloads and are shared across
	users. This makes a single, fully-restricted key sufficient (no server key).
	"""
	_require_crm_user()
	if isinstance(resolved, str):
		try:
			resolved = json.loads(resolved)
		except Exception:
			return {"saved": 0}
	if not isinstance(resolved, dict):
		return {"saved": 0}
	cache = frappe.cache().get_value(GEO_CACHE_KEY) or {}
	saved = 0
	for addr, coords in resolved.items():
		a = (addr or "").strip()
		if not a or not isinstance(coords, dict):
			continue
		lat, lng = coords.get("lat"), coords.get("lng")
		if lat is None or lng is None:
			continue
		cache[a] = {"lat": flt(lat), "lng": flt(lng)}
		saved += 1
	frappe.cache().set_value(GEO_CACHE_KEY, cache, expires_in_sec=86400 * 30)
	return {"saved": saved}


@frappe.whitelist()
def geocode_addresses(addresses, batch=25):
	"""DEPRECATED server-side geocode (fails under a referrer-restricted key).

	Kept as a fallback for unrestricted keys / admin tooling. The SPA now geocodes
	client-side and persists via ``save_geocodes``."""
	_require_crm_user()
	if isinstance(addresses, str):
		try:
			addresses = json.loads(addresses)
		except Exception:
			addresses = [addresses]
	addresses = [a.strip() for a in (addresses or []) if a and a.strip()]
	if not addresses:
		return {"resolved": {}, "errors": 0}

	key = _api_key()
	if not key:
		frappe.throw(_("Google Maps API key not configured. Set it in CRM Settings → Map."))

	import requests
	cache = frappe.cache().get_value(GEO_CACHE_KEY) or {}
	resolved, errors = {}, 0
	for addr in addresses[: cint(batch) or 25]:
		if addr in cache:
			resolved[addr] = cache[addr]
			continue
		try:
			resp = requests.get(
				"https://maps.googleapis.com/maps/api/geocode/json",
				params={"address": addr, "key": key}, timeout=10)
			data = resp.json()
			if data.get("status") == "OK" and data.get("results"):
				loc = data["results"][0]["geometry"]["location"]
				coords = {"lat": loc["lat"], "lng": loc["lng"]}
				cache[addr] = coords
				resolved[addr] = coords
			else:
				errors += 1
		except Exception:
			frappe.log_error(frappe.get_traceback(), "crm.api.maps.geocode_addresses")
			errors += 1
	frappe.cache().set_value(GEO_CACHE_KEY, cache, expires_in_sec=86400 * 30)
	return {"resolved": resolved, "errors": errors}


@frappe.whitelist()
def get_rep_configs():
	"""Admin: per-rep map config rows (home base etc.) from FCRM Settings."""
	_require_crm_user()
	if not _is_manager():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	s = _settings()
	rows = getattr(s, "map_rep_config", []) or []
	return [
		{
			"rep": r.rep,
			"rep_name": frappe.db.get_value("User", r.rep, "full_name") or r.rep,
			"home_address": r.home_address,
			"home_latitude": r.home_latitude,
			"home_longitude": r.home_longitude,
		}
		for r in rows
	]
