# Copyright (c) 2026, Plantvu and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class CRMZone(Document):
	# begin: auto-generated types
	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		active: DF.Check
		assigned_rep: DF.Link | None
		color: DF.Data | None
		plant: DF.Link | None
		polygon: DF.LongText | None
		territory: DF.Data | None
		zone_name: DF.Data
	# end: auto-generated types

	pass
