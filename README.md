# Financials

A Flask + Google Drive–based tool for downloading, normalizing, storing, and analyzing personal financial data.

---

## Repository
https://github.com/CohortInsights/financials

---

## 📂 Project Structure
    financials/
    ├── financials/
    │   ├── __init__.py             # Package initializer
    │   ├── calculator.py           # Normalizes CSVs and persists data to MongoDB
    │   ├── drive.py                # Handles Google Drive API access
    │   ├── web.py                  # Flask app entry point (routes import app directly; no Blueprints)
    │   ├── db.py                   # MongoDB connection utilities
    │   │
    │   ├── routes/                 # Flask route modules (attach directly to app)
    │   │   ├── __init__.py         # Enables route package imports
    │   │   ├── dashboard.py        # /dashboard → renders HTML dashboard
    │   │   ├── api_transactions.py # /api/transactions → serves normalized transaction JSON
    │   │   ├── assign.py           # /assign_transaction → manual assignments
    │   │   └── rules.py            # /api/rules → CRUD endpoints for assignment rules (Mongo)
    │   │
    │   ├── utils/                  # Shared backend helper modules
    │   │   ├── __init__.py         # Enables utils package imports
    │   │   └── services.py         # Provides get_drive_service(), get_calculator(), set_cache_dir()
    │   │
    │   ├── templates/              # HTML/CSS/JS for dashboard UI (served directly)
    │   │   ├── dashboard.html      # Main dashboard (Transactions + Rules tabs, Add Rule modal)
    │   │   ├── code.js             # Base DataTable + client-side behavior
    │   │   ├── transactions.js     # Transactions tab interactions and assignment actions
    │   │   ├── rules.js            # Rules tab (modal open/save, table init/refresh)
    │   │   └── styles.css          # UI styling (incl. modal size/scroll tweaks)
    │   │
    │   ├── scripts/                # Maintenance and administrative utilities
    │   │   ├── delete_entries.py   # Deletes all docs for a given source
    │   │   ├── update_indexes.py   # Updates all MongoDB indexes (idempotent)
    │   │   └── rebuild_assignments.py # Rebuilds rule_matches + transaction assignments (slow/fast path)
    │   │
    │   └── assign_rules.py         # Backend rule engine for automatic transaction categorization
    │
    ├── main_ingest.py              # Standalone ingestion entry point (CLI)
    ├── main.py                     # Entry point that invokes financials/web.py
    │
    ├── tests/                      # Unit tests
    │   └── test_calculator.py      # Tests for normalization logic
    │
    ├── pyproject.toml              # Poetry dependencies and configuration
    ├── README.md                   # Project documentation
    ├── .env                        # Environment variables (credentials, URIs)
    └── .gitignore                  # Ignores secrets and build junk


### Mongo Collections
- transactions : Stores all normalized financial transactions (id, date, source, description, amount, type, assignment). The assignment field always reflects the current winning assignment (manual or automatic)
- assignment_rules : Stores all automatic categorization rules (id, assignment, priority, source, description, min_amount, max_amount). These define the matching logic but do not store which transactions they match
- transaction_assignments : Tracks all assignment applications (id, assignment, type, timestamp). Includes both manual and auto entries. Manual assignments always take precedence
- rule_matches : Materialized table of all rule-to-transaction matches (rule_id, txn_id, priority, assignment). Used to compute winners efficiently and to support incremental rule updates without re-evaluating all rules

---

## 🧩 Conventions

- **drive.py** → Google Drive API access only  
- **calculator.py** → `FinancialsCalculator` handles normalization + persistence  
- **db.py** → manages MongoDB client connections (`db_module.db["transactions"]`)  
- **main_ingest.py** → CLI entry for background ingestion (`poetry run python main_ingest.py`)  
- **web.py** → Flask app entry point with dashboard and JSON API routes  
- **templates/** → dashboard front-end (`dashboard.html`, `styles.css`, `code.js`)  
- **scripts/delete_entries.py** → deletes transactions by source (`--source bmo`, etc.)

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

Tests cover normalization for BMO, Citi, Chase, PayPal, Capitol One, Schwab, and Checks.

---

## 🚀 Running the App

    poetry run flask --app financials/web.py run

Then open: <http://127.0.0.1:5000/dashboard>

---

## 🧲 Data Ingestion

You can import normalized financials directly into MongoDB.

    poetry run python main_ingest.py

### What Happens
`main_ingest.py` calls the ingestion routine defined in `financials/calculator.py`, which:
1. Uses the `FinancialsCalculator` class to download and normalize all statement CSVs for each year.  
2. Pre-loads `Checks-YEAR.csv` (if present) and builds a mapping `{check_no → {payee, assignment}}`.  
3. Normalizes BMO, Citi, PayPal, CapitolOne, Schwab, etc., replacing any BMO “DDA CHECK” transactions with the corresponding **Pay To** and **Assignment** fields from the Checks file.  
4. Calls `add_transaction_ids(df)` to generate consistent IDs derived from each row’s source, date, description, and amount.  
5. Connects to MongoDB and inserts new rows, skipping duplicates, logging counts.  

Each normalized record follows this schema:  
`date, source, description, amount, type, assignment, [action, symbol, quantity, price]`

---

## 🧮 Normalization Details

### BMO + Checks Integration
- When a **Checks-YEAR.csv** file is present, it is read first.  
- Each BMO row with a matching `TRANSACTION REFERENCE NUMBER` or `FI TRANSACTION REFERENCE` is enriched with:
  - `description` → replaced by the check’s “Pay To” value  
  - `assignment` → the check’s “Assignment” value, prefixed with `Expense.` (e.g. “Expense.Charity.KOC”)  
- Non-check rows remain unchanged.  

Example:

| POSTED DATE | DESCRIPTION | AMOUNT | TRANSACTION REF | TYPE | → | description | assignment |
|--------------|--------------|---------|------------------|------|----|--------------|-------------|
| 08/09/2024 | DDA CHECK | -26.34 | 9502 | Debit | → | St Christopher CP | Expense.Charity.Church |
| 08/08/2024 | DDA CHECK | -100.00 | 9504 | Debit | → | City of Verona Dog Licensing | Expense.Taxes.Licenses |

---

### Schwab
- Supports stock trades with fields `action`, `symbol`, `quantity`, and `price`.
- All numeric parsing via `_parse_numeric()` handles `$` and `,` cleanup.
- Adds `type` as Credit/Debit based on `amount` sign.

---

### Checks
- Normalized separately to a lookup mapping `{check_no: {"payee", "assignment"}}`.
- Prepends `"Expense."` to all assignments for downstream categorization.
- Used only as enrichment; no direct insertion into Mongo.

---

## 🧰 Utility Scripts

### Delete Entries

    poetry run python -m financials.scripts.delete_entries --source bmo

Deletes all MongoDB transactions from a specified source.  
Prompts before deletion and logs counts.

---

## 🌐 Dashboard and API

### Dashboard
Access the live UI at `/dashboard`.

Features:
- Multi-year checkbox selection  
- Scrollable, paginated, sortable transactions **DataTable**
- Footer row filters for each column  
- Default sort by **Date (descending)**  
- Supports multi-column sorting via **Shift+click**

### Backend API
The `/api/transactions` route serves JSON data directly from MongoDB with optional year filters.
---

## 🗺️ Roadmap

### Visualization
- [ ] Add `/api/summary` endpoint for chart data  
- [ ] Integrate Chart.js or Plotly visualizations  
- [ ] Support assignment-based spending charts

### Data Ingestion
- ✅ Multi-year imports to MongoDB  
- ✅ Add Schwab and Checks account normalizers  
- ✅ BMO transactions enriched with check assignments  
- ✅ Manual categorization for transactions
- ✅ UI for addition of rules
- ✅ Auto categorization for transactions (see Assignment of Transactions section)

### Assignment of Transactions
- Transactions from all sources have an "Assignment" field in the form a.b.c (e.g. Expense, Expense.Food.Groceries, Income.WRS.Roger)
- An assignment can be made manually from the transactions table
- Automated assignments are controlled by rules stored in the assignment_rules collection
- Rules contain fields of id, assignment, priority, source, description, min_amount, max_amount
- Rules are added, updated, and deleted from the Rules tab (CRUD) and stored in the assignment_rules collection
- The Source field of a rule applies "equals" logic to the source of each transaction (a means "source equals a"; a,b means "source equals (a or b)")
- The Description field applies substring-based logic (a,b means "description contains a and b"; a|b means "description contains a or description contains b")
- The values of min_amount and max_amount apply numeric filters to each transaction amount
- If a transaction matches multiple rules, the rule with the highest priority takes precedence
- If a transaction matches multiple rules with the same priority, the most recently created rule is applied
- When a rule matches a transaction, the rule's assignment is used to set the transaction's assignment, and a corresponding auto entry is added to the transaction_assignments table
- Manual assignments override all rules and are never replaced by automatic logic
- A materialized table named rule_matches stores all rule-to-transaction matches and is used to compute the highest priority match for each transaction
- The fields of transaction_assignments are transaction_id, assignment, type (auto or manual), and timestamp

### DevOps
- [ ] Add GitHub Actions for automated testing

---

## 📜 License

TBD — consider MIT or Apache 2.0.

---

## 🤝 Contributing

Pull requests are welcome. This is an evolving personal project under the **CohortInsights** organization.
