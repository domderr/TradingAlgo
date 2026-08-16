# Protezione del know-how — audit e piano di rientro

Data audit: 2026-08-16. Riferimento: sito offline dal 14 agosto perché il
repository è stato reso privato e GitHub Pages si è depubblicato.

Questo file non viene pubblicato sul sito (escluso in `_config.yml`).

---

## 1. Cosa è risultato esposto

| # | Problema | Dove |
|---|---|---|
| 1 | Autenticazione area riservata **interamente lato client** | `reserved-area.html:1288-1380` |
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

## 2. Cosa è già stato fatto (commit su questo branch)

- **`_config.yml`** (nuovo) — esclude dalla build `mosaic_dev/`, `tools/`,
  `scripts/`, i file `.py`/`.ipynb`/`.xlsx` e i CSV sorgente. Da qui in poi
  la metodologia non esce più dal sito, nemmeno a repo pubblico.
  Restano pubblicati i file che il sito carica a runtime: `haircuts.csv`,
  `reports/*.json`, `assets/subscriptions.json`.
- **`sitemap.xml`** — rimossi 488 URL (487 report + admin tool). Da 515 a 27,
  che sono le sole pagine vetrina.
- **490 file in `reports_html/` + `admin-rebalance-tool.html`** — aggiunto
  `<meta name="robots" content="noindex, nofollow">`.
- **`tools/build_mosaic_html_report.py`** — i 3 template emettono ora il
  `noindex`, così la rigenerazione settimanale non annulla la modifica.
- **`robots.txt`** — `Disallow` su `/mosaic_dev/`, `/scripts/`, `/tools/`.
  Volutamente **nessun** `Disallow` su `/reports_html/`: Google deve poter
  scaricare quelle pagine per leggerne il `noindex`. Bloccarle ora
  lascerebbe le URL già indicizzate nei risultati.
- **`.gitignore` + untrack** — `mosaic_dev/Subscriptions.xlsx` non è più
  versionato (resta in locale).

---

## 3. Cosa resta da fare — richiede te

### 3.1 Prima di rimettere pubblico il repo (bloccante)

`Subscriptions.xlsx` è ancora nella **history** di git dal 2 luglio.
Rimuoverlo dal tracking non lo toglie dai commit passati: a repo pubblico
sarebbe di nuovo scaricabile. Va purgato prima del switch.

```bash
pip install git-filter-repo

git clone --mirror https://github.com/domderr/TradingAlgo.git ta-mirror
cd ta-mirror
git filter-repo --path "mosaic_dev/Subscriptions.xlsx" --invert-paths
git push --force
```

Dopo il force-push: ogni clone locale esistente va ricreato da zero, perché
gli SHA cambiano.

> Valuta se purgare nella stessa passata anche `mosaic_dev/` e `tools/`
> (`--path mosaic_dev/ --path tools/ --invert-paths`), spostandoli in un
> repository privato dedicato. È l'unico modo per togliere la metodologia
> dalla history prima di tornare pubblici.

### 3.2 Rotazione credenziali (bloccante, indipendente dal resto)

Le password degli abbonati sono state in chiaro in un repo pubblico per
sei settimane. Vanno considerate compromesse:

1. genera nuove password in `Subscriptions.xlsx`
2. esegui `python update_subscriptions.py` da `mosaic_dev`
3. verifica che `assets/subscriptions.json` contenga solo `password_hash`
4. comunica il cambio agli abbonati

Valuta con un consulente se ricorrono gli estremi di notifica al Garante
(email + password in chiaro pubblicamente accessibili sono dati personali).

### 3.3 Rimettere il sito online

Da `Settings` del repository:

1. `Settings → General → Danger Zone → Change visibility` → **Public**
   *(in alternativa, per restare privati: GitHub Pro, ~4 $/mese, che abilita
   Pages da repo privati — ma il sito pubblicato resta comunque pubblico)*
2. `Settings → Pages` → Source: branch `main`, cartella `/ (root)`
3. `Settings → Pages → Custom domain` → `tradingalgo.it`
   (il file `CNAME` è già corretto; il DNS punta già agli IP giusti)
4. Attendi il certificato HTTPS, poi spunta **Enforce HTTPS**

Perché le protezioni siano attive *prima* che il sito torni raggiungibile,
questo branch va unito in `main` **prima** del passo 1.

### 3.4 Deindicizzazione

In Google Search Console:
- invia il `sitemap.xml` aggiornato
- usa **Rimozioni** per `tradingalgo.it/reports_html/` (rimozione rapida,
  ~6 mesi) mentre il `noindex` fa effetto in modo permanente
- ricontrolla dopo 30 giorni; solo allora aggiungi il `Disallow` in robots.txt

---

## 4. La protezione vera dei report

Tutto quanto sopra riduce l'esposizione e ferma l'emorragia, ma **non rende
i report inaccessibili**: chi conosce l'URL continua a leggerli. Per una
protezione reale serve un host che esegua codice lato server e verifichi la
sessione prima di servire il file.

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
