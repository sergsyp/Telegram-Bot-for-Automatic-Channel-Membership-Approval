## Context

See `proposal.md`. Rendering and collection already exist. The missing link is catalog identity data: season 3 currently has only automatically generated Telegram publications, whose counters are intentionally excluded from user-facing totals.

## Goals / Non-Goals

**Goals:**

- Register exact season-3 YouTube video URLs in the existing publication map.
- Let the existing idempotent database synchronization and collector populate test data.
- Verify the rendered season output against the BotHost test database.

**Non-Goals:**

- Do not show Telegram counters.
- Do not add guessed VK Video, RuTube, or Dzen links.
- Do not change or deploy production.

## Decisions

Use direct YouTube video URLs found through YouTube search and verified by exact title plus channel owner. This reuses the established `PUBLICATION_LINKS` source of truth and collector instead of hard-coding view counts.

Add a regression test for the five expected mappings and global URL uniqueness. The existing formatting tests continue to define presentation and totals.

## Risks / Trade-offs

- [Only YouTube is currently verified for these older episodes] → Show the truthful partial total and omit missing platforms as the existing contract requires.
- [A collector can temporarily fail] → Preserve the last successful value and verify collection status before acceptance.

## Migration Plan

Commit to `test`, deploy its exact revision on the test BotHost container, run one collection, and inspect the season-3 rendering. Rollback consists of reverting the single test commit; synchronized publication rows can remain inactive or be removed only through a separate controlled data migration if needed.
