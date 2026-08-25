from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class FormGame:
    date: str | None
    home: str
    away: str
    team: str
    opponent: str
    venue: str
    result: str
    score_for: float | None
    score_against: float | None
    competition: str | None
    source: str
    source_event_id: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


class FormService:
    """Normalize recent results from multiple sports sources into simple W/D/L form.

    Provider payloads remain available elsewhere for audits. This service only creates the
    human-facing summary Sabi Boy needs for comparisons and H2H discussion.
    """

    def summarize(self, team: str, source_results: Iterable[dict], *, limit: int = 10) -> dict:
        if not team.strip():
            raise ValueError("Form summary needs an explicit team name.")
        games = self._games(team, source_results)
        games = self._dedupe(games)
        games.sort(key=lambda game: game.date or "", reverse=True)
        games = games[: max(1, min(int(limit), 50))]
        wins = sum(1 for game in games if game.result == "W")
        draws = sum(1 for game in games if game.result == "D")
        losses = sum(1 for game in games if game.result == "L")
        known = [game.result for game in games if game.result in {"W", "D", "L"}]
        return {
            "team": team.strip(),
            "played": len(games),
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "form": "-".join(known) if known else "—",
            "games": [game.as_dict() for game in games],
        }

    def head_to_head(
        self,
        home: str,
        away: str,
        source_results: Iterable[dict],
        *,
        limit: int = 10,
    ) -> dict:
        if not home.strip() or not away.strip():
            raise ValueError("H2H needs explicit home and away team names.")
        games = self._dedupe(self._games(home, source_results))
        away_key = self._norm(away)
        matches = [game for game in games if self._norm(game.opponent) == away_key]
        matches.sort(key=lambda game: game.date or "", reverse=True)
        matches = matches[: max(1, min(int(limit), 50))]
        home_wins = sum(1 for game in matches if game.result == "W")
        draws = sum(1 for game in matches if game.result == "D")
        away_wins = sum(1 for game in matches if game.result == "L")
        return {
            "home_team": home.strip(),
            "away_team": away.strip(),
            "meetings": len(matches),
            "home_team_wins": home_wins,
            "draws": draws,
            "away_team_wins": away_wins,
            "games": [game.as_dict() for game in matches],
        }

    def _games(self, team: str, source_results: Iterable[dict]) -> list[FormGame]:
        games: list[FormGame] = []
        for item in source_results:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or "Unknown source")
            team_id = str(item.get("team_id") or "").strip() or None
            response = item.get("response") if isinstance(item.get("response"), dict) else item
            payload = response.get("payload") if isinstance(response, dict) else None
            raw = payload.get("raw") if isinstance(payload, dict) else None
            events = raw.get("events") if isinstance(raw, dict) else None
            if not isinstance(events, list):
                continue
            for event in events:
                if not isinstance(event, dict):
                    continue
                parsed = self._parse_event(event, team=team, team_id=team_id, source=source)
                if parsed is not None:
                    games.append(parsed)
        return games

    def _parse_event(
        self,
        event: dict,
        *,
        team: str,
        team_id: str | None,
        source: str,
    ) -> FormGame | None:
        if source.casefold() == "thesportsdb":
            return self._parse_sportsdb(event, team=team, source=source)
        if source.casefold() == "espn public data".casefold():
            return self._parse_espn(event, team=team, team_id=team_id, source=source)
        # Best-effort generic parse for Scout/public adapters that resemble either source.
        return self._parse_sportsdb(event, team=team, source=source) or self._parse_espn(
            event, team=team, team_id=team_id, source=source
        )

    def _parse_sportsdb(self, event: dict, *, team: str, source: str) -> FormGame | None:
        home = str(event.get("strHomeTeam") or "").strip()
        away = str(event.get("strAwayTeam") or "").strip()
        if not home or not away:
            event_name = str(event.get("strEvent") or "").strip()
            if " vs " in event_name.casefold():
                left, right = self._split_vs(event_name)
                home, away = left, right
        if not home or not away:
            return None

        team_key = self._norm(team)
        if self._norm(home) == team_key:
            selected, opponent, venue = home, away, "home"
            score_for = self._number(event.get("intHomeScore"))
            score_against = self._number(event.get("intAwayScore"))
        elif self._norm(away) == team_key:
            selected, opponent, venue = away, home, "away"
            score_for = self._number(event.get("intAwayScore"))
            score_against = self._number(event.get("intHomeScore"))
        else:
            return None

        return FormGame(
            date=str(event.get("strTimestamp") or event.get("dateEvent") or "").strip() or None,
            home=home,
            away=away,
            team=selected,
            opponent=opponent,
            venue=venue,
            result=self._result(score_for, score_against),
            score_for=score_for,
            score_against=score_against,
            competition=str(event.get("strLeague") or "").strip() or None,
            source=source,
            source_event_id=str(event.get("idEvent") or "").strip() or None,
        )

    def _parse_espn(
        self,
        event: dict,
        *,
        team: str,
        team_id: str | None,
        source: str,
    ) -> FormGame | None:
        competitions = event.get("competitions")
        if not isinstance(competitions, list) or not competitions or not isinstance(competitions[0], dict):
            return None
        competition = competitions[0]
        competitors = competition.get("competitors")
        if not isinstance(competitors, list) or len(competitors) < 2:
            return None

        selected = None
        opponent = None
        team_key = self._norm(team)
        for competitor in competitors:
            if not isinstance(competitor, dict):
                continue
            info = competitor.get("team") if isinstance(competitor.get("team"), dict) else {}
            name = str(info.get("displayName") or info.get("name") or competitor.get("displayName") or "").strip()
            provider_id = str(info.get("id") or competitor.get("id") or "").strip()
            if (team_id and provider_id == team_id) or (name and self._norm(name) == team_key):
                selected = competitor
            else:
                opponent = competitor
        if selected is None or opponent is None:
            return None

        selected_team = selected.get("team") if isinstance(selected.get("team"), dict) else {}
        opponent_team = opponent.get("team") if isinstance(opponent.get("team"), dict) else {}
        selected_name = str(selected_team.get("displayName") or selected_team.get("name") or team).strip()
        opponent_name = str(opponent_team.get("displayName") or opponent_team.get("name") or "Opponent").strip()
        venue = str(selected.get("homeAway") or "neutral").casefold()
        selected_score = self._score(selected)
        opponent_score = self._score(opponent)
        result = self._result(selected_score, opponent_score)
        if result == "?" and selected.get("winner") is True:
            result = "W"
        elif result == "?" and selected.get("winner") is False and self._completed(event):
            result = "L"

        if venue == "home":
            home, away = selected_name, opponent_name
        elif venue == "away":
            home, away = opponent_name, selected_name
        else:
            names = [
                str((c.get("team") or {}).get("displayName") or (c.get("team") or {}).get("name") or "").strip()
                for c in competitors
                if isinstance(c, dict)
            ]
            home = names[0] if names else selected_name
            away = names[1] if len(names) > 1 else opponent_name

        league = event.get("league") if isinstance(event.get("league"), dict) else None
        competition_name = (
            str((league or {}).get("name") or competition.get("type", {}).get("text") or "").strip()
            if isinstance(competition.get("type"), dict)
            else str((league or {}).get("name") or "").strip()
        )
        return FormGame(
            date=str(event.get("date") or "").strip() or None,
            home=home,
            away=away,
            team=selected_name,
            opponent=opponent_name,
            venue=venue if venue in {"home", "away"} else "neutral",
            result=result,
            score_for=selected_score,
            score_against=opponent_score,
            competition=competition_name or None,
            source=source,
            source_event_id=str(event.get("id") or event.get("uid") or "").strip() or None,
        )

    @staticmethod
    def _score(competitor: dict) -> float | None:
        value = competitor.get("score")
        if isinstance(value, dict):
            value = value.get("value") if value.get("value") is not None else value.get("displayValue")
        return FormService._number(value)

    @staticmethod
    def _result(score_for: float | None, score_against: float | None) -> str:
        if score_for is None or score_against is None:
            return "?"
        if score_for > score_against:
            return "W"
        if score_for < score_against:
            return "L"
        return "D"

    @staticmethod
    def _number(value) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _completed(event: dict) -> bool:
        status = event.get("status") if isinstance(event, dict) else None
        status_type = status.get("type") if isinstance(status, dict) else None
        return bool(isinstance(status_type, dict) and status_type.get("completed"))

    @staticmethod
    def _norm(value: str) -> str:
        return "".join(ch for ch in str(value).casefold() if ch.isalnum())

    @staticmethod
    def _split_vs(value: str) -> tuple[str, str]:
        lower = value.casefold()
        idx = lower.find(" vs ")
        if idx < 0:
            return "", ""
        return value[:idx].strip(), value[idx + 4 :].strip()

    def _dedupe(self, games: list[FormGame]) -> list[FormGame]:
        result: list[FormGame] = []
        seen: set[tuple] = set()
        for game in games:
            key = (
                (game.date or "")[:10],
                tuple(sorted((self._norm(game.home), self._norm(game.away)))),
                game.score_for,
                game.score_against,
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(game)
        return result
