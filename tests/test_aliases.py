import unittest

from sabiai.domain.aliases import AliasResolver, normalize_name


class AliasTests(unittest.TestCase):
    def test_normalize_accents_and_punctuation(self):
        self.assertEqual(normalize_name("Paris Saint-Germain FC"), "paris saint germain fc")
        self.assertEqual(normalize_name("São Paulo"), "sao paulo")

    def test_resolver_keeps_canonical_id(self):
        resolver = AliasResolver()
        resolver.add("team_1", "Manchester United", "Man Utd", "Man United")
        self.assertEqual(resolver.resolve("man-utd"), "team_1")


if __name__ == "__main__":
    unittest.main()
