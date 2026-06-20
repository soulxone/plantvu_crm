# Copyright (c) 2026, Plantvu and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class CRMPlant(Document):
	# begin: auto-generated types
	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		active: DF.Check
		address_line1: DF.Data | None
		city: DF.Data | None
		color: DF.Data | None
		company: DF.Link | None
		country: DF.Data | None
		latitude: DF.Float
		longitude: DF.Float
		pincode: DF.Data | None
		plant_name: DF.Data
		radius_green_mi: DF.Float
		radius_red_mi: DF.Float
		radius_yellow_mi: DF.Float
		state: DF.Data | None
	# end: auto-generated types

	pass
