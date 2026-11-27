"""Read-only discovery: which Shopify stores expose Pokemon collections/products, and are the card APIs up?
Prints findings only; changes nothing. Run in CI (the sandbox cannot reach these hosts)."""
import json, sys, urllib.request, urllib.parse

H = {"User-Agent": "Mozilla/5.0 (Linux; Android 16) Chrome/124.0 Mobile Safari/537.36", "Accept": "application/json"}
HOSTS = ["pokevault.com", "www.pokevault.com", "www.goodsmileus.com", "youtooz.com", "www.kidrobot.com", "www.toynk.com", "creations.mattel.com",
         "www.fangamer.com", "shop.bandai.com", "us.jazwares.com", "www.thinkgeek.com", "www.hottopic.com",
         "www.funko.com", "www.entertainmentearth.com", "www.bigbadtoystore.com", "www.premiumbandai-usa.com",
         "www.nintendo.com", "www.pokemoncenter.com", "www.gamestop.com", "www.sideshow.com", "www.tokyootakumode.com",
         "www.amiami.com", "www.solarisjapan.com", "www.hobbylink.tv"]


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=25) as r:
            return r.status, r.read().decode("utf-8", "ignore")
    except Exception as e:
        return getattr(e, "code", "ERR"), str(e)[:80]


for h in HOSTS:
    st, body = get("https://%s/collections.json?limit=250" % h)
    if st == 200:
        try:
            cols = json.loads(body).get("collections", [])
            poke = [c["handle"] for c in cols if "pok" in (c.get("handle", "") + c.get("title", "")).lower()]
            print("SHOPIFY %-30s collections=%d pokemon_handles=%s" % (h, len(cols), poke))
            continue
        except Exception:
            pass
    st2, body2 = get("https://%s/search/suggest.json?q=pokemon&resources%%5Btype%%5D=product&resources%%5Blimit%%5D=5" % h)
    print("%-38s collections=%s suggest=%s" % (h, st, st2))

for name, url in (("pokemontcg.io", "https://api.pokemontcg.io/v2/cards?q=name:Nemona&pageSize=3"),
                  ("tcgdex", "https://api.tcgdex.net/v2/en/cards?name=Nemona")):
    st, body = get(url)
    print("API", name, st, body[:300].replace("\n", " "))
st, body = get("https://api.tcgdex.net/v2/en/cards?name=Nemona")
try:
    cid = json.loads(body)[0]["id"]
    st, b = get("https://api.tcgdex.net/v2/en/cards/%s" % cid)
    d = json.loads(b)
    print("TCGDEX DETAIL", cid, "keys", sorted(d.keys()), "pricing", json.dumps(d.get("pricing"))[:400])
except Exception as e:
    print("tcgdex detail failed", e)
