## Why

The season catalog already renders external-platform view totals, but season 3 has no registered external publication links. As a result, users see no view statistics for those episodes even though verified YouTube publications exist.

## What Changes

- Register the five verified YouTube publications for season 3.
- Preserve the existing display format and exclusion of Telegram views from totals.
- Add regression coverage for complete and unique season-3 YouTube links.
- Document season-3 statistics coverage.

## Capabilities

### New Capabilities

- `season-catalog-view-stats`: The podcast catalog exposes the latest available external-platform view counts for season episodes with verified publications.

### Modified Capabilities

None.

## Impact

Affected files are `publication_links.py`, catalog/database tests, and `README.md`. The test BotHost database will gain five YouTube publication records and their collected counters; production is out of scope until explicit approval.
