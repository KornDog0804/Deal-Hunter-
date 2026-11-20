"""Phase 1: one failed provider must not end the scan."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import live_pull as lp


def _src(name):
    return {"name": name, "source_type": "shopify_store", "url": "https://example.invalid/products.json"}


def _deal(name, price=19.99):
    return {"artist": name, "title": "Album", "raw_title": name + " - Album", "price": price,
            "source": name, "source_type": "shopify_store", "link": "https://%s.example/p/1" % name.lower(),
            "version": "standard", "format": "vinyl"}


def test_failed_source_is_isolated_and_recorded(monkeypatch):
    monkeypatch.setattr(lp, "SOURCES", [_src("Alpha"), _src("Broken"), _src("Gamma")])
    lp.SOURCE_STATUS.clear()
    lp.FAILED_SOURCES.clear()

    def fake_scrape(source):
        if source["name"] == "Broken":
            raise RuntimeError("site changed its markup")
        return [_deal(source["name"])]

    monkeypatch.setattr(lp, "scrape_source", fake_scrape)
    deals = lp.build()
    names = {d["source"] for d in deals}
    assert {"Alpha", "Gamma"} <= names                      # others still delivered
    assert lp.FAILED_SOURCES == ["Broken"]
    assert lp.SOURCE_STATUS["Broken"].startswith("FAILED: RuntimeError")


def test_every_source_failing_does_not_raise_from_build(monkeypatch):
    monkeypatch.setattr(lp, "SOURCES", [_src("A"), _src("B")])
    lp.SOURCE_STATUS.clear()
    lp.FAILED_SOURCES.clear()
    monkeypatch.setattr(lp, "scrape_source", lambda s: (_ for _ in ()).throw(ValueError("boom")))
    deals = lp.build()                                      # must not raise
    assert lp._real_deal_count(deals) == 0
    assert sorted(lp.FAILED_SOURCES) == ["A", "B"]


def test_source_health_file_lists_failures(monkeypatch, tmp_path):
    monkeypatch.setattr(lp, "BASE", tmp_path)
    monkeypatch.setattr(lp, "SOURCES", [_src("Alpha"), _src("Broken")])
    monkeypatch.setattr(lp, "FAILED_SOURCES", ["Broken"])
    monkeypatch.setattr(lp, "SOURCE_STATUS", {"Broken": "FAILED: RuntimeError: x"})
    lp.write_source_health({"Alpha": 7})
    health = json.loads((tmp_path / "source_health.json").read_text())
    rows = {r["name"]: r for r in health["sources"]}
    assert rows["Alpha"]["deals"] == 7 and rows["Alpha"]["failed"] is False
    assert rows["Broken"]["failed"] is True and health["failed_sources"] == ["Broken"]


def test_all_sources_empty_keeps_previous_live_deals(tmp_path):
    """Run the real script in a scratch copy with one unusable source: it must exit
    non-zero and leave the last good live_deals.json untouched."""
    root = Path(__file__).resolve().parent.parent
    work = tmp_path / "repo"
    work.mkdir()
    for f in list(root.glob("*.py")) + list(root.glob("*.json")):
        shutil.copy(f, work / f.name)
    (work / "sources.json").write_text(json.dumps(
        {"sources": [{"name": "Bogus", "source_type": "no_such_type", "url": "https://example.invalid"}]}))
    before = (work / "live_deals.json").read_bytes()
    proc = subprocess.run([sys.executable, "live_pull.py"], cwd=work, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 1, proc.stdout[-500:] + proc.stderr[-500:]
    assert (work / "live_deals.json").read_bytes() == before
    assert "[ABORT]" in (work / "debug_live_pull.txt").read_text()
    assert (work / "source_health.json").exists()
