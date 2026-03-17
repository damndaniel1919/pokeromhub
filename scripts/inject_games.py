#!/usr/bin/env python3
"""
inject_games.py
───────────────
Reads data/games.json and injects the GAMES array into index.html.
Run after scraper.py to keep the site in sync with the database.

Also handles:
  - Preserving manually set img URLs already in index.html
  - Deduplication (slug-based)
  - Sorting alphabetically
"""

import json
import re
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")
GAMES_FILE = os.path.join(ROOT, "data", "games.json")
INDEX_FILE = os.path.join(ROOT, "index.html")


def slug(title):
    return re.sub(r'[^a-z0-9]', '', title.lower())


def load_games_json():
    with open(GAMES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_existing_imgs(html):
    """Pull out any manually set img URLs already in the HTML so we don't lose them."""
    imgs = {}
    # Match title + img pairs in the existing GAMES array
    pattern = re.compile(
        r'title:\s*"([^"]+)".*?img:\s*"([^"]*)"',
        re.DOTALL
    )
    for m in pattern.finditer(html):
        title = m.group(1)
        img = m.group(2)
        if img:  # only preserve non-empty ones
            imgs[slug(title)] = img
    return imgs


def games_to_js(games, preserved_imgs):
    lines = ["const GAMES = ["]
    for g in sorted(games, key=lambda x: x["title"]):
        key = slug(g["title"])
        img = preserved_imgs.get(key, g.get("img", ""))
        tags_str = ", ".join(f'"{t}"' for t in (g.get("tags") or []))
        desc = (g.get("desc") or "").replace('"', '\\"').replace('\n', ' ').strip()
        title = g["title"].replace('"', '\\"')
        link = (g.get("link") or "").replace('"', '\\"')
        lines.append(f"""  {{
    title: "{title}",
    img: "{img}",
    type: "{g.get('type', 'ROM Hack')}",
    base: "{g.get('base', 'Unknown')}",
    status: "{g.get('status', 'active')}",
    desc: "{desc}",
    tags: [{tags_str}],
    link: "{link}"
  }},""")
    lines.append("];")
    return "\n".join(lines)


def inject(html, new_games_js):
    """Replace the GAMES array in the HTML."""
    pattern = re.compile(
        r'// ─── GAME DATA ─+.*?const GAMES = \[.*?\];',
        re.DOTALL
    )
    replacement = f"// ─── GAME DATA ───────────────────────────────────────────────────────────────\n{new_games_js}"
    new_html, count = pattern.subn(replacement, html)
    if count == 0:
        # Fallback: replace just the GAMES array
        pattern2 = re.compile(r'const GAMES = \[.*?\];', re.DOTALL)
        new_html, count = pattern2.subn(new_games_js, html)
    return new_html, count


if __name__ == "__main__":
    print("Injecting games.json into index.html...")

    games = load_games_json()
    print(f"  {len(games)} games in database")

    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    # Preserve any manually set images
    preserved_imgs = extract_existing_imgs(html)
    if preserved_imgs:
        print(f"  Preserving {len(preserved_imgs)} manually set images")

    new_js = games_to_js(games, preserved_imgs)
    new_html, count = inject(html, new_js)

    if count == 0:
        print("  ✗ Could not find GAMES array in index.html — no changes made")
        exit(1)

    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        f.write(new_html)

    print(f"  ✓ index.html updated with {len(games)} games")
