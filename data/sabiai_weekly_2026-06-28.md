# SabiAI Weekly Analysis — 2026-06-22 to 2026-06-28

## Summary
34 bets settled this week. 18 wins, 16 losses. Win rate: 52.9%. Average odds: 2.02.

Against market-implied probability (49.6%), we beat break-even by **+6.8% EV**. That's a positive week overall.

## Best Sport: World Cup (2/2 wins, avg odds 1.69)
Small sample but clean. Both picks hit.

## Worst Sport: MLB (16W/16L, 50% win rate at avg odds 2.04)
Exactly break-even after vig. Market had the odds right. No edge generated this week.

## Key Pattern: High confidence is broken
- Confidence 0–49%: 58% win rate ✅
- Confidence 50–59%: 56% win rate ✅  
- Confidence 60–100%: **25% win rate** ❌

Our model is badly miscalibrated at the high end. Picks we tagged 60%+ lost 3 out of 4 times. The confidence scores are overstating true probability on short-odds favorites.

Also: odds 2.2+ went 4/9 (44%) — slightly below the 45.5% the odds implied.

## One concrete suggestion for next week
**Tighten the confidence ceiling.** Cap recommended confidence at 65% unless 3+ independent signals agree. Any pick with confidence above 70% should be flagged as WATCHLIST, not APPROVED. The model needs a rebase — it's been too bullish on its own picks.