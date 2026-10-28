# 🍬 SweetShop AI OS

A GitHub-ready, single-file Streamlit application for sweet-shop operations and analytics.

## Features

- Executive dashboard for net sales, estimated gross profit, order counts, average order value and daily trends.
- Product and customer intelligence: weekday heatmaps, peak hours, customer segments, area trends and exploratory basket combinations.
- Demand forecasting with a time-ordered holdout comparison between weekday baseline, Random Forest, Extra Trees, HistGradientBoosting and Ridge regression.
- Production planner that converts historical weekday averages into a buffered preparation suggestion.
- Stock ledger, reorder warnings, batch references and expiry dates.
- Ingredient and recipe tracking with basic ingredient-need calculations.
- Delivery records, on-time tracking, area-level operations and delay reasons.
- Manual daily context diary for temperature, rainfall, humidity, festivals, holidays, local events, promotions, footfall and stockouts.
- Sales entry, product/customer catalog, CSV import/export, promotion tracking, data-quality checks and database backup.

## Run locally

Requires Python 3.10+.

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

The first launch creates a local SQLite database and seeds **synthetic demo data**. Do not treat it as real sales history.

## Use with real data

1. Back up anything important.
2. For a fresh database without automatic demo data, set `SWEETSHOP_DEMO=0` before first launch.
3. Add your product catalog and customers.
4. Enter sales manually or import CSV with required columns:
   - `sold_at`
   - `product`
   - `quantity`
   - `unit_price`
5. Optional CSV columns: `discount`, `channel`, `customer_code`, `order_id`, `payment_method`, `promotion`, `occasion`, `notes`.
6. Product names must exactly match the catalog. Keep units consistent (e.g. don't mix piece and kg for the same SKU).

macOS/Linux:
```bash
SWEETSHOP_DEMO=0 streamlit run app.py
```

Windows PowerShell:
```powershell
$env:SWEETSHOP_DEMO="0"
streamlit run app.py
```

## GitHub upload

Do not commit a real database or personal/customer data. A suitable `.gitignore` is included. Suggested repository steps:

```bash
git init
git add app.py requirements.txt README.md .gitignore
git commit -m "Initial SweetShop AI OS"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/sweetshop-ai-os.git
git push -u origin main
```

## Deploy

For a private prototype, Streamlit Community Cloud can deploy `app.py` from a GitHub repository. Keep in mind its filesystem may not be a durable production database. For multiple staff or business-critical records, use a managed PostgreSQL database, authentication, role-based access, backups, audit logging and HTTPS.

## Limitations you should know

This is a robust starter prototype, not a finished enterprise system. It does not automatically fetch weather, compute official festival calendars, optimize live delivery routes, issue GST invoices, send WhatsApp/SMS notifications, or authenticate staff. The current inventory ledger is not automatically decremented by each sale, and the ingredient calculator depends on manually entered recipes. Fix and test these workflows before using stock suggestions for purchasing or production.

The forecast uses limited calendar and optional manually recorded weather features. It does not currently encode festival labels directly into the model; its model score is not a guarantee of future performance. Evaluate forecasts against held-out dates and compare to a simple baseline before trusting it.

Gross profit is only an estimate using current product cost, excluding taxes, labour, rent, packaging, wastage and delivery overhead. Follow local privacy rules and collect only customer data that is necessary.
