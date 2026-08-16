# Protezione del know-how — audit e piano di rientro

Data audit: 2026-08-16. Riferimento: sito offline dal 14 agosto perché il
repository è stato reso privato e GitHub Pages si è depubblicato.

Questo file non viene pubblicato sul sito (escluso in `_config.yml`).

---

## 1. Cosa è risultato esposto

| # | Problema | Dove |
|---|---|---|
| 1 | Autenticazione area riservata **interamente lato client** | `reserved-area.html` |
| 2 | 487 URL di report a pagamento **dichiarati nel sitemap** | `sitemap.xml` |
| 3 | Metodologia, pipeline e notebook nel repo e serviti dal sito | `mosaic_dev/`, `tools/` |
| 4 | Dati abbonati con **password in chiaro** | `mosaic_dev/Subscriptions.xlsx` |
| 5 | Hash password senza salt (SHA-256 puro) | `assets/subscriptions.json` |
| 6 | Strumento di amministrazione nel sitemap | `admin-rebalance-tool.html` |

Il repository è stato pubblico dal 2 luglio 2026 (primo commit di
`mosaic_dev/`) al 14 agosto 2026. Va assunto che in quella finestra il
contenuto sia stato clonabile, indicizzabile e archiviabile da terzi.

### Il punto architetturale

GitHub Pages è un host statico: non esegue codice lato server, quindi non
può rifiutare una richiesta. L'area riservata verifica la password in
JavaScript e poi reindirizza a un file statico a URL prevedibile
(`reports_html/Italy40/Report_Italy40.html`). Chi digita quell'URL entra
senza password. **Non è un bug da correggere: è un limite della piattaforma.**

Nota importante: rendere privato il repository **non** rende privato il
sito. Pages serve l'output a chiunque anche quando il sorgente è privato.
Il controllo accessi sui siti Pages esiste solo su GitHub Enterprise Cloud.

---

## 2. Cosa è già stato fatto

### 2.1 Separazione backend / frontend

Il backend è stato spostato in **`domderr/TradingAlgo-mosaic`** (privato),
con la sua storia: 68 commit, 41 file.

| `TradingAlgo` — pubblico | `TradingAlgo-mosaic` — privato |
|---|---|
| pagine HTML, `assets/`, CNAME | `mosaic_dev/` (notebook, pipeline, Tickers.xlsx) |
| `reports_html/` (output generato) | `tools/build_mosaic_html_report.py` |
| `reports/*.json`, `haircuts.csv` | `scripts/` |
| `sitemap.xml`, `robots.txt`, `_config.yml` | `admin-rebalance-tool.html`, audit `.xlsx`, `DJ_*.csv` |

Il collegamento fra i due avviene tramite la variabile `MOSAIC_SITE_DIR`,
che punta al checkout locale del sito. Senza la variabile gli script
ricadono sul comportamento precedente, quindi un vecchio checkout unico
continua a funzionare. Flusso operativo: `README.md` del repo privato.

### 2.2 Interventi sul repository pubblico

- **`_config.yml`** (nuovo) — esclude dalla build i percorsi del backend.
  Ora è una seconda barriera, dato che quei file non sono più qui.
- **`sitemap.xml`** — rimossi 488 URL (487 report + admin tool), da 515 a 27
  voci, che sono le sole pagine vetrina.
- **491 pagine** in `reports_html/` e l'admin tool — aggiunto
  `<meta name="robots" content="noindex, nofollow">`.
- **`tools/build_mosaic_html_report.py`** — i 3 template emettono il
  `noindex`, così la rigenerazione settimanale non annulla la modifica.
  *(Il file ora vive nel repo privato.)*
- **`robots.txt`** — `Disallow` sulle cartelle sorgente. Volutamente
  **nessun** `Disallow` su `/reports_html/`: Google deve poter scaricare
  quelle pagine per leggerne il `noindex`. Bloccarle ora lascerebbe nei
  risultati le URL già indicizzate.
- **`.gitignore`** — rete di sicurezza: se un file del backend ricompare in
  questo albero, non entra in un commit.

---

## 3. Cosa resta da fare — richiede te

### 3.1 Purga della history (bloccante, prima di tornare pubblici)

Rimuovere i file dall'albero non li toglie dai commit passati: a repository
pubblico sarebbero di nuovo scaricabili. Da eseguire **prima** del passaggio
a Public.

```bash
pip install git-filter-repo

git clone --mirror https://github.com/domderr/TradingAlgo.git ta-mirror
cd ta-mirror
git filter-repo \
  --path mosaic_dev/ \
  --path tools/ \
  --path scripts/ \
  --path admin-rebalance-tool.html \
  --path DJ_complete.csv \
  --path DJ_components_asof.csv \
  --path "Rebalance Audit.xlsx" \
  --path "Rebalance Audit.backup-before-corrections.xlsx" \
  --path-glob "reports/*.xlsx" \
  --invert-paths
git push --force
```

Tutto ciò che viene rimosso è già conservato in `TradingAlgo-mosaic`, quindi
non si perde nulla. Dopo il force-push ogni clone locale del repo pubblico va
ricreato da zero, perché gli SHA cambiano.

### 3.2 Rotazione credenziali (bloccante, indipendente dal resto)

Le password degli abbonati sono state in chiaro in un repository pubblico per
sei settimane. Vanno considerate compromesse:

1. genera nuove password in `Subscriptions.xlsx` (ora nel repo privato)
2. `python update_subscriptions.py` da `mosaic_dev`
3. verifica che `assets/subscriptions.json` contenga solo `password_hash`
4. comunica il cambio agli abbonati

Valuta con un consulente se ricorrono gli estremi di notifica al Garante
(email + password in chiaro pubblicamente accessibili sono dati personali).

### 3.3 Rimettere il sito online

Da `Settings` del repository **pubblico**:

1. `Settings → General → Danger Zone → Change visibility` → **Public**
2. `Settings → Pages` → Source: branch `main`, cartella `/ (root)`
3. `Settings → Pages → Custom domain` → `tradingalgo.it`
   (il file `CNAME` è già corretto; il DNS punta già agli IP giusti)
4. Attendi il certificato HTTPS, poi spunta **Enforce HTTPS**

Il branch con le protezioni va unito in `main` **prima** del passo 1.

### 3.4 Deindicizzazione

In Google Search Console:
- invia il `sitemap.xml` aggiornato
- usa **Rimozioni** per `tradingalgo.it/reports_html/` (rimozione rapida,
  ~6 mesi) mentre il `noindex` fa effetto in modo permanente
- ricontrolla dopo 30 giorni; solo allora aggiungi il `Disallow` in robots.txt

---

## 4. La protezione vera dei report

La separazione dei repository mette al sicuro la metodologia, ma **non rende
i report inaccessibili**: chi conosce l'URL continua a leggerli, perché
`reports_html/` deve restare pubblicato per funzionare. Per una protezione
reale serve un host che esegua codice lato server e verifichi la sessione
prima di servire il file.

Opzione consigliata, incrementale e a costo quasi nullo:

- la vetrina (landing, pricing, FAQ, articoli) resta su GitHub Pages
- `reports_html/` si sposta su Vercel dietro una serverless function che
  controlla la sessione e solo allora restituisce il contenuto
- `reserved-area.html` punta al dominio Vercel invece che ai file statici

Da fare in quella sede, visto che il costo marginale è zero:
- hash password con **bcrypt/argon2 e salt** al posto di SHA-256 puro
- **watermark per abbonato** su ogni report, così un leak è attribuibile
- rate limiting sui tentativi di login

Sul piano legale: una metodologia di trading non è brevettabile in quanto
tale in UE. La tutela è il **segreto commerciale** (Dir. UE 2016/943) più i
contratti — quindi ToS che vietino esplicitamente la redistribuzione, e
pubblicazione dei risultati senza i parametri che li generano.
