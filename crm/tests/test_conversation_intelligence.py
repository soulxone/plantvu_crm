# Copyright (c) 2026, Plantvu and Contributors
# For license information, please see license.txt
"""Tests for Plantvu Conversation Intelligence (mocked core choke-point)."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from crm.api import conversation_intelligence as ci


def _fake_claude(result):
	def _f(system, user_content, **kwargs):
		_f.last = {"kwargs": kwargs, "user": user_content}
		return {"result": result, "run": "PV-TEST", "usage": {"input": 1, "output": 1}}
	return _f


class TestConversationIntelligence(FrappeTestCase):
	def setUp(self):
		ci.install_ci_custom_fields()
		self.call = frappe.get_doc({
			"doctype": "CRM Call Log",
			"id": "test-ci-" + frappe.generate_hash(length=6),
			"type": "Incoming",
			"status": "Completed",
			"duration": 120,
		}).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.db.rollback()

	def test_fields_installed(self):
		meta = frappe.get_meta("CRM Call Log")
		for f in ("pv_ci_transcript", "pv_ci_summary", "pv_ci_sentiment",
				  "pv_ci_objections", "pv_ci_competitors", "pv_ci_next_step"):
			self.assertTrue(meta.has_field(f), f"CRM Call Log.{f} should exist")

	def test_no_transcript_raises(self):
		with patch.object(ci, "_get_call_claude", return_value=_fake_claude({})):
			with self.assertRaises(frappe.ValidationError):
				ci.analyze_call_log(self.call.name)

	def test_analyze_with_transcript_writes_back(self):
		fake = _fake_claude({
			"summary": "Buyer interested, comparing to Dynamics.",
			"sentiment": "Positive",
			"objections": ["Worried about migration"],
			"competitor_mentions": ["Microsoft Dynamics"],
			"next_step": "Send ROI comparison.",
		})
		with patch.object(ci, "_get_call_claude", return_value=fake):
			res = ci.analyze_call_log(self.call.name, transcript="Hi, we currently use Dynamics...")
		self.assertEqual(res["sentiment"], "Positive")
		self.assertIn("output_schema", fake.last["kwargs"])
		self.assertEqual(fake.last["kwargs"]["kind"], "summarize")
		self.assertEqual(
			frappe.db.get_value("CRM Call Log", self.call.name, "pv_ci_sentiment"), "Positive")
