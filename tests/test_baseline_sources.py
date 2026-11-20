"""BASELINE: all 42 sources must still exist and still route to a handler."""
import json
import live_pull as lp

# NOTE: sources.json holds 42 entries (you referred to "40"). Pinned at the real count.
EXPECTED_SOURCE_COUNT = 42
KNOWN_ROUTED_TYPES = {
    "shopify_store", "merchnow_store", "html_store", "walmart_catalog_source",
    "amazon_catalog_source", "target_catalog_source", "popsike_source",
}


def load_sources():
    return json.load(open("sources.json"))["sources"]


def test_all_sources_present():
    assert len(load_sources()) == EXPECTED_SOURCE_COUNT


def test_source_names_unique_and_urls_present():
    names = [s["name"] for s in load_sources()]
    assert len(names) == len(set(names))
    assert all(s["url"].startswith("https://") for s in load_sources())


def test_every_source_type_is_routed(monkeypatch):
    """Patch every builder; no source may fall through to 'unknown source_type'."""
    sentinel = [{"title": "x", "artist": "y", "price": 1.0, "link": "https://e/x"}]
    for fn in ("build_shopify_deals", "build_html_deals", "build_deepdiscount",
               "build_walmart_catalog", "build_target_catalog", "build_unfd",
               "build_millions"):
        monkeypatch.setattr(lp, fn, lambda source, _s=sentinel: list(_s))
    lp.SOURCE_STATUS.clear()
    for src in load_sources():
        assert src["source_type"] in KNOWN_ROUTED_TYPES, src
        lp.scrape_source(src)
        assert "SKIPPED (unknown type" not in lp.SOURCE_STATUS.get(src["name"], "")
