# SabiAI GitHub Research: Football Betting Model Repos

Research date: 2026-06-18  
Method: cloned and inspected source code, notebooks, configs, tests, and README files locally under `/tmp/sabiai_repo_research`. Dixon-Coles repo selected after GitHub/web search: `Torvaney/mezzala`, because it is a package-style Python implementation with reusable adapters, model blocks, weights, and scoreline probabilities.

## Executive Summary

The strongest production base is **georgedouzas/sports-betting** for data schemas, odds handling, value-bet selection, and time-series backtesting. The best score-probability engine is **Torvaney/mezzala** for Dixon-Coles. The best xG feature/model layer is **ML-KULeuven/soccer_xg**. The best rolling team-form feature patterns are split between **ProphitBet** and **FootballBettingModel**. **football_analytics** is not a betting model, but it is a very useful data-source map and scraper/reference archive.

Do not build a production betting engine by copying any single repo end to end. Combine:

1. `sports-betting` style data contracts, odds schemas, `TimeSeriesSplit` backtesting, ROI/yield reporting, and value-bet logic.
2. `mezzala` style Dixon-Coles goal model for calibrated scoreline distributions.
3. `soccer_xg` style event-to-xG modelling when shot/event data is available.
4. ProphitBet/FootballBettingModel rolling pre-match team features.
5. `football_analytics`/`soccerdata`/ScraperFC source adapters for FBref, ClubElo, Understat, FiveThirtyEight, Capology, SofaScore, and WhoScored-style sources.

## Summary Table

| Repo/tool | Data sources | Features | Model architecture | Probability derivation | Value detection | Backtesting/results | Code quality |
|---|---|---|---|---|---|---|---|
| ProphitBet | football-data.co.uk CSVs; FootyStats fixtures/odds via Selenium | Rolling wins/losses/goals, goal difference, win rates, shots on target, corners, average odds | Scikit-learn classifiers: logistic regression, LDA/QDA, decision tree, random forest, XGBoost, KNN, Naive Bayes, SVM; TensorFlow DNN; isotonic calibration | Download historical rows, compute rolling features by season, drop non-trainable match/result columns, train classifier, call `predict_proba` for 1X2 or O/U labels | User filters by odds/probability ranges; custom `profit_balance`; no robust expected-value settlement engine | Accuracy/F1/precision/recall, K-fold and sliding CV; no hard published ROI in code | Feature-rich desktop app, but GUI-heavy and not clean service architecture |
| FootballBettingModel | Kaggle Ultimate 25k / European Soccer Database SQLite; bookmaker odds from dataset | Dual team-perspective rows, player rating sums, FIFA team style, rolling goals/points, season points, rating ratios, average odds, optional Elo notebook | Logistic regression, XGBoost, SVM, home-advantage baseline, average-odds baseline | Build one row per team per match, train 3-class model on loss/draw/win, use `predict_proba`, compare probability quality to normalized odds | Betting simulation picks highest model probability and settles at available odds; optional Kelly sizing | README reports around 50% classification and about 5.5% ROI over 75 selected games; notebooks compare model vs odds log loss/Brier | Notebook experiment with useful feature engineering, but not production-ready |
| MatchOutcomeAI | API-Football / api-sports.io for Premier League fixtures/statistics | Team ids, game week, shots, shots on target, fouls, corners, offsides, possession, cards, saves, passes, 5-game recent form | GradientBoostingClassifier selected after notebook comparisons | Scrape finished matches + match statistics, label result by goal difference, train/test split, `predict_proba` for away/draw/home | No bookmaker odds ingestion and no EV comparison | README claims >50% and detailed per-model metrics, with Gradient Boosting 77.12% accuracy and XGBoost 76.54%; code prints CV/accuracy/F1 | Prototype CLI. Major leakage issue: uses post-match stats as features and uses zeros for future-match stats |
| georgedouzas/sports-betting | Own `data` branch CSVs from soccer modelling data; historical + fixtures; market average/maximum odds | Date, league/division/year, teams, odds, rolling/adjusted points and goals, targets for goals/shots/corners/fouls/cards | Framework, not one model: `OddsComparisonBettor`, `ClassifierBettor`, `BettorGridSearchCV`; examples use LogisticRegression, HistGradientBoosting, KNN, MultiOutputClassifier | DataLoader separates X/Y/O, classifier predicts positive probabilities per market, normalizes complementary markets, then `bet()` selects events with positive expected return | Yes. Core rule: value if `model_probability * decimal_odds > 1`; selects highest EV among complementary outcomes | Built-in `backtest()` with TimeSeriesSplit, yield per bet, ROI percentage, final cash, bet counts; tests assert ROI fields | Best production skeleton: package, typed, tests, CLI, configs, GUI, strict schemas |
| ML-KULeuven/soccer_xg | SPADL event streams from Opta, Wyscout, StatsBomb; test downloader uses StatsBomb open data | Shot/action type, body part, result, start/end location, movement, distance/angle, speed, goal angle, Caley zones, triangular grids, context | xG wrapper with scikit-learn pipelines; default logistic regression; provided open-play logistic and XGBoost models; penalty/free-kick model wrappers | Convert events to SPADL actions, compute shot features, train binary goal classifier, `predict_proba` gives shot xG, aggregate shot xG by team/match | No betting odds logic | Validation metrics: ROC AUC, Brier, calibration error, max calibration deviation, residual area | Strong research/package quality for xG, not a match betting engine |
| eddwebster/football_analytics | Broad archive: FBref, Understat, StatsBomb, Wyscout, Opta/WhoScored, ClubElo, FiveThirtyEight SPI, Capology, SofaScore, TransferMarkt, StrataBet, Metrica, Signality | xG, npxG, xPts, PPDA, OPPDA, deep completions, Elo, salaries, player stats, event/tracking features, pitch control, VAEP | Mostly notebooks/scripts; xG notebooks use logistic regression, random forests, XGBoost; not a unified betting model | Source-specific notebooks parse/scrape data, then analysis/model notebooks generate metrics like xG or visualizations | No betting engine | No production betting backtests; resource and analysis archive | Excellent source map and examples; unsuitable as direct production core |
| Torvaney/mezzala | Example uses openfootball JSON; adapters allow arbitrary match result rows | Home/away team, home/away goals; optional arbitrary terms via blocks/adapters; time weights via weights | Dixon-Coles: Poisson attack/defence/home advantage/base rate with rho low-score adjustment; scipy optimization | Fit attack/defence/home/base/rho parameters, compute home/away expected goals, enumerate scoreline grid, apply DC tau adjustment, sum scoreline probabilities to 1X2/O-U/BTTS | No odds comparison built in | No betting ROI; reusable model package | Clean, small, reusable Python package. Needs wrapping for betting/backtests |

## 1. ProphitBet-Soccer-Bets-Predictor

Repository: `kochlisGit/ProphitBet-Soccer-Bets-Predictor`  
Inspected commit: `49fb86b`

### Data Sources

- `storage/network/leagues.json` maps leagues to `football-data.co.uk` URLs.
- Main leagues use season URLs like `https://www.football-data.co.uk/mmz4281/{YY}{YY+1}/E0.csv`.
- Extra leagues use `football-data.co.uk/new/*.csv`.
- Upcoming fixtures are scraped from FootyStats fixture pages with Selenium.
- Main-league historical rows include average 1X2 odds (`AvgH`, `AvgD`, `AvgA`) and, where available, average O/U 2.5 odds. Missing average odds fall back to Bet365 odds (`B365H`, `B365D`, `B365A`, `B365>2.5`, `B365<2.5`).

### Features

`src/preprocessing/statistics.py` computes pre-match rolling and cumulative features:

- Last-N home/away wins and losses.
- Last-N home/away goals for and against.
- Home-vs-away differences for goals forward, goals against, and goal difference.
- Margin-performance features for wins/losses above a configurable goal-difference threshold.
- Cumulative home/away win and loss rates.
- Extended features for main leagues: shots on target and corners (`HSTF`, `ASTF`, `HCF`, `ACF`).

`src/preprocessing/dataset.py` explicitly drops non-trainable columns: date, season, teams, goals, result, O/U result, raw shots/corners, and week. The model trains only on engineered statistics and odds-like columns left in the frame.

### Model Architecture

The model abstraction wraps scikit-learn-like classifiers in `ClassificationModel`:

- Logistic regression / LogisticRegressionCV.
- Discriminant analysis.
- Decision tree.
- Random forest.
- XGBoost.
- KNN.
- Naive Bayes.
- SVM.
- TensorFlow DNN with dense layers and optional attention/variable-selection behavior.

Most scikit-learn classifiers can be wrapped with `CalibratedClassifierCV(method='isotonic')`. That is a valuable pattern: betting needs calibrated probabilities, not just accuracy.

### Probability Derivation

1. Historical CSVs are downloaded and normalized to columns like `Date`, `Season`, `Home`, `Away`, `HG`, `AG`, `Result`, `1`, `X`, `2`, plus optional `HST`, `AST`, `HC`, `AC`.
2. O/U label is created from `HG + AG >= 2.5`.
3. Rows are sorted by date and grouped by season.
4. Rolling statistics are computed with `shift(1).rolling(window=N)`, avoiding use of the current match in feature values.
5. A target is constructed for 1X2 or O/U.
6. Inputs are normalized and optionally resampled with imbalanced-learn samplers.
7. Classifier is trained and optionally isotonic-calibrated.
8. `predict_proba()` gives class probabilities for match outcome or O/U.

### Value Detection

Value detection is not implemented as a full settlement engine. The app supports:

- Manual odds entry.
- Filtering by odds ranges.
- Filtering by output probability thresholds.
- Custom `compute_profit_balance(odds)`, described in README as a metric where if profit balance is lower than accuracy, selected matches are mathematically profitable.

It does not consistently compute expected value as `p * odds - 1` and settle backtests across fixtures. That should be borrowed from `sports-betting`, not ProphitBet.

### Backtesting Results

Code supports:

- Holdout evaluation.
- Stratified K-fold cross-validation.
- Sliding cross-validation.
- Metrics: accuracy, macro F1, precision, recall.

No source-level reproducible ROI/yield result was found.

### Code Quality

Feature-rich and useful, but GUI-heavy. Good pieces to borrow:

- League downloader abstraction.
- Football-data column normalization.
- `shift(1).rolling(...)` feature discipline.
- Probability calibration switch.
- Analysis tools for feature importance/correlation/Boruta.

Avoid copying the PyQt app structure into production.

## 2. FootballBettingModel

Repository: `qwyt/FootballBettingModel`  
Inspected commit: `cc016fd`

### Data Sources

- README says the project uses the Kaggle "Ultimate 25k+ Matches Football Dataset", based on the European Soccer Database.
- Code reads `../dataset/database.sqlite`.
- Tables used: `Match`, `Team_Attributes`, `Team`, `League`, `Country`, optionally `Player` and `Player_Attributes`.
- Betting odds columns include Bet365, Blue Square, Bet&Win, Gamebookers, Interwetten, Ladbrokes, Pinnacle, Sporting Odds, Sportingbet, Stan James, Stanleybet, VC Bet, William Hill, market maximum, and market average.

### Features

Feature engineering is the most useful part of this repo:

- Converts each match into two rows, one from each team's perspective.
- Adds `is_home_team`.
- Adds team and opponent win/draw/loss odds.
- Aggregates the 11 starting players' FIFA `overall_rating` into team rating sums.
- Adds team style attributes from `Team_Attributes`: buildup speed/passing/dribbling, chance creation passing/crossing/shooting, defensive pressure/aggression/width/line, and class labels.
- Rolling 5-match means for goals scored, goals conceded, goal deficit, and points.
- Opponent rolling stats joined back onto the same match row.
- Ratios: team rating ratio, rolling goals-for ratio, goals-against ratio, goal-deficit ratio, points ratio, season-points ratio.
- Last-season points and season-to-date points.

### Model Architecture

`workbench/src/model_config.py` defines:

- Home-advantage baseline.
- Average betting odds baseline.
- Logistic regression variants.
- XGBoost variants.
- SVM variants.

The notebook workflow focuses on probability quality, not just class accuracy.

### Probability Derivation

1. Load SQLite tables and convert dates to `days_after_first_date`.
2. Average bookmaker odds into `home_win_odds`, `draw_odds`, `away_win_odds`.
3. Convert match into home-perspective row and away-perspective row.
4. Map row target to loss/draw/win from that team's perspective.
5. Add rolling and rating features using only prior rows via `rolling(...).shift()`.
6. Select a feature set via `FeatureSet` bit flags.
7. Train classifier and call `predict_proba()`.
8. Attach probabilities back to `match_api_id` and `team_id`.
9. Benchmark model probabilities against normalized bookmaker-implied probabilities using log loss, Brier-style score, accuracy, and F1.

### Value Detection

`workbench/src/simulation.py` implements betting simulation:

- Merge model probabilities with odds.
- Pick the class with highest model probability.
- Map class to `win_odds`, `draw_odds`, or `opponent_win_odds`.
- Stake either a fixed bankroll fraction or a Kelly-derived amount.
- If the predicted outcome matches actual result, profit is `(odds - 1) * stake`; otherwise loss is `stake`.

This is a simple simulation, but it does not require expected value to be positive before betting unless combined with threshold filtering in notebooks. Production should require `p_model > p_market + margin` or `p_model * odds > 1 + edge`.

### Backtesting Results

README reports:

- Roughly 50% loss/draw/win classification performance.
- XGBoost materially better than logistic regression for probability quality when larger features are used.
- Around 5.5% ROI over 75 selected games in one strategy.

Code also includes probability threshold filtering and model-vs-odds benchmarking.

### Code Quality

Strong analysis notebook, weak production shape. Useful patterns:

- Dual-perspective match rows.
- Explicit odds dictionary and average odds construction.
- Player rating aggregation.
- Team/opponent rolling ratio features.
- Probability benchmarking vs market.

Problems:

- Many notebooks.
- Comments like `BROKEN, TODO REMOVE`.
- Some metrics code has label inconsistencies in places.
- No clean package API or robust tests beyond limited processing tests.

## 3. MatchOutcomeAI

Repository: `ratloop/MatchOutcomeAI`  
Inspected commit: `d815f44`

### Data Sources

- API-Football via `https://v3.football.api-sports.io`.
- Requires `X-RapidAPI-Key` in `data_scraper/api_data_scraper.py`.
- League is hardcoded to `39` (Premier League).
- Scrapes finished fixtures and fixture statistics.

### Features

Raw API statistics per match:

- Game week, home/away team labels.
- Goals, half-time goals.
- Shots on target, total shots.
- Fouls, corners, offsides.
- Possession percentage.
- Yellow/red cards.
- Goalkeeper saves.
- Attempted and successful passes.
- Engineered recent form: wins/draws/losses over last 5 matches.

### Model Architecture

The final predictor uses `GradientBoostingClassifier`. README says comparison notebooks evaluated logistic regression, SVM, KNN, decision tree, random forest, bagging, gradient boosting, XGBoost, and Naive Bayes.

### Probability Derivation

1. Scrape finished Premier League fixtures.
2. For each fixture, call `/fixtures/statistics?fixture=...` and store match-level post-match statistics.
3. Convert JSON to CSV.
4. Encode home and away teams with `LabelEncoder`.
5. Parse `game_week`.
6. Label target as `np.sign(home_goals - away_goals)`.
7. Add recent-form features.
8. Train/test split randomly.
9. Fit `GradientBoostingClassifier`.
10. Return `predict_proba()` as away/draw/home probabilities.

### Value Detection

No odds integration. No bookmaker comparison. No EV or staking logic.

### Backtesting Results

README reports model comparison metrics:

- Logistic Regression: 61.15% accuracy.
- SVM: 54.42%.
- KNN: 40.96%.
- Decision Tree: 60.96%.
- Random Forest: 63.85%.
- Bagging: 69.23%.
- Gradient Boosting: 77.12%.
- XGBoost: 76.54%.
- Naive Bayes: 56.15%.

These results are not production-trustworthy because the source predictor trains on post-match statistics that are not known before kickoff.

### Code Quality

Prototype CLI. Major issue:

- Future prediction builds a row with `[0] * 22` for unknown match stats, while training rows contain actual completed-match stats. That creates a train/inference mismatch and likely leakage.

Borrow only:

- API-Football scraper shape.
- JSON-to-CSV normalization.
- User-facing CLI simplicity.

Do not borrow the model design for production.

## 4. georgedouzas/sports-betting

Repository: `georgedouzas/sports-betting`  
Inspected commit: `56cc79b`

### Data Sources

- `SoccerDataLoader` downloads CSVs from the repo's `data` branch:
  - `data/soccer/modelling/{league}_{division}_{year}.csv`
  - `data/soccer/modelling/fixtures.csv`
- Available params are discovered by scraping the GitHub tree.
- Odds types include `market_average` and `market_maximum`; tests/configs mention bookmaker-specific examples like William Hill, Interwetten, Bet365.

### Features

The `SoccerDataLoader.SCHEMA` is a production-worthy contract. Inputs include:

- Date, league, division, year, home team, away team.
- Odds for home/draw/away and over/under 2.5 from market maximum and market average.
- Home/away average points, adjusted points, goals for, goals against, adjusted goals for/against.
- Latest averages of the above.

Targets include:

- Full-time home/away goals.
- Shots, shots on target, corners, fouls committed, yellow cards, red cards.

Outputs are transformed into binary multi-output betting markets such as:

- Home win, draw, away win.
- Over/under 2.5 and 3.5.

### Model Architecture

This is a betting framework:

- `BaseBettor`: validates X/Y/O schemas, normalizes complementary probabilities, computes `bet()` and Sharpe-style score.
- `OddsComparisonBettor`: derives probabilities directly from consensus odds minus alpha.
- `ClassifierBettor`: wraps any scikit-learn classifier with `predict_proba`.
- `BettorGridSearchCV`: grid search for bettor parameters using bettor scoring.
- Examples/configs use LogisticRegression, HistGradientBoostingClassifier, KNN, MultiOutputClassifier, one-hot encoding, imputation, and TimeSeriesSplit.

### Probability Derivation

For classifier bettors:

1. `SoccerDataLoader.extract_train_data()` returns `X`, `Y`, and `O`, with date index.
2. Classifier is fitted on X to multi-output targets Y.
3. `predict_proba()` extracts positive-class probabilities per market.
4. Complementary markets are normalized so home/draw/away sum to 1 and over/under pairs sum to 1.
5. Those normalized probabilities become model probabilities for betting.

For odds-comparison bettors:

1. Select odds columns by odds type.
2. Compute consensus probability as `1 / average_decimal_odds`.
3. Subtract `alpha`.
4. Floor at 0.
5. Normalize complementary events.

### Value Detection

Yes, and this is the clearest implementation in the reviewed repos:

- `B_pred = Y_proba_pred * O > 1`.
- For complementary event groups, compute estimated returns `odds * probability - 1`.
- Select only the maximum-return event in each complementary group.

This is the betting core SabiAI should copy conceptually.

### Backtesting Results

`backtest()`:

- Sorts data by datetime index.
- Uses `TimeSeriesSplit`.
- Fits on each training fold.
- Calls `bettor.bet()` on test fold.
- Settles returns as `(Y * odds - 1) * value_bets`.
- Reports training/testing date windows, betting days, number of bets, yield per bet, ROI percentage, final cash, and per-market bet/yield counts.

Tests assert ROI/yield fields and validate input errors. No headline production ROI is claimed in the repo.

### Code Quality

Best production skeleton:

- Package layout.
- CLI/configs/docs/tests.
- Clear schemas and naming conventions.
- Decoupled dataloaders and bettors.
- Time-series backtesting.
- Multi-market design.

Shortcomings:

- Depends on its own historical CSVs rather than live APIs.
- Feature set is mostly rolling points/goals, not rich event/xG/player availability.
- No Dixon-Coles or xG scoreline generator built in.

## 5. ML-KULeuven/soccer_xg

Repository: `ML-KULeuven/soccer_xg`  
Inspected commit: `b9489d9`

### Data Sources

- Requires SPADL-formatted event streams.
- README says it supports event streams from Opta, Wyscout, and StatsBomb.
- Test data downloader uses StatsBomb open data and converts events to SPADL HDF5 via `socceraction`.

### Features

`soccer_xg/features.py` includes:

- VAEP/socceraction base features: action type, body part, result, start/end location, movement, space delta, start/end polar coordinates, team, time delta.
- Speed features based on prior game states.
- Goal angle.
- Caley shot zones.
- Triangular and rectangular spatial grids.

These features are shot/action-level, not match-level.

### Model Architecture

`XGModel` wraps a scikit-learn pipeline.

- Default pipeline is logistic regression oriented.
- Provided models include open-play logistic regression and open-play XGBoost in basic/advanced variants.
- Penalty and free-kick models can be combined with open-play models.
- Hyperparameter helpers exist for XGBoost and logistic regression randomized search.

### Probability Derivation

1. Convert provider events to SPADL actions.
2. Select shots.
3. Generate shot features.
4. Label shot as goal/non-goal.
5. Train binary classifier.
6. `estimate()` returns `xG = model.predict_proba(features)[:, 1]` for shots.
7. Aggregate xG per team/match/window for higher-level modelling.

For betting, xG should feed either:

- A goals-rate model, such as Dixon-Coles using xG-for/xG-against rather than raw goals.
- A classifier feature table, such as recent xG differential, xG shot quality, xG conceded, set-piece xG, and finishing/keeper residuals.

### Value Detection

None. No odds logic.

### Backtesting Results

Validation reports:

- ROC AUC.
- Brier score.
- Expected calibration error.
- Adaptive calibration error.
- Calibration curve deviation and residual area.

No betting ROI.

### Code Quality

Good research package. Useful patterns:

- Clean `DataApi`.
- Feature generator list.
- Model wrapper with train/validate/estimate.
- Calibration metrics.
- Saved model loading.

Production caveat: it solves shot xG, not match odds. Needs aggregation and match-probability layer.

## 6. eddwebster/football_analytics

Repository: `eddwebster/football_analytics`  
Inspected commit: `47cac1b`

### Data Sources

This is a broad football analytics archive and resource guide. Useful source references and scripts include:

- FBref.
- Understat.
- StatsBomb.
- Wyscout.
- Opta/WhoScored.
- ClubElo.
- FiveThirtyEight SPI.
- Capology salaries.
- SofaScore team stats.
- TransferMarkt.
- StrataBet.
- Metrica Sports and Signality tracking.
- `soccerdata` embedded docs/examples.

Scripts inspected under `scripts/ScraperFC`:

- `ClubElo.py`: requests `http://api.clubelo.com/{team}` and returns Elo for a date range.
- `Understat.py`: Selenium scrapes league/match tables, xG, xA, xPts, npxG/npxGA/npxGD, PPDA, OPPDA, deep completions.
- `FBRef.py`: Selenium/pandas reads FBref league, squad, and player tables.
- `FiveThirtyEight.py`: downloads `soccer-spi` zip and extracts match xG, nsxG, adjusted scores.
- `SofaScore.py`: rough team stats scraper for ratings, chance/shots/passing/duels/cards.
- `Capology.py`: salary scraper by league/season/currency.

### Features

Not a single model feature table, but source patterns include:

- xG, npxG, xA, xPts.
- PPDA/OPPDA and deep completions.
- Elo ratings.
- SPI/FiveThirtyEight xG and non-shot xG.
- FBref aggregated player/team performance.
- Capology financial/salary context.
- SofaScore ratings and team stats.
- Event/tracking-derived pitch control, EPV, VAEP examples.

### Model Architecture

Mostly notebooks and scripts. Some xG notebooks use:

- Logistic regression.
- Random forest.
- XGBoost.
- Scikit-learn model selection and metrics.

No unified match betting architecture.

### Probability Derivation

No end-to-end betting probability derivation. Useful patterns are source-specific:

- Scrape/parse data.
- Engineer analytics metrics.
- Train xG or visualization models.

### Value Detection

No production odds comparison or EV logic.

### Backtesting Results

No betting backtest results.

### Code Quality

Excellent resource and exploratory archive. Weak production fit:

- Many notebooks.
- Large data archive.
- Scraper code likely stale in places due source-site changes.

Borrow source ideas and field definitions, not app architecture.

## 7. Torvaney/mezzala Dixon-Coles

Repository: `Torvaney/mezzala`  
Inspected commit: `2c55d13`

### Data Sources

- README example uses `openfootball/football.json` Premier League JSON.
- Core code is source-agnostic through adapters:
  - `KeyAdapter` for dict-like rows.
  - `AttributeAdapter` for object rows.
  - `LumpedAdapter` to bucket rare teams/terms.

### Features

Base model needs:

- Home team.
- Away team.
- Home goals.
- Away goals.

Blocks add terms:

- `BaseRate`: average scoring level.
- `HomeAdvantage`: home advantage parameter.
- `TeamStrength`: team offence and defence parameters.
- `KeyBlock`/`ConstantBlock`: arbitrary extra terms.

Weights:

- Uniform.
- Exponential time decay.
- Arbitrary key weight.

### Model Architecture

Dixon-Coles:

- Home goals and away goals modelled as Poisson rates.
- Team attack, team defence, base rate, and home advantage are learned in log-space.
- Rho adjusts low-score dependence via the Dixon-Coles tau correction for 0-0, 0-1, 1-0, 1-1.
- Parameters are estimated with `scipy.optimize.minimize`.
- Team attack constraints force average attack strength to 1.

### Probability Derivation

1. Adapter extracts teams and final goals from historical rows.
2. `parse_params()` builds parameter keys and constraints.
3. `_create_feature_matrices()` builds home and away design matrices.
4. `fit()` optimizes negative weighted pseudo-log-likelihood.
5. `predict_one()` enumerates scorelines from 0-0 through `up_to - 1`.
6. Home and away goal rates are `exp(X dot params)`.
7. Scoreline probability is `Poisson(home_goals, home_rate) * Poisson(away_goals, away_rate) * tau`.
8. 1X2 probabilities are produced by summing scoreline probabilities:
   - Home win: all `home_goals > away_goals`.
   - Draw: equal scorelines.
   - Away win: all `home_goals < away_goals`.
9. O/U probabilities are produced by summing scorelines with total goals above/below threshold.
10. BTTS probability is produced by summing scorelines where `home_goals > 0 and away_goals > 0`.

### Value Detection

None. It outputs probabilities only. Pair it with `sports-betting` style EV logic.

### Backtesting Results

No betting ROI in repo. Package provides model/prediction primitives.

### Code Quality

Clean and compact. Best Dixon-Coles Python implementation found for reuse. Caveats:

- Autogenerated from notebooks.
- Rho constraints are noted as incomplete in comments.
- Needs production wrapper for fitting windows, league/team mappings, markets, calibration, and backtesting.

## Key Code Patterns Worth Borrowing

### From ProphitBet

- Football-data downloader normalizes multiple league CSV formats.
- Missing average odds fallback to Bet365 odds.
- Rolling feature implementation uses `shift(1)` to avoid current-match leakage.
- Isotonic calibration around scikit-learn classifiers.
- Feature analysis utilities: RandomForest impurity, logistic coefficients, correlations, variance, Boruta.

### From FootballBettingModel

- Dual-perspective match table: one row per team per match.
- Average bookmaker odds across many providers.
- Rolling 5-match team/opponent form.
- Team/opponent ratio features.
- Player rating sums from starting XI.
- Model probability vs normalized bookmaker probability benchmarking.
- Kelly-inspired staking experiment.

### From MatchOutcomeAI

- API-Football endpoint usage and JSON flattening.
- Simple CLI prediction flow.

Do not borrow its train/inference design because it uses post-match stats as features.

### From sports-betting

- X/Y/O data separation.
- Strict odds and output naming convention.
- Multi-output market design.
- Complementary probability normalization.
- `probability * odds > 1` value-bet rule.
- Select maximum EV within mutually exclusive markets.
- TimeSeriesSplit backtest with ROI, yield, final cash, and bet counts.
- Config-driven bettor construction.

### From soccer_xg

- SPADL event abstraction.
- xG feature functions: location, angle, body part, action context, speed, Caley zones.
- Calibration metrics beyond accuracy.
- Saved model wrapper and shot-level `estimate()`.

### From football_analytics

- Data source catalog.
- Scraper/source adapter examples for ClubElo, FBref, Understat, FiveThirtyEight, Capology, SofaScore.
- xG notebooks for chance quality modelling.
- Tracking/EPV/pitch-control reference scripts for later premium features.

### From mezzala

- Adapter abstraction.
- Block-based model terms.
- Time weighting.
- Scoreline probability grid.
- 1X2/O-U/BTTS derivation by summing scorelines.

## Recommended Aggregation Strategy

Build the production SabiAI betting model as layered services:

1. **Source adapters**
   - Primary historical results and odds: football-data.co.uk, because it is free, broad, and includes bookmaker odds.
   - Secondary live/upcoming: API-Football or a paid fixture/odds provider.
   - Advanced team strength: ClubElo and FiveThirtyEight SPI where available.
   - Advanced performance: Understat or FBref for xG, npxG, xA, PPDA, deep completions.
   - Premium event source: StatsBomb/Wyscout/Opta converted to SPADL for xG/VAEP.

2. **Canonical warehouse**
   - Raw tables: fixtures, results, odds_snapshots, team_stats, player_stats, events, shots, lineups, injuries if available.
   - Feature tables keyed by `match_id`, `team_id`, `as_of_timestamp`.
   - Never overwrite bookmaker odds. Store snapshots and closing odds separately.
   - Add provider/team mapping tables.

3. **Feature factory**
   - Rolling features must be computed as of prediction time.
   - Use ProphitBet `shift(1)` discipline.
   - Use FootballBettingModel dual-perspective rows where helpful.
   - Generate match-level features for both teams and relative/difference features.

4. **Probability engines**
   - Baseline: market-implied probabilities after overround removal.
   - Statistical core: Dixon-Coles scoreline model from goals and xG-adjusted rates.
   - ML overlay: calibrated gradient boosting/logistic multi-output model using pre-match feature table.
   - Optional ensemble: blend market, Dixon-Coles, ML, and xG rates using time-series validation weights.

5. **Market derivation**
   - 1X2 from scoreline sums.
   - O/U 0.5, 1.5, 2.5, 3.5 from scoreline sums.
   - BTTS from scoreline sums.
   - Correct score directly from scoreline grid.
   - Asian lines later with push/half-win logic.

6. **Value engine**
   - Normalize bookmaker odds to no-vig probabilities.
   - Compute edge:
     - `fair_odds = 1 / p_model`
     - `ev = p_model * offered_odds - 1`
     - `edge_vs_market = p_model - p_market_novig`
   - Bet only if:
     - `ev >= min_ev`, for example 0.03 to 0.07.
     - Probability confidence/calibration bucket is acceptable.
     - Liquidity/bookmaker constraints pass.
   - Use fractional Kelly capped by risk limits, with flat-stake mode for evaluation.

7. **Backtesting**
   - Use `sports-betting` style TimeSeriesSplit and rolling-origin evaluation.
   - Evaluate by bet date, league, market, odds band, probability band, closing-line value, ROI, yield, max drawdown, hit rate, calibration, Brier/log loss.
   - Include market baseline and random/no-bet baselines.

## Data Source Priority List

### Tier 1: Must Have

1. **football-data.co.uk**
   - Results, fixtures after completion, shots/corners for main leagues, broad bookmaker odds.
   - Best free backtesting base.

2. **Odds feed with timestamped pre-match prices**
   - Use API-Football odds, The Odds API, OddsPortal scraping only if legally acceptable, or paid bookmaker feed.
   - Need opening, current, and closing odds snapshots.

3. **Fixture/result provider**
   - API-Football is acceptable for fixtures, results, lineups, events/statistics if plan supports it.

### Tier 2: Strong Model Lift

4. **ClubElo**
   - Daily team strength. Easy to join by team/date.

5. **Understat**
   - xG, npxG, xA, xPts, PPDA, deep completions for major leagues.

6. **FBref via soccerdata**
   - Team and player aggregate stats, shooting, passing, possession, defensive actions.

7. **FiveThirtyEight SPI archive**
   - Historical xG/nsxG/adjusted score/SPI where available. Useful benchmark, but FiveThirtyEight soccer data is not a complete live future source.

### Tier 3: Premium/Expansion

8. **StatsBomb/Wyscout/Opta event data**
   - Use for custom xG, set-piece xG, shot quality, VAEP.

9. **SofaScore/FotMob**
   - Player ratings, form, lineups, injuries, xG depending availability.

10. **TransferMarkt/Capology**
   - Squad value, salaries, age, transfers. Better for long-term strength/injury depth than match-level prediction.

11. **Tracking data**
   - Pitch control/EPV later, not needed for first production betting model.

## Feature Engineering Blueprint

All features must be computed with an `as_of` cutoff before kickoff.

### Match Identity

- League, division, season, round/week.
- Home team, away team.
- Rest days.
- Travel distance if available.
- Derby flag and neutral venue flag if available.

### Results/Form

- Rolling 3/5/10 match points.
- Rolling home-only and away-only points.
- Rolling goals for/against.
- Rolling goal difference.
- Rolling clean sheets and failed-to-score.
- Strength-adjusted form using opponent Elo/SPI.

### Chance Quality

- Rolling xG for/against.
- Rolling non-penalty xG for/against.
- Rolling xG difference.
- Rolling shot count and shots on target.
- Average xG per shot for and against.
- Big chances for/against where source provides it.
- Set-piece xG and open-play xG if event data exists.

### Possession/Territory

- Possession.
- Field tilt if available.
- PPDA/OPPDA.
- Deep completions.
- Final-third entries and box entries if available.

### Team Strength

- ClubElo and Elo difference.
- SPI and SPI difference if available.
- Market-implied strength from closing odds.
- Promotion/relegation/new-team priors.

### Player/Squad

- Starting XI rating sum or average.
- Missing player value/rating.
- Injuries/suspensions count weighted by minutes/share of team value.
- Keeper rating/post-shot xG residual if available.
- Squad value/salary as slow-moving priors.

### Odds/Market

- Opening odds, current odds, closing odds.
- No-vig market probabilities.
- Overround.
- Odds movement.
- Disagreement across bookmakers.
- Market maximum vs average.

### Relative Features

For most team stats, store:

- Home raw value.
- Away raw value.
- Difference: home minus away.
- Ratio: home / away, with clipping and missing handling.
- League-relative z-score.

### Targets

- 1X2.
- Exact goals: home goals, away goals.
- Over/under 0.5, 1.5, 2.5, 3.5.
- BTTS.
- Corners/cards later.

## Model Architecture Recommendation

### Phase 1 Production Model

Use a two-track ensemble:

1. **Dixon-Coles scoreline model**
   - Fit per league with rolling training window.
   - Inputs: historical goals, optional time decay, home advantage, attack/defence strengths.
   - Upgrade rates using xG when available:
     - Fit on goals for settlement reality.
     - Add xG-adjusted priors or covariates to rates.
   - Output: scoreline matrix and derived 1X2/O-U/BTTS.

2. **Calibrated ML market model**
   - Model: HistGradientBoosting or XGBoost/LightGBM if dependency allowed; logistic regression as baseline.
   - Targets: multi-output binary markets or multinomial 1X2.
   - Features: rolling form, xG, Elo, odds no-vig probabilities, team/player features.
   - Calibration: isotonic or Platt by league/market, validated with time-series folds.

Blend them:

- Start with market no-vig probability as anchor.
- Add Dixon-Coles and ML as deviations from market.
- Weight by validation log loss and calibration bucket.
- Refuse bets where model disagreement is too high.

### Probability Flow

For each fixture:

1. Build feature row using only data available before kickoff.
2. Pull current bookmaker odds snapshot.
3. Compute no-vig market probabilities.
4. Run Dixon-Coles to produce scoreline matrix.
5. Sum scoreline matrix into 1X2, O/U, BTTS.
6. Run ML model to produce calibrated probabilities for same markets.
7. Blend probabilities and renormalize complementary markets.
8. Compute fair odds and EV.
9. Select the best positive-EV event per complementary market.
10. Stake with capped fractional Kelly or flat test stake.
11. Log prediction, odds snapshot, model version, features hash, and decision.

### Backtest Flow

Use a rolling-origin backtest:

1. Train on seasons up to date T.
2. Predict next fold chronologically.
3. Use only odds available before kickoff, preferably closing or selected snapshot time.
4. Settle with final result.
5. Report:
   - ROI percentage.
   - Yield per bet.
   - Bet count.
   - Hit rate.
   - Closing-line value.
   - Max drawdown.
   - Calibration by probability bin.
   - Log loss/Brier vs market.
   - Results by league, market, odds band, model family.

## Production Readiness Ranking

1. `georgedouzas/sports-betting`: best production skeleton.
2. `Torvaney/mezzala`: best reusable Dixon-Coles core.
3. `ML-KULeuven/soccer_xg`: best xG package.
4. `ProphitBet`: useful feature and calibration patterns, but desktop-app oriented.
5. `FootballBettingModel`: useful notebook feature engineering, not production.
6. `football_analytics`: source map and scraper archive, not model engine.
7. `MatchOutcomeAI`: prototype only; do not reuse model logic without correcting leakage.

## Immediate Build Plan for SabiAI

1. Implement `FootballDataLoader` inspired by ProphitBet but returning `sports-betting` style `(X, Y, O)` with date index.
2. Implement `OddsSnapshot` tables and no-vig conversion.
3. Port/adapt `mezzala` ideas into a `ScorelineModel` wrapper with methods:
   - `fit(matches)`
   - `predict_score_matrix(fixture)`
   - `to_markets(score_matrix)`
4. Build rolling feature factory:
   - Results and goals from football-data.
   - Elo from ClubElo.
   - xG from Understat/FBref where available.
5. Build `ValueEngine` using `sports-betting` rule:
   - `ev = p * odds - 1`
   - select max EV among complementary outcomes.
6. Build rolling-origin backtester before any live recommendations.
7. Add calibration dashboards before staking real money.

## Main Risks to Avoid

- Post-match leakage, especially match statistics like shots/possession from completed games used as if known for future fixtures.
- Random train/test splits for time-series betting.
- Optimizing accuracy instead of calibrated probability and EV.
- Treating ROI from tiny selected samples as stable.
- Ignoring bookmaker overround and odds timing.
- Failing to store odds snapshots and prediction versions.
- Joining team names without audited mapping tables.

