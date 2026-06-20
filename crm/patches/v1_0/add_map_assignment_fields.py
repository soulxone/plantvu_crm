# Copyright (c) 2026, Plantvu and contributors
"""Persisted territory/plant/rep assignment fields on Customer + CRM Lead.

Written by crm.api.maps.recompute_assignments so coverage is queryable/reportable.
Idempotent. Safe no-op where the doctypes are absent.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	fields = {}
	common = [
		{
			"fieldname": "custom_map_coverage_section",
			"fieldtype": "Section Break",
			"label": "Map Coverage",
			"collapsible": 1,
			"insert_after": "territory",
		},
		{
			"fieldname": "custom_map_plant",
			"fieldtype": "Link",
			"label": "Map Plant",
			"options": "CRM Plant",
			"insert_after": "custom_map_coverage_section",
			"read_only": 1,
		},
		{
			"fieldname": "custom_map_zone",
			"fieldtype": "Data",
			"label": "Map Zone",
			"insert_after": "custom_map_plant",
			"read_only": 1,
		},
		{
			"fieldname": "custom_map_rep",
			"fieldtype": "Link",
			"label": "Map Rep",
			"options": "User",
			"insert_after": "custom_map_zone",
			"read_only": 1,
		},
	]
	for dt in ("Customer", "CRM Lead"):
		if frappe.db.exists("DocType", dt):
			fields[dt] = [dict(f) for f in common]

	if fields:
		create_custom_fields(fields, update=True)
		frappe.db.commit()
