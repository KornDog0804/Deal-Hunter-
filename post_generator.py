# -*- coding: utf-8 -*-
import json

with open("scored_deals.json", "r", encoding="utf-8") as f:
    deals = json.load(f)

posts = []

for d in deals:
    score = d["total"]
    decision = d["decision"]

    if decision == "IGNORE":
        continue

    if score >= 6:
        opener = "🚨 VINYL ALERT 🚨"
        vibe = "High-priority pickup"
    elif score >= 4:
        opener = "💿 KORNDOG DEAL WATCH 💿"
        vibe = "Solid grab"
    else:
        opener = "👀 MAYBE WORTH A LOOK 👀"
        vibe = "Niche find"

    price = d.get("price", 0)
    source = d.get("source", "Unknown Source")
    link = d.get("link", "Link coming soon")

    post = f"""{opener}

{d['artist']} – {d['title']}
🔥 Score: {score}

💰 Price: ${price}
📦 Source: {source}

🟢 {vibe}

👉 {link}

Vinyl Therapy never dies 🟣🟢"""

    posts.append(post)

with open("facebook_posts.txt", "w", encoding="utf-8") as f:
    f.write("\n\n----------------------------\n\n".join(posts))

print("Facebook posts generated!")
