## Purpose

Expose trustworthy external-platform view totals in podcast season listings while excluding unsupported or unverified counters.

## ADDED Requirements

### Requirement: Season catalog shows available external views
The bot SHALL show the latest available YouTube, VK Video, RuTube, and Dzen counters under each season episode that has verified publications and collected statistics. It MUST omit platforms without a collected value and MUST exclude Telegram from the displayed platforms and total.

#### Scenario: Season 3 has collected YouTube counters
- **WHEN** a user opens season 3 after the registered YouTube publications have been collected
- **THEN** each episode with a collected value shows a line containing its YouTube count and the matching total

#### Scenario: A platform has no collected value
- **WHEN** an episode has no successful current counter for a supported external platform
- **THEN** that platform is omitted without inventing a zero value

### Requirement: Publication identity is verified
The catalog MUST associate an external publication with an episode only when its exact title and publisher identity have been verified.

#### Scenario: Exact season-3 YouTube publication is registered
- **WHEN** a season-3 YouTube result matches both the episode title and the publisher `Мир 1С (Сергей Сыпачев)`
- **THEN** its direct video URL is registered once for that episode
