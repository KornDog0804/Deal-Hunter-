"""
Product identifiers (UPC/EAN barcode, SKU, catalogue number, label, release year) mined from
structured retailer data. Pure functions, no network.

Rules that protect accuracy:
 * a barcode must have a valid GTIN check digit, otherwise it is discarded;
 * label / year / catno are taken ONLY from explicitly labelled text ("Label: X", "Release Date: ...",
   "Cat. No: ..."), never guessed from a loose number in a sentence;
 * a SKU is kept separately: it is only a *hint* (it may be a catalogue number, a store code, or a barcode).
"""
import json
import re

_LABELLED_BARCODE = re.compile(r"\b(?:upc|ean|gtin|barcode)\b[^0-9]{0,12}(\d[\d \-]{6,17}\d)", re.I)
_LABELLED_CATNO = re.compile(
    r"(?:cat(?:alog(?:ue)?)?\.?\s*(?:no\.?|number|#)|cat#|catalog:|catalogue:)\s*[:#]?\s*"
    r"([A-Z0-9][A-Z0-9 \-./]{2,20}[A-Z0-9])", re.I)
_LABELLED_LABEL = re.compile(r"\blabel\s*[:\-]\s*([A-Za-z0-9][A-Za-z0-9 &'.\-]{1,38}?)\s*(?:$|[\n|;,<]|\s{2,}|(?=\b(?:release|format|cat|upc|genre|barcode|catalog)\b))", re.I)
_LABELLED_DATE = re.compile(
    r"\brelease(?:d)?(?:\s*date)?\s*[:\-]?\s*(?:[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+|\d{1,2}/\d{1,2}/|[A-Za-z]{3,9}\s+)?"
    r"(19[5-9]\d|20[0-4]\d)\b", re.I)


def gtin_valid(digits):
    """GTIN-8/12/13/14 check digit."""
    if not digits.isdigit() or len(digits) not in (8, 12, 13, 14):
        return False
    body, check = digits[:-1], int(digits[-1])
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def normalize_barcode(value):
    """Digits only; GTIN-14 with a leading 0 -> 13; None unless the check digit is valid."""
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 14 and digits.startswith("0"):
        digits = digits[1:]
    return digits if gtin_valid(digits) and len(digits) in (12, 13) else None


def mine_text(text):
    """Labelled identifiers from free text. Returns only what is present."""
    out, t = {}, str(text or "")
    m = _LABELLED_BARCODE.search(t)
    if m:
        bc = normalize_barcode(m.group(1))
        if bc:
            out["barcode"] = bc
    m = _LABELLED_CATNO.search(t)
    if m:
        out["catno"] = m.group(1).strip(" .-/")
    m = _LABELLED_LABEL.search(t)
    if m:
        out["label"] = m.group(1).strip(" .-")
    m = _LABELLED_DATE.search(t)
    if m:
        out["year"] = int(m.group(1))
    return out


def from_shopify(product, variant, body_text=""):
    """Identifiers from a Shopify product + the variant we price from."""
    ids = {}
    sku = str((variant or {}).get("sku") or "").strip()
    bc = normalize_barcode((variant or {}).get("barcode"))
    if bc:
        ids["barcode"] = bc
    if sku:
        sku_bc = normalize_barcode(sku)
        if sku_bc and "barcode" not in ids:
            ids["barcode"] = sku_bc
            ids["barcode_source"] = "sku"
        elif not sku_bc:
            ids["sku"] = sku
    mined = mine_text(body_text or (product or {}).get("body_html", ""))
    for k, v in mined.items():
        ids.setdefault(k, v)
    vendor = str((product or {}).get("vendor") or "").strip()
    if vendor:
        ids["vendor"] = vendor
    if "barcode" in ids and "barcode_source" not in ids:
        ids["barcode_source"] = "variant" if bc else "text"
    return ids


def from_jsonld(html):
    """schema.org Product data (gtin*, sku, mpn, brand) from <script type=application/ld+json>."""
    ids = {}
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', str(html or ""), re.S | re.I):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        items = data if isinstance(data, list) else [data]
        stack = list(items)
        while stack:
            it = stack.pop()
            if isinstance(it, dict):
                if it.get("@graph"):
                    stack.extend(it["@graph"])
                if str(it.get("@type", "")).lower() in ("product", "musicalbum"):
                    for k in ("gtin", "gtin8", "gtin12", "gtin13", "gtin14", "isbn"):
                        bc = normalize_barcode(it.get(k))
                        if bc:
                            ids["barcode"] = bc
                            ids["barcode_source"] = "jsonld"
                    if it.get("mpn") and not ids.get("sku"):
                        ids["mpn"] = str(it["mpn"]).strip()
                    if it.get("sku") and not ids.get("sku"):
                        ids["sku"] = str(it["sku"]).strip()
                    stack.extend(v for v in it.values() if isinstance(v, (dict, list)))
            elif isinstance(it, list):
                stack.extend(it)
    return ids
