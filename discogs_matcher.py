# -*- coding: utf-8 -*-
"""
discogs_matcher.py - strict Discogs release matching for Deal Hunter.

WHY THIS EXISTS
The old code searched Discogs by "artist title" and, in the worst case, took
results[0] (price_lookup.py) or accepted a fuzzy artist/title score
(discogs_integration.py). Many pressings share an artist and title, so a Japan
1982 pressing could be valued against a US reissue. This module never guesses:

  * it compares catalog number, label, country, year and format when the
    listing provides them,
  * any provided identifier that CONTRADICTS the candidate vetoes it,
  * if two different releases are too close to call, nothing is selected.

It does no network I/O itself. `search_and_match` takes an injected `http_get`.

MATCH STATUSES
  exact       catalog number matches (and nothing contradicts)   -> trustworthy
  strong      artist+title plus >=2 of label/year/country agree   -> trustworthy
  title_only  artist+title match, pressing NOT verified           -> estimate only
  ambiguous   several releases tie; none selected                 -> no valuation
  none        no acceptable candidate                             -> no valuation
"""

import hashlib
import re
import unicodedata

import product_identifiers as pid
from difflib import SequenceMatcher

EXACT = "exact"
STRONG = "strong"
TITLE_ONLY = "title_only"
AMBIGUOUS = "ambiguous"
NONE = "none"

# A release may be used for a valuation only with one of these statuses.
VALUABLE_STATUSES = {EXACT, STRONG, TITLE_ONLY}
# Only these may drive a BUY NOW style decision.
DECISION_GRADE_STATUSES = {EXACT, STRONG}

# Tunables (kept as module constants so tests and Phase 2 can read them).
MIN_TITLE_SIM = 0.85
MIN_ARTIST_SIM = 0.80
MIN_TITLE_SIM_WITH_CATNO = 0.60
MIN_ARTIST_SIM_WITH_CATNO = 0.50
MIN_SCORE_MARGIN = 0.04          # top candidate must beat a *different* release by this much
TITLE_ONLY_CONFIDENCE_CAP = 0.60
STRONG_CONFIDENCE_CAP = 0.85

COUNTRY_ALIASES = {
    "us": "US", "usa": "US", "u.s.": "US", "u.s.a.": "US", "united states": "US",
    "uk": "UK", "u.k.": "UK", "united kingdom": "UK", "great britain": "UK",
    "japan": "Japan", "jp": "Japan", "japanese": "Japan",
    "europe": "Europe", "eu": "Europe", "germany": "Germany", "de": "Germany",
    "canada": "Canada", "australia": "Australia", "france": "France",
    "netherlands": "Netherlands", "italy": "Italy", "sweden": "Sweden",
}

VARIANT_TERMS = [
    "red", "blue", "green", "yellow", "orange", "purple", "pink", "white", "black",
    "clear", "translucent", "splatter", "marble", "marbled", "picture disc", "gold",
    "silver", "smoke", "galaxy", "reissue", "remastered", "deluxe", "limited",
    "anniversary", "180g", "colored", "coloured",
]


# --------------------------------------------------------------------------
# normalization helpers
# --------------------------------------------------------------------------

def _nfkc(value):
    return unicodedata.normalize("NFKC", str(value or ""))


def norm_text(value):
    """Lowercase, strip accents/punctuation, collapse whitespace."""
    text = unicodedata.normalize("NFKD", _nfkc(value))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_catno(value):
    """'25·3P-379' / '25-3P 379' / '253P379' all -> '253P379'."""
    return re.sub(r"[^A-Z0-9]", "", _nfkc(value).upper())


def normalize_country(value):
    key = _nfkc(value).strip().lower()
    return COUNTRY_ALIASES.get(key, _nfkc(value).strip().title() if key else "")


def _to_int_year(value):
    m = re.search(r"\b(19[4-9]\d|20[0-4]\d)\b", str(value or ""))
    return int(m.group(1)) if m else None


def similarity(a, b):
    a, b = norm_text(a), norm_text(b)
    if not a or not b:
        return 0.0
    ratio = SequenceMatcher(None, a, b).ratio()
    # A leading "the" should not sink an otherwise identical artist.
    a2, b2 = re.sub(r"^the ", "", a), re.sub(r"^the ", "", b)
    return max(ratio, SequenceMatcher(None, a2, b2).ratio())


def strip_discogs_artist_suffix(artist):
    """Discogs disambiguates artists as 'Name (2)'."""
    return re.sub(r"\s*\(\d+\)\s*$", "", str(artist or "")).strip()


def split_discogs_title(full_title):
    """'Artist - Title' -> (artist, title)."""
    text = str(full_title or "")
    if " - " in text:
        artist, title = text.split(" - ", 1)
        return strip_discogs_artist_suffix(artist), title.strip()
    return "", text.strip()


# Edition words retailers append to a title ("Mob Rules Colored Vinyl", "Blond White Cover").
# They are stripped ONLY from the END of the title and never the first token, so an album
# actually called "Red" or "Blue" survives.
_EDITION_WORDS = {
    "vinyl", "lp", "2lp", "3lp", "record", "records", "colored", "coloured", "color", "colour",
    "alt", "alternate", "alternative", "cover", "edition", "exclusive", "limited", "variant",
    "red", "blue", "green", "yellow", "orange", "purple", "pink", "white", "black", "clear",
    "translucent", "splatter", "marble", "marbled", "gold", "silver", "smoke", "galaxy",
    "picture", "disc", "reissue", "remastered", "deluxe", "anniversary", "180g", "indie",
    "neon", "coral", "swirl", "zoetrope", "turquoise", "grey", "gray", "copper", "ice", "amber",
    "teal", "aqua", "lime", "mint", "tan", "cream", "bone", "violet", "magenta", "opaque",
}


_LP_COUNT = re.compile(r"\b\d\s*-?\s*(?:lp|disc|cd)s?\b", re.I)


def clean_query_title(title):
    """Search-safe title: no parentheticals, no '2LP' counts, no quote marks, no trailing 'Vinyl'/'LP'."""
    text = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", str(title or ""))
    text = _LP_COUNT.sub(" ", text).replace('"', " ").replace("\u201c", " ").replace("\u201d", " ")
    text = re.sub(r"\s+", " ", text).strip(" -,:/")
    words = text.split(" ") if text else []
    while len(words) > 1 and words[-1].lower().strip(".,") in ("vinyl", "lp", "record", "records"):
        words.pop()
    return " ".join(words).strip()


def title_plain(title):
    """Parentheticals/LP counts removed, edition words kept ('Floral Green' stays 'Floral Green')."""
    return clean_query_title(title)


def title_core(title):
    """Drop edition noise so '(Splatter Vinyl) 2LP' / 'Colored Vinyl' do not hurt title similarity."""
    text = clean_query_title(title)
    words = text.split(" ") if text else []
    while len(words) > 1 and re.sub(r"[^a-z0-9]", "", words[-1].lower()) in _EDITION_WORDS:
        words.pop()
    return " ".join(words).strip()


# --------------------------------------------------------------------------
# identifiers from a Deal Hunter listing
# --------------------------------------------------------------------------

_COLOR_WORDS = {"red", "blue", "green", "yellow", "orange", "purple", "pink", "white", "black", "clear",
                "gold", "silver", "smoke", "grey", "gray", "brown", "cream", "violet", "aqua", "teal", "magenta"}
_COLOR_SYNONYMS = {"gray": "grey", "transparent": "clear", "violet": "purple"}
_PATTERN_WORDS = {"splatter", "marble", "marbled", "swirl", "galaxy", "picture", "pinwheel", "haze", "smoke", "split"}
_ANNIV = re.compile(r"\b(\d{1,3})(?:st|nd|rd|th)?\s*[- ]?anniv", re.I)


def edition_text(raw_title, artist="", title_core_text=""):
    """The edition-describing part of a listing title: everything except the artist and the core album title."""
    t = norm_text(raw_title)
    for chunk in (norm_text(artist), norm_text(title_core_text)):
        if chunk:
            t = t.replace(chunk, " ", 1)
    return t


def _edition_features(text):
    t = norm_text(text)
    words = set(re.findall(r"[a-z]+", t))
    colors = {_COLOR_SYNONYMS.get(w, w) for w in words if w in _COLOR_WORDS or w in _COLOR_SYNONYMS}
    patterns = {w for w in words if w in _PATTERN_WORDS} - ({"smoke"} if "smoke" in colors else set())
    anniv = {int(m) for m in _ANNIV.findall(t)}
    return {"colors": colors, "patterns": patterns, "anniv": anniv,
            "deluxe": "deluxe" in words, "standard": "standard" in words or "regular" in words}


def edition_conflicts(listing_edition, candidate_edition):
    """EXPLICIT contradictions only (both sides state a value for the same attribute and they disagree).
    A missing edition word on one side is not a conflict - it is just missing evidence."""
    a, b = _edition_features(listing_edition), _edition_features(candidate_edition)
    out = []
    if a["colors"] and b["colors"] and not (a["colors"] & b["colors"]):
        out.append("color(%s!=%s)" % ("/".join(sorted(a["colors"])), "/".join(sorted(b["colors"]))))
    if a["patterns"] and b["patterns"] and not (a["patterns"] & b["patterns"]):
        out.append("pattern")
    if a["anniv"] and b["anniv"] and not (a["anniv"] & b["anniv"]):
        out.append("anniversary(%s!=%s)" % (sorted(a["anniv"]), sorted(b["anniv"])))
    if (a["deluxe"] and b["standard"] and not b["deluxe"]) or (b["deluxe"] and a["standard"] and not a["deluxe"]):
        out.append("deluxe_vs_standard")
    return out


_CATNO_PATTERN = re.compile(
    r"(?:cat(?:alog(?:ue)?)?\.?\s*(?:no\.?|number|#)|cat#)\s*[:#]?\s*"
    r"([A-Z0-9][A-Z0-9 ·・\-./]{2,24})",
    re.I,
)
_COUNTRY_TEXT = re.compile(
    r"\b(Japan(?:ese)?|UK|US|USA|Europe(?:an)?|Germany|Canada|Australia|France|Netherlands|Italy)"
    r"\s+(?:pressing|press|import|edition|release)\b",
    re.I,
)


def _first(deal, *keys):
    for key in keys:
        value = deal.get(key)
        if value not in (None, "", [], {}):
            return value
    return ""


def extract_identifiers(deal):
    """
    Pull whatever pressing identity a listing actually provides.

    Structured fields win (Phase 2 will fill them from a Record City import);
    text patterns are used only for explicit markers such as 'Cat#'. Nothing is
    inferred from a plain title, so retail listings usually yield only
    artist+title and are classified `title_only` at best.
    """
    blob = " ".join(str(deal.get(k) or "") for k in ("raw_title", "title", "page_text_snippet"))

    structured = deal.get("identifiers") if isinstance(deal.get("identifiers"), dict) else {}
    mined = pid.mine_text(blob)          # labelled text only: "UPC:", "Label:", "Release Date:", "Cat. No:"

    catno = _first(deal, "catalog_number", "catno", "cat_no", "catalogue_number") or structured.get("catno") or mined.get("catno")
    if not catno:
        m = _CATNO_PATTERN.search(blob)
        catno = m.group(1).strip() if m else ""
    barcode = pid.normalize_barcode(_first(deal, "barcode", "upc", "ean", "gtin")) or structured.get("barcode") or mined.get("barcode") or ""
    sku = str(structured.get("sku") or "").strip()

    country = _first(deal, "country", "pressing_country")
    if not country:
        m = _COUNTRY_TEXT.search(blob)
        country = m.group(1) if m else ""

    fmt = str(_first(deal, "discogs_format", "format") or "").lower()
    low = blob.lower()
    qty = None
    m = re.search(r"\b(\d)\s?x?\s?lp\b", low)
    if m:
        qty = int(m.group(1))
    elif re.search(r"\b(double|2\s?lp)\b", low):
        qty = 2

    variants = sorted({t for t in VARIANT_TERMS if re.search(r"\b" + re.escape(t) + r"\b", low)})

    raw_artist = str(deal.get("artist") or "").strip()
    return {
        "artist": raw_artist,
        "title": title_core(deal.get("title") or ""),
        "title_plain": title_plain(deal.get("title") or ""),
        "catno": str(catno or "").strip(),
        "label": str(_first(deal, "label", "record_label") or structured.get("label") or mined.get("label") or "").strip(),
        "barcode": barcode,
        "sku": sku,
        "country": normalize_country(country),
        "year": _to_int_year(_first(deal, "year", "release_year")) or structured.get("year") or mined.get("year"),
        "format": fmt,
        "qty": qty,
        "variants": variants,
        "edition_text": edition_text(deal.get("raw_title") or deal.get("title") or "", raw_artist,
                                     title_core(deal.get("title") or "")),
    }


def pressing_suffix(ident):
    """'cat=253P379|cty=japan|yr=1982' - empty when the listing gave no pressing identifiers."""
    extras = []
    if ident.get("barcode"):
        extras.append("bc=" + ident["barcode"])
    if ident.get("sku"):
        extras.append("sku=" + normalize_catno(ident["sku"]))
    if ident.get("catno"):
        extras.append("cat=" + normalize_catno(ident["catno"]))
    if ident.get("label"):
        extras.append("lbl=" + norm_text(ident["label"]))
    if ident.get("country"):
        extras.append("cty=" + ident["country"].lower())
    if ident.get("year"):
        extras.append("yr=%d" % ident["year"])
    return "|".join(extras)


def identity_key(ident):
    """Cache key that separates different pressings of the same artist+title."""
    key = "%s::%s" % (norm_text(ident.get("artist")), norm_text(ident.get("title")))
    suffix = pressing_suffix(ident)
    return key + ("::" + suffix if suffix else "")


def build_search_params(ident):
    """
    Ordered Discogs /database/search parameter sets. Most specific first.
    Deliberately NO title-only query: that is how unrelated artists slipped in.
    """
    base = {"type": "release", "per_page": 25}
    if ident.get("format") in ("", "vinyl"):
        base["format"] = "Vinyl"
    queries = []
    if ident.get("barcode"):
        queries.append(dict(base, barcode=ident["barcode"]))
    if ident.get("sku") and ident.get("artist"):
        queries.append(dict(base, catno=ident["sku"], artist=ident["artist"]))
    if ident.get("catno"):
        q = dict(base, catno=ident["catno"])
        if ident.get("artist"):
            q["artist"] = ident["artist"]
        queries.append(q)
    if ident.get("artist") and ident.get("title"):
        plain = ident.get("title_plain") or ident["title"]
        for t in dict.fromkeys([plain, ident["title"]]):      # full cleaned title first, then edition-trimmed
            q = dict(base, artist=ident["artist"], release_title=t)
            for key in ("label", "country", "year"):
                if ident.get(key):
                    q[key] = ident[key]
            queries.append(q)
        # last resort: fuzzy artist+title text search. Still needs the artist, and every
        # candidate is validated by the strict matcher afterwards.
        queries.append(dict(base, q="%s %s" % (ident["artist"], plain)))
    return queries


# --------------------------------------------------------------------------
# candidate evaluation
# --------------------------------------------------------------------------

def _candidate_fields(cand):
    artist, title = split_discogs_title(cand.get("title", ""))
    labels = cand.get("label") or []
    if isinstance(labels, str):
        labels = [labels]
    formats = cand.get("format") or []
    if isinstance(formats, str):
        formats = [formats]
    qty = None
    for fmt in cand.get("formats") or []:
        if isinstance(fmt, dict) and str(fmt.get("name", "")).lower() == "vinyl":
            try:
                qty = int(fmt.get("qty"))
            except (TypeError, ValueError):
                pass
            formats = list(formats) + list(fmt.get("descriptions") or [])
    catnos = [c.strip() for c in re.split(r"[,/;]", str(cand.get("catno") or "")) if c.strip()]
    return {
        "id": cand.get("id"),
        "artist": artist,
        "title": title,
        "labels": [str(l) for l in labels],
        "catnos": catnos,
        "barcodes": [b for b in (pid.normalize_barcode(x) for x in (cand.get("barcode") or [])
                                 if isinstance(cand.get("barcode"), list)) if b],
        "country": normalize_country(cand.get("country")),
        "year": _to_int_year(cand.get("year")),
        "formats": [str(f) for f in formats],
        "qty": qty,
        "edition": " ".join(re.findall(r"\(([^)]*)\)", title)) + " " + " ".join(str(f) for f in formats),
        "uri": cand.get("uri", ""),
        "raw": cand,
    }


def catno_matches(deal_catno, candidate_catnos, labels=()):
    """Equal after normalization, ignoring a leading label name ('EPIC 25AP120')."""
    want = normalize_catno(deal_catno)
    if not want:
        return False
    label_prefixes = [normalize_catno(l) for l in labels if normalize_catno(l)]
    for have_raw in candidate_catnos:
        have = normalize_catno(have_raw)
        if not have:
            continue
        if have == want:
            return True
        for prefix in label_prefixes:
            if have.startswith(prefix) and have[len(prefix):] == want:
                return True
            if want.startswith(prefix) and want[len(prefix):] == have:
                return True
    return False


def _label_agrees(deal_label, cand_labels):
    want = norm_text(deal_label)
    for label in cand_labels:
        have = norm_text(label)
        if not have:
            continue
        if want == have or want in have or have in want or similarity(want, have) >= 0.8:
            return True
    return False


_CREDIT_JOIN = ("and", "with", "feat", "featuring", "vs", "plus", "x")


def artist_similarity(deal_artist, cand_artist):
    """Name similarity that also accepts credit variants: 'Bob Marley' vs 'Bob Marley & The Wailers'
    (the shorter name must be a whole-word prefix followed by a join word) and Discogs
    disambiguation numbers ('Archers (3)'). A bare prefix like 'Black' vs 'Black Sabbath' is NOT accepted."""
    clean = lambda v: re.sub(r"\s*\(\d+\)\s*$", "", str(v or "")).strip()
    a, b = clean(deal_artist), clean(cand_artist)
    base = similarity(a, b)
    na, nb = norm_text(a), norm_text(b)
    short, long_ = (na, nb) if len(na) <= len(nb) else (nb, na)
    if short and long_.startswith(short + " "):
        rest = long_[len(short) + 1:].split(" ", 1)[0]
        if rest in _CREDIT_JOIN:
            base = max(base, 0.9)
    return base


def evaluate_candidate(ident, cand):
    """Score one candidate. Returns dict with `vetoes`, `positives`, `score`."""
    c = _candidate_fields(cand)
    vetoes, positives = [], []

    # Best of: edition-stripped title, or the title with only parentheticals removed.
    # Discogs titles often carry edition text in parentheses ("Guts (Spilled)"): compare on the title
    # with that text removed too. The edition text itself is NOT thrown away: it is compared with the
    # listing's edition words below (variant_bonus / edition_conflict) so pressings can still be told apart.
    cand_titles = {c["title"], clean_query_title(c["title"]), title_core(c["title"])}
    title_sim = max(similarity(a, b) for a in (ident.get("title"), ident.get("title_plain") or "")
                    for b in cand_titles if b)
    artist_sim = artist_similarity(ident.get("artist"), c["artist"])

    barcode_hit = bool(ident.get("barcode") and ident["barcode"] in c["barcodes"])
    sku_hit = False
    if ident.get("sku") and c["catnos"]:
        sku_hit = catno_matches(ident["sku"], c["catnos"], c["labels"] + [ident.get("label", "")])
    if barcode_hit:
        positives.append("barcode_match")
    elif ident.get("barcode") and c["barcodes"]:
        vetoes.append("barcode_mismatch")

    catno_hit = False
    if ident.get("catno"):
        if c["catnos"]:
            catno_hit = catno_matches(ident["catno"], c["catnos"], c["labels"] + [ident.get("label", "")])
            (positives if catno_hit else vetoes).append("catno_match" if catno_hit else "catno_mismatch")

    if sku_hit:
        positives.append("sku_catno_match")
    strong_id = catno_hit or barcode_hit
    min_title = MIN_TITLE_SIM_WITH_CATNO if strong_id else MIN_TITLE_SIM
    min_artist = MIN_ARTIST_SIM_WITH_CATNO if strong_id else MIN_ARTIST_SIM
    if title_sim < min_title:
        vetoes.append("title_mismatch(%.2f)" % title_sim)
    if artist_sim < min_artist:
        vetoes.append("artist_mismatch(%.2f)" % artist_sim)

    label_pos = year_pos = country_pos = 0
    if ident.get("country") and c["country"]:
        if ident["country"] == c["country"]:
            country_pos = 1
            positives.append("country_match")
        else:
            vetoes.append("country_mismatch(%s!=%s)" % (ident["country"], c["country"]))
    if ident.get("year") and c["year"]:
        if ident["year"] == c["year"]:
            year_pos = 1
            positives.append("year_match")
        else:
            vetoes.append("year_mismatch(%s!=%s)" % (ident["year"], c["year"]))
    if ident.get("label") and c["labels"]:
        if _label_agrees(ident["label"], c["labels"]):
            label_pos = 1
            positives.append("label_match")
        else:
            vetoes.append("label_mismatch")

    fmt_lower = " ".join(c["formats"]).lower()
    if ident.get("format") in ("", "vinyl"):
        if c["formats"] and "vinyl" not in fmt_lower and "lp" not in fmt_lower:
            vetoes.append("format_not_vinyl")
    elif ident["format"] in ("cd", "cassette") and c["formats"]:
        if ident["format"] not in fmt_lower:
            vetoes.append("format_mismatch")
    if ident.get("qty") and c["qty"] and ident["qty"] != c["qty"]:
        vetoes.append("disc_count_mismatch(%s!=%s)" % (ident["qty"], c["qty"]))

    # A barcode identifies the release, so the listing's own country/year/label/disc-count/catno guesses
    # are demoted to "soft" mismatches: they do not veto, but they do count against it if the barcode is shared.
    soft = []
    if barcode_hit:
        soft = [v for v in vetoes if v.startswith(("country_mismatch", "year_mismatch", "label_mismatch",
                                                   "disc_count_mismatch", "catno_mismatch"))]
        vetoes[:] = [v for v in vetoes if v not in soft]

    # EXPLICIT edition contradictions (red vs blue, 20th vs 25th anniversary, deluxe vs standard) always disqualify.
    conflicts = edition_conflicts(ident.get("edition_text", ""), c["edition"])
    for cf in conflicts:
        vetoes.append("edition_conflict:" + cf)

    cand_text = norm_text(fmt_lower + " " + c["title"])
    wanted = ident.get("variants") or []
    overlap = sum(1 for v in wanted if re.search(r"\b" + re.escape(v) + r"\b", cand_text))
    variant_bonus = 0.05 * (overlap / len(wanted)) if wanted else 0.0

    # edition words on one side but a contradicting one on the other (e.g. listing "Deluxe", Discogs "(Standard)")
    paren = " ".join(re.findall(r"\(([^)]*)\)", c["title"])).lower()
    edition_penalty = 0.03 if (("deluxe" in paren) != ("deluxe" in " ".join(wanted).lower() + " " + norm_text(ident.get("title_plain", "")))
                               and "deluxe" in (paren + " ".join(wanted))) else 0.0
    score = (0.35 * title_sim + 0.20 * artist_sim + (0.30 if catno_hit else 0.0) + (0.30 if barcode_hit else 0.0)
             - edition_penalty
             + 0.05 * label_pos + 0.05 * year_pos + 0.05 * country_pos + variant_bonus)
    return {"id": c["id"], "score": round(score, 4), "vetoes": vetoes, "positives": positives,
            "title_sim": round(title_sim, 3), "artist_sim": round(artist_sim, 3),
            "fields": c, "catno_hit": catno_hit, "barcode_hit": barcode_hit, "sku_hit": sku_hit,
            "soft_mismatch": soft, "corroborated": bool(label_pos or year_pos or country_pos or catno_hit or overlap)}


def _result(status, confidence=0.0, chosen=None, reasons=None, rejected=None, tied=None):
    f = (chosen or {}).get("fields") or {}
    return {
        "status": status,
        "confidence": round(float(confidence), 3),
        "release_id": f.get("id"),
        "uri": f.get("uri", ""),
        "matched_artist": f.get("artist", ""),
        "matched_title": f.get("title", ""),
        "matched_label": ", ".join(f.get("labels", [])[:2]),
        "matched_catno": ", ".join(f.get("catnos", [])[:2]),
        "matched_country": f.get("country", ""),
        "matched_year": f.get("year"),
        "reasons": reasons or [],
        "rejected": rejected or [],
        "tied_ids": tied or [],
    }


def evaluate_candidates(ident, candidates):
    """Pick ONE release or return none/ambiguous. Never falls back to results[0]."""
    scored, rejected = {}, []
    for cand in candidates or []:
        if not isinstance(cand, dict) or not cand.get("id"):
            continue
        ev = evaluate_candidate(ident, cand)
        if ev["vetoes"]:
            rejected.append({"id": ev["id"], "why": ev["vetoes"]})
            continue
        prev = scored.get(ev["id"])
        if prev is None or ev["score"] > prev["score"]:
            scored[ev["id"]] = ev

    accepted = sorted(scored.values(), key=lambda e: e["score"], reverse=True)
    if not accepted:
        return _result(NONE, 0.0, reasons=["no_candidate_passed_checks"], rejected=rejected[:10])

    top = accepted[0]

    # SHARED BARCODE: several different Discogs releases carry the listing's barcode (reissues often share one).
    # The barcode alone cannot say which pressing it is, so we need independent evidence for exactly one of them.
    bc_hits = [e for e in accepted if e["barcode_hit"]]
    if len(bc_hits) > 1:
        proven = [e for e in bc_hits if e["corroborated"] and not e["soft_mismatch"]]
        if len(proven) == 1:
            top = proven[0]
            top["positives"] = top["positives"] + ["barcode_shared_resolved"]
            return _result(EXACT, max(0.90, min(0.95, top["score"])), top, top["positives"], rejected[:10])
        return _result(AMBIGUOUS, 0.0, reasons=["barcode_shared_by_%d_releases" % len(bc_hits)],
                       rejected=rejected[:10], tied=[e["id"] for e in bc_hits][:10])
    if len(accepted) > 1 and (top["score"] - accepted[1]["score"]) < MIN_SCORE_MARGIN:
        # Prefer an exact catalog-number hit over a non-hit before declaring a tie.
        exact_hits = [e for e in accepted if e["catno_hit"] or e["barcode_hit"]]
        if len(exact_hits) == 1:
            top = exact_hits[0]
        else:
            tied = [e["id"] for e in accepted if (top["score"] - e["score"]) < MIN_SCORE_MARGIN]
            return _result(AMBIGUOUS, 0.0, reasons=["multiple_releases_too_close"],
                           rejected=rejected[:10], tied=tied[:10])

    corroborating = [p for p in top["positives"] if p not in ("catno_match", "barcode_match", "sku_catno_match")]
    if top["catno_hit"] or top["barcode_hit"]:
        conf = max(0.90, min(1.0, top["score"]))
        return _result(EXACT, conf, top, top["positives"], rejected[:10])
    if top["sku_hit"] and top["title_sim"] >= MIN_TITLE_SIM and top["artist_sim"] >= MIN_ARTIST_SIM:
        # a SKU is only a hint that it is the catalogue number; matching Discogs' catno earns "strong", not "exact"
        return _result(STRONG, min(STRONG_CONFIDENCE_CAP, max(0.70, top["score"])), top, top["positives"], rejected[:10])
    if len(corroborating) >= 2:
        conf = min(STRONG_CONFIDENCE_CAP, max(0.70, top["score"]))
        return _result(STRONG, conf, top, top["positives"], rejected[:10])
    conf = min(TITLE_ONLY_CONFIDENCE_CAP, top["score"])
    reasons = top["positives"] + ["pressing_not_verified"]
    return _result(TITLE_ONLY, conf, top, reasons, rejected[:10])


def search_and_match(ident, http_get, max_queries=3):
    """
    Query Discogs via the injected `http_get(params) -> dict | None`, pool the
    candidates and evaluate them. Stops early on an exact/strong match.
    """
    if not ident.get("artist") or not ident.get("title"):
        return _result(NONE, 0.0, reasons=["missing_artist_or_title"])
    pooled, seen = [], set()
    result = _result(NONE, 0.0, reasons=["no_results"])
    for params in build_search_params(ident)[:max_queries]:
        data = http_get(params) or {}
        for cand in data.get("results", []) or []:
            if cand.get("id") not in seen:
                seen.add(cand.get("id"))
                pooled.append(cand)
        if not pooled:
            continue
        result = evaluate_candidates(ident, pooled)
        if result["status"] in DECISION_GRADE_STATUSES:
            break
    return result


def match_fingerprint(result):
    """Short stable id for logging/debug of what was chosen."""
    blob = "%s|%s" % (result.get("status"), result.get("release_id"))
    return hashlib.sha1(blob.encode()).hexdigest()[:10]
