# Financials

A Flask + Google Drive–based tool for downloading, normalizing, storing, and analyzing personal financial data.

---

## Repository
https://github.com/CohortInsights/financials

---

## 📂 Project Structure
    financials/
    ├── financials/
    │   ├── __init__.py
    │   ├── calculator.py
    │   ├── drive.py
    │   ├── web.py
    │   ├── db.py
    │   │
    │   ├── routes/
    │   │   ├── __init__.py
    │   │   ├── dashboard.py
    │   │   ├── api_transactions.py
    │   │   ├── assign.py
    │   │   └── rules.py
    │   │
    │   ├── utils/
    │   │   ├── __init__.py
    │   │   ├── services.py
    │   │   └── google_types.py            # Merchant-type lookup + caching + Google Places integration
    │   │
    │   ├── templates/
    │   │   ├── dashboard.html
    │   │   ├── code.js
    │   │   ├── transactions.js
    │   │   ├── rules.js
    │   │   └── styles.css
    │   │
    │   ├── scripts/
    │   │   ├── delete_entries.py
    │   │   ├── update_indexes.py
    │   │   ├── rebuild_assignments.py
    │   │   └── get_google_types.py        # CLI tool for merchant-type enrichment (cached or live)
    │   │
    │   └── assign_rules.py
    │
    ├── main_ingest.py
    ├── main.py
    │
    ├── cfg/
    │   └── google_types_to_expenses.csv   # Curated ontology mapping Google types → Expense.* categories
    │
    ├── tests/
    │   └── test_calculator.py
    │
    ├── pyproject.toml
    ├── README.md
    ├── .env
    └── .gitignore

### Mongo Collections

- transactions  
  Stores all normalized financial transactions (id, date, source, description, amount, type, assignment).  
  The `assignment` field always reflects the current winning assignment (manual or automatic).

- assignment_rules  
  Stores all automatic categorization rules (assignment, priority, source filters, description substring filters, amount ranges).  
  These rules define the matching logic used by the assignment engine.

- transaction_assignments  
  Audit log of all assignment events.  
  Contains `{transaction_id, assignment, type (manual|auto), timestamp}`.  
  Manual assignments always override automatic rules and can never be replaced.

- rule_matches  
  Materialized table storing every rule-to-transaction match `{rule_id, txn_id, priority, assignment}`.  
  Supports efficient winner selection and incremental updates when rules are created, edited, or deleted.

- google_merchant_types  
  Cache of semantic merchant lookups via the Google Places API.  
  One document per *unique transaction description*.  
  Fields include:  
  • description (string, bank-provided)  
  • types (array of filtered Google semantic types)  
  • place_id (Google Places identifier)  
  • status ("ok", "not_found", "ambiguous", "error")  
  • updated_at (timestamp)  
  This cache prevents repeated paid API calls and enables semantic rule generation.


---

## Mongo Collection Details

This project uses several MongoDB collections to support ingestion, normalization, rule-based assignment, and merchant-type enrichment. Below is a detailed description of each collection and its schema.

### transactions
Stores all normalized financial transactions imported from CSVs.  
Each record is uniquely identified by a synthetic `id` generated from date, source, description, and amount.

Fields:
- id : unique string identifier  
- date : datetime  
- source : string (bmo, citi, chase, paypal, etc.)  
- description : string (raw bank description)  
- amount : float  
- type : "Credit" or "Debit"  
- assignment : string (manual or winning auto-assignment)  
- action, symbol, quantity, price : optional fields for Schwab trade data

### assignment_rules
Defines automatic categorization rules.  
Rules are applied to every transaction based on source, description substring logic, and amount ranges.

Fields:
- id  
- assignment  
- priority  
- source (comma-separated list of allowed sources or empty string for “any”)  
- description (substring OR/AND logic, e.g. "amazon|amzn" or "kwik,trip")  
- min_amount  
- max_amount  

### transaction_assignments
Audit log of all assignment events.  
Stores both manual and automatic assignments.

Fields:
- id : transaction id  
- assignment  
- type : "manual" or "auto"  
- timestamp

Manual assignments always override automatic rules.

### rule_matches
Materialized table storing all rule-to-transaction matches.  
Used to efficiently compute winning rule for each transaction.

Fields:
- rule_id  
- txn_id  
- priority  
- assignment  

This table is fully rebuilt when rules change.

### google_merchant_types
Stores the results of Google Places merchant-type lookups for unique transaction descriptions.  
This provides semantic enrichment for rule creation and automated categorization.

Fields:
- description : raw bank description  
- types : array of Google semantic types (filtered to supported ontology)  
- place_id : Google Places identifier  
- status : "ok" (successful lookup), "not_found", "ambiguous", or "error"  
- updated_at : timestamp of last lookup  

This collection acts as a cache to prevent repeated paid API lookups.

---

## Google Merchant-Type Enrichment

Financial transaction descriptions from banks are often opaque or non-semantic (e.g. “KWIK TRIP 123”, “SQ *JOES COFFEE”). To support more accurate auto-assignment rules, the system integrates with the Google Places API to map raw descriptions into semantic merchant categories.

### Enrichment Workflow

1. Extract unique transaction descriptions from MongoDB, filtered by optional flags (`--source`, `--year`, `--description`).  
2. For each description:  
   - Check google_merchant_types for cached lookup results.  
   - If status is "ok", reuse the stored types.  
   - If no cached entry exists, and live mode is enabled, perform a Google Places API searchText lookup.  
3. Filter returned Google types against the project's curated ontology (from google_types_to_expenses.csv).  
4. Store the result in google_merchant_types with status, types, and place_id.  

This process ensures:
- No repeated paid requests  
- Transparent caching  
- Full cost visibility before any charge is incurred  
- Safe dry-run mode  
- Reproducibility for all future runs  

### Enrichment Script

The enrichment process is driven by:

financials/scripts/get_google_types.py

It supports:
- --source : restrict by account source  
- --year : restrict by transaction year  
- --description : case-insensitive substring filter  
- --all : process all transactions  
- --live : enable real Google API calls (with confirmation prompt)  

Without `--live`, the script performs only cache lookups.

Example usage:
poetry run python -m financials.scripts.get_google_types --source BMO --year 2025 --description "KWIK TRIP" --live

### Google Places API Integration

The system uses:
POST https://places.googleapis.com/v1/places:searchText

The returned merchant types are mapped only if they appear in the curated Google-type ontology defined in:

financials/cfg/google_types_to_expenses.csv

This prevents noise from generic Google categories and ensures consistent mapping to Financials assignments.

### Automatic Rule Seeding

Rules can be bulk-created from the type-to-expense mapping:

poetry run python -m financials.scripts.update_indexes --rules

This installs assignment_rules with:
- priority = 2  
- description = google merchant type  
- assignment = mapped Expense.* category  

These rules provide broad, semantically accurate auto-assignment coverage without manual creation.

### Benefits

- Stronger, more semantic auto-assignment  
- No brittle substring matching for most merchants  
- Very low cost due to caching and controlled live lookups  
- Full transparency and safety before any paid API usage  
- Easy extensibility for new merchant categories  
- Reproducible enrichment data for consistent long-term reporting  

---

## 🧩 Conventions

- drive.py → Google Drive API access only  
- calculator.py → FinancialsCalculator handles normalization + persistence  
- db.py → manages MongoDB client connections (`db_module.db["transactions"]`)  
- main_ingest.py → CLI entry for background ingestion (`poetry run python main_ingest.py`)  
- web.py → Flask app entry point with dashboard and JSON API routes  
- templates/ → dashboard front-end (`dashboard.html`, `styles.css`, `code.js`)  
- scripts/delete_entries.py → deletes transactions by source (`--source bmo`, etc.)

---

## ⚙️ Setup

Requires Python 3.12+ and Poetry.

    poetry install
    poetry shell

---

## 🔑 Credentials

Provide Google Drive OAuth credentials under json/, ignored by Git.  
On first run, token files (e.g. token.drive.pickle) are created automatically.  
Do not commit these credentials.

---

## 🧪 Running Tests

    poetry run pytest -v

Tests cover normalization for BMO, Citi, Chase, PayPal, Capitol One, Schwab, and Checks.

---

## 🚀 Running the App

    poetry run flask --app financials/web.py run

Then open:  
http://127.0.0.1:5000/dashboard

---

## 🧲 Data Ingestion

You can import normalized data directly into MongoDB.

    poetry run python main_ingest.py

### What Happens
1. Download and normalize CSVs from Google Drive  
2. Pre-load Checks-YEAR.csv (if present)  
3. Enrich BMO transactions with check metadata  
4. Generate transaction IDs  
5. Insert new rows into MongoDB  

Schema:  
date, source, description, amount, type, assignment, [action, symbol, quantity, price]

---

## 🧮 Normalization Details

### BMO + Checks Integration
- Replace DDA CHECK rows with payee and assignment from Checks file  
- Automatically prefix assignments with Expense.*  
- Skip non-matching rows  

Example:

POSTED DATE | DESCRIPTION | AMOUNT | TRANSACTION REF | TYPE → description | assignment  
08/09/2024 | DDA CHECK | -26.34 | 9502 | Debit → St Christopher CP | Expense.Charity.Church

### Schwab
- Handles stock trades  
- Parses price, quantity, symbol  
- Produces credit/debit type automatically

### Checks
- Loaded as mapping {check_no : {payee, assignment}}  
- Not stored directly in Mongo  

---

## 🧰 Utility Scripts

### Delete Entries
    poetry run python -m financials.scripts.delete_entries --source bmo

Removes all transactions for a given source.

---

## 🌐 Dashboard and API

### Dashboard

- Multi-year filtering  
- DataTables backend  
- Column filtering  
- Shift-click multi-column sort  
- Modal UI for rules  

### Backend API

- /api/transactions  
- Optional year filtering  
- JSON output  

---

## 🗺️ Roadmap

### Visualization
- Add summary endpoint  
- Add spending charts  
- Add assignment breakdowns  

### Data Ingestion
- Multi-year support (done)  
- Schwab + Checks support (done)  
- Manual categorization (done)  
- Rule UI (done)  
- Auto-assignment engine (done)

### Assignment Engine
- Manual > automatic precedence  
- Priority-based rule selection  
- Materialized rule_matches  
- Auto + manual auditing

### DevOps
- Optional GitHub Actions

---

## 📜 License
TBD (MIT or Apache 2.0)

---

## 🤝 Contributing
Pull requests are welcome.  
This is an evolving personal project under the CohortInsights organization.
