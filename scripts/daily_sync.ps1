<#
Run this script once per day with Windows Task Scheduler.
Order is intentional:
  lifecycle_manager (state machine: upcoming→active, hard-delete expired)
  -> scrape + clean (expired / beyond-3-day preview / daily TTL)
  -> expand store channels (
       brand locators + Sino/SHKP/Swire directories
       + enrich_flagship_phones (74-mall Store Locator reverse match)
       + link_reit_channel (Link REIT / Hang Lung tenants)
       + strata_mall_openrice (strata / food-court structured scrape)
       + payment join + social_media_parser + food_court_scanner + community_aggregator
       + store_authenticity six-field gate + lifecycle rematerialize
     )
  -> build SPA malls.json (re-apply lifecycle + six-field authenticity)
  -> validate lifecycle invariants (no expired residue, no placeholders, 6-column)
  -> audit empty individual-store malls
  -> optional database cleanup
#>

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

Write-Host "==> Lifecycle state machine: classify + prune expired residue"
python scripts/lifecycle_manager.py `
  --discounts discounts.json `
  --malls malls.json
if ($LASTEXITCODE -ne 0) { throw "lifecycle_manager.py failed with exit $LASTEXITCODE" }

Write-Host "==> Daily review: official scrape + lifecycle clean"
python scraper_advanced.py --config data/sources.json --targets malls `
  --discounts-output discounts.json `
  --mall-overrides data/mall_overrides.json `
  --chain-store-offers data/chain_store_offers.json `
  --malls-output data/malls-registry.json
if ($LASTEXITCODE -ne 0) { throw "scraper_advanced.py failed with exit $LASTEXITCODE" }

Write-Host "==> Daily review: expand channels + authenticity + lifecycle rematerialize"
python scripts/expand_store_channels.py
if ($LASTEXITCODE -ne 0) { throw "expand_store_channels.py failed with exit $LASTEXITCODE" }

Write-Host "==> Build SPA malls.json (lifecycle + authenticity filters)"
python scripts/build_spa_malls.py `
  --discounts discounts.json `
  --registry data/malls-registry.json `
  --output malls.json
if ($LASTEXITCODE -ne 0) { throw "build_spa_malls.py failed with exit $LASTEXITCODE" }

Write-Host "==> Validate lifecycle rules (3-day preview / in-progress / no expired)"
python scripts/validate_lifecycle.py `
  --discounts discounts.json `
  --malls malls.json
if ($LASTEXITCODE -ne 0) { throw "validate_lifecycle.py failed with exit $LASTEXITCODE" }

Write-Host "==> Audit malls with zero individual store offers"
python scripts/audit_empty_store_malls.py
if ($LASTEXITCODE -ne 0) { throw "audit_empty_store_malls.py failed with exit $LASTEXITCODE" }

if ($env:DATABASE_URL) {
  Write-Host "==> Database cleanup"
  python scripts/cleanup_expired.py
  if ($LASTEXITCODE -ne 0) { throw "cleanup_expired.py failed with exit $LASTEXITCODE" }
}

Write-Host "daily_sync completed successfully"
