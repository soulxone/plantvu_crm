# Copyright (c) 2026, Plantvu and contributors
"""Key Google-Places enrichment fields surfaced on Customer + CRM Lead.

The full payload lives in CRM Geo Enrichment; these are the at-a-glance fields
on the record (written by crm.api.enrichment). Idempotent.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	common = [
		{
			"fieldname": "custom_geo_section",
			"fieldtype": "Section Break",
			"label": "Google Places",
			"collapsible": 1,
			"insert_after": "custom_map_rep",
		},
		{"fieldname": "custom_place_phone", "fieldtype": "Data", "label": "Place Phone",
		 "insert_after": "custom_geo_section", "read_only": 1},
		{"fieldname": "custom_place_website", "fieldtype": "Data", "label": "Place Website",
		 "insert_after": "custom_place_phone", "read_only": 1},
		{"fieldname": "custom_place_category", "fieldtype": "Data", "label": "Place Category",
		 "insert_after": "custom_place_website", "read_only": 1},
		{"fieldname": "custom_column_geo", "fieldtype": "Column Break", "insert_after": "custom_place_category"},
		{"fieldname": "custom_place_rating", "fieldtype": "Float", "label": "Google Rating",
		 "precision": "1", "insert_after": "custom_column_geo", "read_only": 1},
		{"fieldname": "custom_geo_enriched", "fieldtype": "Datetime", "label": "Last Enriched",
		 "insert_after": "custom_place_rating", "read_only": 1},
	]
	fields = {}
	for dt in ("Customer", "CRM Lead"):
		if frappe.db.exists("DocType", dt):
			fields[dt] = [dict(f) for f in common]
	if fields:
		create_custom_fields(fields, update=True)
		frappe.db.commit()
