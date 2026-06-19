# Copyright (c) 2026, Plantvu and Contributors
# For license information, please see license.txt
"""Tests for Plantvu Sales Sequences (offline; no email actually sent)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from crm.api import sequences as seq


class TestSequences(FrappeTestCase):
	def setUp(self):
		seq.install_sequence_custom_fields()
		self.seq = seq.save_sequence(
			sequence_name="Test Cadence " + frappe.generate_hash(length=5),
			description="t",
			enabled=1,
			steps=frappe.as_json([
				{"action_type": "Email", "wait_days": 0, "subject": "Hi", "email_body": "Hello"},
				{"action_type": "Task", "wait_days": 3, "task_title": "Follow up", "task_priority": "Low"},
			]),
		)["name"]
		self.lead = frappe.get_doc({
			"doctype": "CRM Lead", "first_name": "Seq", "last_name": "Test",
			"organization": "Acme", "status": "New", "email": "seq@example.com",
		}).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.db.rollback()

	def test_fields_installed(self):
		for dt in ("CRM Lead", "CRM Deal"):
			self.assertTrue(frappe.get_meta(dt).has_field("pv_active_sequences"))

	def test_enroll_sets_first_next_run(self):
		r = seq.enroll_record("CRM Lead", self.lead.name, self.seq)
		self.assertEqual(r["status"], "Active")
		enr = frappe.get_doc("CRM Sequence Enrollment", r["enrollment"])
		self.assertEqual(enr.current_step_index, 0)
		self.assertEqual(enr.lead, self.lead.name)
		self.assertIsNotNone(enr.next_run)

	def test_duplicate_active_enroll_blocked(self):
		seq.enroll_record("CRM Lead", self.lead.name, self.seq)
		with self.assertRaises(frappe.ValidationError):
			seq.enroll_record("CRM Lead", self.lead.name, self.seq)

	def test_enrollment_requires_exactly_one_target(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "CRM Sequence Enrollment", "sequence": self.seq}).insert(
				ignore_permissions=True)

	def test_execute_advances_pointer(self):
		r = seq.enroll_record("CRM Lead", self.lead.name, self.seq)
		enr = frappe.get_doc("CRM Sequence Enrollment", r["enrollment"])
		seq._execute_current(enr)
		enr.reload()
		# after first step (Email), pointer advances to step 2 (Task), still active
		self.assertEqual(enr.current_step_index, 1)
		self.assertEqual(enr.status, "Active")
