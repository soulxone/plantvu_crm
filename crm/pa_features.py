# Copyright (c) 2026, Plantvu and contributors
"""Control-Plane feature contributions for the Plantvu CRM fork.

The CRM fork's app_name is "crm", so its whitelisted methods are ``crm.*``. This
contributor registers every Plantvu-ADDED CRM surface into the plantvu_admin
feature registry via the ``pa_features`` hook, so each is on/off per company in
the Control-Plane and its methods are gated by the admin before_request sweep.

AI-flavoured surfaces hang under the core ``ai`` app (so turning AI off turns
them off too); the map sub-surfaces hang under ``crm.map``. None of this gates
the base frappe/crm product — only the Plantvu add-in capabilities.
"""

FEATURES = [
    {"key": "crm.map", "label": "CRM Map", "kind": "feature", "category": "CRM",
     "default_on": True,
     "methods": ["crm.api.maps.get_map_settings", "crm.api.maps.get_sales_reps",
                 "crm.api.maps.get_map_records", "crm.api.maps.save_geocodes",
                 "crm.api.maps.geocode_addresses", "crm.api.maps.get_rep_configs"]},
    {"key": "crm.map.plants", "label": "Plants & Coverage Rings", "kind": "feature",
     "app": "crm.map", "category": "CRM", "default_on": True,
     "methods": ["crm.api.maps.get_plants", "crm.api.maps.save_plant", "crm.api.maps.delete_plant"]},
    {"key": "crm.map.zones", "label": "Territory Zones", "kind": "feature",
     "app": "crm.map", "category": "CRM", "default_on": True,
     "methods": ["crm.api.maps.get_zones", "crm.api.maps.save_zone",
                 "crm.api.maps.delete_zone", "crm.api.maps.recompute_assignments"]},
    {"key": "crm.smart_route", "label": "AI Smart Route (Danczyk)", "kind": "feature",
     "app": "ai", "category": "CRM", "default_on": True,
     "methods": ["crm.api.routing.plan_smart_route"]},
    {"key": "crm.sales_ai", "label": "CRM Sales AI", "kind": "feature",
     "app": "ai", "category": "CRM", "default_on": True,
     "methods": ["crm.api.sales_ai.score_record", "crm.api.sales_ai.qualify_lead",
                 "crm.api.sales_ai.compose_email", "crm.api.sales_ai.summarize_thread"]},
    {"key": "crm.conversation_intelligence", "label": "Conversation Intelligence",
     "kind": "feature", "app": "ai", "category": "CRM", "default_on": True,
     "methods": ["crm.api.conversation_intelligence.analyze_call_log"]},
    {"key": "crm.sequences", "label": "Sales Sequences / Cadences", "kind": "feature",
     "category": "CRM", "default_on": True,
     "methods": ["crm.api.sequences.enroll_record", "crm.api.sequences.unenroll_record",
                 "crm.api.sequences.pause_enrollment", "crm.api.sequences.resume_enrollment",
                 "crm.api.sequences.get_active_enrollments", "crm.api.sequences.execute_step",
                 "crm.api.sequences.draft_email_for_step", "crm.api.sequences.list_sequences"]},
    {"key": "crm.forecast", "label": "Weighted Pipeline Forecast", "kind": "feature",
     "category": "CRM", "default_on": True,
     "methods": ["crm.api.forecast.get_forecast", "crm.api.forecast.get_forecast_narrative"]},
    {"key": "crm.geo_enrichment", "label": "Geo Enrichment", "kind": "feature",
     "category": "CRM", "default_on": False,
     "methods": ["crm.api.enrichment.enrich_record", "crm.api.enrichment.get_enrichment",
                 "crm.api.enrichment.enrich_all"]},
    {"key": "crm.battle_cards", "label": "Battle Cards (competitor intel)", "kind": "feature",
     "category": "CRM", "default_on": True,
     "methods": ["crm.api.battlecards.save_battlecard", "crm.api.battlecards.generate_battlecard",
                 "crm.api.battlecards.get_battlecard", "crm.api.battlecards.list_battlecards",
                 "crm.api.battlecards.list_in_area", "crm.api.battlecards.delete_battlecard"]},
    {"key": "crm.smart_leads", "label": "Smart Leads (territory prospecting)", "kind": "feature",
     "category": "CRM", "default_on": True,
     "methods": ["crm.api.smart_leads.discover", "crm.api.smart_leads.create_leads"]},
]


def get_features():
    """``pa_features`` hook target — register the CRM fork's add-in surfaces."""
    return FEATURES
