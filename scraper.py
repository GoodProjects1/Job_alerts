#!/usr/bin/env python3
"""
scraper.py — Raccoglie offerte da API pubbliche gratuite e scrive jobs.json.

Filosofia: il server lancia una RETE LARGA (CANDIDATE_TERMS) e mette in jobs.json
tutti i candidati plausibili. Il filtro fine e il punteggio (settore AND area AND
seniority, RAL, ecc.) li applica la DASHBOARD, dove puoi modificarli senza
ritoccare questo file. Così il sistema è scalabile: cambi idea → modifichi nel
sito, non nel codice.

Gira ogni giorno con GitHub Actions (vedi job-alert.yml).
"""

import json
import re
import sys
import datetime
import urllib.request
import urllib.error
import urllib.parse
import ssl

# ============================================================
# CONFIG — rete larga. Genera/aggiorna queste liste dal pulsante
# "Copia config per lo scraper" nella dashboard, e incollale qui.
# Tienile AMPIE: meglio raccogliere qualche offerta in più e poi
# filtrare con precisione nella dashboard.
# ============================================================

CANDIDATE_TERMS = [
    # settore (EN / IT / DE)
    "crypto", "cryptocurrency", "blockchain", "web3", "defi", "digital asset",
    "virtual asset", "fintech", "financial services", "banking", "exchange",
    "cripto", "criptovalute", "finanziario", "bancario", "banca",
    "kryptowährung", "finanzdienstleistungen",
    # area / funzione (EN / IT / DE)
    "aml", "anti-money laundering", "kyc", "financial crime", "compliance",
    "regulatory", "tax", "data", "reporting", "analytics",
    "antiriciclaggio", "conformità", "fiscale", "dati", "analista",
    "geldwäsche", "steuer", "compliance-", "mlro", "reporting officer",
]

# Se un'offerta contiene una di queste, viene scartata già qui.
EXCLUDE = ["unpaid"]

MAX_AGE_DAYS = 30          # ignora offerte più vecchie di tot giorni
RESULTS_CAP = 600          # tetto di sicurezza al numero di offerte salvate

# Aziende crypto/fintech che assumono in EU su compliance/AML/tax/data.
# La maggior parte pubblica tramite Greenhouse (token = nome nell'URL careers).
# Il log dirà quali si collegano: quelle che falliscono le correggiamo.
GREENHOUSE_BOARDS = ["coinbase", "kraken", "gemini", "circle", "ripple",
                     "chainlinklabs", "consensys", "paxos", "fireblocks",
                     "moonpay", "bitpanda", "gnosis"]
# Aziende su Lever (slug nell'URL, es. jobs.lever.co/<slug>)
LEVER_COMPANIES = ["ledger", "bitstamp"]

# Adzuna (consigliato: copre l'Italia E restituisce gli stipendi).
# Chiave gratuita su developer.adzuna.com.
ADZUNA_APP_ID = ""
ADZUNA_APP_KEY = ""
ADZUNA_COUNTRIES = ["it", "gb", "de", "nl"]   # paesi da interrogare (it = Italia)
ADZUNA_QUERIES = ["crypto compliance", "AML", "tax compliance fintech"]

# Arbeitsagentur (agenzia del lavoro tedesca): la più grande banca dati DE,
# GRATIS e senza registrazione. Molte posizioni remote in inglese in ambito EU.
ARBEITSAGENTUR_QUERIES = ["crypto", "blockchain", "compliance", "AML", "fintech"]

OUTPUT_FILE = "jobs.json"
SEEN_FILE = "seen.json"
HTTP_TIMEOUT = 25
USER_AGENT = "job-alert-bot/2.0 (+github actions)"
TODAY = datetime.date.today().isoformat()


# ============================================================
# UTILITÀ
# ============================================================

def fetch_json(url, headers=None, insecure=False):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    ctx = ssl._create_unverified_context() if insecure else None
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT, context=ctx) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.URLError as e:
        # certificato rifiutato → ritenta una volta ignorando la verifica SSL
        if not insecure and isinstance(getattr(e, "reason", None), ssl.SSLError):
            return fetch_json(url, headers, insecure=True)
        print(f"  ! errore su {url}: {e}", file=sys.stderr)
        return None
    except (ValueError, TimeoutError) as e:
        print(f"  ! errore su {url}: {e}", file=sys.stderr)
        return None


def strip_html(text, limit=500):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def candidate(text):
    """True se l'offerta entra nella rete larga (almeno un termine) e non è esclusa."""
    t = (text or "").lower()
    if any(x.lower() in t for x in EXCLUDE):
        return False
    if not CANDIDATE_TERMS:
        return True
    return any(k.lower() in t for k in CANDIDATE_TERMS)


def recent_enough(date_iso):
    try:
        d = datetime.date.fromisoformat(str(date_iso)[:10])
    except (ValueError, TypeError):
        return True
    return (datetime.date.today() - d).days <= MAX_AGE_DAYS


def num(x):
    try:
        return int(float(x)) if x not in (None, "") else None
    except (ValueError, TypeError):
        return None


def make_id(job):
    base = job.get("url") or f"{job['source']}|{job['company']}|{job['title']}"
    return re.sub(r"\s+", "", base.lower())


def finalize(job, desc=""):
    """Aggiunge il campo `text` (haystack minuscolo) usato dalla dashboard per il matching fine."""
    parts = [job.get("title", ""), job.get("company", ""), job.get("location", ""),
             " ".join(job.get("tags", []) or []), strip_html(desc, 450)]
    job["text"] = re.sub(r"\s+", " ", " ".join(parts)).strip().lower()[:700]
    return job


# ============================================================
# FONTI
# ============================================================

def from_remotive():
    data = fetch_json("https://remotive.com/api/remote-jobs?limit=300")
    out = []
    for j in (data or {}).get("jobs", []):
        out.append(finalize({
            "title": j.get("title", ""), "company": j.get("company_name", ""),
            "location": j.get("candidate_required_location") or "Remote",
            "tags": (j.get("tags") or [])[:4], "source": "Remotive",
            "url": j.get("url", ""), "date": (j.get("publication_date") or TODAY)[:10],
            "salaryMin": None, "salaryMax": None,
        }, j.get("description", "")))
    return out


def from_arbeitnow():
    data = fetch_json("https://www.arbeitnow.com/api/job-board-api")
    out = []
    for j in (data or {}).get("data", []):
        ts = j.get("created_at")
        date = datetime.date.fromtimestamp(ts).isoformat() if isinstance(ts, int) else TODAY
        out.append(finalize({
            "title": j.get("title", ""), "company": j.get("company_name", ""),
            "location": j.get("location") or ("Remote" if j.get("remote") else ""),
            "tags": (j.get("tags") or [])[:4], "source": "Arbeitnow",
            "url": j.get("url", ""), "date": date,
            "salaryMin": None, "salaryMax": None,
        }, j.get("description", "")))
    return out


def from_jobicy():
    data = fetch_json("https://jobicy.com/api/v2/remote-jobs?count=100")
    out = []
    for j in (data or {}).get("jobs", []):
        out.append(finalize({
            "title": j.get("jobTitle", ""), "company": j.get("companyName", ""),
            "location": j.get("jobGeo") or "Remote",
            "tags": (j.get("jobIndustry") or [])[:3], "source": "Jobicy",
            "url": j.get("url", ""), "date": (j.get("pubDate") or TODAY)[:10],
            "salaryMin": num(j.get("annualSalaryMin")), "salaryMax": num(j.get("annualSalaryMax")),
        }, j.get("jobExcerpt", "")))
    return out


def from_remoteok():
    data = fetch_json("https://remoteok.com/api")
    out = []
    for j in (data or [])[1:] if isinstance(data, list) else []:
        out.append(finalize({
            "title": j.get("position", ""), "company": j.get("company", ""),
            "location": j.get("location") or "Remote",
            "tags": (j.get("tags") or [])[:4], "source": "RemoteOK",
            "url": j.get("url", ""), "date": (j.get("date") or TODAY)[:10],
            "salaryMin": num(j.get("salary_min")), "salaryMax": num(j.get("salary_max")),
        }, j.get("description", "")))
    return out


def from_himalayas():
    data = fetch_json("https://himalayas.app/jobs/api?limit=200")
    out = []
    for j in (data or {}).get("jobs", []):
        ts = j.get("pubDate") or j.get("publishedDate")
        try:
            date = datetime.date.fromtimestamp(int(ts)).isoformat() if ts else TODAY
        except (ValueError, TypeError, OSError):
            date = TODAY
        out.append(finalize({
            "title": j.get("title", ""), "company": j.get("companyName", ""),
            "location": ", ".join(j.get("locationRestrictions") or []) or "Remote",
            "tags": (j.get("categories") or [])[:3], "source": "Himalayas",
            "url": j.get("applicationLink") or j.get("guid", ""), "date": date,
            "salaryMin": num(j.get("minSalary")), "salaryMax": num(j.get("maxSalary")),
        }, j.get("description", "")))
    return out


def from_greenhouse():
    out = []
    for board in GREENHOUSE_BOARDS:
        data = fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true")
        if data is None:
            print(f"    greenhouse/{board}: FALLITO (token errato?)")
            continue
        jobs_ = data.get("jobs", [])
        print(f"    greenhouse/{board}: {len(jobs_)}")
        for j in jobs_:
            out.append(finalize({
                "title": j.get("title", ""), "company": board.capitalize(),
                "location": (j.get("location") or {}).get("name", ""),
                "tags": [], "source": "Greenhouse",
                "url": j.get("absolute_url", ""), "date": (j.get("updated_at") or TODAY)[:10],
                "salaryMin": None, "salaryMax": None,
            }, j.get("content", "")))
    return out


def from_lever():
    out = []
    for company in LEVER_COMPANIES:
        data = fetch_json(f"https://api.lever.co/v0/postings/{company}?mode=json")
        if data is None:
            print(f"    lever/{company}: FALLITO (slug errato?)")
            continue
        print(f"    lever/{company}: {len(data)}")
        for j in data:
            cats = j.get("categories") or {}
            ts = j.get("createdAt")
            date = datetime.date.fromtimestamp(ts / 1000).isoformat() if isinstance(ts, int) else TODAY
            out.append(finalize({
                "title": j.get("text", ""), "company": company.capitalize(),
                "location": cats.get("location", ""),
                "tags": [cats.get("team")] if cats.get("team") else [], "source": "Lever",
                "url": j.get("hostedUrl", ""), "date": date,
                "salaryMin": None, "salaryMax": None,
            }, j.get("descriptionPlain", "")))
    return out


def from_adzuna():
    if not (ADZUNA_APP_ID and ADZUNA_APP_KEY):
        return []
    out = []
    for country in ADZUNA_COUNTRIES:
        for what in ADZUNA_QUERIES:
            url = (f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
                   f"?app_id={ADZUNA_APP_ID}&app_key={ADZUNA_APP_KEY}"
                   f"&results_per_page=50&what={urllib.parse.quote(what)}&content-type=application/json")
            data = fetch_json(url)
            for j in (data or {}).get("results", []):
                out.append(finalize({
                    "title": j.get("title", ""),
                    "company": (j.get("company") or {}).get("display_name", ""),
                    "location": (j.get("location") or {}).get("display_name", ""),
                    "tags": [(j.get("category") or {}).get("label", "")] if j.get("category") else [],
                    "source": "Adzuna", "url": j.get("redirect_url", ""),
                    "date": (j.get("created") or TODAY)[:10],
                    "salaryMin": num(j.get("salary_min")), "salaryMax": num(j.get("salary_max")),
                }, j.get("description", "")))
    return out


def from_arbeitsagentur():
    out = []
    headers = {"X-API-Key": "jobboerse-jobsuche"}
    for what in ARBEITSAGENTUR_QUERIES:
        url = ("https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"
               f"?was={urllib.parse.quote(what)}&arbeitszeit=ho&size=50&page=1&pav=false")
        data = fetch_json(url, headers=headers)
        for j in (data or {}).get("stellenangebote", []):
            ort = j.get("arbeitsort") or {}
            loc = ", ".join(x for x in [ort.get("ort"), ort.get("land")] if x) or "Deutschland"
            ref = j.get("refnr", "")
            url_job = j.get("externeUrl") or (
                f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{ref}" if ref else "")
            out.append(finalize({
                "title": j.get("titel", ""), "company": j.get("arbeitgeber", ""),
                "location": loc, "tags": [j.get("beruf")] if j.get("beruf") else [],
                "source": "Arbeitsagentur", "url": url_job,
                "date": (j.get("aktuelleVeroeffentlichungsdatum") or TODAY)[:10],
                "salaryMin": None, "salaryMax": None,
            }, j.get("titel", "")))
    return out


SOURCES = [from_remotive, from_arbeitnow, from_jobicy, from_remoteok,
           from_himalayas, from_arbeitsagentur, from_greenhouse, from_lever, from_adzuna]


# ============================================================
# PIPELINE
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
        except Exception as e:
            print(f"  ! {source.__name__} fallita: {e}", file=sys.stderr)

    seen = set(load_json(SEEN_FILE, []))
    kept, batch_ids = [], set()
    for j in raw:
        if not j.get("title") or not j.get("url"):
            continue
        if not candidate(j.get("text", "")):
            continue
        if not recent_enough(j.get("date", TODAY)):
            continue
        jid = make_id(j)
        if jid in batch_ids:
            continue
        batch_ids.add(jid)
        # mai vista prima → segnala come "di oggi" così la dashboard la evidenzia
        if jid not in seen:
            j["date"] = TODAY
        kept.append(j)

    kept.sort(key=lambda x: x.get("date", ""), reverse=True)
    kept = kept[:RESULTS_CAP]

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False, indent=2)

    all_ids = list(seen | batch_ids)[-5000:]
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(all_ids, f)

    new_today = sum(1 for j in kept if j["date"] == TODAY)
    print(f"Fatto: {len(kept)} candidati salvati ({new_today} nuovi). "
          f"Il filtro fine lo applica la dashboard.")


if __name__ == "__main__":
    main()
