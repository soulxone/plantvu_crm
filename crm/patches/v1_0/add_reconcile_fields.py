# Copyright (c) 2026, Plantvu and contributors
"""Lead↔Customer reconciliation fields: link an Expansion lead to its existing
Customer + classify New Logo vs Expansion. Set by crm.api.reconcile. Idempotent."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    if not frappe.db.exists("DocType", "CRM Lead"):
        return
    create_custom_fields({
        "CRM Lead": [
            {"fieldname": "custom_lead_kind", "fieldtype": "Select", "label": "Lead Kind",
             "options": "\nNew Logo\nExpansion", "insert_after": "status",
             "in_standard_filter": 1, "description": "Expansion = new business at an existing customer."},
            {"fieldname": "custom_existing_customer", "fieldtype": "Link", "options": "Customer",
             "label": "Existing Customer", "insert_after": "custom_lead_kind",
             "description": "The account this expansion lead belongs to (linked, not merged)."},
        ]
    }, update=True)
    frappe.db.commit()
