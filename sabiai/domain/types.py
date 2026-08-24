from enum import Enum


class ParticipantType(str, Enum):
    TEAM = "team"
    PLAYER = "player"
    PAIR = "pair"
    DRIVER = "driver"
    FIELD = "field"
    OTHER = "other"


class ParticipantRole(str, Enum):
    HOME = "home"
    AWAY = "away"
    NEUTRAL = "neutral"


class EventStatus(str, Enum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    FINISHED = "finished"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"


class MarketKind(str, Enum):
    WIN_DRAW_LOSE = "win_draw_lose"
    WINNER = "winner"
    DOUBLE_CHANCE = "double_chance"
    HANDICAP = "handicap"
    TOTAL = "total"
    TEAM_TOTAL = "team_total"
    SET_FRAME_MAP = "set_frame_map"
    COUNT = "count"
    PLAYER = "player"
    RACE_FIELD = "race_field"
    OTHER = "other"


class Outcome(str, Enum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    DRAW = "draw"
    VOID = "void"


class TicketStatus(str, Enum):
    DRAFT = "draft"
    BUILT = "built"
    RECORDED = "recorded"
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    PARTIAL = "partial"
    VOID = "void"
