# Copyright (c) 2026, Plantvu and Contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CRMSequenceEnrollment(Document):
	def validate(self):
		# Exactly one of lead / deal must be set.
		if bool(self.lead) == bool(self.deal):
			frappe.throw(_("An enrollment must link exactly one Lead or one Deal."))
