import json
from scripts import provider_probe as pp

PROD = {"handle": "issues", "body_html": "<p>UPC: 081227890988 Label: Immortal</p>",
        "variants": [{"sku": "E269100", "barcode": ""}]}
PROD2 = {"handle": "x", "body_html": "", "variants": [{"sku": "0081227890988", "barcode": "081227890988"}]}


def test_probe_counts_and_keeps_sku_separate():
    fetch = lambda url: json.dumps({"products": [PROD, PROD2]})
    cov, links = pp.probe_shopify({"url": "https://s.com/products.json"}, fetch)
    assert cov["listings"] == 2 and cov["barcode"] == 2 and cov["status"] == "ok"
    ids = links["https://s.com/products/issues"]
    assert ids["sku"] == "E269100" and "catno" not in ids   # SKU is never promoted to a catalogue number


def test_run_survives_failures():
    def fetch(url):
        raise OSError("blocked")
    cov, links = pp.run([{"name": "A", "source_type": "shopify_store", "url": "https://a.com/products.json"}], [], fetch, sleep=0)
    assert cov["A"]["listings"] == 0 and links == {}
