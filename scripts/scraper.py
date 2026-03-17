#!/usr/bin/env python3
"""
PokeROMHub Scraper
─────────────────
Scrapes r/PokemonROMhacks and merges results into games.json,
deduplicating against existing entries and flagging status changes.

Requirements:
    pip install requests beautifulsoup4

Usage:
    python scripts/scraper.py

Outputs:
    - data/games.json       (full game database)
    - data/changes.json     (what changed this run, for logging)
"""

import requests
import json
import re
import time
import os
from datetime import datetime, timezone

HEADERS = {
    "User-Agent": "PokeROMHub-Scraper/1.0 (fan game directory; open source)"
}

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
GAMES_FILE = os.path.join(DATA_DIR, "games.json")
CHANGES_FILE = os.path.join(DATA_DIR, "changes.json")

WIKI_URLS = [
    "https://www.reddit.com/r/PokemonROMhacks/wiki/gameslist",
    "https://www.reddit.com/r/PokemonROMhacks/wiki/index",
    "https://www.reddit.com/r/PokemonROMhacks/wiki/recommendations",
]

KNOWN_GAMES = [
    "Pokemon Uranium", "Pokemon Insurgence", "Pokemon Reborn",
    "Pokemon Unbound", "Pokemon Rejuvenation", "Pokemon Radical Red",
    "Pokemon Gaia", "Pokemon Clover", "Pokemon Prism", "Pokemon Sage",
    "Pokemon Crystal Clear", "Pokemon Emerald Rogue", "Pokemon Xenoverse",
    "Pokemon Showdown", "PokeMMO", "Pokemon Quetzal", "Pokemon Volt White",
    "Pokemon Flora Sky", "Pokemon Light Platinum", "Pokemon Glazed",
    "Pokemon Blazed Glazed", "Pokemon Dark Rising", "Pokemon Snakewood",
    "Pokemon Adventure Red Chapter", "Pokemon Ash Gray", "Pokemon Brown",
    "Pokemon Liquid Crystal", "Pokemon Renegade Platinum", "Pokemon Blaze Black",
    "Pokemon Sacred Gold", "Pokemon Storm Silver", "Pokemon Flawless Platinum",
    "Pokemon Ultra Violet", "Pokemon Grape", "Pokemon Quartz",
]


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def slug(title):
    """Normalised key for deduplication."""
    return re.sub(r'[^a-z0-9]', '', title.lower())


def guess_type(text):
    t = text.lower()
    if any(x in t for x in ["rpg maker", "rpgmaker", "essentials"]):
        return "RPG Maker"
    if any(x in t for x in ["mmo", "multiplayer online"]):
        return "MMORPG"
    if any(x in t for x in ["fan-made engine", "custom engine", "unity", "godot"]):
        return "Fan-Made Engine"
    return "ROM Hack"


def guess_base(text):
    bases = {
        "FireRed": ["firered", "fire red", "frlg"],
        "Emerald": ["emerald"],
        "Ruby": ["ruby"],
        "HeartGold": ["heartgold", "heart gold", "hgss"],
        "Platinum": ["platinum"],
        "Crystal": ["crystal"],
        "Gold": ["gold version"],
        "Silver": ["silver version"],
        "RPG Maker XP": ["rpg maker", "rpgmaker", "essentials"],
    }
    t = text.lower()
    for base, keywords in bases.items():
        if any(k in t for k in keywords):
            return base
    return "Unknown"


def guess_status(text):
    t = text.lower()
    if any(x in t for x in ["complete", "completed", "finished", "v1.0", "full game", "full release"]):
        return "complete"
    if any(x in t for x in ["hiatus", "abandoned", "discontinued", "on hold", "cancelled"]):
        return "hiatus"
    return "active"


def extract_tags(text):
    tag_map = {
        "fakemon": ["fakemon", "fake mon", "original pokemon"],
        "open world": ["open world", "open-world"],
        "difficulty hack": ["difficulty", "hard mode", "nuzlocke"],
        "dark story": ["dark", "mature", "gritty"],
        "mega evolution": ["mega evolution", "mega evo"],
        "competitive": ["competitive", "smogon"],
        "multiplayer": ["multiplayer", "co-op", "coop", "online"],
        "custom music": ["custom music", "original music"],
        "gen 8 mechanics": ["gen 8", "dynamax", "sword shield"],
        "QoL": ["quality of life", "qol"],
        "original region": ["original region", "new region", "custom region"],
        "roguelite": ["roguelite", "roguelike", "rogue"],
    }
    t = text.lower()
    return [tag for tag, kws in tag_map.items() if any(k in t for k in kws)][:5]


def clean_title(raw):
    """Strip flair prefixes and version numbers from post titles."""
    t = re.sub(r'^\[[^\]]+\]\s*', '', raw).strip()
    t = re.sub(r'\s+v[\d\.]+.*$', '', t, flags=re.IGNORECASE).strip()
    return t


# ─── LOAD EXISTING GAMES ─────────────────────────────────────────────────────

def load_existing():
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(GAMES_FILE):
        with open(GAMES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"  Loaded {len(data)} existing games from games.json")
        return {slug(g["title"]): g for g in data}
    print("  No existing games.json — starting fresh")
    return {}


# ─── SCRAPERS ────────────────────────────────────────────────────────────────

def scrape_wiki(url, games):
    print(f"  Fetching: {url}")
    try:
        r = requests.get(url + ".json", headers=HEADERS, timeout=10)
        if r.status_code != 200:
            print(f"  ✗ HTTP {r.status_code}")
            return 0
        md = r.json()["data"]["content_md"]
        found = 0

        for match in re.finditer(r'\[([^\]]{4,80})\]\((https?://[^\)]+)\)', md):
            title = match.group(1).strip()
            link = match.group(2).strip()
            if any(x in title.lower() for x in ["click", "wiki", "discord", "here", "subreddit"]):
                continue
            context = md[max(0, match.start()-100):match.end()+200]
            key = slug(title)
            if key not in games:
                games[key] = make_entry(title, link, context)
                found += 1

        for match in re.finditer(r'\*\*([^*]{4,60})\*\*\s*[-–:]\s*([^\n]{10,200})', md):
            title, desc = match.group(1).strip(), match.group(2).strip()
            key = slug(title)
            if key not in games:
                games[key] = make_entry(title, "", f"{title} {desc}")
                games[key]["desc"] = desc[:200]
                found += 1
            elif not games[key].get("desc"):
                games[key]["desc"] = desc[:200]

        print(f"  ✓ +{found} new")
        return found
    except Exception as e:
        print(f"  ✗ {e}")
        return 0


def scrape_posts(games, sort="top", limit=100):
    url = f"https://www.reddit.com/r/PokemonROMhacks/{sort}.json?limit={limit}&t=all"
    print(f"  Fetching {sort} posts...")
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            print(f"  ✗ HTTP {r.status_code}")
            return 0
        posts = r.json()["data"]["children"]
        found = 0
        for post in posts:
            d = post["data"]
            raw_title = d.get("title", "")
            selftext = d.get("selftext", "")
            flair = (d.get("link_flair_text") or "").lower()
            url_field = d.get("url", "")
            permalink = "https://reddit.com" + d.get("permalink", "")

            if not any(k in flair for k in ["release", "completed", "demo", "showcase", "hack", "game", "rom"]):
                if not any(k in raw_title.lower() for k in ["pokemon", "pokémon", "hack", "rom", "fangame"]):
                    continue

            title = clean_title(raw_title)
            if len(title) < 4:
                continue

            context = f"{raw_title} {selftext[:300]} {flair}"
            key = slug(title)
            ext_link = url_field if (url_field.startswith("http") and "reddit.com" not in url_field) else permalink

            if key not in games:
                desc = first_sentence(selftext)
                games[key] = make_entry(title, ext_link, context, desc)
                found += 1

        print(f"  ✓ +{found} new")
        time.sleep(1)
        return found
    except Exception as e:
        print(f"  ✗ {e}")
        return 0


def scrape_search(game_name, games):
    key = slug(game_name)
    if key in games:
        return 0
    query = game_name.replace(" ", "+")
    url = f"https://www.reddit.com/r/PokemonROMhacks/search.json?q={query}&restrict_sr=1&sort=top&limit=3"
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        if r.status_code != 200:
            return 0
        posts = r.json()["data"]["children"]
        for post in posts:
            d = post["data"]
            selftext = d.get("selftext", "")
            url_field = d.get("url", "")
            permalink = "https://reddit.com" + d.get("permalink", "")
            ext_link = url_field if (url_field.startswith("http") and "reddit.com" not in url_field) else permalink
            context = f"{d.get('title','')} {selftext[:300]}"
            games[key] = make_entry(game_name, ext_link, context, first_sentence(selftext))
            time.sleep(0.4)
            return 1
    except Exception:
        pass
    return 0


# ─── STATUS CHANGE DETECTION ─────────────────────────────────────────────────

def detect_changes(old_games, new_games):
    """Compare old vs new and log what changed."""
    changes = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "new_games": [],
        "status_changes": [],
        "total_before": len(old_games),
        "total_after": len(new_games),
    }

    for key, game in new_games.items():
        if key not in old_games:
            changes["new_games"].append(game["title"])
        else:
            old_status = old_games[key].get("status")
            new_status = game.get("status")
            if old_status and new_status and old_status != new_status:
                changes["status_changes"].append({
                    "title": game["title"],
                    "from": old_status,
                    "to": new_status,
                })

    return changes


# ─── ENTRY FACTORY ───────────────────────────────────────────────────────────

def make_entry(title, link, context, desc=""):
    return {
        "title": title,
        "img": "",
        "type": guess_type(context),
        "base": guess_base(context),
        "status": guess_status(context),
        "desc": desc,
        "tags": extract_tags(context),
        "link": link,
        "added": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


def first_sentence(text):
    if not text:
        return ""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return next((s for s in sentences if len(s) > 20), "")[:200]


# ─── SAVE ────────────────────────────────────────────────────────────────────

def save(games, changes):
    os.makedirs(DATA_DIR, exist_ok=True)

    # Preserve manually set fields (img, desc overrides) from existing entries
    games_list = sorted(games.values(), key=lambda x: x["title"])
    with open(GAMES_FILE, "w", encoding="utf-8") as f:
        json.dump(games_list, f, indent=2, ensure_ascii=False)
    print(f"\n  ✓ Saved {len(games_list)} games to {GAMES_FILE}")

    with open(CHANGES_FILE, "w", encoding="utf-8") as f:
        json.dump(changes, f, indent=2, ensure_ascii=False)

    if changes["new_games"]:
        print(f"  🆕 {len(changes['new_games'])} new games: {', '.join(changes['new_games'][:5])}")
    if changes["status_changes"]:
        print(f"  🔄 {len(changes['status_changes'])} status changes:")
        for sc in changes["status_changes"]:
            print(f"     {sc['title']}: {sc['from']} → {sc['to']}")
    if not changes["new_games"] and not changes["status_changes"]:
        print("  ✓ No changes detected")


# ─── MAIN ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("PokeROMHub Scraper")
    print(f"Run at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 55)

    # Load what we already have
    print("\n[0] Loading existing data...")
    old_games = load_existing()
    games = dict(old_games)  # work on a copy

    # 1. Wiki
    print("\n[1/3] Scraping wiki pages...")
    for url in WIKI_URLS:
        scrape_wiki(url, games)
        time.sleep(1)

    # 2. Posts
    print("\n[2/3] Scraping subreddit posts...")
    scrape_posts(games, sort="top", limit=100)
    scrape_posts(games, sort="hot", limit=100)
    scrape_posts(games, sort="new", limit=50)   # catch recent releases

    # 3. Known games
    print("\n[3/3] Filling in known games...")
    for name in KNOWN_GAMES:
        if slug(name) not in games:
            print(f"  Searching: {name}")
            scrape_search(name, games)

    # Detect changes
    changes = detect_changes(old_games, games)

    # Save
    print("\n[Saving]")
    save(games, changes)

    print(f"\nDone — {len(games)} total games in database")
    print("Upload games.json here and I'll merge it into your site!")
