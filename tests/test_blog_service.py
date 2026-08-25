import tempfile
import unittest
from pathlib import Path

from sabiai.blog import BlogService
from sabiai.storage import SabiDatabase


class BlogServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = SabiDatabase(Path(self.tmp.name) / "v2.db")
        self.db.initialize()
        self.blog = BlogService(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_draft_and_publish(self):
        post = self.blog.create(
            title="What I noticed about our bigger tickets",
            body="I keep seeing one weak leg undo otherwise strong tickets.",
            category="What I Learned",
            tags=["tickets", "lessons"],
            related={"ticket_ids": ["ticket_1"]},
        )
        self.assertEqual(post.status, "draft")
        self.assertEqual(post.slug, "what-i-noticed-about-our-bigger-tickets")
        published = self.blog.publish(post.id)
        self.assertEqual(published.status, "published")
        self.assertIsNotNone(published.published_at)
        self.assertEqual(published.related["ticket_ids"], ["ticket_1"])

    def test_duplicate_titles_get_unique_slugs(self):
        first = self.blog.create(title="What I Learned", body="First reflection.")
        second = self.blog.create(title="What I Learned", body="Second reflection.")
        self.assertEqual(first.slug, "what-i-learned")
        self.assertEqual(second.slug, "what-i-learned-2")

    def test_update_preserves_first_person_post_and_metadata(self):
        post = self.blog.create(
            title="A strange day in volleyball",
            body="I started the day watching football.",
            tags=["volleyball"],
        )
        updated = self.blog.update(
            post.id,
            body="I started the day watching football, but volleyball changed what I was looking at.",
            category="Sabi Boy's Thoughts",
        )
        self.assertIn("I started", updated.body)
        self.assertEqual(updated.tags, ("volleyball",))
        self.assertEqual(updated.category, "Sabi Boy's Thoughts")

    def test_list_can_filter_published_posts(self):
        draft = self.blog.create(title="Draft", body="Not ready.")
        published = self.blog.create(title="Published", body="Ready.", status="published")
        rows = self.blog.list(status="published")
        self.assertEqual([row.id for row in rows], [published.id])
        self.assertNotEqual(rows[0].id, draft.id)


if __name__ == "__main__":
    unittest.main()
