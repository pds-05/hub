import unittest

from app.services.scrape_config_schema import normalize_scrape_scheme


class ScrapeConfigSchemaTest(unittest.TestCase):
    def test_http_scheme_uses_operator_enum(self) -> None:
        self.assertEqual(normalize_scrape_scheme("http"), "HTTP")

    def test_https_scheme_uses_operator_enum(self) -> None:
        self.assertEqual(normalize_scrape_scheme("https"), "HTTPS")

    def test_unsupported_scheme_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            normalize_scrape_scheme("ftp")


if __name__ == "__main__":
    unittest.main()
