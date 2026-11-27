import olivia_pull as op

CARD = {"name": "Nemona", "number": "90", "rarity": "Special Illustration Rare",
        "set": {"name": "Paldea Evolved", "printedTotal": 93},
        "images": {"small": "http://x/i.png"},
        "tcgplayer": {"url": "https://prices.pokemontcg.io/tcgplayer/x",
                      "prices": {"holofoil": {"market": 12.5}, "normal": {"market": 3.0}}}}


def test_trainer_needs_pokemon_context():
    assert op.matches("Pokemon TCG Nemona Supporter") == ["POKEMON"]
    assert op.matches("Drayton Manor theme park tickets") == []
    assert op.matches("Pokémon card Drayton full art") == ["POKEMON"]


def test_card_row_uses_cheapest_priced_variant_and_labels_market():
    r = op.pokemon_card_row(CARD, "NEMONA")
    assert r["price"] == 3.0 and r["product_type"] == "CARDS" and r["chase"] is True
    assert "90/93" in r["title"] and "Market price" in r["availability_text"]


def test_unpriced_or_linkless_cards_skipped():
    assert op.pokemon_card_row({**CARD, "tcgplayer": {"url": "u", "prices": {}}}, "NEMONA") is None


def test_fail_soft_and_exact_name_only():
    def boom(url): raise OSError("blocked")
    assert op.pokemon_trainer_card_rows(boom) == []
    other = {**CARD, "name": "Nemona's Adventure"}
    rows = op.pokemon_trainer_card_rows(lambda u: {"data": [CARD, other]})
    assert len(rows) == 1 and rows[0]["character"] == "NEMONA"   # "Nemona's Adventure" and the Drayton query add nothing


def test_figure_sources_tag_pokemon_and_survive_missing_collections(monkeypatch):
    calls = []
    def fake(**kw):
        calls.append((kw["source"], kw["forced_interest"], len(kw["endpoints"])))
        return []
    monkeypatch.setattr(op, "shopify_collection_rows", fake)
    assert op.pokemon_figure_rows() == []
    assert calls == [("Good Smile US", "POKEMON", 3), ("Youtooz", "POKEMON", 1)]


def test_tcgdex_fallback_when_main_api_down():
    def fake(url):
        if "pokemontcg.io" in url:
            raise OSError("502")
        if url.endswith("cards?name=Nemona"):
            return [{"id": "sv02-090", "name": "Nemona"}, {"id": "x", "name": "Nemona's Pikachu"}]
        if url.endswith("cards?name=Drayton"):
            return []
        return {"name": "Nemona", "localId": "090", "rarity": "Illustration Rare", "image": "https://a/b",
                "set": {"name": "Paldea Evolved", "cardCount": {"official": 93}},
                "pricing": {"tcgplayer": {"holofoil": {"marketPrice": 4.5}}}}
    rows = op.pokemon_trainer_card_rows(fake)
    assert len(rows) == 1 and rows[0]["price"] == 4.5 and "090/93" in rows[0]["title"] and rows[0]["chase"]
