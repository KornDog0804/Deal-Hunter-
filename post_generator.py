# -*- coding: utf-8 -*-
import json

def hype_level(score):
    if score >= 9:
        return "🚨 GRAIL ALERT 🚨", "MOVE FAST — this won’t sit"
    elif score >= 7:
        return "🔥 VINYL HEAT 🔥", "Strong pickup"
    elif score >= 5:
        return "💿 KORNDOG FIND 💿", "Worth a look"
    else:
        return "👀 LOW KEY FIND 👀", "Niche pull"

with open("scored_deals.json", "r", encoding="utf-8") as f:
    deals = json.load(f)

posts = []

for d in deals:
    score = d.get("total", 0)
    decision = d.get("decision", "IGNORE")

    if decision == "IGNORE":
        continue

    opener, vibe = hype_level(score)

    best_price = d.get("best_price", d.get("price", 0))
    price_text = f"${best_price:.2f}" if isinstance(best_price, (int, float)) and best_price > 0 else "Price not pulled yet"

    best_source = d.get("best_source", d.get("source", "Unknown Source"))
    buy_link = d.get("buy_link", d.get("link", "Link coming soon"))
    amazon_link = d.get("amazon_link", "Link coming soon")
    label = d.get("best_label", "KORNDOG FIND")

    if label == "KORNDOG FIND":
        buy_line = f"💿 Best Buy: KornDog Find ({best_source})"
    elif label == "AMAZON PICK":
        buy_line = "🛒 Best Buy: Amazon"
    elif label == "WALMART PICK":
        buy_line = "🛍 Best Buy: Walmart"
    else:
        buy_line = f"📦 Best Buy: {best_source}"

    post = f"""{opener}

{d.get('artist', 'Unknown Artist')} – {d.get('title', 'Unknown Title')}

💰 Best Price: {price_text}
{buy_line}

🟢 {vibe}

👉 {buy_link}

🛒 Amazon Option:
👉 {amazon_link}

Vinyl Therapy never dies 🟣🟢"""

    posts.append(post)

with open("facebook_posts.txt", "w", encoding="utf-8") as f:
    f.write("\n\n----------------------------\n\n".join(posts))

print("Facebook posts generated!")
