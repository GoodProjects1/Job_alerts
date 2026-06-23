# Radar offerte — guida

Dashboard personale per la ricerca di lavoro con **matching a criteri multipli**:
non una lista piatta di parole chiave, ma "settore **E** area **E** seniority"
insieme, con un punteggio che mette in cima le offerte più pertinenti. I criteri
si modificano **direttamente nella pagina**, senza toccare il codice.

Preimpostato per: settore crypto/finanziario · da remoto · ruoli senior/manager/officer
· ambito dati, tax, compliance, AML · con segnalazione della RAL dove disponibile.

## Come funziona

```
RETE LARGA (server, ogni mattina)          FILTRO FINE (dashboard, in tempo reale)
scraper.py → raccoglie molti candidati  →  jobs.json  →  index.html applica
da API gratuite e li mette in jobs.json                 i TUOI criteri AND + punteggio
```

L'idea: lo script raccoglie in abbondanza, la dashboard seleziona con precisione.
Così cambi idea sui criteri quando vuoi, senza rilanciare nulla.

- `index.html` — la dashboard + l'editor dei criteri (il vero centro di controllo)
- `scraper.py` — la "rete larga" che alimenta `jobs.json`
- `jobs.json` — l'archivio candidati (lo crea lo script, non si tocca a mano)
- `seen.json` — memoria delle offerte già viste (per marcare le "nuove di oggi")
- `.github/workflows/job-alert.yml` — l'automazione giornaliera

## Usare i criteri (nella dashboard)

Apri il pannello **Criteri di ricerca**. Ogni **gruppo** è un insieme di sinonimi:

- **Obbligatorio (AND)** — l'offerta deve contenere almeno un termine del gruppo,
  altrimenti viene scartata. Mettendo "Settore", "Area" e "Seniority" come
  obbligatori, restano solo le offerte che soddisfano tutti e tre.
- **Bonus (punti)** — non obbligatorio, ma aggiunge punteggio (es. "Remoto").
- **Peso** — quanto conta quel gruppo nel punteggio finale.

In più: una lista di **esclusioni** (es. junior, stage), un **punteggio minimo**
per comparire, e un filtro opzionale per **RAL minima** (attivo solo sulle offerte
dove lo stipendio è effettivamente indicato — molte non lo riportano).

Le modifiche si salvano nel tuo browser e restano anche dopo la chiusura.

## Tenere allineata la rete larga

Quando aggiungi termini importanti nei criteri, premi **"Copia config per lo
scraper"**: genera due liste (`CANDIDATE_TERMS` ed `EXCLUDE`) da incollare nella
sezione CONFIG di `scraper.py`. Serve perché il server raccolga abbastanza
candidati su quei temi. È un'operazione rara: la fai solo quando entri in un'area
nuova (es. aggiungi un settore), non a ogni piccola modifica.

## Le fonti

Attive senza chiavi: **Remotive, Arbeitnow, Jobicy, RemoteOK, Himalayas**
(remoto/tech, con qualche offerta finance/crypto). Per coprire meglio il tuo
ambito conviene attivare:

- **Adzuna** — copre l'Italia **e restituisce gli stipendi** (ottimo per la RAL).
  Chiave gratuita su developer.adzuna.com → incolla `ADZUNA_APP_ID/KEY` e imposta
  `ADZUNA_COUNTRY` e `ADZUNA_QUERIES` nello `scraper.py`.
- **Greenhouse / Lever** — le offerte ufficiali di aziende crypto/fintech che
  ti interessano (es. Coinbase, Kraken, Revolut): aggiungi il loro nome in
  `GREENHOUSE_BOARDS` / `LEVER_COMPANIES`. È la fonte più pulita e mirata.

> LinkedIn e Indeed restano fuori di proposito: bloccano gli scraper e lo vietano
> nei termini. Le fonti qui sopra danno risultati simili in modo legittimo.

## Provarlo in locale

```bash
python scraper.py            # crea jobs.json
python -m http.server 8000   # avvia un server locale
# apri http://localhost:8000  (NON col doppio clic, o jobs.json non si carica)
```

## Pubblicarlo gratis (GitHub Pages)

1. Carica i file nel repo. Il workflow va in `.github/workflows/job-alert.yml`.
2. **Settings → Actions → General → Workflow permissions → Read and write.**
3. **Actions →** lancia "Aggiorna offerte di lavoro" una prima volta a mano.
4. **Settings → Pages →** branch `main`, cartella `/ (root)`.

Da lì la pagina si aggiorna da sola ogni mattina. I criteri li regoli quando
vuoi dalla dashboard.

## Vuoi anche una notifica push?

Il passo naturale è un **bot Telegram** agganciato allo scraper: appena finisce
la raccolta, ti manda l'elenco delle nuove offerte. Chiedimelo e te lo aggiungo.
