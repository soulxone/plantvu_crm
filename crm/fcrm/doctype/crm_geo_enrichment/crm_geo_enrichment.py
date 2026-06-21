# Copyright (c) 2026, Plantvu and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class CRMGeoEnrichment(Document):
	# begin: auto-generated types
	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		business_name: DF.Data | None
		category: DF.Data | None
		formatted_address: DF.SmallText | None
		gmaps_url: DF.Data | None
		hours: DF.SmallText | None
		last_enriched: DF.Datetime | None
		latitude: DF.Float
		longitude: DF.Float
		phone: DF.Data | None
		photo_url: DF.Data | None
		place_id: DF.Data | None
		products: DF.SmallText | None
		rating: DF.Float
		raw_json: DF.Code | None
		reference_doctype: DF.Data | None
		reference_name: DF.Data | None
		reviews_count: DF.Int
		source: DF.Data | None
		web_summary: DF.SmallText | None
		website: DF.Data | None
	# end: auto-generated types

	pass
