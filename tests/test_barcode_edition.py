"""Barcode / SKU identification and edition-text (parentheses) handling. Accuracy guards first."""
import discogs_matcher as dm
from tests.test_discogs_matcher import cand

BC = "081227890988"


def ident(**kw):
    base = {"artist": "Korn", "title": "Issues", "catno": "", "label": "", "country": "", "year": None,
            "format": "vinyl", "qty": None, "variants": [], "barcode": "", "sku": ""}
    base.update(kw)
    return base


def with_bc(c, *codes):
    c = dict(c)
    c["barcode"] = list(codes)
    return c


def test_barcode_hit_is_exact():
    c = with_bc(cand(1, "Korn - Issues", 1999, "US", "Immortal", "E2 69100"), BC)
    other = with_bc(cand(2, "Korn - Issues", 2016, "Europe", "Sony", "88875"), "888751234567")
    res = dm.evaluate_candidates(ident(barcode=BC), [other, c])
    assert res["status"] == dm.EXACT and res["release_id"] == 1


def test_barcode_mismatch_is_vetoed():
    other = with_bc(cand(2, "Korn - Issues", 2016, "Europe", "Sony", "88875"), "888751234567")
    res = dm.evaluate_candidates(ident(barcode=BC), [other])
    assert res["status"] != dm.EXACT and res["release_id"] != 2 or res["status"] in (dm.NONE, dm.TITLE_ONLY)


def test_barcode_does_not_rescue_wrong_artist():
    c = with_bc(cand(3, "Metallica - Issues", 1999, "US", "X", "Z1"), BC)
    res = dm.evaluate_candidates(ident(barcode=BC), [c])
    assert res["status"] in (dm.NONE, dm.TITLE_ONLY) or res["release_id"] is None


def test_parenthetical_edition_in_candidate_title_matches():
    c = cand(4, "Korn - Issues (Limited Edition)", 1999, "US", "Immortal", "E2 69100")
    res = dm.evaluate_candidates(ident(), [c])
    assert res["status"] != dm.NONE


def test_barcode_search_param_comes_first():
    qs = dm.build_search_params(ident(barcode=BC))
    assert qs[0].get("barcode") == BC


def test_extract_identifiers_uses_structured_and_mined():
    out = dm.extract_identifiers({"artist": "Korn", "title": "Issues", "identifiers": {"barcode": BC, "sku": "E269100"},
                                  "description": "Label: Immortal"})
    assert out["barcode"] == BC and out["sku"] == "E269100"
