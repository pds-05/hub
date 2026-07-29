SCRAPE_SCHEMES = {
    "http": "HTTP",
    "https": "HTTPS",
}


def normalize_scrape_scheme(scheme: str) -> str:
    try:
        return SCRAPE_SCHEMES[scheme.lower()]
    except KeyError as exc:
        raise ValueError("Exporter URL scheme must be HTTP or HTTPS") from exc
