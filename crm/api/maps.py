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
	"lead": {"label": "Leads", "color": "#FF9800"},
	"customer": {"label": "Customers", "color": "#0B9E92"},
	"organization": {"label": "Organizations", "color": "#7C4DFF"},
	"deal": {"label": "Deals", "color": "#3F51B5"},
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
	# Data fieldtype (plain) — not a secret (referrer-restricted, client-exposed),
	# and storing plain avoids broken-encryption decrypt failures on some sites.
	return getattr(_settings(), "google_maps_api_key", "") or ""


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

def _customer_rep_field(meta):
	"""Best-effort rep/account-manager field on ERPNext Customer, if present."""
	for f in ("account_manager", "custom_account_manager", "sales_rep", "custom_sales_rep"):
		if _has(meta, f):
			return f
	return None


def _collect_customers(rep, limit):
	"""ERPNext Customer records (the real customer base on ERPNext sites)."""
	if not frappe.db.exists("DocType", "Customer"):
		return []
	meta = frappe.get_meta("Customer")
	fields = ["name", "customer_name"]
	for f in ("customer_group", "territory"):
		if _has(meta, f):
			fields.append(f)
	rep_field = _customer_rep_field(meta)
	if rep_field:
		fields.append(rep_field)
	filters = {}
	if _has(meta, "disabled"):
		filters["disabled"] = 0
	# Customers can only be rep-scoped when a rep field exists; otherwise all
	# customers are shown (managers and reps alike) until such a field is added.
	if rep and rep_field:
		filters[rep_field] = rep
	out = []
	for r in frappe.get_all("Customer", fields=fields, filters=filters, limit=limit):
		o = r.get(rep_field) if rep_field else ""
		out.append({
			"id": f"Customer::{r.name}",
			"kind": "customer",
			"label": r.get("customer_name") or r.name,
			"sublabel": r.get("customer_group") or "",
			"address": _address_for("Customer", r.name),
			"status": r.get("customer_group") or "Customer",
			"owner": o or "",
			"owner_name": _rep_name(o) if o else "",
			"territory": r.get("territory") or "",
			"route": f"/app/customer/{r.name}",
		})
	return out


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
		# Only map leads with a real structured address; geocoding a bare company
		# name returns garbage, so address-less leads stay in the list unmapped.
		addr = _addr_str({k: r.get(v) for k, v in af.items()}) if af else ""
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


# ── per-tenant brand (data, not code) ───────────────────────────────────────
# The map fork is brand-AGNOSTIC: it ships the Plantvu default and asks
# plantvu_admin (if installed) for the per-company override. Welch red therefore
# lives in welchwyse's PA Map Brand row, never hardcoded here. See
# plantvu_admin/branding.py. Soft dependency — defaults stand alone if the admin
# app is absent or the crm.map_branding feature is off.
_BRAND_DEFAULT = {
	"customer_pin_color": "#0B9E92",
	"customer_glyph": "plantvu-mark",
	"customer_logo": "",
	"lead_pin_color": "#FF9800",
	"deal_pin_color": "#3F51B5",
	"organization_pin_color": "#7C4DFF",
	"accent_color": "#0B9E92",
}


def _get_branding():
	brand = dict(_BRAND_DEFAULT)
	try:
		if "plantvu_admin" in frappe.get_installed_apps():
			fn = frappe.get_attr("plantvu_admin.branding.get_map_brand")
			override = fn() or {}
			for field in _BRAND_DEFAULT:
				if override.get(field):
					brand[field] = override[field]
	except Exception:
		pass
	return brand


# ── whitelisted endpoints ───────────────────────────────────────────────────

@frappe.whitelist()
def get_map_settings():
	"""Key, map id, home base, manager flag, rep list, and brand for the map page."""
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
		"branding": _get_branding(),
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
	wanted = set(kinds) if kinds else {"lead", "customer", "organization", "deal"}

	# enforce per-rep scoping for non-managers
	if not _is_manager():
		rep = frappe.session.user
	rep = (rep or "").strip() or None

	limit = 5000
	records = []
	if "lead" in wanted:
		records += _collect_leads(rep, limit)
	if "customer" in wanted:
		records += _collect_customers(rep, limit)
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


# ── plants & coverage (Phase 2a) ─────────────────────────────────────────────

def _require_manager():
	if not _is_manager():
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _haversine_mi(lat1, lng1, lat2, lng2):
	import math
	r = 3958.8  # earth radius in miles
	dlat = math.radians(lat2 - lat1)
	dlng = math.radians(lng2 - lng1)
	a = (math.sin(dlat / 2) ** 2
	     + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2)
	return r * 2 * math.asin(math.sqrt(a))


@frappe.whitelist()
def get_plants():
	"""Active plants with coords, colour and coverage-radius bands."""
	_require_crm_user()
	if not frappe.db.exists("DocType", "CRM Plant"):
		return []
	rows = frappe.get_all(
		"CRM Plant",
		filters={"active": 1},
		fields=["name", "plant_name", "company", "address_line1", "city", "state",
		        "pincode", "country", "latitude", "longitude", "color", "logo",
		        "radius_green_mi", "radius_yellow_mi", "radius_red_mi"],
	)
	for r in rows:
		r["address"] = _addr_str({
			"address_line1": r.get("address_line1"), "city": r.get("city"),
			"state": r.get("state"), "pincode": r.get("pincode"), "country": r.get("country"),
		})
	return rows


@frappe.whitelist()
def save_plant(plant):
	"""Create or update a plant (manager only)."""
	_require_manager()
	if isinstance(plant, str):
		plant = json.loads(plant)
	name = plant.get("name")
	doc = frappe.get_doc("CRM Plant", name) if name and frappe.db.exists("CRM Plant", name) else frappe.new_doc("CRM Plant")
	for f in ("plant_name", "company", "address_line1", "city", "state", "pincode",
	          "country", "latitude", "longitude", "color", "logo",
	          "radius_green_mi", "radius_yellow_mi", "radius_red_mi"):
		if f in plant and plant.get(f) is not None:
			doc.set(f, plant.get(f))
	doc.active = 1
	doc.save()
	frappe.db.commit()
	return {"name": doc.name}


@frappe.whitelist()
def delete_plant(name):
	"""Soft-delete (deactivate) a plant (manager only)."""
	_require_manager()
	if frappe.db.exists("CRM Plant", name):
		frappe.db.set_value("CRM Plant", name, "active", 0)
		frappe.db.commit()
	return {"ok": True}


@frappe.whitelist()
def get_zones():
	"""Drawn zone polygons (territory grouping + plant + rep + GeoJSON)."""
	_require_crm_user()
	if not frappe.db.exists("DocType", "CRM Zone"):
		return []
	rows = frappe.get_all(
		"CRM Zone", filters={"active": 1},
		fields=["name", "zone_name", "territory", "plant", "assigned_rep", "color", "polygon"])
	out = []
	for r in rows:
		try:
			r["points"] = json.loads(r.get("polygon") or "[]")
		except Exception:
			r["points"] = []
		r.pop("polygon", None)
		out.append(r)
	return out


@frappe.whitelist()
def save_zone(zone):
	"""Create/update a drawn zone (manager only). `points` = [[lat,lng],...]."""
	_require_manager()
	if isinstance(zone, str):
		zone = json.loads(zone)
	name = zone.get("name")
	doc = frappe.get_doc("CRM Zone", name) if name and frappe.db.exists("CRM Zone", name) else frappe.new_doc("CRM Zone")
	for f in ("zone_name", "territory", "plant", "assigned_rep", "color"):
		if zone.get(f) is not None:
			doc.set(f, zone.get(f))
	if zone.get("points") is not None:
		doc.polygon = json.dumps(zone.get("points"))
	doc.active = 1
	doc.save()
	frappe.db.commit()
	return {"name": doc.name}


@frappe.whitelist()
def delete_zone(name):
	_require_manager()
	if frappe.db.exists("CRM Zone", name):
		frappe.db.set_value("CRM Zone", name, "active", 0)
		frappe.db.commit()
	return {"ok": True}


def _point_in_polygon(lat, lng, poly):
	"""Ray-casting point-in-polygon. poly = [[lat,lng],...]."""
	inside = False
	n = len(poly)
	if n < 3:
		return False
	j = n - 1
	for i in range(n):
		yi, xi = poly[i][0], poly[i][1]
		yj, xj = poly[j][0], poly[j][1]
		if ((xi > lng) != (xj > lng)) and (lat < (yj - yi) * (lng - xi) / ((xj - xi) or 1e-12) + yi):
			inside = not inside
		j = i
	return inside


def _assignment_fields(doctype):
	"""Custom assignment fields present on the doctype (added by patch)."""
	meta = frappe.get_meta(doctype)
	return {
		"plant": "custom_map_plant" if _has(meta, "custom_map_plant") else None,
		"zone": "custom_map_zone" if _has(meta, "custom_map_zone") else None,
		"rep": "custom_map_rep" if _has(meta, "custom_map_rep") else None,
	}


@frappe.whitelist()
def recompute_assignments():
	"""Assign each addressed customer/lead to a territory zone, then plant + rep.

	Priority: (1) point-in-polygon into a drawn CRM Zone -> zone.plant + zone.rep;
	(2) fallback to nearest active plant whose RED radius covers the record.
	Writes persisted assignment fields; out-of-range records are flagged as gaps.
	"""
	_require_manager()
	plants = [p for p in get_plants() if p.get("latitude") and p.get("longitude")]
	zones = [z for z in get_zones() if z.get("points")]
	if not plants and not zones:
		return {"error": "No plants or zones with coordinates configured."}
	cache = frappe.cache().get_value(GEO_CACHE_KEY) or {}

	def nearest(lat, lng):
		best, best_d = None, None
		for p in plants:
			d = _haversine_mi(lat, lng, p["latitude"], p["longitude"])
			if best_d is None or d < best_d:
				best, best_d = p, d
		if best and best_d <= (best.get("radius_red_mi") or 150):
			return best, round(best_d, 1)
		return None, (round(best_d, 1) if best_d is not None else None)

	def zone_for(lat, lng):
		for z in zones:
			if _point_in_polygon(lat, lng, z["points"]):
				return z
		return None

	# iterate customers + leads that have a cached geocode
	assigned, gaps, scanned, by_zone = 0, 0, 0, 0
	for kind, collector in (("Customer", _collect_customers), ("CRM Lead", _collect_leads)):
		af = _assignment_fields(kind)
		if not af["plant"]:
			continue
		for rec in collector(None, 10000):
			addr = (rec.get("address") or "").strip()
			coords = cache.get(addr)
			if not coords:
				continue
			scanned += 1
			z = zone_for(coords["lat"], coords["lng"])
			plant, dist = nearest(coords["lat"], coords["lng"])
			name = rec["ref"]["name"] if rec.get("ref") else rec["id"].split("::", 1)[-1]
			vals = {}
			if z:
				vals[af["plant"]] = z.get("plant") or (plant["name"] if plant else "")
				if af.get("zone"):
					vals[af["zone"]] = z.get("zone_name") or z.get("name")
				if af.get("rep") and z.get("assigned_rep"):
					vals[af["rep"]] = z.get("assigned_rep")
				assigned += 1
				by_zone += 1
			elif plant:
				vals[af["plant"]] = plant["name"]
				if af.get("zone"):
					vals[af["zone"]] = ""
				assigned += 1
			else:
				vals[af["plant"]] = ""
				if af.get("zone"):
					vals[af["zone"]] = ""
				gaps += 1
			try:
				frappe.db.set_value(kind, name, vals, update_modified=False)
			except Exception:
				pass
	frappe.db.commit()
	return {"scanned": scanned, "assigned": assigned, "by_zone": by_zone, "gaps": gaps,
	        "plants": len(plants), "zones": len(zones)}


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
