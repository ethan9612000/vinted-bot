import random
import statistics
import time

import requests

DISCORD_WEBHOOK_URL = "COLLE_TON_WEBHOOK_ICI"
BASE_URL = "https://www.vinted.fr"

SEARCHES = [
    {"name": "Nike Air Force 1", "search_text": "nike air force 1", "price_to": 80},
    {"name": "Carhartt Detroit", "search_text": "carhartt detroit veste", "price_to": 100},
    {"name": "Levi's 501", "search_text": "levis 501", "price_to": 50},
]

MIN_DISCOUNT = 0.30
MIN_PROFIT = 10.0
MIN_SAMPLES = 15
RESALE_FACTOR = 0.90
SUSPICIOUS_BELOW = 0.25

BUYER_FEE_PCT = 0.05
BUYER_FEE_FIXED = 0.70
SHIPPING_COST = 3.50

BAD_WORDS = ["lot", "défaut", "defaut", "taché", "tache", "abîmé", "abime", "pour pièces",
             "réplique", "replique", "fake", "custom", "enfant", "kids", "bébé", "bebe"]

CHECK_INTERVAL = 60
REFERENCE_REFRESH = 30 * 60
REFERENCE_PAGES = 3

session = requests.Session()
session.headers.update({
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fr-FR,fr;q=0.9",
})

seen_ids = set()
references = {}


def refresh_session():
    session.cookies.clear()
    session.get(BASE_URL, timeout=15)


def api_items(search, order, page=1, per_page=20):
    params = {
        "search_text": search["search_text"],
        "order": order,
        "page": page,
        "per_page": per_page,
    }
    for key in ("price_from", "price_to", "catalog_ids", "brand_ids", "size_ids",
                "status_ids", "color_ids"):
        if key in search:
            params[key] = search[key]

    url = f"{BASE_URL}/api/v2/catalog/items"
    resp = session.get(url, params=params, timeout=15)
    if resp.status_code in (401, 403):
        refresh_session()
        resp = session.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("items", [])


def price_of(item):
    price = item.get("price")
    try:
        if isinstance(price, dict):
            return float(price["amount"])
        return float(price)
    except (TypeError, ValueError, KeyError):
        return None


def update_reference(search):
    prices = []
    for page in range(1, REFERENCE_PAGES + 1):
        items = api_items(search, order="relevance", page=page, per_page=96)
        prices += [p for p in map(price_of, items) if p is not None]
        time.sleep(random.uniform(2, 4))
        if len(items) < 96:
            break

    if len(prices) < MIN_SAMPLES:
        print(f"[i] {search['name']} : seulement {len(prices)} annonces, référence ignorée.")
        references.pop(search["name"], None)
        return

    prices.sort()
    cut = max(1, len(prices) // 10)
    trimmed = prices[cut:-cut] or prices
    median = statistics.median(trimmed)
    references[search["name"]] = {"median": median, "n": len(prices), "at": time.time()}
    print(f"[i] {search['name']} : référence = {median:.2f} € ({len(prices)} annonces)")


def evaluate(search_name, item):
    ref = references.get(search_name)
    price = price_of(item)
    if not ref or price is None:
        return None

    title = (item.get("title") or "").lower()
    if any(word in title for word in BAD_WORDS):
        return None

    median = ref["median"]
    resale = median * RESALE_FACTOR
    buy_cost = price + price * BUYER_FEE_PCT + BUYER_FEE_FIXED + SHIPPING_COST
    profit = resale - buy_cost
    discount = 1 - price / median

    if discount < MIN_DISCOUNT or profit < MIN_PROFIT:
        return None

    return {
        "price": price,
        "median": median,
        "resale": resale,
        "profit": profit,
        "discount": discount,
        "suspicious": price < median * SUSPICIOUS_BELOW,
        "samples": ref["n"],
    }


def notify(search_name, item, deal):
    photo = (item.get("photo") or {}).get("url")
    warn = "\n⚠️ Prix très bas : vérifie l'authenticité (contrefaçon/arnaque possible)." \
        if deal["suspicious"] else ""
    embed = {
        "title": f"💰 {item.get('title', 'Bonne affaire')}",
        "url": item.get("url") or f"{BASE_URL}/items/{item['id']}",
        "description": f"🔎 {search_name}{warn}",
        "color": 0xE67E22 if deal["suspicious"] else 0x2ECC71,
        "fields": [
            {"name": "Prix", "value": f"{deal['price']:.2f} €", "inline": True},
            {"name": "Médiane marché", "value": f"{deal['median']:.2f} €", "inline": True},
            {"name": "Remise", "value": f"-{deal['discount'] * 100:.0f} %", "inline": True},
            {"name": "Revente estimée", "value": f"{deal['resale']:.2f} €", "inline": True},
            {"name": "Marge estimée", "value": f"{deal['profit']:.2f} €", "inline": True},
            {"name": "Taille / Marque",
             "value": f"{item.get('size_title') or '-'} / {item.get('brand_title') or '-'}",
             "inline": True},
        ],
        "footer": {"text": f"Référence calculée sur {deal['samples']} annonces"},
    }
    if photo:
        embed["image"] = {"url": photo}
    requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]}, timeout=15)
