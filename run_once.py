import json
import os
import random
import time
from pathlib import Path

import vinted_deals_bot as bot

bot.DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK"]
STATE = Path("seen.json")

first_run = not STATE.exists()
seen = set(json.loads(STATE.read_text())) if not first_run else set()

bot.refresh_session()

for search in bot.SEARCHES:
    name = search["name"]
    try:
        bot.update_reference(search)
        items = bot.api_items(search, order="newest_first", per_page=30)
    except Exception as exc:
        print(f"[!] Erreur sur « {name} » : {exc}")
        continue

    for item in reversed(items):
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        if first_run:
            continue
        deal = bot.evaluate(name, item)
        if deal:
            bot.notify(name, item, deal)
            print(f"[+] {item.get('title')} : {deal['price']:.2f} €")

    time.sleep(random.uniform(2, 4))

STATE.write_text(json.dumps(sorted(seen)[-3000:]))
print(f"[i] Terminé, {len(seen)} annonces connues.")
