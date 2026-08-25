from sabiai.sports import FormService


def _source_results():
    return [
        {
            "source": "ESPN Public Data",
            "team_id": "359",
            "response": {
                "payload": {
                    "raw": {
                        "events": [
                            {
                                "id": "1",
                                "date": "2026-08-20T18:00Z",
                                "status": {"type": {"completed": True}},
                                "competitions": [
                                    {
                                        "competitors": [
                                            {
                                                "homeAway": "home",
                                                "score": "2",
                                                "winner": True,
                                                "team": {"id": "359", "displayName": "Arsenal"},
                                            },
                                            {
                                                "homeAway": "away",
                                                "score": "1",
                                                "winner": False,
                                                "team": {"id": "363", "displayName": "Chelsea"},
                                            },
                                        ]
                                    }
                                ],
                            },
                            {
                                "id": "2",
                                "date": "2026-08-10T18:00Z",
                                "status": {"type": {"completed": True}},
                                "competitions": [
                                    {
                                        "competitors": [
                                            {
                                                "homeAway": "away",
                                                "score": "0",
                                                "winner": False,
                                                "team": {"id": "359", "displayName": "Arsenal"},
                                            },
                                            {
                                                "homeAway": "home",
                                                "score": "0",
                                                "winner": False,
                                                "team": {"id": "364", "displayName": "Liverpool"},
                                            },
                                        ]
                                    }
                                ],
                            },
                            {
                                "id": "3",
                                "date": "2026-07-20T18:00Z",
                                "status": {"type": {"completed": True}},
                                "competitions": [
                                    {
                                        "competitors": [
                                            {
                                                "homeAway": "away",
                                                "score": "1",
                                                "winner": False,
                                                "team": {"id": "359", "displayName": "Arsenal"},
                                            },
                                            {
                                                "homeAway": "home",
                                                "score": "3",
                                                "winner": True,
                                                "team": {"id": "363", "displayName": "Chelsea"},
                                            },
                                        ]
                                    }
                                ],
                            },
                        ]
                    }
                }
            },
        }
    ]


def test_form_service_returns_simple_wdl_sequence():
    summary = FormService().summarize("Arsenal", _source_results(), limit=10)

    assert summary["played"] == 3
    assert summary["wins"] == 1
    assert summary["draws"] == 1
    assert summary["losses"] == 1
    assert summary["form"] == "W-D-L"
    assert summary["games"][0]["opponent"] == "Chelsea"
    assert summary["games"][0]["venue"] == "home"


def test_h2h_filters_only_the_requested_opponent():
    h2h = FormService().head_to_head("Arsenal", "Chelsea", _source_results(), limit=10)

    assert h2h["meetings"] == 2
    assert h2h["home_team_wins"] == 1
    assert h2h["draws"] == 0
    assert h2h["away_team_wins"] == 1
    assert all(game["opponent"] == "Chelsea" for game in h2h["games"])


def test_sportsdb_shape_is_normalized_too():
    source_results = [
        {
            "source": "TheSportsDB",
            "team_id": "133604",
            "response": {
                "payload": {
                    "raw": {
                        "events": [
                            {
                                "idEvent": "x1",
                                "dateEvent": "2026-08-01",
                                "strHomeTeam": "Arsenal",
                                "strAwayTeam": "Leeds",
                                "intHomeScore": "3",
                                "intAwayScore": "0",
                                "strLeague": "Premier League",
                            }
                        ]
                    }
                }
            },
        }
    ]

    summary = FormService().summarize("Arsenal", source_results)
    assert summary["form"] == "W"
    assert summary["games"][0]["score_for"] == 3.0
    assert summary["games"][0]["score_against"] == 0.0
