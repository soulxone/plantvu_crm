# Copyright (c) 2026, Plantvu and contributors
"""
Geo enrichment — pull default Google Maps (Places) info + a web summary
(Firecrawl) for any addressed Lead / Customer / CRM Organization and store it in
the CRM Geo Enrichment doctype + a few key custom fields on the record.

Server-side calls use the dedicated `google_maps_server_key` (the browser key is
HTTP-referrer-restricted and cannot be used server-side). Firecrawl is optional.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, now_datetime, add_to_date

from crm.api import maps  # reuse address/permission helpers


def _settings():
	return frappe.get_cached_doc("FCRM Settings")


def _server_key():
	s = _settings()
	return getattr(s, "google_maps_server_key", "") or getattr(s, "google_maps_api_key", "") or ""


def _firecrawl_key():
	return getattr(_settings(), "crm_firecrawl_api_key", "") or ""


def _record_info(doctype, name):
	"""Return (display_name, one-line address) for a Customer / CRM Lead / CRM Organization."""
	if doctype == "Customer":
		cn = frappe.db.get_value("Customer", name, "customer_name") or name
		return cn, maps._address_for("Customer", name)
	if doctype == "CRM Organization":
		d = frappe.db.get_value("CRM Organization", name, ["organization_name", "address"], as_dict=True) or {}
		addr = ""
		if d.get("address"):
			ad = frappe.db.get_value("Address", d["address"],
				["address_line1", "city", "state", "pincode", "country"], as_dict=True)
			addr = maps._addr_str(ad) if ad else ""
		if not addr:
			addr = maps._address_for("CRM Organization", name)
		return (d.get("organization_name") or name), addr
	if doctype == "CRM Lead":
		meta = frappe.get_meta("CRM Lead")
		af = maps._lead_addr_fields(meta)
		fields = ["lead_name", "organization"] + list(af.values())
		row = frappe.db.get_value("CRM Lead", name, fields, as_dict=True) or {}
		addr = maps._addr_str({k: row.get(v) for k, v in af.items()}) if af else ""
		return (row.get("organization") or row.get("lead_name") or name), addr
	return name, ""


# ── external lookups ─────────────────────────────────────────────────────────

def _places_lookup(name, address, key):
	"""Find Place by name+address, then Place Details. Returns a flat dict."""
	import requests
	q = f"{name} {address}".strip()
	if not q:
		return {}
	try:
		fp = requests.get(
			"https://maps.googleapis.com/maps/api/place/findplacefromtext/json",
			params={"input": q, "inputtype": "textquery", "fields": "place_id", "key": key},
			timeout=12).json()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "enrichment.find_place")
		return {"_status": "ERROR"}
	cands = fp.get("candidates") or []
	if not cands:
		return {"_status": fp.get("status") or "ZERO_RESULTS"}
	pid = cands[0]["place_id"]
	try:
		det = requests.get(
			"https://maps.googleapis.com/maps/api/place/details/json",
			params={"place_id": pid, "key": key,
			        "fields": "name,formatted_phone_number,website,types,rating,"
			                  "user_ratings_total,opening_hours,url,geometry,formatted_address,photos"},
			timeout=12).json()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "enrichment.place_details")
		return {"place_id": pid, "_status": "ERROR"}
	r = det.get("result") or {}
	photo = ""
	if r.get("photos"):
		ref = r["photos"][0].get("photo_reference")
		if ref:
			photo = ("https://maps.googleapis.com/maps/api/place/photo"
			         f"?maxwidth=480&photo_reference={ref}&key={key}")
	loc = (r.get("geometry") or {}).get("location") or {}
	return {
		"place_id": pid,
		"business_name": r.get("name"),
		"phone": r.get("formatted_phone_number"),
		"website": r.get("website"),
		"category": ", ".join((r.get("types") or [])[:3]).replace("_", " "),
		"rating": r.get("rating"),
		"reviews_count": r.get("user_ratings_total"),
		"hours": json.dumps((r.get("opening_hours") or {}).get("weekday_text") or []),
		"gmaps_url": r.get("url"),
		"formatted_address": r.get("formatted_address"),
		"photo_url": photo,
		"latitude": loc.get("lat"),
		"longitude": loc.get("lng"),
		"_status": det.get("status"),
	}


def _firecrawl_enrich(website, fc_key):
	"""Scrape the company website for a short summary (Firecrawl REST)."""
	if not fc_key or not website:
		return {}
	import requests
	try:
		r = requests.post(
			"https://api.firecrawl.dev/v1/scrape",
			headers={"Authorization": f"Bearer {fc_key}", "Content-Type": "application/json"},
			json={"url": website, "formats": ["markdown"], "onlyMainContent": True},
			timeout=40).json()
		md = ((r.get("data") or {}).get("markdown") or "").strip()
		if not md:
			return {}
		# first substantive paragraph as a summary
		paras = [p.strip() for p in md.split("\n\n") if len(p.strip()) > 60]
		return {"web_summary": (paras[0] if paras else md)[:500]}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "enrichment.firecrawl")
		return {}


# ── write-back ───────────────────────────────────────────────────────────────

_WRITEBACK = {
	"custom_place_phone": "phone",
	"custom_place_website": "website",
	"custom_place_category": "category",
	"custom_place_rating": "rating",
}


def _write_back(doctype, name, data):
	meta = frappe.get_meta(doctype)
	vals = {}
	for field, src in _WRITEBACK.items():
		if maps._has(meta, field) and data.get(src) is not None:
			v = data.get(src)
			if isinstance(v, str) and len(v) > 140:
				v = v[:140]
			vals[field] = v
	if maps._has(meta, "custom_geo_enriched"):
		vals["custom_geo_enriched"] = now_datetime()
	if vals:
		try:
			frappe.db.set_value(doctype, name, vals, update_modified=False)
		except Exception:
			pass


def _upsert(doctype, name, data, src):
	existing = frappe.db.exists("CRM Geo Enrichment",
		{"reference_doctype": doctype, "reference_name": name})
	doc = frappe.get_doc("CRM Geo Enrichment", existing) if existing else frappe.new_doc("CRM Geo Enrichment")
	doc.reference_doctype = doctype
	doc.reference_name = name
	for f in ("place_id", "business_name", "phone", "website", "category", "rating",
	          "reviews_count", "hours", "gmaps_url", "formatted_address", "photo_url",
	          "latitude", "longitude", "web_summary"):
		if data.get(f) is not None:
			doc.set(f, data.get(f))
	doc.source = src
	doc.last_enriched = now_datetime()
	doc.raw_json = json.dumps(data)[:9000]
	doc.save(ignore_permissions=True)


# ── whitelisted endpoints ────────────────────────────────────────────────────

@frappe.whitelist()
def enrich_record(reference_doctype, reference_name, use_web=1):
	"""Enrich one record from Google Places (+ Firecrawl if a website is found)."""
	maps._require_manager()
	key = _server_key()
	if not key:
		frappe.throw(_("Set a Google Maps Server Key in CRM Settings → Map first."))
	disp, address = _record_info(reference_doctype, reference_name)
	if not address:
		return {"error": "No address on this record to look up."}
	data = _places_lookup(disp, address, key)
	if not data.get("place_id"):
		return {"found": False, "status": data.get("_status", "ZERO_RESULTS")}
	src = "google_places"
	if cint(use_web) and data.get("website"):
		web = _firecrawl_enrich(data.get("website"), _firecrawl_key())
		if web:
			data.update(web)
			src = "google_places+firecrawl"
	_upsert(reference_doctype, reference_name, data, src)
	_write_back(reference_doctype, reference_name, data)
	frappe.db.commit()
	return {"found": True, "data": {k: data.get(k) for k in
		("business_name", "phone", "website", "category", "rating", "reviews_count",
		 "web_summary", "gmaps_url", "hours")}}


@frappe.whitelist()
def get_enrichment(reference_doctype, reference_name):
	"""Return stored enrichment for a record (or None)."""
	maps._require_crm_user()
	n = frappe.db.exists("CRM Geo Enrichment",
		{"reference_doctype": reference_doctype, "reference_name": reference_name})
	if not n:
		return None
	d = frappe.get_doc("CRM Geo Enrichment", n)
	return {k: d.get(k) for k in
		("business_name", "phone", "website", "category", "rating", "reviews_count",
		 "hours", "gmaps_url", "photo_url", "formatted_address", "web_summary",
		 "products", "last_enriched", "source")}


@frappe.whitelist()
def enrich_all(kinds="customer", limit=300):
	"""Queue a background job to enrich addressed records of the given kinds."""
	maps._require_manager()
	if not _server_key():
		frappe.throw(_("Set a Google Maps Server Key in CRM Settings → Map first."))
	frappe.enqueue("crm.api.enrichment._enrich_all_job", queue="long", timeout=3600,
	               kinds=kinds, limit=cint(limit), user=frappe.session.user)
	return {"queued": True}


def _enrich_all_job(kinds="customer", limit=300, user=None, only_stale=False):
	"""Background: enrich records with a cached geocode + address."""
	wanted = [k.strip() for k in str(kinds).split(",") if k.strip()]
	dt_map = {"customer": ("Customer", maps._collect_customers),
	          "lead": ("CRM Lead", maps._collect_leads)}
	cache = frappe.cache().get_value(maps.GEO_CACHE_KEY) or {}
	cutoff = add_to_date(now_datetime(), days=-30)
	done = found = 0
	for k in wanted:
		if k not in dt_map:
			continue
		dt, collector = dt_map[k]
		for rec in collector(None, 10000):
			if done >= limit:
				break
			addr = (rec.get("address") or "").strip()
			if not addr or addr not in cache:
				continue
			name = rec["ref"]["name"]
			if only_stale:
				le = frappe.db.get_value("CRM Geo Enrichment",
					{"reference_doctype": dt, "reference_name": name}, "last_enriched")
				if le and frappe.utils.get_datetime(le) > cutoff:
					continue
			try:
				r = enrich_record(dt, name, use_web=1)
				done += 1
				if r.get("found"):
					found += 1
			except Exception:
				frappe.log_error(frappe.get_traceback(), "enrichment.enrich_all")
	frappe.db.commit()
	frappe.publish_realtime("crm_geo_enrich_done", {"enriched": done, "found": found}, user=user)


def enrich_stale():
	"""Scheduler: nightly refresh of stale enrichments (opt-in)."""
	s = _settings()
	if not getattr(s, "enable_geo_enrichment_schedule", 0):
		return
	if not _server_key():
		return
	_enrich_all_job(kinds="customer,lead", limit=200, only_stale=True)
