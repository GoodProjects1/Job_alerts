#!/usr/bin/env python3
"""
scraper.py — Raccoglie offerte di lavoro da API pubbliche e gratuite,
filtra per parole chiave, rimuove i duplicati e scrive jobs.json,
che la dashboard (index.html) legge per mostrare le offerte.

Pensato per girare ogni giorno tramite GitHub Actions (vedi job-alert.yml).
Nessun server, nessun database: usa due file JSON nel repo.
"""

import json
import re
import sys
import datetime
import urllib.request
import urllib.error
import urllib.parse

# ============================================================
# 1) CONFIGURAZIONE — modifica solo questa sezione
# ============================================================

# Parole chiave: tiene un'offerta se ALMENO UNA compare nel titolo/descrizione.
# Lascia la lista vuota [] per non filtrare e prendere tutto.
KEYWORDS = ["Crypto", "compliance", "tax", "data", "aml","senior"]

# Escludi offerte che contengono queste parole (utile per togliere rumore).
EXCLUDE = ["unpaid", "internship non retribuito"]

# Quanti giorni indietro considerare "fresche" le offerte.
MAX_AGE_DAYS = 21

# Aziende che usano Greenhouse: il "board token" è nell'URL pubblico delle
# loro careers, es. boards.greenhouse.io/airbnb  ->  "airbnb"
GREENHOUSE_BOARDS = []   # es: ["airbnb", "stripe"]

# Aziende che usano Lever: lo "slug" è nell'URL, es. jobs.lever.co/netflix -> "netflix"
LEVER_COMPANIES = []     # es: ["netflix"]

# Adzuna (opzionale, copre anche l'Italia). Registrati gratis su
# developer.adzuna.com e incolla qui le credenziali. Lascia vuoto per saltarlo.
ADZUNA_APP_ID = ""
ADZUNA_APP_KEY = ""
ADZUNA_COUNTRY = "it"     # it, gb, us, de, fr ...
ADZUNA_WHAT = "python developer"

OUTPUT_FILE = "jobs.json"
SEEN_FILE = "seen.json"   # memoria delle offerte già viste (per il dedup)
HTTP_TIMEOUT = 25
USER_AGENT = "job-alert-bot/1.0 (+github actions)"

TODAY = datetime.date.today().isoformat()


# ============================================================
# 2) UTILITÀ
# ============================================================

def fetch_json(url, headers=None):
    """Scarica e converte in JSON, restituendo None in caso di errore."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError) as e:
        print(f"  ! errore su {url}: {e}", file=sys.stderr)
        return None


def matches(text):
    """True se il testo passa i filtri parole chiave / esclusioni."""
    t = (text or "").lower()
    if any(x.lower() in t for x in EXCLUDE):
        return False
    if not KEYWORDS:
        return True
    return any(k.lower() in t for k in KEYWORDS)


def recent_enough(date_iso):
    try:
        d = datetime.date.fromisoformat(date_iso[:10])
    except (ValueError, TypeError):
        return True  # se la data manca, non scartare
    return (datetime.date.today() - d).days <= MAX_AGE_DAYS


def clean(text, limit=80):
    text = re.sub(r"<[^>]+>", "", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def make_id(job):
    """ID stabile per il dedup: fonte + azienda + titolo (oppure url)."""
    base = job.get("url") or f"{job['source']}|{job['company']}|{job['title']}"
    return re.sub(r"\s+", "", base.lower())


# ============================================================
# 3) FONTI — ognuna restituisce una lista di offerte normalizzate
# ============================================================

def from_remotive():
    data = fetch_json("https://remotive.com/api/remote-jobs?limit=200")
    out = []
    for j in (data or {}).get("jobs", []):
        out.append({
            "title": j.get("title", ""),
            "company": j.get("company_name", ""),
            "location": j.get("candidate_required_location") or "Remote",
            "tags": (j.get("tags") or [])[:4],
            "source": "Remotive",
            "url": j.get("url", ""),
            "date": (j.get("publication_date") or TODAY)[:10],
            "_text": j.get("title", "") + " " + clean(j.get("description", ""), 400),
        })
    return out


def from_arbeitnow():
    data = fetch_json("https://www.arbeitnow.com/api/job-board-api")
    out = []
    for j in (data or {}).get("data", []):
        ts = j.get("created_at")
        date = datetime.date.fromtimestamp(ts).isoformat() if isinstance(ts, int) else TODAY
        out.append({
            "title": j.get("title", ""),
            "company": j.get("company_name", ""),
            "location": j.get("location") or ("Remote" if j.get("remote") else ""),
            "tags": (j.get("tags") or [])[:4],
            "source": "Arbeitnow",
            "url": j.get("url", ""),
            "date": date,
            "_text": j.get("title", "") + " " + clean(j.get("description", ""), 400),
        })
    return out


def from_jobicy():
    data = fetch_json("https://jobicy.com/api/v2/remote-jobs?count=100")
    out = []
    for j in (data or {}).get("jobs", []):
        out.append({
            "title": j.get("jobTitle", ""),
            "company": j.get("companyName", ""),
            "location": j.get("jobGeo") or "Remote",
            "tags": (j.get("jobIndustry") or [])[:3],
            "source": "Jobicy",
            "url": j.get("url", ""),
            "date": (j.get("pubDate") or TODAY)[:10],
            "_text": j.get("jobTitle", "") + " " + clean(j.get("jobExcerpt", ""), 400),
        })
    return out


def from_remoteok():
    data = fetch_json("https://remoteok.com/api")
    out = []
    # Il primo elemento è metadata: lo saltiamo.
    for j in (data or [])[1:] if isinstance(data, list) else []:
        out.append({
            "title": j.get("position", ""),
            "company": j.get("company", ""),
            "location": j.get("location") or "Remote",
            "tags": (j.get("tags") or [])[:4],
            "source": "RemoteOK",
            "url": j.get("url", ""),
            "date": (j.get("date") or TODAY)[:10],
            "_text": j.get("position", "") + " " + clean(j.get("description", ""), 400),
        })
    return out


def from_greenhouse():
    out = []
    for board in GREENHOUSE_BOARDS:
        data = fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true")
        for j in (data or {}).get("jobs", []):
            out.append({
                "title": j.get("title", ""),
                "company": board.capitalize(),
                "location": (j.get("location") or {}).get("name", ""),
                "tags": [],
                "source": "Greenhouse",
                "url": j.get("absolute_url", ""),
                "date": (j.get("updated_at") or TODAY)[:10],
                "_text": j.get("title", "") + " " + clean(j.get("content", ""), 400),
            })
    return out


def from_lever():
    out = []
    for company in LEVER_COMPANIES:
        data = fetch_json(f"https://api.lever.co/v0/postings/{company}?mode=json")
        for j in (data or []):
            cats = j.get("categories") or {}
            ts = j.get("createdAt")
            date = datetime.date.fromtimestamp(ts / 1000).isoformat() if isinstance(ts, int) else TODAY
            out.append({
                "title": j.get("text", ""),
                "company": company.capitalize(),
                "location": cats.get("location", ""),
                "tags": [cats.get("team")] if cats.get("team") else [],
                "source": "Lever",
                "url": j.get("hostedUrl", ""),
                "date": date,
                "_text": j.get("text", "") + " " + clean(j.get("descriptionPlain", ""), 400),
            })
    return out


def from_adzuna():
    if not (ADZUNA_APP_ID and ADZUNA_APP_KEY):
        return []
    url = (f"https://api.adzuna.com/v1/api/jobs/{ADZUNA_COUNTRY}/search/1"
           f"?app_id={ADZUNA_APP_ID}&app_key={ADZUNA_APP_KEY}"
           f"&results_per_page=50&what={urllib.parse.quote(ADZUNA_WHAT)}&content-type=application/json")
    data = fetch_json(url)
    out = []
    for j in (data or {}).get("results", []):
        out.append({
            "title": j.get("title", ""),
            "company": (j.get("company") or {}).get("display_name", ""),
            "location": (j.get("location") or {}).get("display_name", ""),
            "tags": [(j.get("category") or {}).get("label", "")] if j.get("category") else [],
            "source": "Adzuna",
            "url": j.get("redirect_url", ""),
            "date": (j.get("created") or TODAY)[:10],
            "_text": j.get("title", "") + " " + clean(j.get("description", ""), 400),
        })
    return out


SOURCES = [from_remotive, from_arbeitnow, from_jobicy, from_remoteok,
           from_greenhouse, from_lever, from_adzuna]


# ============================================================
# 4) PIPELINE PRINCIPALE
# ============================================================

def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def main():
    print(f"Avvio raccolta — {TODAY}")
    raw = []
    for source in SOURCES:
        try:
            got = source()
            print(f"  {source.__name__}: {len(got)} offerte")
            raw.extend(got)
        except Exception as e:  # una fonte rotta non deve fermare le altre
            print(f"  ! {source.__name__} fallita: {e}", file=sys.stderr)

    # Filtro + dedup interno alla raccolta odierna
    seen_ids = set(load_json(SEEN_FILE, []))
    fresh, batch_ids = [], set()
    for j in raw:
        if not j.get("title") or not j.get("url"):
            continue
        if not matches(j.get("_text", "")):
            continue
        if not recent_enough(j.get("date", TODAY)):
            continue
        jid = make_id(j)
        if jid in batch_ids:
            continue
        batch_ids.add(jid)
        j.pop("_text", None)
        j["_id"] = jid
        j["_is_new"] = jid not in seen_ids   # nuova = mai vista prima
        fresh.append(j)

    # Le offerte mai viste prima sono quelle "nuove di oggi":
    # forziamo la loro data a oggi così la dashboard le evidenzia.
    new_count = 0
    for j in fresh:
        if j.pop("_is_new", False):
            j["date"] = TODAY
            new_count += 1

    fresh.sort(key=lambda x: x.get("date", ""), reverse=True)

    # Salva l'archivio per la dashboard
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump([{k: v for k, v in j.items() if k != "_id"} for j in fresh],
                  f, ensure_ascii=False, indent=2)

    # Aggiorna la memoria (tieni gli ultimi ~3000 id per non gonfiare il file)
    all_ids = list(seen_ids | batch_ids)[-3000:]
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(all_ids, f)

    print(f"Fatto: {len(fresh)} offerte totali, di cui {new_count} nuove oggi.")


if __name__ == "__main__":
    main()
