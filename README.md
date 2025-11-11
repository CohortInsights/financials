# Financials

A Flask + Google Drive–based tool for downloading, normalizing, storing, and analyzing financial statement data.

---

## Repository
https://github.com/CohortInsights/financials

---

## 📂 Project Structure

    financials/
    ├── financials/
    │   ├── __init__.py         # Package initializer
    │   ├── calculator.py       # Normalizes CSVs and persists data to MongoDB
    │   ├── drive.py            # Handles Google Drive API access
    │   ├── web.py              # Flask routes and dashboard API
    │   ├── db.py               # MongoDB connection utilities
    │   └── templates/          # Front-end assets for the dashboard UI
    │       ├── dashboard.html  # Main HTML interface for viewing transactions
    │       ├── styles.css      # Shared stylesheet (layout, buttons, filter row)
    │       └── code.js         # DataTables configuration, sorting, filtering logic
    ├── main_ingest.py          # Standalone ingestion entry point
    ├── main.py                 # Standalone entry point that invokes web.py
    ├── tests/
    │   └── test_calculator.py  # Unit tests for normalization logic
    ├── pyproject.toml          # Poetry dependencies and config
    ├── README.md               # Project documentation
    ├── .env                    # Environment (credentials, URIs)
    └── .gitignore              # Ignores secrets and build junk

---

## 🧩 Conventions

- **drive.py** → Google Drive API access only  
- **calculator.py** → `FinancialsCalculator` handles normalization + persistence  
- **db.py** → manages MongoDB client connections (`db_module.db["transactions"]`)  
- **main_ingest.py** → CLI entry for background ingestion (`poetry run python main_ingest.py`)  
- **web.py** → Flask app entry point with dashboard and JSON API routes  
- **templates/** → contains all front-end assets (HTML, CSS, and JS) that power the `/dashboard` view:
  - `dashboard.html` defines layout, year checkboxes, and DataTable structure  
  - `code.js` handles multi-year selection, dynamic filtering, and sorting (Shift+click support)  
  - `styles.css` provides consistent visual styling for table headers, filters, and controls  

---

## ⚙️ Setup

Requires **Python 3.12+** and [Poetry](https://python-poetry.org/).

    poetry install
    poetry shell

---

## 🔑 Credentials

Provide Google Drive OAuth credentials under `json/`, ignored by Git.  
On first run, token files (e.g. `token.drive.pickle`) are created automatically.  
Do **not** commit these credentials.

---

## 🧪 Running Tests

    poetry run pytest -v

Tests cover normalization for BMO, Citi, Chase, PayPal, Capitol One, and Schwab.

---

## 🚀 Running the App

    poetry run flask --app financials/web.py run

Then open: <http://127.0.0.1:5000/dashboard>

---

## 🧲 Data Ingestion

You can import normalized financials directly into MongoDB.

    poetry run python main_ingest.py

### What Happens
`main_ingest.py` calls the ingestion routine defined in `financials/ingest.py`, which:
1. Uses the `FinancialsCalculator` class to download and normalize all statement CSVs for each year.  
2. Calls `add_transaction_ids(df)` to generate consistent IDs derived from each row’s source, date, description, and amount.  
3. Connects to MongoDB and passes the enriched DataFrame to the `transactions` collection.  
4. Inserts new rows, skips duplicates, and logs summary info.  

Each normalized record follows this schema:  
`date, source, description, amount, type, id`

### Newly Supported Source: Schwab
The 2025 update adds a **Schwab normalizer** that extends the standard schema with these additional fields:

| Field | Example | Description |
|--------|----------|-------------|
| `action` | `Buy` | Schwab’s action type (Buy, Dividend, Deposit, etc.) |
| `symbol` | `AAPL` | Stock or fund symbol |
| `quantity` | `5.0` | Number of shares |
| `price` | `175.35` | Executed price per share |

All other sources (BMO, Citi, Discover, PayPal, CapitolOne) continue to emit the core five-field schema.  
MongoDB’s schemaless design allows Schwab rows to coexist seamlessly with prior data.

---

## 🌐 Dashboard and API

### Dashboard
Access the live UI at `/dashboard`.

Features:
- Multi-year selection via checkboxes (e.g., 2023, 2024, 2025)
- Scrollable, paginated, sortable **DataTable**
- Per-column **filter row in the table footer**
- Default sort by **Date (descending)**
- Auto-refresh on checkbox selection

### Backend API
The `/api/transactions` route serves JSON data directly from MongoDB.

    @bp.route("/api/transactions")
    def api_transactions():
        from flask import request, jsonify
        from financials import db as db_module
        import pandas as pd
        from datetime import datetime
        import numpy as np

        transactions = db_module.db["transactions"]
        years_param = request.args.get("years")
        year_param = request.args.get("year")
        query = {}

        if years_param:
            year_list = [int(y) for y in years_param.split(",") if y.strip().isdigit()]
            if year_list:
                query = {"$expr": {"$in": [{"$year": "$date"}, year_list]}}
        elif year_param and year_param.isdigit():
            start = datetime(int(year_param), 1, 1)
            end = datetime(int(year_param) + 1, 1, 1)
            query = {"date": {"$gte": start, "$lt": end}}
        else:
            current_year = datetime.now().year
            query = {"$expr": {"$in": [{"$year": "$date"}, [current_year]]}}

        cursor = transactions.find(query, {"_id": 0})
        df = pd.DataFrame(list(cursor))

        if not df.empty:
            if "date" in df.columns and pd.api.types.is_datetime64_any_dtype(df["date"]):
                df["date"] = df["date"].dt.strftime("%Y-%m-%d")
            if "amount" in df.columns:
                df["amount"] = df["amount"].fillna(0)
            df = df.replace({np.nan: ""})

        return jsonify(df.to_dict(orient="records"))

This route:
- Supports single-year (`year=`) or multi-year (`years=2023,2025`) queries  
- Uses `$expr` + `$in` to match discrete years  
- Converts `NaN` to `""` and `NaN` amounts to `0`  
- Returns valid JSON for the dashboard’s DataTable

---

## 📊 Example Output

| Date | Source | Description | Amount | Type |
|------|---------|--------------|--------|------|
| 2025-09-03 | PayPal | StubHub, Inc | $12.60 | Credit |
| 2024-07-10 | BMO | Target Stores | -$48.00 | Debit |
| ... | ... | ... | ... | ... |

Use footer filters to refine results and Shift+click headers for multi-column sorts.

---

## 📌 Current Status

- ✅ Multi-year checkbox selection  
- ✅ Footer filter row (full DataTables sorting restored)  
- ✅ Mongo `$expr` multi-year filtering  
- ✅ Clean JSON API  
- ✅ Schwab CSV ingestion and normalization  
- ⏳ Future: chart visualizations via `/api/summary`  

---

## 🗺️ Roadmap

### Visualization
- [ ] Add `/api/summary` endpoint for chart data  
- [ ] Integrate Chart.js or Plotly.js visualizations  
- [ ] Support client-driven chart refreshes tied to year filters  

### Data Ingestion
- ✅ Multi-year imports to MongoDB  
- ✅ Add Schwab account normalizer  
- [ ] Add Checks normalizer (optional, for extended data)  

### DevOps
- [ ] Add GitHub Actions for automated testing  

---

## 📜 License

TBD — consider MIT or Apache 2.0.

---

## 🤝 Contributing

Pull requests are welcome. This is an evolving personal project under the **CohortInsights** organization.
