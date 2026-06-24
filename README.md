# TradingAlgo

Root unica del progetto TradingAlgo.

## Cartelle vive

- `site`: sito statico pubblicato su GitHub.
- `mosaic_dev`: pipeline TradingAlgo Mosaic, notebook, dati, output e todo list.

## Archivio

Le copie storiche originali restano in `G:\Il mio Drive\TradingAlgo_Project\_archive`:

- `TradingAlgoMosaic`
- `TradingAlgo.it`
- `TradingAlgoMosaic_Dev`

## Comandi principali

Da `mosaic_dev`:

```powershell
python download_market_data.py --markets all
python run_all_15_markets_from_csv.py
```

Da `site`:

```powershell
# Aprire/modificare i file statici del sito.
# Se serve pubblicare, collegare questa cartella al repository GitHub desiderato.
```

## Regola operativa

Usare solo `TradingAlgo` come punto di lavoro. Le vecchie cartelle fuori root non sono piu sorgenti operative.
