from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from uuid import uuid4

from sabiai.storage import SabiDatabase


@dataclass(frozen=True, slots=True)
class BlogPost:
    id: str
    slug: str
    title: str
    body: str
    excerpt: str | None
    category: str | None
    tags: tuple[str, ...]
    status: str
    related: dict
    published_at: str | None
    created_at: str
    updated_at: str


class BlogService:
    VALID_STATUS = {"draft", "published", "archived"}

    def __init__(self, database: SabiDatabase):
        self.db = database

    def create(
        self,
        *,
        title: str,
        body: str,
        excerpt: str | None = None,
        category: str | None = None,
        tags: list[str] | tuple[str, ...] = (),
        related: dict | None = None,
        slug: str | None = None,
        status: str = "draft",
        published_at: str | None = None,
    ) -> BlogPost:
        title = title.strip()
        body = body.strip()
        if not title:
            raise ValueError("Blog post needs a title.")
        if not body:
            raise ValueError("Blog post needs a body.")
        status = self._status(status)
        post_id = f"post_{uuid4().hex}"
        post_slug = self._unique_slug(slug or title)
        stamp = published_at
        if status == "published" and not stamp:
            stamp = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO blog_posts(
                       id,slug,title,body,excerpt,category,tags_json,status,
                       related_json,published_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    post_id,
                    post_slug,
                    title,
                    body,
                    excerpt.strip() if excerpt else None,
                    category.strip() if category else None,
                    json.dumps(self._tags(tags), ensure_ascii=False),
                    status,
                    json.dumps(related or {}, ensure_ascii=False),
                    stamp,
                ),
            )
        post = self.get(post_id=post_id)
        if post is None:
            raise RuntimeError("Blog post could not be reloaded after creation.")
        return post

    def update(
        self,
        post_id: str,
        *,
        title: str | None = None,
        body: str | None = None,
        excerpt: str | None = None,
        category: str | None = None,
        tags: list[str] | tuple[str, ...] | None = None,
        related: dict | None = None,
        status: str | None = None,
    ) -> BlogPost:
        current = self.get(post_id=post_id)
        if current is None:
            raise KeyError(f"Unknown blog post: {post_id}")
        next_title = title.strip() if title is not None else current.title
        next_body = body.strip() if body is not None else current.body
        if not next_title or not next_body:
            raise ValueError("Blog title and body cannot be empty.")
        next_status = self._status(status) if status is not None else current.status
        published_at = current.published_at
        if next_status == "published" and not published_at:
            published_at = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            conn.execute(
                """UPDATE blog_posts SET
                       title=?,body=?,excerpt=?,category=?,tags_json=?,status=?,
                       related_json=?,published_at=?,updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (
                    next_title,
                    next_body,
                    excerpt.strip() if excerpt is not None and excerpt else (None if excerpt == "" else current.excerpt),
                    category.strip() if category is not None and category else (None if category == "" else current.category),
                    json.dumps(self._tags(tags) if tags is not None else list(current.tags), ensure_ascii=False),
                    next_status,
                    json.dumps(related if related is not None else current.related, ensure_ascii=False),
                    published_at,
                    post_id,
                ),
            )
        updated = self.get(post_id=post_id)
        if updated is None:
            raise RuntimeError("Blog post disappeared after update.")
        return updated

    def publish(self, post_id: str, *, published_at: str | None = None) -> BlogPost:
        current = self.get(post_id=post_id)
        if current is None:
            raise KeyError(f"Unknown blog post: {post_id}")
        stamp = published_at or current.published_at or datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            conn.execute(
                """UPDATE blog_posts
                   SET status='published', published_at=?, updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (stamp, post_id),
            )
        post = self.get(post_id=post_id)
        if post is None:
            raise RuntimeError("Blog post disappeared after publication.")
        return post

    def archive(self, post_id: str) -> BlogPost:
        return self.update(post_id, status="archived")

    def get(self, *, post_id: str | None = None, slug: str | None = None) -> BlogPost | None:
        if not post_id and not slug:
            raise ValueError("Provide post_id or slug.")
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM blog_posts WHERE id=?" if post_id else "SELECT * FROM blog_posts WHERE slug=?",
                (post_id or slug,),
            ).fetchone()
        return self._row(row) if row else None

    def list(
        self,
        *,
        status: str | None = None,
        category: str | None = None,
        limit: int = 50,
    ) -> list[BlogPost]:
        where = []
        params: list[object] = []
        if status:
            where.append("status=?")
            params.append(self._status(status))
        if category:
            where.append("category=?")
            params.append(category.strip())
        sql = "SELECT * FROM blog_posts"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY COALESCE(published_at, created_at) DESC, created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 250)))
        with self.db.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._row(row) for row in rows]

    def _unique_slug(self, value: str) -> str:
        base = self._slugify(value)
        candidate = base
        counter = 2
        with self.db.connect() as conn:
            while conn.execute("SELECT 1 FROM blog_posts WHERE slug=?", (candidate,)).fetchone():
                candidate = f"{base}-{counter}"
                counter += 1
        return candidate

    @staticmethod
    def _slugify(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
        return slug[:96] or f"post-{uuid4().hex[:8]}"

    @classmethod
    def _status(cls, value: str) -> str:
        status = value.strip().casefold()
        if status not in cls.VALID_STATUS:
            raise ValueError(f"Unknown blog status: {value}")
        return status

    @staticmethod
    def _tags(tags) -> list[str]:
        return list(dict.fromkeys(str(tag).strip() for tag in tags if str(tag).strip()))

    @staticmethod
    def _row(row) -> BlogPost:
        return BlogPost(
            id=row["id"],
            slug=row["slug"],
            title=row["title"],
            body=row["body"],
            excerpt=row["excerpt"],
            category=row["category"],
            tags=tuple(json.loads(row["tags_json"] or "[]")),
            status=row["status"],
            related=json.loads(row["related_json"] or "{}"),
            published_at=row["published_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
