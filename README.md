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
    │   └── templates/          # HTML/CSS/JS for dashboard UI
    ├── main_ingest.py          # Standalone ingestion entry point
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
- **templates/** → dashboard front-end (`dashboard.html`, `styles.css`, `code.js`)  

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

Tests cover normalization for BMO, Citi, Chase, PayPal, and Capitol One.

---

## 🚀 Running the App

    poetry run flask --app financials/web.py run

Then open: <http://127.0.0.1:5000/dashboard>

---

## 🧲 Data Ingestion

You can now import normalized financials directly into MongoDB.

    poetry run python main_ingest.py

### What Happens
`main_ingest.py` calls the ingestion routine defined in `financials/ingest.py`, which:
1. Uses the `FinancialsCalculator` class to download and normalize all statement CSVs for each year.  
2. Calls `add_transaction_ids(df)` to generate consistent IDs derived from each row’s source, date, description, and amount.  
3. Connects to MongoDB and passes the enriched DataFrame to the `transactions` collection.  
4. Inserts new rows, skips duplicates, and logs summary info.  

Each normalized record follows this schema:  
`date, source, description, amount, type, id`

### Example
    from financials.calculator import FinancialsCalculator
    from financials.drive import GoogleDrive
    from financials import db as db_module

    drive = GoogleDrive("roger_drive")
    calc = FinancialsCalculator(drive)
    df = calc.load_year_data("2024")
    df = calc.add_transaction_ids(df)

    transactions = db_module.db["transactions"]
    inserted = calc.save_to_collection(df, transactions)
    print(f"Inserted {inserted} new transactions")

---

## 🌐 Dashboard and API

### Dashboard
Access the live UI at `/dashboard`.

Features:
- “Since” dropdown to choose starting year (e.g., 2025, 2024, 2023)
- Scrollable, paginated, sortable **DataTable**
- Per-column **text filters**
- Default sort by **Date (descending)**
- Auto-refresh on year selection

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
        year = request.args.get("year")
        query = {}

        if year and year.isdigit():
            start = datetime(int(year), 1, 1)
            end = datetime(int(year) + 1, 1, 1)
            query = {"date": {"$gte": start, "$lt": end}}

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
- Filters by `datetime` range for the selected year  
- Converts `NaN` to `""` (and numeric NaN to 0)  
- Returns clean, valid JSON for DataTables consumption

---

## 🖥️ Front-End Behavior

### code.js
Implements:
- Year dropdown and reload control  
- Dynamic `/api/transactions?year=YYYY` fetching  
- DataTables initialization with per-column filters and default date sort  
- Full client-side filtering, searching, and paging  

### dashboard.html
- Hosts dropdown + button controls  
- Displays DataTable (`<table id="transactions">`)  
- Imports DataTables JS/CSS via CDN  
- Injects `user_data` JSON into the page for JS use

### styles.css
- Theming for dropdowns and buttons  
- Responsive layout for the data table  
- Styled filter inputs below each column header  

---

## 📊 Example Output

The dashboard table now includes:
| Date | Source | Description | Amount | Type |
|------|---------|--------------|--------|------|
| 2025-09-03 | PayPal | StubHub, Inc | $12.60 | Credit |
| ... | ... | ... | ... | ... |

Use column filters to search instantly (e.g., type “PayPal” or “Credit”).

---

## 📌 Current Status

- ✅ CSV normalization (BMO, Citi, Chase, PayPal, Capitol One)  
- ✅ MongoDB connection + `datetime` filtering  
- ✅ Data ingestion + ID generation  
- ✅ Flask API (`/api/transactions`) returning clean JSON  
- ✅ Dashboard with DataTables sorting, filtering, pagination  
- ⏳ Schwab and Checks normalizers pending  
- ⏳ Charts and category breakdowns next  

---

## 🗺️ Roadmap

### Visualization
- ✅ Table view with filtering and sorting  
- [ ] Add numeric range filter for `Amount` column  
- [ ] Add chart visualizations (balances, categories, trends)  
- [ ] CSV export option  

### Data Ingestion
- ✅ Multi-year imports to MongoDB  
- [ ] Add Schwab and Checks account normalizers  

### DevOps
- [ ] Add GitHub Actions for automated testing  

---

## 📜 License

TBD — consider MIT or Apache 2.0.

---

## 🤝 Contributing

Pull requests are welcome. This is an evolving personal project under the **CohortInsights** organization.
