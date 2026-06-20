# Copyright (c) 2026, Plantvu and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class CRMMapRep(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		home_address: DF.Data | None
		home_latitude: DF.Float
		home_longitude: DF.Float
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		rep: DF.Link
	# end: auto-generated types

	pass
