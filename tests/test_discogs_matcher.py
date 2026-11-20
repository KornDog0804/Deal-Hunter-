"""Phase 1: strict Discogs matching rules."""
import discogs_matcher as dm


def cand(i, title, year, country, label, catno, fmt=("Vinyl", "LP", "Album"), qty=None):
    c = {"id": i, "title": title, "year": str(year), "country": country,
         "label": [label], "catno": catno, "format": list(fmt), "uri": "/release/%d" % i}
    if qty:
        c["formats"] = [{"name": "Vinyl", "qty": str(qty), "descriptions": list(fmt)}]
    return c


JP = cand(1001, "Men At Work - Business As Usual", 1982, "Japan", "Epic", "25·3P-379")
US = cand(1002, "Men At Work - Business As Usual", 1982, "US", "Columbia", "FC 37978")
UK = cand(1003, "Men At Work - Business As Usual", 1982, "UK", "Epic", "EPC 85669")

JP_IDENT = {"artist": "Men At Work", "title": "Business As Usual", "catno": "25·3P-379",
            "label": "Epic", "country": "Japan", "year": 1982, "format": "vinyl", "qty": None, "variants": []}


def test_catno_normalization_equivalence():
    for v in ("25·3P-379", "25-3P 379", "253P379", "25・3P-379"):
        assert dm.normalize_catno(v) == "253P379"


def test_catno_ignores_leading_label_name():
    assert dm.catno_matches("25AP 120", ["EPIC 25AP 120"], labels=["Epic"])


def test_japan_pressing_picks_japan_release_exactly():
    res = dm.evaluate_candidates(JP_IDENT, [US, UK, JP])
    assert res["status"] == dm.EXACT and res["release_id"] == 1001
    assert res["confidence"] >= 0.9


def test_never_values_japan_pressing_against_us_pressing():
    res = dm.evaluate_candidates(JP_IDENT, [US, UK])   # Japan release absent
    assert res["status"] == dm.NONE and res["release_id"] is None
    assert any("country_mismatch" in "".join(r["why"]) for r in res["rejected"])


def test_unrelated_results_are_not_accepted():
    junk = [cand(1, "Someone Else - Other Album", 2001, "US", "X", "X1"),
            cand(2, "Another Person - Different Record", 1999, "UK", "Y", "Y2")]
    ident = dict(JP_IDENT, catno="", country="", year=None, label="")
    res = dm.evaluate_candidates(ident, junk)
    assert res["status"] == dm.NONE and res["release_id"] is None


def test_catno_mismatch_vetoes_candidate():
    res = dm.evaluate_candidates(JP_IDENT, [dict(JP, catno="ZZ-999")])
    assert res["status"] == dm.NONE


def test_year_label_mismatch_veto():
    assert dm.evaluate_candidates(JP_IDENT, [dict(JP, year="1990")])["status"] == dm.NONE
    assert dm.evaluate_candidates(JP_IDENT, [dict(JP, label=["Totally Other"])])["status"] == dm.NONE


def test_disc_count_mismatch_veto():
    ident = dict(JP_IDENT, catno="", country="", year=None, label="", qty=2)
    one_disc = cand(5, "Men At Work - Business As Usual", 1982, "US", "Columbia", "X", qty=1)
    assert dm.evaluate_candidates(ident, [one_disc])["status"] == dm.NONE


def test_title_only_unique_is_labeled_unverified_and_low_confidence():
    ident = {"artist": "Noah Kahan", "title": "The Great Divide", "catno": "", "label": "",
             "country": "", "year": None, "format": "vinyl", "qty": None, "variants": []}
    res = dm.evaluate_candidates(ident, [cand(7, "Noah Kahan - The Great Divide", 2024, "US", "Mercury", "B1")])
    assert res["status"] == dm.TITLE_ONLY
    assert res["confidence"] <= dm.TITLE_ONLY_CONFIDENCE_CAP
    assert "pressing_not_verified" in res["reasons"]
    assert res["status"] not in dm.DECISION_GRADE_STATUSES


def test_two_equally_good_pressings_are_ambiguous_not_first_result():
    ident = {"artist": "Noah Kahan", "title": "The Great Divide", "catno": "", "label": "",
             "country": "", "year": None, "format": "vinyl", "qty": None, "variants": []}
    a = cand(7, "Noah Kahan - The Great Divide", 2024, "US", "Mercury", "B1")
    b = cand(8, "Noah Kahan - The Great Divide", 2024, "Europe", "Mercury", "B2")
    res = dm.evaluate_candidates(ident, [a, b])
    assert res["status"] == dm.AMBIGUOUS and res["release_id"] is None
    assert set(res["tied_ids"]) == {7, 8}


def test_variant_terms_break_a_tie():
    ident = {"artist": "Test Band", "title": "Test Album", "catno": "", "label": "", "country": "",
             "year": None, "format": "vinyl", "qty": None, "variants": ["green"]}
    black = cand(10, "Test Band - Test Album", 2023, "US", "L", "A1", fmt=("Vinyl", "LP", "Black"))
    green = cand(11, "Test Band - Test Album", 2023, "US", "L", "A2", fmt=("Vinyl", "LP", "Green"))
    res = dm.evaluate_candidates(ident, [black, green])
    assert res["release_id"] == 11


def test_strong_needs_two_corroborating_identifiers():
    ident = dict(JP_IDENT, catno="")            # no catalog number, but label+year+country agree
    res = dm.evaluate_candidates(ident, [JP, US, UK])
    assert res["status"] == dm.STRONG and res["release_id"] == 1001
    one = dict(JP_IDENT, catno="", country="", year=None)   # only label agrees -> not strong
    assert dm.evaluate_candidates(one, [JP])["status"] == dm.TITLE_ONLY


def test_search_params_never_title_only():
    for params in dm.build_search_params(JP_IDENT):
        assert params.get("artist") and ("release_title" in params or "catno" in params)
    assert dm.build_search_params({"artist": "", "title": "X"}) == []


def test_identity_key_separates_pressings():
    us = dict(JP_IDENT, catno="FC 37978", country="US", label="Columbia")
    assert dm.identity_key(JP_IDENT) != dm.identity_key(us)
    plain = {"artist": "A", "title": "T"}
    assert dm.identity_key(plain) == "a::t"          # retail keys stay simple


def test_extract_identifiers_structured_and_text():
    ident = dm.extract_identifiers({"artist": "Men At Work", "title": "Business As Usual (Japan Pressing)",
                                    "catalog_number": "25·3P-379", "label": "Epic", "year": 1982,
                                    "country": "japan", "format": "vinyl"})
    assert ident["catno"] and ident["country"] == "Japan" and ident["year"] == 1982
    text = dm.extract_identifiers({"artist": "A", "title": "T", "raw_title": "A - T Cat# ABC-123 2LP Green Vinyl"})
    assert text["catno"].startswith("ABC-123") and text["qty"] == 2 and "green" in text["variants"]
    plain = dm.extract_identifiers({"artist": "A", "title": "T (2024 Reissue)"})
    assert plain["catno"] == "" and plain["country"] == "" and plain["year"] is None  # nothing inferred


def test_search_and_match_uses_injected_http_and_stops_early():
    calls = []

    def fake(params):
        calls.append(params)
        return {"results": [UK, US, JP]}

    res = dm.search_and_match(JP_IDENT, fake)
    assert res["status"] == dm.EXACT and len(calls) == 1
    assert dm.search_and_match({"artist": "", "title": ""}, fake)["status"] == dm.NONE
