# Telegram AI ingestion terms decision — 2026-09-02

## Decision

Park Intel will not ingest third-party Telegram channels for automated AI
classification, analysis, benchmarking, or deployment. The MTProto source is
permanently retired unless a future, separately reviewed contract establishes
valid permission for every channel in scope.

This is a policy eligibility decision, not a missing-credential or networking
blocker. Obtaining an API ID, API hash, or user session would not make the
proposed use eligible.

## Primary-source basis

- [Telegram API Terms of Service](https://core.telegram.org/api/terms), section
  1.5, incorporates Telegram's content-licensing restrictions for AI-related
  use of data obtained through the API.
- [Telegram Content Licensing Terms](https://telegram.org/tos/content-licensing)
  prohibit using Telegram platform data for development, enhancement,
  benchmarking, or deployment of artificial intelligence or machine-learning
  systems unless the stated consent requirements are satisfied.

The exception requires explicit, informed, affirmative, continuing consent in
the applicable context. Public availability, joining a third-party channel, or
using content only for model inference does not by itself establish that
consent. Park Intel does not have such permission from the proposed third-party
channel owners.

## Product consequence

- Remove the collector, adapter, dependency, setup command, bootstrap source,
  scheduler path, and credential instructions.
- Preserve historical registry and Article rows for audit and retrospective
  research, but force the legacy source inactive and retired.
- Replace useful Telegram mirrors only with the publisher's own permitted API,
  feed, website, or an upstream official source under a separate contract.
- Close issue #54 as not planned so credentials cannot be mistaken for the only
  remaining gate.

## Revisit condition

Reconsideration requires new primary-source terms or written permissions that
materially change the consent basis. It must go through a new issue and terms
review; generic source-registry reactivation is intentionally blocked.
