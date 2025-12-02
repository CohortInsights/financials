# Financials

A Flask + Google Drive–based tool for downloading, normalizing, storing, enriching, and categorizing personal financial data using fast, incremental assignment logic.

---

## Repository
https://github.com/CohortInsights/financials

---

## 📂 Project Structure

    financials/
    ├── financials/
    │   ├── __init__.py                  # Package init; loads Flask app + Mongo connection
    │   ├── calculator.py                # Normalizes raw CSVs; creates transaction docs
    │   ├── drive.py                     # Google Drive ingestion utilities
    │   ├── web.py                       # Flask entrypoint (registers routes + templates)
    │   ├── db.py                        # MongoDB client and helpers
    │   │
    │   ├── routes/
    │   │   ├── __init__.py              # Route namespace
    │   │   ├── dashboard.py             # Dashboard page routes
    │   │   ├── api_transactions.py      # API for loading transactions table
    │   │   ├── rules.py                 # API for rule create/edit/delete + recomputation
    │   │   └── assign.py                # Internal hooks used by assignment engine
    │   │
    │   ├── utils/
    │   │   ├── __init__.py
    │   │   ├── services.py              # Misc service helpers
    │   │   ├── google_types.py          # Google merchant-type lookup + primary-type logic
    │   │   └── ...                      # Additional helpers
    │   │
    │   ├── templates/
    │   │   ├── dashboard.html           # Main dashboard UI
    │   │   ├── code.js                  # Global JS orchestrator
    │   │   ├── transactions.js          # DataTables logic for transaction listing
    │   │   ├── rules.js                 # UI for rule table + modal + CRUD operations
    │   │   └── styles.css               # Site styles
    │   │
    │   ├── scripts/
    │   │   ├── delete_entries.py        # Bulk delete transactions by source/year
    │   │   ├── update_indexes.py        # Ensures all MongoDB indexes exist
    │   │   ├── update_rules.py          # Incremental rule recalculation helper
    │   │   ├── rebuild_assignments.py   # Full rebuild of rule_matches + assignments
    │   │   ├── get_google_types.py      # Enrichment script for merchant-type lookups
    │   │   └── ...                      # Additional scripts
    │   │
    │   └── assign_rules.py              # Core assignment engine: rule_matches + winners
    │
    ├── main_ingest.py                   # Top-level ingestion: Drive → Calculator → DB
    ├── main.py                          # Optional entrypoint for app/maintenance tasks
    │
    ├── cfg/
    │   └── google_types_to_expenses.csv # Map Google semantic types → Expense categories
    │
    ├── tests/
    │   └── test_calculator.py           # Tests for normalization pipeline
    │
    ├── pyproject.toml                   # Poetry config and dependencies
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
- normalized_description  
- amount  
- type  
- assignment  
- google_primary_type (computed dynamically, not stored)

### assignment_rules
Definition of automatic rules.  
Fields:
- assignment  
- priority  
- source substring  
- description substring  
- min_amount  
- max_amount  

### rule_matches
Materialized table of **all rule → transaction matches**.

Used for:
- incremental rule create/edit/delete  
- scalable winner selection  

Important:
- `rule_id` is stored as a **string**, not ObjectId  

Fields:
- rule_id  
- txn_id  
- assignment  
- priority  

### transaction_assignments
Audit log of assignment application events.

### google_merchant_types
Cache of semantic merchant lookups from Google Places.

Fields:
- description_key  
- google_raw_types  
- google_filtered_types  
- google_primary_type  
- google_place_id  
- google_lookup_status  
- google_last_checked  

### google_type_mappings
Mapping of Google semantic types to internal Expense.* categories.

---

## Ingestion & Normalization Workflow

1. **calculator.py** processes raw CSVs from each provider.  
2. Extracts, normalizes, and stores transactions in Mongo.  
3. Computes and stores `normalized_description`.  
4. New descriptions become candidates for semantic enrichment.

---

## Google Merchant-Type Enrichment

Performed via `get_google_types_for_descriptions`:

1. Lookup `normalized_description` in the `google_merchant_types` cache.  
2. If missing:  
   - use cached results  
   - optionally call Google Places (`--live`)  
3. Filter raw Google types using `google_type_mappings`.  
4. Store: filtered types, raw types, place_id, lookup status.  
5. Select a single `google_primary_type`.  
6. This type is appended to the description during rule matching.

---

## Rule & Assignment Workflow (High-Level Overview)

Assignments are driven by:

- `assignment_rules`  
- `rule_matches`  
- `transactions.assignment`

### Workflow:

1. **rule_matches generation**  
   - For each transaction, evaluate all rules.  
   - Insert matches into `rule_matches`.  
   - Matching uses:  
     - source filters  
     - description + appended google_primary_type  
     - min/max amount  

2. **Winner selection**  
   - For each transaction, choose rule with **highest priority** from its matches.

3. **Assignment write-back**  
   - Update the `transactions` collection with the winning assignment.  
   - Happens on:  
     - new ingestion  
     - new rule  
     - rule edit  
     - rule delete  
     - rebuild operations  

---

## Incremental Rule Update Model

Fast-path updates avoid full rebuilds:

- **New transactions:**  
  generate rule_matches → compute winners → update assignment.

- **New rule:**  
  compute matches for that rule → compute winners for affected txns.

- **Edit rule:**  
  recompute matches → recompute winners.

- **Delete rule:**  
  remove rule_matches for that rule → recompute winners for those txns.

The system maintains correctness through materialized rule_matches and targeted recomputation.

---

## Assignment Rebuild Tools

### rebuild_assignments.py
Full slow-path rebuild of **all** rule_matches and assignments.

### update_rules.py
Recompute rule_matches for existing rules (incremental).

### update_indexes.py
Ensures all required Mongo indexes exist for performance.

### get_google_types.py
Standalone enrichment utility for merchant-type lookups.

---

## UI Event Model

The frontend listens globally for:

