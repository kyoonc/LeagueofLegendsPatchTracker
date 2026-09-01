# Patch Ledger — League of Legends champion patch history

Catching up on League of Legends after a break usually means reading through
dozens of patch notes, trying to mentally undo every buff that got reverted
two patches later. **Patch Ledger** does that math for you: pick a champion
and a patch range, and it shows the *net* change — what's actually different
now versus then, with every back-and-forth fluctuation collapsed away (but
still visible if you want to see it).

**Live site:** https://leagueof-legends-patch-tracker.vercel.app
**API:** https://leagueoflegendspatchtracker.onrender.com

## What it does

- Scrapes every official League of Legends patch note from patch 9.1 (Jan
  2019) through the current patch
- Parses champion stat/ability changes out of two structurally different
  HTML formats Riot has used across that span
- Collapses a chosen patch range down to net change per stat — a stat that
  went `40 → 50 → 40` across three patches is correctly shown as unchanged,
  not as three separate edits
- Updates itself automatically on a schedule via GitHub Actions

## Architecture

```
scraper.py  -->  parser.py  -->  build_database.py  -->  api.py  -->  frontend/
(raw HTML)      (structured        (SQLite)          (FastAPI)      (React)
                 JSON records)
```

The pipeline is intentionally split into separate, independently-runnable
stages — scraping, parsing, and diffing are each their own script with their
own responsibility, which made debugging dramatically easier than one
monolithic script would have.

## Tech stack

- **Backend:** Python, FastAPI, SQLite, BeautifulSoup
- **Frontend:** React (Vite)
- **Automation:** GitHub Actions (scheduled scrape + rebuild)
- **Hosting:** Render (API), Vercel (frontend) — both free tier, no card required. Render's free tier spins down after inactivity, so the first request after a quiet period can take 30-60 seconds to wake back up — a deliberate tradeoff for zero hosting cost, not a bug.

## Engineering challenges worth mentioning

This project involved more real debugging than the pitch suggests. A few
highlights:

- **Two structurally different HTML formats spanning 7 years.** Patch notes
  pre-~2023 use plain `<div>`/`<span>` markup; 2023-onward uses markdown-style
  `<ul>`/`<li>` bullets. The parser detects and handles both from a single
  shared code path rather than needing two separate parsers.
- **Cross-era text normalization bugs.** The same stat could appear as
  `ATTACK DAMAGE` (legacy, all-caps) and `Attack Damage` (modern, title case)
  — and champion names like *Bel'Veth* showed up with both straight (`'`) and
  curly (`'`) apostrophes depending on which era last touched them. Found by
  cross-referencing champions with 7+ years of history and catching stats
  that silently failed to group together across the two spellings.
- **Malformed source HTML.** A handful of patches had genuinely unbalanced
  `<div>` tags in Riot's own CMS output — confirmed by independently tracing
  tag balance with three different HTML parsers, which all agreed on where
  the real content ended up getting silently truncated.
- **URL archaeology.** Patch note URLs have changed shape at least four times
  across the site's history (region subdomains, dash-separated slugs, a
  `lol-` prefix, a full-year format for one season's patches) — the scraper
  tries multiple known patterns per patch rather than assuming one.

## Running it locally

**Backend:**
```
pip install -r requirements.txt
python build_database.py       # builds patches.db from parsed_changes.json
uvicorn api:app --reload
```
Visit `http://127.0.0.1:8000/docs` for an interactive API explorer.

**Frontend:**
```
cd frontend
npm install
npm run dev
```
Visit `http://localhost:5173`.

## Re-running the full pipeline from scratch

```
python scraper.py          # downloads raw patch HTML
python parser.py           # extracts structured records
python build_database.py   # rebuilds the SQLite database
```

In production, this same sequence runs automatically every week via
`.github/workflows/update-patches.yml`, which commits the refreshed data
back to this repo — that commit then triggers an automatic redeploy on
Render.

## Data source

All patch note content is sourced from Riot Games' official patch notes at
[leagueoflegends.com](https://www.leagueoflegends.com/en-us/news/tags/patch-notes/).
This is an unofficial, fan-made tool and isn't affiliated with or endorsed
by Riot Games.
