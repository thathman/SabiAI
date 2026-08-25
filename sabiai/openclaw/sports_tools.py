class SportsTools:
    def __init__(self, app):
        self.app = app

    def handlers(self) -> dict:
        return {
            "sports.list": self.list_sports,
            "sports.describe": self.describe,
        }

    def list_sports(self, args: dict) -> dict:
        return {
            "sports": [
                {"name": profile.name, "slug": profile.slug}
                for profile in self.app.sports.all()
            ],
            "open_ended": True,
            "note": "This registry is a starting knowledge set, not a coverage limit.",
        }

    def describe(self, args: dict) -> dict:
        profile = self.app.sports.resolve(str(args.get("sport", "")))
        return {
            "name": profile.name,
            "slug": profile.slug,
            "participant_shape": profile.participant_shape,
            "event_parts": list(profile.event_parts),
            "common_metrics": list(profile.common_metrics),
            "research_topics": list(profile.research_topics),
            "draw_possible": profile.draw_possible,
            "needs_discovery": profile.needs_discovery,
        }
