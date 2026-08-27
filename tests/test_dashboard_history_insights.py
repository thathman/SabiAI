import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DashboardHistoryInsightsTests(unittest.TestCase):
    def test_history_enhancement_is_loaded(self):
        index = (ROOT / "dashboard" / "v2" / "index.html").read_text(encoding="utf-8")
        self.assertIn('/assets/history_insights.js', index)

    def test_history_enhancement_uses_read_only_v2_endpoints(self):
        script = (ROOT / "dashboard" / "v2" / "history_insights.js").read_text(encoding="utf-8")
        self.assertIn('/tickets/version-outcomes', script)
        self.assertIn('/bookmakers/price-history', script)
        self.assertIn('/bookmakers/price-disagreements', script)
        for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            self.assertNotIn(f"method: '{method}'", script)
            self.assertNotIn(f'method: "{method}"', script)

    def test_dashboard_api_routes_for_advanced_history_are_get_only(self):
        api = (ROOT / "sabiai" / "dashboard" / "api.py").read_text(encoding="utf-8")
        self.assertIn('@router.get("/tickets/version-outcomes")', api)
        self.assertIn('@router.get("/bookmakers/price-history")', api)
        self.assertIn('@router.get("/bookmakers/price-disagreements")', api)

    def test_finance_view_uses_canonical_overview_profit_loss_endpoint(self):
        script = (ROOT / "dashboard" / "v2" / "app.js").read_text(encoding="utf-8")
        self.assertIn("api('/overview')", script)
        self.assertNotIn("api('/history/profit_loss')", script)


if __name__ == "__main__":
    unittest.main()
