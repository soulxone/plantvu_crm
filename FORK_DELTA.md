# Fork delta — what Plantvu CRM changes vs. upstream `frappe/crm`

The whole maintenance strategy is to keep the upstream-edit surface **tiny and
known**, so merges from `frappe/crm` are mechanical. This file is the source of
truth for that surface. Update it whenever you edit an upstream file.

- **Upstream remote:** `https://github.com/frappe/crm.git`
- **Current merge-base:** `8693c962` (run `git merge-base HEAD upstream/develop` to refresh)
- See `MAINTAINING.md` for the sync procedure and `ATTRIBUTION.md` for the AGPL credit.

## A. NEW Plantvu files (additive — zero merge risk)
Plantvu features live in new files. These never conflict with upstream:
- Backend: `crm/api/{maps,routing,enrichment,smart_leads,battlecards,reconcile,sales_ai,sequences,forecast,conversation_intelligence}.py`, `crm/pa_features.py`, the `crm/fcrm/doctype/crm_{plant,zone,battle_card,geo_enrichment,map_rep}` doctypes, and the `crm/patches/v1_0/add_*` patches.
- Frontend: `frontend/src/pages/Map.vue`, `frontend/src/components/{SearchPalette,SalesAIPanel,CallIntelligencePanel,CollisionGuard,AssistMenu}.vue`.

## B. EDITED upstream files (the merge-conflict surface — keep this list complete)

| File | Change | Why | On-merge |
|------|--------|-----|----------|
| `frontend/src/components/Layouts/AppSidebar.vue` | +33 lines: Search Palette (⌘K) button + `openSearchPalette` import; + `:title="'Plantvu CRM'"` on `<HelpModal>` | Wire the SearchPalette feature into the nav; rebrand onboarding panel header | Re-apply the button block + the HelpModal title prop. The `:title` override is needed because frappe-ui's `OnboardingSteps.vue` renders `'Welcome to ' + title` as a **plain literal (not `__()`)** with default `'Frappe CRM'` — translation can't reach it |
| `frontend/src/components/Modals/AboutModal.vue` | Title → "Plantvu CRM"; + "Built on Frappe CRM · AGPL-3.0" line; + Source (AGPL) link | Brand + **AGPL §13 credit** | Keep the credit + source link (license requirement). Take upstream's structure, re-add our 3 bits |
| `frontend/src/components/SalesHierarchyBanner.vue` | 1 string: "Frappe CRM" → "Plantvu CRM" | Brand | translatable (`__()`) — candidate for translation-override (see C) |
| `frontend/src/components/Settings/ERPNextSettings.vue` | 1 string: "Frappe CRM" → "Plantvu CRM" | Brand | translatable — candidate for translation-override |
| `frontend/src/pages/NotPermitted.vue` | 1 string: "Frappe CRM" → "Plantvu CRM" | Brand | translatable — candidate for translation-override |
| `crm/hooks.py` | `pa_features`, `CRM Lead.after_insert` (reconcile), scheduler entries; brand: `app_title`/`app_icon_title`/`add_to_apps_screen[].title` → "Plantvu CRM" | Integration + brand | Re-add the Plantvu keys; upstream rarely touches these |
| `crm/patches.txt` | appends the Plantvu `add_*` patches | Migrations | Append-only; trivial |
| `crm/__init__.py` | `__title__` → "Plantvu CRM" | Brand | 1-line; re-apply |
| `crm/www/crm.py` | "access Frappe CRM" → "Plantvu CRM" (permission throw) | Brand | translatable (`__()`) — candidate for translation-override (see C) |
| `crm/fcrm/doctype/crm_invitation/crm_invitation.py` | invite email subject title → "Plantvu CRM" | Brand | 1-line; re-apply |
| `crm/templates/emails/crm_invitation.html` | "invited to join Frappe CRM" → "Plantvu CRM" | Brand | 1-line; re-apply |
| `crm/fcrm/doctype/crm_twilio_settings/crm_twilio_settings.py` | `friendly_resource_name` → "Plantvu CRM" (names TwiML app/keys in customer Twilio) | Brand | 1-line; re-apply |
| `crm/fcrm/workspace/frappe_crm/frappe_crm.json` | desk workspace `label` + `title` → "Plantvu CRM" (**keep `name` key = "Frappe CRM"** — it's the PK; renaming orphans the doc) | Brand | re-apply label+title only |

**Intentionally NOT rebranded** (leave as upstream): copyright headers (`Frappe Technologies` — AGPL attribution), `app_publisher`, the `AboutModal.vue` "Built on Frappe CRM" credit + upstream link (AGPL §13), real product names ("Frappe Mail", "Frappe Cloud"), and the workspace `name` PK.

## C. Reduction opportunity (shrink the surface further)
The 3 one-line brand strings in §B that use `__()` (SalesHierarchyBanner,
ERPNextSettings, NotPermitted) can be **removed from the edit surface** by
shipping a same-language **translation override** that maps the upstream English
string → the "Plantvu CRM" variant, then reverting those 3 files to vanilla.
That converts 3 edits into one additive translation file. (Deferred: it changes
live rendering, so validate on a site before rolling.)

The AppSidebar SearchPalette wire and the AboutModal credit are intentional and
stay — they have no clean upstream extension point today.
