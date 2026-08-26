from unittest.mock import MagicMock, patch

from scripts.bet9ja_book import BET9JA_URL, _search_current_event


def test_bet9ja_builder_searches_current_site_when_league_guess_misses():
    page = MagicMock()
    search = MagicMock()
    search.count.return_value = 1
    search.first.is_visible.return_value = True
    page.locator.return_value = search
    leg = {
        "match": "Borneo Samarinda vs Madura United",
        "pick": "Borneo Samarinda to win",
        "sport": "Football",
    }

    with patch("scripts.bet9ja_book._dismiss_overlay"), patch(
        "scripts.bet9ja_book._find_and_click_odds", return_value=True
    ) as add:
        result = _search_current_event(page, leg)

    assert result is True
    page.goto.assert_called_once_with(
        BET9JA_URL,
        wait_until="domcontentloaded",
        timeout=30000,
    )
    search.first.fill.assert_called_once_with("Borneo Samarinda")
    add.assert_called_once_with(page, leg)
