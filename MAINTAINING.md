# Maintaining the Plantvu CRM fork

Plantvu CRM is a **thin fork** of `frappe/crm`. The whole strategy rests on keeping
upstream as untouched as possible so merges stay cheap and the AGPL attribution
stays clean.

## Golden rules

1. **Add, don't rewrite.** New capabilities go in NEW modules / doctypes +
   `pa_features` flags + custom fields — never as edits to upstream files.
   (Today only ~3% of upstream frontend files are touched; keep it that way.)
2. **Never rename `app_name`.** It must stay `"crm"` — installed data and every
   dependent app key off it. Renaming forces a data migration for zero product gain.
3. **Never strip** the AGPL `LICENSE` or Frappe copyright headers.
4. Overlay/extend upstream UI (slots, CSS theme overlay) instead of editing
   components, so the merge-conflict surface keeps shrinking.

## Sync upstream

```bash
git remote add upstream https://github.com/frappe/crm.git   # one-time
git fetch upstream
git merge upstream/main      # or rebase; conflict surface is small:
                             # hooks.py, patches.txt, FCRM Settings, ~9 .vue files
```

**Cadence:** review each Frappe CRM release, pinned to the Frappe/ERPNext **v16+**
line Plantvu targets. Because divergence is additive, these merges are routine —
the cost of staying current is far lower than owning 100% of CRM maintenance.

## Why we stay a fork (not an independent app)

AGPL-3.0 makes a "clean break" impossible anyway — any standalone Plantvu CRM is
still a derivative work with the same attribution + source-availability duties.
Staying a thin fork keeps upstream's security fixes, framework compatibility, and
roadmap, at a low and bounded merge cost. See `ATTRIBUTION.md`.
