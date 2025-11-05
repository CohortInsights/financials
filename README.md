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
    │   ├── web.py              # Flask routes and dashboard
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
- **db.py** → manages MongoDB client connections  
- **main_ingest.py** → CLI entry for background ingestion (`poetry run python main_ingest.py`)  
- **web.py** → Flask app entry point (dashboard integration)  
- **templates/** → front-end dashboard (`dashboard.html`, `styles.css`, `code.js`)  

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

Tests cover normalization for BMO, Citi, Chase, and PayPal CSVs.

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
3. Connects to MongoDB and passes the enriched DataFrame to `save_to_collection(df, collection)`, which:
   - Ensures a unique index on `id`.
   - Converts dates to Mongo-compatible types.
   - Inserts all new transactions while skipping duplicates automatically.
4. Logs results (inserted vs. skipped) to the console.

### Example (pseudo-code)
    from financials.calculator import FinancialsCalculator
    from financials.db import get_mongo_collection
    from financials.drive import GoogleDrive

    drive = GoogleDrive()                          # authenticated Drive client
    calc = FinancialsCalculator(drive)
    df = calc.load_year_data("2024")               # normalize CSVs for 2024
    df = calc.add_transaction_ids(df)              # assign unique transaction IDs

    collection = get_mongo_collection("financials")
    inserted = calc.save_to_collection(df, collection)
    print(f"Inserted {inserted} new transactions")

---

## 📌 Current Status

- ✅ CSV normalization for BMO, Citi, Chase, PayPal  
- ✅ MongoDB schema and connection verified  
- ✅ Transaction ID generation implemented  
- ✅ Data ingestion via `main_ingest.py` to MongoDB  
- ✅ Unit tests validated for normalization logic  
- ⏳ Capitol One normalization pending  
- ⏳ Schwab investment account parsing pending  

---

## 🗺️ Roadmap

### Data Ingestion
- ✅ Import normalized data and store in MongoDB (with transaction IDs)  
- [ ] Add Capitol One and Schwab account normalizers  

### Persistence
- [ ] Extend MongoDB schema for multi-year rollups and indexing  

### Visualization
- [ ] Dashboard charts for trends, balances, and categories  
- [ ] UI edit/export features  

### DevOps
- [ ] GitHub Actions for automated testing  

---

## 📜 License

TBD — consider MIT or Apache 2.0.

---

## 🤝 Contributing

Pull requests are welcome. This is an evolving personal project under the **CohortInsights** organization.
