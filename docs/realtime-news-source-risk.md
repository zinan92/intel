# Realtime News Source Risk Decision

## Decision

CLS Telegraph and Eastmoney 7x24 are accepted only as an internal, read-only
trial input for the Park Intel realtime lane. They are public web endpoints
observed through the providers' web clients, not documented or licensed API
contracts. This is an operational experiment, not approval to redistribute
provider content or make the lane a production data entitlement.

The lane is opt-in through `REALTIME_LANE_ENABLED=1` and remains outside the
existing hourly digest, LLM tagging, event aggregation, and trading-signal
inputs until an explicit convergence decision. A provider response of 403,
429, or 451 pauses that source type for 15 minutes and records an operator-
visible failure. The default polling gap is at least one second per provider;
the scheduler cadence is 60 seconds.

## Allowed handling

- Store normalized title, summary/content where technically permitted, source
  id, provider URL when supplied, timestamps, and lane provenance for internal
  evaluation.
- Keep live smoke output and receipts sanitized: counts, schema status,
  latency, timestamps, and hashes only; never commit full provider responses,
  credentials, or production logs.
- Use the feed for internal decision-support research, not automated order
  placement.

## Follow-up gate

Before enabling this lane unattended or switching the canonical digest input,
review each provider's current terms, robots/access policy, redistribution
rights, rate limits, and a licensed/official-feed alternative. Record that
decision separately; a successful HTTP response is not evidence of permission,
coverage, uptime, or convergence.
