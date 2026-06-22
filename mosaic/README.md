# TradingAlgo Mosaic engine

This folder contains the versioned source used to generate Mosaic market reports.

## Contents

- `TA_Portfolios.ipynb`: main calculation notebook.
- `Tickers.xlsx`: market universes and benchmarks.
- `download_market_data.py`: optional market data downloader.
- `run_all_15_markets.py`: run all markets from live data.
- `run_all_15_markets_from_csv.py`: run all markets from local `market_data/`.
- `ProcessingObjective.txt`, `Bio.txt`, `Disclaimer.txt`, `logo.png`: report assets/text.

## Workflow

1. Edit the notebook or scripts in this folder.
2. Test one market first, for example Italy:

   ```powershell
   python ..\tools\build_mosaic_html_report.py --dev-dir . --site-dir .. --market Italy30 --market-choice 5 --rerun
   ```

3. Verify the generated page in `..\reports_html\Italy30\Report_Italy30.html`.
4. If the result is correct, generate the remaining markets.
5. Commit both the engine changes and the generated site output.

Generated folders such as `output/`, `market_data/`, and logs are intentionally ignored.
