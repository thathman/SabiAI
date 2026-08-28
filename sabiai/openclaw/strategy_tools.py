from __future__ import annotations

from sabiai.storage import StrategyPlanStore
from sabiai.strategy import StrategyLearningService


class StrategyTools:
    """Read-only strategy board context for Sabi Boy."""

    def __init__(self, app):
        self.app = app

    def handlers(self) -> dict:
        return {
            "strategy.plans": self.plans,
            "strategy.latest": self.latest,
            "strategy.learning": self.learning,
        }

    def plans(self, args: dict) -> dict:
        store = StrategyPlanStore(self.app._db(initialize=True))
        return {
            "plans": store.latest(
                limit=int(args.get("limit", 20)),
                strategy_code=args.get("strategy_code"),
            )
        }

    def latest(self, args: dict) -> dict:
        return {"plans": StrategyPlanStore(self.app._db(initialize=True)).latest_by_strategy()}

    def learning(self, args: dict) -> dict:
        service = StrategyLearningService(self.app._db(initialize=True))
        return {
            "owner": str(args.get("owner") or "sabi_boy"),
            "strategies": service.summaries(
                owner=str(args.get("owner") or "sabi_boy"),
                limit=int(args.get("limit", 50)),
            ),
            "policy": {
                "minimum_sample": service.MIN_SAMPLE,
                "policy_sample": service.POLICY_SAMPLE,
                "automatic_changes": False,
            },
        }
