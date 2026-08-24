# Betting Record Skill

## Overview
Tracks Hendrix's sports betting picks, records stakes, outcomes, and calculates profit/loss over time.

## How It Works
1. Every morning at 8am Lagos → I send value bets (already set up)
2. Hendrix picks his choices and places the bet
3. Next day (or whenever) → Hendrix shares his picks and results
4. I record them here

## When Hendrix Shares Picks/Results
Use the `add_bet` action.

Format to expect from Hendrix:
```
Bet: [sport] | [match] | [pick] | odds [decimal] | stake [NGN amount]
Result: W or L
```

Example:
```
Bet: Tennis | Sabalenka vs Shnaider | Sabalenka to win | odds 1.15 | stake 5000
Result: W
```

Or simpler — just tell me the key info and I'll fill in the rest:
```
Placed on Sabalenka at 1.15, 5k. Won/Won
```

## Commands

### `add_bet [sport] [pick] [odds] [stake] [W/L]`
Records a bet result.

### `bet record` or `betting record`
Shows current betting stats — total picks, win rate, profit/loss, ROI.

### `bet stats`
Detailed breakdown by sport and by bookmaker.

## Data File
`~/.openclaw/workspace/expense-tracker/data/betting_record.json`

## Metrics Tracked
- Total picks sent vs bets placed
- Win/Loss record
- Total stake (NGN)
- Total payout (NGN)
- Net profit/loss
- ROI (Return on Investment)
- Breakdown by sport
- Breakdown by bookmaker (if provided)

## ROI Calculation
ROI = (Total Payout - Total Stake) / Total Stake × 100

Positive ROI = profit. Negative ROI = loss.

## Bookmaker
Hendrix uses **1xBet** as primary bookmaker.