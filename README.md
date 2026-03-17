# PokeROMHub

The most comprehensive directory of Pokémon fan games on the internet.

## Setup

### 1. Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/pokeromhub.git
git push -u origin main
```

### 2. Enable GitHub Pages

1. Go to your repo → **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: **main** → **/ (root)**
4. Save — your site will be live at `https://YOUR_USERNAME.github.io/pokeromhub`

### 3. Weekly auto-scrape is already configured

The GitHub Action in `.github/workflows/weekly-scrape.yml` runs every Monday at 9am Melbourne time. It will:
- Scrape r/PokemonROMhacks for new games
- Detect status changes (e.g. a game going from active → complete)
- Update `data/games.json`
- Re-inject the games into `index.html`
- Commit and push automatically if anything changed

You can also trigger it manually from the **Actions** tab in your repo.

---

## Local scraping

```bash
pip install requests beautifulsoup4
python scripts/scraper.py
```

Then either:
- Upload `data/games.json` to Claude to review and merge, or
- Run `python scripts/inject_games.py` to inject it directly

---

## Adding box art

Find the game in `data/games.json` and set its `img` field to a direct image URL:

```json
{ "title": "Pokémon Uranium", "img": "https://your-host.com/uranium.jpg", ... }
```

Then run `python scripts/inject_games.py` to update the site.

Images are preserved automatically — the injector never overwrites a manually set `img` URL.

---

## File structure

```
pokeromhub/
├── index.html                    # The site
├── data/
│   ├── games.json                # Game database (source of truth)
│   └── changes.json              # Last scrape change log
├── scripts/
│   ├── scraper.py                # Reddit scraper
│   └── inject_games.py           # Injects games.json into index.html
└── .github/
    └── workflows/
        └── weekly-scrape.yml     # Automated weekly job
```
