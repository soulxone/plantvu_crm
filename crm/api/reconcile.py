# Copyright (c) 2026, Plantvu and contributors
"""Lead ↔ Customer reconciliation — "new business at an existing customer".

Some leads are really expansion at an account you already serve. This links such
a Lead to the existing Customer (it does NOT merge them — a Lead and a Customer
are different lifecycle objects) and flags it as Expansion, so the rep gets
Collision-Guard context and conversion can reuse the existing account instead of
spawning a duplicate.

Match signals (confidence-scored): normalized company name, email domain (reuses
the core Collision resolver), and — when present — phone. Flag-gated: crm.reconcile.
"""

import frappe
from frappe import _

from crm.api import maps  # _require_crm_user


def _on():
    try:
        from plantvu.control.features import is_on
        return is_on("crm.reconcile", True)
    except Exception:
        return True


def _norm(name):
    s = (name or "").lower()
    for ch in ",.&'\"-/()":
        s = s.replace(ch, " ")
    toks = [t for t in s.split() if t not in ("inc", "llc", "corp", "co", "company",
                                              "ltd", "the", "group", "incorporated")]
    return " ".join(toks).strip()


def _customer_index():
    idx = {}
    for c in frappe.get_all("Customer", fields=["name", "customer_name"], limit_page_length=0):
        k = _norm(c.customer_name or c.name)
        if k:
            idx.setdefault(k, c.name)
    return idx


def _lead_signals(lead):
    org = lead.get("organization") or lead.get("company_name") or lead.get("lead_name")
    email = lead.get("email") or lead.get("email_id")
    phone = lead.get("mobile_no") or lead.get("phone")
    return org, email, phone


def _match(lead):
    """Return [{customer, signal, confidence}] best-first."""
    org, email, phone = _lead_signals(lead)
    out, seen = [], set()
    nk = _norm(org)
    if nk:
        idx = _customer_index()
        if nk in idx:
            out.append({"customer": idx[nk], "signal": "name", "confidence": "high"})
            seen.add(idx[nk])
    if email and "@" in email:
        try:
            from plantvu.collision.aggregator import find_customer_for_email
            cust = find_customer_for_email(email)
            if cust and cust not in seen:
                out.append({"customer": cust, "signal": "email-domain", "confidence": "high"})
                seen.add(cust)
        except Exception:
            pass
    if phone:
        try:
            ph = "".join(ch for ch in str(phone) if ch.isdigit())[-10:]
            if ph:
                for c in frappe.get_all("Customer", or_filters=[["mobile_no", "like", f"%{ph}%"]],
                                        fields=["name"], limit_page_length=5):
                    if c.name not in seen:
                        out.append({"customer": c.name, "signal": "phone", "confidence": "medium"})
                        seen.add(c.name)
        except Exception:
            pass
    return out


@frappe.whitelist()
def match_lead(name):
    """Candidate existing Customers for a Lead (no writes)."""
    maps._require_crm_user()
    lead = frappe.get_doc("CRM Lead", name)
    return {"lead": name, "candidates": _match(lead)}


@frappe.whitelist()
def reconcile_lead(name, customer=None):
    """Link a Lead to an existing Customer (Expansion). Picks the best high-confidence
    match if no customer is given."""
    maps._require_crm_user()
    lead = frappe.get_doc("CRM Lead", name)
    if not customer:
        high = [c for c in _match(lead) if c["confidence"] == "high"]
        if not high:
            return {"linked": False, "reason": "no high-confidence match"}
        customer = high[0]["customer"]
    meta = lead.meta
    patch = {}
    if meta.has_field("custom_existing_customer"):
        patch["custom_existing_customer"] = customer
    if meta.has_field("custom_lead_kind"):
        patch["custom_lead_kind"] = "Expansion"
    if patch:
        frappe.db.set_value("CRM Lead", name, patch, update_modified=False)
        frappe.db.commit()
    return {"linked": True, "customer": customer}


def on_lead_insert(doc, method=None):
    """after_insert hook: auto-flag a new lead that matches an existing Customer
    as Expansion + link it. Defensive — never breaks lead creation."""
    try:
        if not _on():
            return
        high = [c for c in _match(doc) if c["confidence"] == "high"]
        if not high:
            return
        meta = doc.meta
        patch = {}
        if meta.has_field("custom_existing_customer"):
            patch["custom_existing_customer"] = high[0]["customer"]
        if meta.has_field("custom_lead_kind"):
            patch["custom_lead_kind"] = "Expansion"
        if patch:
            frappe.db.set_value("CRM Lead", doc.name, patch, update_modified=False)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "reconcile.on_lead_insert")
