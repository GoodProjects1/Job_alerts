# Radar offerte — guida rapida

Una dashboard personale che ogni mattina raccoglie offerte di lavoro da più
fonti gratuite, le filtra in base alle tue parole chiave e ti mostra subito le
novità del giorno. Tutto gratis, senza server e senza database: gira su GitHub.

## Come funziona (in breve)

```
ogni mattina            GitHub Actions
   │                          │
   ▼                          ▼
scraper.py  ──►  scarica da API gratuite  ──►  filtra + toglie i doppioni
                                                      │
                                                      ▼
                                              scrive jobs.json
                                                      │
                                                      ▼
            index.html (la dashboard) legge jobs.json e mostra le offerte
```

- `scraper.py` — raccoglie e filtra le offerte
- `jobs.json` — l'archivio aggiornato (lo crea lo script, non toccarlo a mano)
- `seen.json` — memoria delle offerte già viste, per segnare le "nuove di oggi"
- `index.html` — la dashboard che apri nel browser
- `.github/workflows/job-alert.yml` — l'automazione giornaliera

## Le fonti già incluse (nessuna chiave richiesta)

Remotive, Arbeitnow, Jobicy e RemoteOK funzionano subito: sono orientate al
lavoro remoto e tech. In più puoi attivare, se vuoi:

- **Greenhouse / Lever** — le offerte ufficiali di aziende specifiche (basta il
  loro nome dall'URL delle careers). È il modo più affidabile e pulito.
- **Adzuna** — aggrega molte fonti e copre anche l'Italia. Richiede una chiave
  gratuita su developer.adzuna.com.

> Nota: LinkedIn e Indeed non sono inclusi di proposito. Bloccano gli scraper e
> lo vietano nei loro termini, quindi un bot lì si rompe spesso e rischia il ban.
> Le API qui sopra danno risultati simili in modo legittimo e stabile.

## Installazione (circa 15 minuti)

### 1. Personalizza le tue parole chiave
Apri `scraper.py` e modifica la sezione CONFIGURAZIONE in cima:

```python
KEYWORDS = ["python", "react", "data", "junior"]   # i tuoi interessi
EXCLUDE  = ["unpaid"]                                # cosa escludere
GREENHOUSE_BOARDS = ["stripe"]                        # aziende che ti piacciono
```

(Opzionale) apri `index.html` e aggiorna la lista `HIGHLIGHT` con le stesse
parole, così vengono evidenziate nelle card.

### 2. Provalo sul tuo computer (consigliato)
Con Python installato:

```bash
python scraper.py        # crea jobs.json
# poi apri index.html nel browser per vedere il risultato
```

### 3. Mettilo online gratis con GitHub Pages
1. Crea un repository su GitHub e carica questi file. Il workflow va messo in
   una cartella chiamata esattamente `.github/workflows/` (rinomina
   `job-alert.yml` mantenendolo lì dentro).
2. Vai in **Settings → Pages** e attiva Pages dal branch `main`.
3. Vai in **Actions**, apri "Aggiorna offerte di lavoro" e premi **Run workflow**
   per la prima esecuzione (poi parte da solo ogni mattina).
4. La tua dashboard sarà su `https://<tuo-utente>.github.io/<repo>/`.

Fatto: da quel momento la pagina si aggiorna da sola tutti i giorni.

## Personalizzazioni facili

| Cosa vuoi cambiare            | Dove                                            |
|-------------------------------|-------------------------------------------------|
| Parole chiave / esclusioni    | `KEYWORDS`, `EXCLUDE` in `scraper.py`           |
| Orario di aggiornamento       | riga `cron` in `job-alert.yml`                  |
| Aziende da seguire            | `GREENHOUSE_BOARDS`, `LEVER_COMPANIES`          |
| Quanti giorni tenere fresche  | `MAX_AGE_DAYS` in `scraper.py`                  |
| Colori / aspetto              | sezione `<style>` in `index.html`               |

## E se volessi anche una notifica push?

La dashboard ti basta per il check quotidiano, ma se vuoi ricevere un avviso
quando arrivano offerte nuove, il passo successivo naturale è un **bot Telegram**:
si aggiunge in una ventina di righe allo `scraper.py` e ti manda l'elenco delle
nuove offerte appena il workflow finisce. Chiedimelo e te lo preparo.
