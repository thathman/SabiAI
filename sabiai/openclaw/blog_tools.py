from __future__ import annotations

from sabiai.blog import BlogService, BlogTriggerService
from sabiai.storage import HistoryService

from .serializers import json_value


class BlogTools:
    def __init__(self, app):
        self.app = app

    def handlers(self) -> dict:
        return {
            "blog.create": self.create,
            "blog.update": self.update,
            "blog.publish": self.publish,
            "blog.archive": self.archive,
            "blog.get": self.get,
            "blog.list": self.list_posts,
            "blog.reflection.context": self.reflection_context,
            "blog.triggers": self.triggers,
        }

    def _service(self) -> BlogService:
        return BlogService(self.app._db(initialize=True))

    def create(self, args: dict) -> dict:
        post = self._service().create(
            title=str(args.get("title", "")),
            body=str(args.get("body", "")),
            excerpt=args.get("excerpt"),
            category=args.get("category"),
            tags=args.get("tags") or [],
            related=args.get("related") or {},
            slug=args.get("slug"),
            status=str(args.get("status", "draft")),
            published_at=args.get("published_at"),
        )
        return json_value(post)

    def update(self, args: dict) -> dict:
        post = self._service().update(
            str(args["post_id"]),
            title=args.get("title"),
            body=args.get("body"),
            excerpt=args.get("excerpt") if "excerpt" in args else None,
            category=args.get("category") if "category" in args else None,
            tags=args.get("tags") if "tags" in args else None,
            related=args.get("related") if "related" in args else None,
            status=args.get("status"),
        )
        return json_value(post)

    def publish(self, args: dict) -> dict:
        return json_value(
            self._service().publish(
                str(args["post_id"]),
                published_at=args.get("published_at"),
            )
        )

    def archive(self, args: dict) -> dict:
        return json_value(self._service().archive(str(args["post_id"])))

    def get(self, args: dict) -> dict:
        post = self._service().get(
            post_id=args.get("post_id"),
            slug=args.get("slug"),
        )
        return {"found": post is not None, "post": json_value(post) if post else None}

    def list_posts(self, args: dict) -> dict:
        posts = self._service().list(
            status=args.get("status"),
            category=args.get("category"),
            limit=int(args.get("limit", 50)),
        )
        return {"posts": [json_value(post) for post in posts]}

    def reflection_context(self, args: dict) -> dict:
        db = self.app._db(initialize=True)
        blog = BlogService(db)
        history = HistoryService(db)
        recent_posts = blog.list(limit=int(args.get("post_limit", 8)))
        triggers = BlogTriggerService(db).evaluate(
            hours=int(args.get("trigger_hours", 24)),
            streak_milestone=int(args.get("streak_milestone", 3)),
        )
        return {
            "purpose": "Use this context to write a first-person Sabi Boy reflection grounded in our own history and previous thinking, not generic sports news.",
            "history": history.summary(),
            "by_sport": history.by_sport(),
            "by_market": history.by_market(),
            "triggers": [json_value(item) for item in triggers],
            "recent_posts": [
                {
                    "id": post.id,
                    "slug": post.slug,
                    "title": post.title,
                    "excerpt": post.excerpt,
                    "category": post.category,
                    "tags": list(post.tags),
                    "status": post.status,
                    "published_at": post.published_at,
                }
                for post in recent_posts
            ],
        }

    def triggers(self, args: dict) -> dict:
        items = BlogTriggerService(self.app._db(initialize=True)).evaluate(
            hours=int(args.get("hours", 24)),
            streak_milestone=int(args.get("streak_milestone", 3)),
        )
        return {
            "triggers": [json_value(item) for item in items],
            "should_reflect": bool(items),
            "highest_priority": items[0].priority if items else None,
        }
