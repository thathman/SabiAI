# Sabi Boy Research Context

This glossary defines the language for Sabi Boy's multi-sport daily research and decision process.

## Research structure

**Daily Research Run**:
A single calendar-day operation that discovers that day's fixtures, gathers evidence, evaluates candidates and publishes one consolidated report.
_Avoid_: one giant scan, daily prompt

**Coverage Map**:
The inventory of sports with fixtures that day, grouped by country, competition and division, including which sources and data types are available for each group.
_Avoid_: sports list, fixture dump

**Research Slice**:
A bounded unit of work for one sport and one country/competition/division group. A run may contain many slices, but each slice remains independently cacheable and reviewable.
_Avoid_: mini-scan, worker pick

**Evidence Packet**:
The timestamped, source-attributed facts and prices used to assess one event or research slice.
_Avoid_: model context, raw scrape

**Decision Pass**:
The final cross-sport comparison that ranks qualified candidates from completed evidence packets and applies strategy and exposure rules before recording picks.
_Avoid_: final scan, model guess

## Reuse and freshness

**Research Cache**:
Reusable same-day fixture, price and evidence data addressed by sport, geography, competition/division, event, market, source and freshness.
_Avoid_: memory, saved prompt

**Coverage Gap**:
A sport, country, competition/division or market that could not be checked to the required freshness or reliability threshold. A gap is reported; it is never silently treated as no value.
_Avoid_: unsupported, ignored league

## Named strategies

**Daily Chain**:
One calendar-day position in a 30-day sequence. A fully won position rolls its payout into the next day's stake; a loss resets to Day 1 and the base stake; a void or partial result does not advance the sequence.
_Avoid_: daily accumulator, one-day parlay

**Weekly Long Shot**:
A separate strategy built from eligible, independent fixtures in the rolling seven-day window. It is not part of the Daily Chain and must not consume the chain's current stake.
_Avoid_: daily long shot, chain variant

**Steal**:
A candidate whose independently supported probability is materially better than the available decimal price, subject to freshness, market and settlement checks.
_Avoid_: guaranteed win, free money
