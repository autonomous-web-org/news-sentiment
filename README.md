# News Sentiment Score

This repository aggregates historical news and computes per‑ticker sentiment scores as a time series, providing all‑time coverage for each symbol and refreshing the results every day to reflect the latest developments. The goal is to make sentiment trends easy to explore and compare across tickers, enabling research, monitoring, and long‑term analysis without additional setup.

## Security Measures
Scan using Gitleaks periodically.
```bash
gitleaks detect -v
```

## Available (Exchanges - Tickers)
- NSE - RELIANCE
- NASDAQ - PEP
- NYSE - PG
- HKEX - 1972
- SSE - 600519
- TADAWUL - SABIC
- TSX - BN
- TYO - 8001
- XPAR - LVMH

_UPDATED DAILY_

## To-do
- in bot configure panel, instead of loading the whole file only load screens metadata and then load each screen data on-demand. for instance, loading the data of the exchange that is required, not all of them.
- an alternate/extension to above is separating each exchange data to a separate .json file.


## Made it possible using:
- https://www.python.org/
- https://react.dev/
- https://newsapi.org/v2/everything
- https://finance.yahoo.com/