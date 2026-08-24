# SabiAI Weekly Review — 2026-06-21

**Window:** 2026-06-14 → 2026-06-21 (last 7 days, singles only)
**Sample:** 68 settled picks

## Headline
- Win rate: **48.5%** (33W / 35L)
- Avg odds: **2.97**
- Avg P&L per unit staked: **+0.083** (basically break-even — the longshots carried the week)

## Best vs Worst Sport
- **World Cup — BEST** (17 picks, 47.1% win rate, avg odds 6.0, **+0.532/u**). The longshot hunting worked this week: France 1.51, Netherlands 1.71, two Over 2.5s, even a 14.0 draw all landed.
- **MLB — WORST** (51 picks, 49.0% win rate, avg odds 1.96, **−0.066/u**). Volume is the problem — 75% of all picks were MLB and the model is leaking.

## Pattern in Wins vs Losses
- **Confidence 60–69 on MLB is the leak.** 22 MLB picks, 10 wins (45.5%), −0.164/u. The model is "confident" but the market is right.
- **Odds 2.10–2.49 also underperformed** (42.9%, 14 picks).
- **<50% confidence picks (longshot teasers) hit 27%** — 11 picks at avg odds 8.6 dragged the P&L despite one big World Cup winner.
- **70+ confidence held up best** (55.6%) and even 50–59 held at 50%, so the calibration is fine at the extremes — the middle of the confidence curve is where MLB is mispriced.

## One Concrete Suggestion For Next Week
**Tighten the MLB filter on the 60–69 confidence band.** Either (a) raise the minimum EV threshold for MLB picks in that band from 3% to 8% in `value_bet_finder.py` (DEFAULT_MIN_EV is currently 0.03 globally), or (b) require `our_prob − market_prob ≥ 6%` instead of the current 3% to push a pick through. The data says when MLB is "sort of sure" it's a trap — let the model only fire on 70+ or walk away.

Backup suggestion if the code change is too fiddly: cap MLB stake at 50% of normal Kelly next week until the model recalibrates.

## Compound Bets (Bonus)
2 chain picks logged, both won (England 1.39, Switzerland 1.73). Chains intact.
