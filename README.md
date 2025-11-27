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
    │   │   └── google_types.py
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
    │   │   └── get_google_types.py
    │   │
    │   └── assign_rules.py
    │
    ├── main_ingest.py
    ├── main.py
    │
    ├── cfg/
    │   └── google_types_to_expenses.csv
    │
    ├── tests/
    │   └── test_calculator.py
    │
    ├── pyproject.toml
    ├── README.md
    ├── .env
    └── .gitignore

---

## Mongo Collections

### transactions
Normalized financial transactions.  
Fields:
- id  
- date  
- source  
- description  
- amount  
- type  
- assignment  
- google_primary_type (computed in API, not stored)  
- trade fields for Schwab (optional)

### assignment_rules
Automatic categorization rules with:
- assignment  
- priority  
- source filters  
- description substring filters  
- min_amount  
- max_amount  

### transaction_assignments
Audit log with:
- id  
- assignment  
- type = manual | auto  
- timestamp  

Manual assignments override auto-assignment.

### rule_matches
Materialized table of all rule → transaction matches.  
Used for:
- incremental rule-add  
- incremental delete/edit  
- fast-path winner selection

Fields:
- rule_id  
- txn_id  
- priority  
- assignment  

### google_merchant_types
Semantic merchant lookup cache (via Google Places API).

Fields:
- description_key  
- google_types  
- google_raw_types  
- google_primary_type  
- google_place_id  
- google_lookup_status (“ok”, “not_found”, etc.)  
- google_last_checked  

### google_type_mappings
Curated mapping of Google semantic types → Financials Expense.* categories.

Fields:
- google_type  
- expense_assignment  
- priority  

This is the ontology used by merchant-type enrichment.

---

## Google Merchant-Type Enrichment

Merchant-type enrichment resolves raw bank descriptions into semantic Google categories.

The workflow:
1. Normalize description → description_key  
2. Lookup from google_merchant_types  
3. If cached, reuse  
4. If missing and --live passed, query Google Places  
5. Filter raw types using google_type_mappings  
6. Store: filtered types, raw types, place_id, lookup status, primary type  
7. Primary type is a single best semantic label based on priority score

---

## Primary Google Type in Dashboard

The dashboard now exposes the merchant's primary Google semantic type.

- A new table column “Google Type” appears in Transactions  
- It is loaded from google_merchant_types  
- It is never stored in transactions  
- It is computed dynamically in api_transactions.py via get_primary_types_for_descriptions  

This greatly improves debugging of rule behavior.

---

## Assignment Engine Integration

The assignment engine (assign_rules.py) now incorporates merchant primary types in all paths:

- new transaction ingestion  
- incremental rule creation  
- incremental rule deletion  
- incremental rule update  
- full rebuild (slow path)  
- fast path (winner selection)

Implementation details:
- Primary type is appended to the description before rule matching  
- Matching continues to use substring logic (source, description, amount)  
- Rules may match against semantic types (e.g., “restaurant”, “grocery”)  

Helper used:
get_primary_types_for_descriptions in google_types.py

This helper returns a map:
    normalized_description → primary Google type (or empty)

---

## Enrichment Script

financials/scripts/get_google_types.py

Capabilities:
- --source  
- --year  
- --description  
- --all  
- --live (enables paid Google lookups)  
- Dry-run with full cost preview  
- Cached lookups always reused  

Example:
    poetry run python -m financials.scripts.get_google_types --year 2025 --live

---

## Setup

Requires Python 3.12+ and Poetry.

    poetry install
    poetry shell

---

## Credentials

Google Drive OAuth credentials stored under json/.  
Token files created automatically.

---

## Tests

    poetry run pytest -v

---

## Running the App

    poetry run flask --app financials/web.py run

Open:  
http://127.0.0.1:5000/dashboard

---

## Data Ingestion

    poetry run python main_ingest.py

---

## Utility Scripts

### Delete Entries
    poetry run python -m financials.scripts.delete_entries --source bmo

---

## Dashboard and API

### /api/transactions
Now returns:
- google_primary_type column  
- semantic debugging info  

---

## Roadmap

- Visualization layer  
- Assignment breakdowns  
- More semantic rules  
- Google-type based rule generator UI  

---

## License
TBD