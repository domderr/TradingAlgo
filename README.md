# TradingAlgo

Root unica del progetto TradingAlgo: sito statico, pipeline Mosaic e output pubblicati.

## Cartelle vive

- Root del repository: pagine HTML del sito statico pubblicato.
- `mosaic_dev`: sorgente operativo della pipeline TradingAlgo Mosaic.
- `mosaic_dev/market_data`: dati prezzo locali usati dai run da CSV.
- `mosaic_dev/output`: output intermedi prodotti dalla pipeline.
- `reports`: indici JSON/CSV usati dal sito.
- `reports_html`: report HTML generati per mercato.
- `assets`: immagini, dati statici e asset pubblici del sito.
- `tools`: script di build/report HTML.
- `scripts`: utility per pagine dati e asset statici.

## Pipeline operativa

Da `mosaic_dev`:

```powershell
python download_market_data.py --markets all
python run_all_15_markets_from_csv.py
```

Per rigenerare un report HTML specifico:

```powershell
python ..\tools\build_mosaic_html_report.py --dev-dir . --site-dir .. --market Italy30 --market-choice 5 --rerun
```

## File chiave

- `mosaic_dev/TA_Portfolios.ipynb`: motore strategia e report data.
- `mosaic_dev/Tickers.xlsx`: universi e benchmark dei mercati.
- `mosaic_dev/conservative_haircuts.csv`: haircut prudenziali per mercato.
- `mosaic_dev/apply_conservative_haircuts.py`: applicazione haircut agli output.
- `mosaic_dev/run_all_15_markets_from_csv.py`: runner batch principale da dati locali.
- `tools/build_mosaic_html_report.py`: generatore dei report HTML.

## Output generati

I file sotto `mosaic_dev/output`, `mosaic_dev/market_data` e `mosaic_dev/runs` sono generati o dati locali di lavoro. Non sono il punto da modificare a mano, salvo controlli puntuali.

Prima di sovrascrivere gli indici del sito, il runner salva una fotografia locale degli output precedenti in:

- `mosaic_dev/output/site_snapshots/<YYYYMMDD_HHMMSS>/`

Queste fotografie non sono pubblicate dal sito e non vengono cancellate automaticamente. Servono per verifiche future di coerenza tra elaborazioni.

Regola importante: gli snapshot sono immutabili. Non devono essere rielaborati quando cambia la logica di costruzione dei portafogli; vanno usati solo come evidenza storica di cio' che era stato prodotto in quel momento.

Ogni snapshot include una copia degli input strategici usati per la run:

- `Tickers.xlsx`
- `conservative_haircuts.csv`

`Subscriptions.xlsx` e' escluso dagli snapshot di elaborazione: e' un file privato per gli accessi, non un input di costruzione dei portafogli.

I report pubblicati sono in:

- `reports/reports_index.json`
- `reports/reports_index.csv`
- `reports_html/<Market>/Report_<Market>.html`

## Archivio

Le vecchie copie operative non sono sorgenti attive. La cartella duplicata `mosaic` e' stata rimossa; la pipeline viva e' solo `mosaic_dev`.

## Regola operativa

Usare solo `TradingAlgo` come punto di lavoro. Modificare il motore in `mosaic_dev`, rigenerare gli output con i runner, poi verificare le pagine in `reports_html`.
