# Gold Price Benchmarks

A lightweight static dashboard for comparing India-first 24K gold benchmarks
across IBJA, Dubai, live global spot, Indian retail/bullion references,
consumer portals, jewellery context, and USD/INR.

## What It Shows

- **24K primary benchmarks** for live global spot, IBJA India, and Dubai.
- **India-first display**: INR per gram is the headline metric.
- **Global context**: USD per troy ounce is shown as a secondary conversion
  using `1 troy oz = 31.1034768g`.
- **Comparable units**: per gram, per 10g, per tola, and per troy ounce.
- **22K/916 context** for jewellery buyers.
- **Buyer context** from retail bullion, digital/home-delivery, jewellery-brand,
  and consumer reference pages.
- **Source status** labels: `fresh`, `stale`, or `unavailable`.

The scraper does not invent fallback prices. If a source cannot be parsed, the
site tracks it in source coverage instead of showing it as a headline row.

## Source Strategy

- **Global spot**: uses a no-key XAU/USD feed as live market context, clearly
  labeled as live/non-official.
- **Dubai**: attempts Dubai Gold & Jewellery Group/Dubai official pages first,
  then clearly labeled DGJG-derived mirrors if direct pages are not parseable.
- **India benchmark**: IBJA 999/24K and 916/22K rates.
- **FX**: attempts FBIL USD/INR first, then a no-key live FX fallback if needed.
- **India retail**: attempts MMTC-PAMP, SafeGold, Augmont, All India Bullion
  Mumbai 999 retail/RTGS/GST rows, Upstox, Goodreturns Chandigarh, Groww, and
  jewellery retail pages.
- **Market context**: tracks MCX, Moneycontrol, and NDTV Profit as market/context
  sources when publicly fetchable; they are not treated as retail buyer prices.
- **Default city**: Mumbai for All India Bullion retail context.

## Local Development

```bash
pip install -r requirements.txt
python scraper.py
python -m pytest -q
python -m http.server 8000
```

Open `http://127.0.0.1:8000/`.

## Data Shape

`data.json` contains:

- `generated_at`
- `fx.usd_inr`, `fx.source`, `fx.source_type`, `fx.as_of`
- `rates[]` with source, purity, currency, unit, price, status, and normalized
  INR/USD fields
- `spreads[]` comparing available 24K rates against IBJA and Dubai benchmarks

## Deployment

This repo is designed for GitHub Pages. The included GitHub Action refreshes
`data.json` every 15 minutes and commits only when parsed data changes.
