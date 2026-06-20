# Copyright (c) 2026, Plantvu and contributors
"""Add structured address fields to CRM Lead so leads can be plotted on the map.

Frappe CRM's Lead has no street address (only a free-text organization + a
territory link). The in-CRM map geocodes these custom fields. Idempotent.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	if not frappe.db.exists("DocType", "CRM Lead"):
		return

	create_custom_fields(
		{
			"CRM Lead": [
				{
					"fieldname": "custom_map_section",
					"fieldtype": "Section Break",
					"label": "Location",
					"insert_after": "territory",
					"collapsible": 1,
				},
				{
					"fieldname": "custom_address_line1",
					"fieldtype": "Data",
					"label": "Address Line 1",
					"insert_after": "custom_map_section",
				},
				{
					"fieldname": "custom_address_line2",
					"fieldtype": "Data",
					"label": "Address Line 2",
					"insert_after": "custom_address_line1",
				},
				{
					"fieldname": "custom_city",
					"fieldtype": "Data",
					"label": "City",
					"insert_after": "custom_address_line2",
				},
				{
					"fieldname": "custom_column_map",
					"fieldtype": "Column Break",
					"insert_after": "custom_city",
				},
				{
					"fieldname": "custom_state",
					"fieldtype": "Data",
					"label": "State / Province",
					"insert_after": "custom_column_map",
				},
				{
					"fieldname": "custom_pincode",
					"fieldtype": "Data",
					"label": "Postal Code",
					"insert_after": "custom_state",
				},
				{
					"fieldname": "custom_country",
					"fieldtype": "Data",
					"label": "Country",
					"insert_after": "custom_pincode",
				},
			]
		},
		update=True,
	)
	frappe.db.commit()
