from __future__ import annotations

from .capabilities import canonical_sport_slug, engine_sport_profiles
from .registry import SportProfile, SportRegistry, default_sports


def complete_sports() -> SportRegistry:
    """Return the compatibility registry extended to every proactive engine sport.

    V2.4's discovery configuration grew beyond the original knowledge registry. Keeping this
    extension separate avoids renaming legacy slugs while ensuring sports found by the radar
    are no longer described as unknown by research/OpenClaw.
    """
    registry = default_sports()
    existing = {canonical_sport_slug(profile.slug) for profile in registry.all()}
    for engine in engine_sport_profiles():
        if engine.slug in existing:
            continue
        slug = engine.slug.replace("_", "-")
        aliases = (engine.slug,)
        participant_shape = {
            "team": "team",
            "head_to_head": "individual_or_team",
            "field": "field",
            "race": "field",
            "fight": "individual",
        }.get(engine.event_shape, "team_or_individual")
        registry.register(
            SportProfile(
                name=engine.name,
                slug=slug,
                aliases=aliases,
                participant_shape=participant_shape,
                common_metrics=engine.primary_metrics,
                research_topics=engine.evidence_topics,
                draw_possible=engine.draw_possible,
            )
        )
        existing.add(engine.slug)
    return registry


__all__ = ["complete_sports"]
