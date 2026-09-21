# Weekly Finance Newsletter Source Evaluation

Date: 2026-08-23

## Decision for the Prototype

Use Nasdaq's no-key economic-events and earnings endpoints as discovery sources. Verify the highest-impact scheduled events against first-party calendars before publishing an exact time.

## Sources Evaluated

### Nasdaq Economic Events

- Endpoint: https://api.nasdaq.com/api/calendar/economicevents
- Observed fields: country, event name, GMT time, previous value, consensus, and description.
- Strength: broad global coverage with no API key.
- Limitation: the endpoint is not formally documented for this use, and the prototype found a date discrepancy. Nasdaq discovery placed the US GDP/PCE release one day later than BEA's official schedule.
- Role: discovery only; do not treat its date as authoritative for top-tier events.

### Nasdaq Earnings Calendar

- Endpoint: https://api.nasdaq.com/api/calendar/earnings
- Existing reusable implementation: https://github.com/simonlin1212/global-stock-data
- Observed fields: symbol, company, release timing, EPS forecast, and market capitalization.
- Strength: enough coverage to identify the small set of market-moving earnings without a key.
- Limitation: EPS values are forecasts and must never be presented as reported results.
- Role: primary discovery source for the prototype.

### First-Party Verification

- BEA schedule: https://www.bea.gov/news/schedule
  - Verified GDP (Second Estimate) and Personal Income and Outlays for August 26, 2026 at 8:30 AM US Eastern time.
- Federal Reserve calendar: https://www.federalreserve.gov/newsevents/2026-august.htm
  - Verified Chairman Kevin Warsh's Jackson Hole keynote on August 28, 2026 at 10:00 AM US Eastern time.
- BLS calendar: https://www.bls.gov/schedule/news_release/bls.ics
  - Available as a no-key calendar feed, but no additional release was used in this prototype.

### Other No-Key Options

- Xoomar: https://xoomar.com/api/markets/calendar?importance=high
  - Keyless JSON, sourced from BLS, Fed, and BEA. Useful as a US high-impact fallback, but it returned no events in the prototype's next-week window.
- a-stock-data: https://github.com/simonlin1212/a-stock-data
  - Useful for A-share market, announcements, news, and trading signals; it does not provide the required global macro calendar.
- ecocal: https://github.com/lcsrodriguez/ecocal
  - Global coverage, but it depends on extracting an external calendar provider. This adds fragility and provenance risk.
- investing.com.economic-calendar: https://github.com/freenetwork/investing.com.economic-calendar
  - HTML scraper with outdated selectors and no clear license. Rejected for the production path.

## Production Implication

The production collector needs source-specific health and provenance. A weekly report may publish an unverified event date only as a watch item without an exact time. Exact times for top-tier releases require a successful first-party verification receipt.
