# Copyright (c) 2026, Plantvu and Contributors
# For license information, please see license.txt
"""Tests for Plantvu Sales AI (crm.api.sales_ai).

The model call is mocked at the core choke-point so these run offline and never
spend tokens. They verify: context building, write-back to pv_ai_* fields,
permission gating, and that each endpoint forwards a JSON schema where expected.
"""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from crm.api import sales_ai


def _fake_claude_factory(result):
	"""Return a stand-in for plantvu.ai.client.call_claude."""
	def _fake(system, user_content, **kwargs):
		_fake.last = {"system": system, "user": user_content, "kwargs": kwargs}
		return {"result": result, "run": "PV-TEST-0001", "usage": {"input": 1, "output": 1}}
	return _fake


class TestSalesAI(FrappeTestCase):
	def setUp(self):
		self.lead = frappe.get_doc({
			"doctype": "CRM Lead",
			"first_name": "Dyna",
			"last_name": "Test",
			"organization": "Acme Boxes",
			"industry": "Manufacturing",
			"status": "New",
			"email": "buyer@acmeboxes.example.com",
			"no_of_employees": "51-200",
		}).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.db.rollback()

	def test_custom_fields_installed(self):
		sales_ai.install_sales_ai_custom_fields()
		for dt in ("CRM Lead", "CRM Deal"):
			meta = frappe.get_meta(dt)
			for f in ("pv_ai_score", "pv_ai_tier", "pv_ai_summary",
					  "pv_ai_next_action", "pv_ai_scored_on"):
				self.assertTrue(meta.has_field(f), f"{dt}.{f} should exist")

	def test_context_only_includes_known_fields(self):
		_doc, ctx = sales_ai._record_context("CRM Lead", self.lead.name)
		self.assertIn("Acme Boxes", ctx)
		self.assertIn("Organization", ctx)
		# Naming series / internal columns must not leak into the prompt.
		self.assertNotIn("naming_series", ctx)

	def test_score_writes_back_and_returns(self):
		sales_ai.install_sales_ai_custom_fields()
		fake = _fake_claude_factory({
			"score": 82, "tier": "Hot", "summary": "Strong manufacturing fit.",
			"reasons": ["Corrugated manufacturer", "Has budget signals"],
			"risks": ["Timeline unclear"], "next_action": "Book a discovery call.",
		})
		with patch.object(sales_ai, "_get_call_claude", return_value=fake):
			result = sales_ai.score_record("CRM Lead", self.lead.name)

		self.assertEqual(result["score"], 82)
		# Structured scoring must pass a JSON schema to the model.
		self.assertIn("output_schema", fake.last["kwargs"])
		self.assertEqual(frappe.db.get_value("CRM Lead", self.lead.name, "pv_ai_score"), 82)
		self.assertEqual(frappe.db.get_value("CRM Lead", self.lead.name, "pv_ai_tier"), "Hot")

	def test_qualify_lead_returns_draft_email(self):
		fake = _fake_claude_factory({
			"qualification": {"budget": "Mid", "authority": "Buyer", "need": "CRM+ops",
							  "timeline": "Q3", "verdict": "Qualified"},
			"competitor_talking_points": ["One platform vs CRM+ERP integration"],
			"recommended_next_action": "Send tailored email.",
			"draft_email": {"subject": "Quick idea for Acme Boxes",
							"body": "Hi Dyna, ..."},
		})
		with patch.object(sales_ai, "_get_call_claude", return_value=fake):
			result = sales_ai.qualify_lead(self.lead.name)
		self.assertEqual(result["qualification"]["verdict"], "Qualified")
		self.assertIn("subject", result["draft_email"])
		self.assertIn("output_schema", fake.last["kwargs"])

	def test_compose_email_is_prose(self):
		fake = _fake_claude_factory("Subject: Hello\n\nHi there, ...")
		with patch.object(sales_ai, "_get_call_claude", return_value=fake):
			result = sales_ai.compose_email("CRM Lead", self.lead.name,
											instruction="Intro email")
		self.assertIn("draft", result)
		# Prose composer must NOT force a JSON schema.
		self.assertNotIn("output_schema", fake.last["kwargs"])

	def test_unsupported_doctype_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			sales_ai._check_read("ToDo", "x")
