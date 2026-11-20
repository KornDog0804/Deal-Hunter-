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


def test_shared_barcode_without_extra_evidence_is_ambiguous():
    a = with_bc(cand(10, "Korn - Issues", 1999, "US", "Immortal", "E2 69100"), BC)
    b = with_bc(cand(11, "Korn - Issues", 2016, "Europe", "Sony", "88875"), BC)
    res = dm.evaluate_candidates(ident(barcode=BC), [a, b])
    assert res["status"] == dm.AMBIGUOUS and set(res["tied_ids"]) == {10, 11}


def test_shared_barcode_resolved_by_year_evidence():
    a = with_bc(cand(10, "Korn - Issues", 1999, "US", "Immortal", "E2 69100"), BC)
    b = with_bc(cand(11, "Korn - Issues", 2016, "Europe", "Sony", "88875"), BC)
    res = dm.evaluate_candidates(ident(barcode=BC, year=1999), [a, b])
    assert res["status"] == dm.EXACT and res["release_id"] == 10


def test_color_conflict_disqualifies():
    c = cand(20, "Korn - Issues", 1999, "US", "Immortal", "E2 69100", fmt=("Vinyl", "LP", "Album", "Blue"))
    res = dm.evaluate_candidates(ident(edition_text=" red vinyl "), [c])
    assert res["status"] in (dm.NONE,) and any("edition_conflict" in "".join(r["why"]) for r in res["rejected"])


def test_anniversary_conflict_disqualifies_even_with_barcode():
    c = with_bc(cand(21, "Korn - Issues (25th Anniversary)", 2024, "US", "Sony", "X"), BC)
    res = dm.evaluate_candidates(ident(barcode=BC, edition_text=" 20th anniversary edition "), [c])
    assert res["status"] == dm.NONE


def test_missing_edition_word_is_not_a_conflict():
    c = cand(22, "Korn - Issues (Limited Edition)", 1999, "US", "Immortal", "E2 69100", fmt=("Vinyl", "LP", "Red"))
    assert dm.edition_conflicts(" vinyl ", "limited edition red") == []


def test_album_title_color_word_does_not_conflict():
    t = dm.edition_text("Metallica - The Black Album (2LP)", "Metallica", dm.title_core("The Black Album"))
    assert "black" not in t


def test_sequel_number_mismatch_is_vetoed():
    c = with_bc(cand(30, "Lil Wayne - Tha Carter III", 2008, "US", "Cash Money", "X"))
    res = dm.evaluate_candidates(ident(artist="Lil Wayne", title="Tha Carter II"), [c])
    assert res["status"] == dm.NONE and any("sequel_number" in "".join(r["why"]) for r in res["rejected"])


def test_roman_and_arabic_volume_equivalent():
    assert dm.sequel_numbers("Moodsville Volume 4") == dm.sequel_numbers("Moodsville, Vol. IV") == {4}
    assert dm.sequel_numbers("Fear Of Music 2LP") == set()


def test_unknown_artist_barcode_is_strong_not_exact():
    c = with_bc(cand(31, "Opium - Project X", 2026, "Worldwide", "Interscope", "B1"), BC)
    res = dm.evaluate_candidates(ident(artist="Unknown Artist", title="Project X", barcode=BC), [c])
    assert res["status"] in (dm.STRONG, dm.NONE) and res["status"] != dm.EXACT
