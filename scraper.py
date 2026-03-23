#!/usr/bin/env python3
"""
PokeROMHub Scraper — Supabase edition
Scrapes r/PokemonROMhacks and upserts results into Supabase.

Requirements: pip install requests
Env vars: SUPABASE_URL, SUPABASE_KEY (set as GitHub Actions secrets)
"""

import requests, json, re, time, os
from datetime import datetime, timezone

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://wslfqpkzwfitniciucru.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

REDDIT_HEADERS = {"User-Agent": "PokeROMHub-Scraper/1.0 (fan game directory)"}
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
CHANGES_FILE = os.path.join(DATA_DIR, "changes.json")

WIKI_URLS = [
    "https://www.reddit.com/r/PokemonROMhacks/wiki/gameslist",
    "https://www.reddit.com/r/PokemonROMhacks/wiki/index",
    "https://www.reddit.com/r/PokemonROMhacks/wiki/recommendations",
]

def sb_headers():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}

def slug(t): return re.sub(r'[^a-z0-9]', '', t.lower())

def guess_type(t):
    t = t.lower()
    if any(x in t for x in ["rpg maker","rpgmaker","essentials"]): return "RPG Maker"
    if any(x in t for x in ["mmo","multiplayer online"]): return "MMORPG"
    if any(x in t for x in ["fan-made","custom engine","unity","godot"]): return "Fan-Made Engine"
    return "ROM Hack"

def guess_base(t):
    t = t.lower()
    for base, kws in [("FireRed",["firered","fire red"]),("Emerald",["emerald"]),("HeartGold",["heartgold"]),("Platinum",["platinum"]),("Crystal",["crystal"]),("RPG Maker XP",["rpg maker","essentials"])]:
        if any(k in t for k in kws): return base
    return "Unknown"

def guess_status(t):
    t = t.lower()
    if any(x in t for x in ["complete","completed","finished","full release"]): return "complete"
    if any(x in t for x in ["hiatus","abandoned","discontinued"]): return "hiatus"
    return "active"

def extract_tags(t):
    t = t.lower()
    return [tag for tag, kws in [("fakemon",["fakemon"]),("open world",["open world"]),("difficulty hack",["difficulty"]),("dark story",["dark","mature"]),("mega evolution",["mega evolution"]),("competitive",["competitive"]),("multiplayer",["multiplayer","co-op"]),("roguelite",["roguelite","roguelike"])] if any(k in t for k in kws)][:5]

def first_sentence(text):
    if not text: return ""
    return next((s for s in re.split(r'(?<=[.!?])\s+', text.strip()) if len(s) > 20), "")[:200]

def clean_title(raw):
    t = re.sub(r'^\[[^\]]+\]\s*', '', raw).strip()
    return re.sub(r'\s+v[\d\.]+.*$', '', t, flags=re.IGNORECASE).strip()

def make_entry(title, link, context, desc=""):
    return {"title": title, "img": "", "type": guess_type(context), "base": guess_base(context),
            "status": guess_status(context), "description": desc, "tags": extract_tags(context),
            "link": link, "added": datetime.now(timezone.utc).strftime("%Y-%m-%d")}

def get_existing():
    if not SUPABASE_KEY: return {}
    r = requests.get(f"{SUPABASE_URL}/rest/v1/games?select=title,status", headers=sb_headers(), timeout=10)
    if r.status_code != 200: print(f"  Could not fetch existing: {r.status_code}"); return {}
    return {slug(g["title"]): g for g in r.json()}

def upsert(games):
    if not SUPABASE_KEY: print(f"  [dry-run] Would upsert {len(games)} games"); return
    if not games: return
    r = requests.post(f"{SUPABASE_URL}/rest/v1/games",
                      headers={**sb_headers(), "Prefer": "resolution=ignore-duplicates"},
                      json=games, timeout=15)
    if r.status_code in (200, 201): print(f"  Upserted {len(games)} games")
    else: print(f"  Upsert failed: {r.status_code} — {r.text[:200]}")

def scrape_wiki(url, found, existing):
    print(f"  {url}")
    try:
        r = requests.get(url + ".json", headers=REDDIT_HEADERS, timeout=10)
        if r.status_code != 200: print(f"  HTTP {r.status_code}"); return []
        md = r.json()["data"]["content_md"]
        new = []
        for m in re.finditer(r'\[([^\]]{4,80})\]\((https?://[^\)]+)\)', md):
            title, link = m.group(1).strip(), m.group(2).strip()
            if any(x in title.lower() for x in ["click","wiki","discord","here"]): continue
            key = slug(title)
            if key not in existing and key not in found:
                ctx = md[max(0,m.start()-100):m.end()+200]
                found[key] = make_entry(title, link, ctx)
                new.append(found[key])
        print(f"  +{len(new)} new"); time.sleep(1); return new
    except Exception as e: print(f"  Error: {e}"); return []

def scrape_posts(found, existing, sort="top", limit=100):
    print(f"  r/PokemonROMhacks {sort}...")
    try:
        r = requests.get(f"https://www.reddit.com/r/PokemonROMhacks/{sort}.json?limit={limit}&t=all", headers=REDDIT_HEADERS, timeout=10)
        if r.status_code != 200: print(f"  HTTP {r.status_code}"); return []
        new = []
        for post in r.json()["data"]["children"]:
            d = post["data"]
            raw, selftext = d.get("title",""), d.get("selftext","")
            flair = (d.get("link_flair_text") or "").lower()
            if not any(k in flair for k in ["release","completed","demo","hack","game"]):
                if not any(k in raw.lower() for k in ["pokemon","pokémon","hack","rom"]): continue
            title = clean_title(raw)
            if len(title) < 4: continue
            key = slug(title)
            if key in existing or key in found: continue
            url_f = d.get("url","")
            link = url_f if (url_f.startswith("http") and "reddit.com" not in url_f) else "https://reddit.com" + d.get("permalink","")
            entry = make_entry(title, link, f"{raw} {selftext[:300]} {flair}", first_sentence(selftext))
            found[key] = entry; new.append(entry)
        print(f"  +{len(new)} new"); time.sleep(1); return new
    except Exception as e: print(f"  Error: {e}"); return []

if __name__ == "__main__":
    print("="*55)
    print(f"PokeROMHub Scraper — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("="*55)
    os.makedirs(DATA_DIR, exist_ok=True)

    print("\n[0] Fetching existing games from Supabase...")
    existing = get_existing()
    print(f"  {len(existing)} in database")

    found = {}
    print("\n[1] Scraping Reddit...")
    for url in WIKI_URLS:
        scrape_wiki(url, found, existing)
    scrape_posts(found, existing, "top", 100)
    scrape_posts(found, existing, "new", 50)

    print(f"\n[2] Upserting {len(found)} new games...")
    upsert(list(found.values()))

    changes = {"run_at": datetime.now(timezone.utc).isoformat(), "new_games": [g["title"] for g in found.values()],
               "status_changes": [], "total_before": len(existing), "total_after": len(existing) + len(found)}
    with open(CHANGES_FILE, "w") as f: json.dump(changes, f, indent=2)
    print(f"\nDone — {len(found)} new, {len(existing)+len(found)} total")
