# Copyright (c) 2026, Plantvu and contributors
"""Smart Lead flag on CRM Lead — marks AI-discovered, territory-sourced prospects.

Set by crm.api.smart_leads.create_leads (+ a "Smart Lead" tag). custom_place_id
dedupes against Google Places so the same business isn't re-discovered. Idempotent.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    if not frappe.db.exists("DocType", "CRM Lead"):
        return
    create_custom_fields({
        "CRM Lead": [
            {"fieldname": "custom_smart_lead", "fieldtype": "Check", "label": "Smart Lead",
             "insert_after": "source", "read_only": 1, "in_standard_filter": 1,
             "description": "Discovered via territory Smart Leads on the CRM map."},
            {"fieldname": "custom_place_id", "fieldtype": "Data", "label": "Google Place ID",
             "insert_after": "custom_smart_lead", "read_only": 1, "hidden": 1},
        ]
    }, update=True)
    frappe.db.commit()
