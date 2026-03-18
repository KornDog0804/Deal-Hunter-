import json

# Load scored deals
with open("scored_deals.json", "r") as f:
    deals = json.load(f)

posts = []

for d in deals:
    score = d["total"]
    decision = d["decision"]

    # Skip junk
    if decision == "IGNORE":
        continue

    # Style based on score
    if score >= 6:
        opener = "🚨 VINYL ALERT 🚨"
        vibe = "High-priority pickup"
    elif score >= 4:
        opener = "💿 KORNDOG DEAL WATCH 💿"
        vibe = "Solid grab"
    else:
        opener = "👀 MAYBE WORTH A LOOK 👀"
        vibe = "Niche find"

    post = f"""{opener}

{d['artist']} – {d['title']}
🔥 Score: {score}

💰 Price: ${d['price']}
📦 Source: {d['source']}

🟢 {vibe}

👉 Drop Link Here

Vinyl Therapy never dies 🟣🟢"""

    posts.append(post)

# Save output
with open("facebook_posts.txt", "w") as f:
    f.write("\n\n----------------------------\n\n".join(posts))

print("Facebook posts generated!")
