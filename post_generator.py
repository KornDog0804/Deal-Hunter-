# -*- coding: utf-8 -*-
import json
from affiliate import build_amazon_link

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

    price = d.get("price", 0)
    price_text = f"${price:.2f}" if isinstance(price, (int, float)) and price > 0 else "Price not pulled yet"
    source = d.get("source", "Unknown Source")
    original_link = d.get("link", "Link coming soon")
    amazon_link = build_amazon_link(d)

    post = f"""{opener}

{d.get('artist', 'Unknown Artist')} – {d.get('title', 'Unknown Title')}

💰 Price: {price_text}
📦 Source: {source}

🟢 {vibe}

🛒 Amazon Option:
👉 {amazon_link}

🔗 Original Listing:
👉 {original_link}

Vinyl Therapy never dies 🟣🟢"""

    posts.append(post)

with open("facebook_posts.txt", "w", encoding="utf-8") as f:
    f.write("\n\n----------------------------\n\n".join(posts))

print("Facebook posts generated!")
