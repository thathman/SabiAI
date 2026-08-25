from __future__ import annotations

from sabiai.bookmakers import (
    BookmakerCommandRunner,
    BookmakerDiscoveryPlanner,
    BookmakerExecutionPlanner,
    TicketConversionService,
    default_bookmakers,
    legacy_command_adapters,
)
from sabiai.config import Settings
from sabiai.markets import MarketInterpreter
from sabiai.odds import ArbitrageEngine
from sabiai.sources import default_source_bundle
from sabiai.sports import ResearchPlanner, default_sports
from sabiai.storage import SabiDatabase, TicketDraftStore
from sabiai.tickets import TicketNormalizer, TicketTextImporter, TicketWorkshop

from .blog_tools import BlogTools
from .bookmaker_compare_tools import BookmakerCompareTools
from .bookmaker_tools import BookmakerTools
from .market_tools import MarketTools
from .record_tools import RecordTools
from .research_tools import ResearchTools
from .settlement_tools import SettlementTools
from .source_tools import SourceTools
from .sports_insight_tools import SportsInsightTools
from .sports_tools import SportsTools
from .system_tools import SystemTools
from .ticket_research_tools import TicketResearchTools
from .ticket_tools import TicketTools


class SabiToolGateway:
    """Stable OpenClaw boundary for Sabi Boy V2.

    Domain rules live in dedicated packages. This class owns shared services and tool
    registration only, keeping the OpenClaw surface small enough to audit as V2 grows.
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.from_env()
        self.source_bundle = default_source_bundle(self.settings)

        self.market_interpreter = MarketInterpreter()
        self.bookmakers = default_bookmakers()
        self.bookmaker_adapters = legacy_command_adapters()
        self.bookmaker_execution = BookmakerExecutionPlanner(
            bookmakers=self.bookmakers,
            adapters=self.bookmaker_adapters,
        )
        self.bookmaker_runner = BookmakerCommandRunner()
        self.bookmaker_discovery = BookmakerDiscoveryPlanner(self.bookmakers)
        self.ticket_converter = TicketConversionService(
            bookmakers=self.bookmakers,
            interpreter=self.market_interpreter,
        )

        self.sports = default_sports()
        self.research_planner = ResearchPlanner(self.sports)

        self.ticket_normalizer = TicketNormalizer(
            self.bookmakers,
            self.market_interpreter,
        )
        self.ticket_text_importer = TicketTextImporter()
        self.ticket_workshop = TicketWorkshop()
        self.arbitrage = ArbitrageEngine()

        groups = (
            SystemTools(self),
            SourceTools(self),
            SportsTools(self),
            SportsInsightTools(self),
            ResearchTools(self),
            MarketTools(self),
            BookmakerTools(self),
            BookmakerCompareTools(self),
            TicketTools(self),
            TicketResearchTools(self),
            RecordTools(self),
            SettlementTools(self),
            BlogTools(self),
        )
        self._handlers: dict[str, callable] = {}
        for group in groups:
            for name, handler in group.handlers().items():
                if name in self._handlers:
                    raise RuntimeError(f"Duplicate Sabi Boy tool registration: {name}")
                self._handlers[name] = handler
        self._handlers["system.tools"] = self.list_tools

    def dispatch(self, tool: str, args: dict | None = None) -> dict:
        handler = self._handlers.get(tool)
        if handler is None:
            return {
                "ok": False,
                "tool": tool,
                "error": f"Unknown Sabi Boy V2 tool: {tool}",
            }
        try:
            return {
                "ok": True,
                "tool": tool,
                "data": handler(args or {}),
            }
        except Exception as exc:
            return {
                "ok": False,
                "tool": tool,
                "error": str(exc),
            }

    def list_tools(self, args: dict | None = None) -> dict:
        namespaces: dict[str, list[str]] = {}
        for name in sorted(self._handlers):
            namespace = name.split(".", 1)[0]
            namespaces.setdefault(namespace, []).append(name)
        return {
            "count": len(self._handlers),
            "tools": sorted(self._handlers),
            "namespaces": namespaces,
        }

    def _db(self, *, initialize: bool = False) -> SabiDatabase:
        db = SabiDatabase(self.settings.v2_db)
        if initialize:
            db.initialize()
        return db

    def _draft_store(self) -> TicketDraftStore:
        return TicketDraftStore(self._db(initialize=True))
