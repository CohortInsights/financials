# Financials

A Flask + Google Drive–based tool for downloading, normalizing, and analyzing financial statement data.

---

## Repository
https://github.com/CohortInsights/financials

## 📂 Project Structure

```
financials/
├── financials/
│   ├── calculator.py       # Normalizes CSVs from multiple financial sources
│   ├── drive.py            # Handles Google Drive API access only
│   ├── web.py              # Flask entry point (routes, dashboard, main program)
│   ├── db.py               # Connections and serialization of DataFrames to MongoDB
│   └── templates/          # HTML, CSS, and JS for dashboard UI
├── tests/
│   └── test_calculator.py  # Unit tests for normalization logic
├── pyproject.toml          # Poetry dependencies + config
├── README.md               # Project documentation (context capsule)
└── .gitignore              # Ignores secrets, build junk, virtualenvs
```
[__init__.py](financials%2F__init__.py)
---

## 🧩 Conventions

- **drive.py** → strictly for Google Drive API access  
- **calculator.py** → `FinancialsCalculator` class handles all data processing (normalization, analysis)  
- **web.py** → Flask app entry point, routes, dashboard integration  
- **templates/** → Dashboard frontend (`dashboard.html`, `styles.css`, `code.js`)  
- **tests/** → Unit tests, run with pytest under Poetry  
- Secrets (OAuth JSON + pickle tokens) are ignored via `.gitignore`  

---

## ⚙️ Setup

This project uses [Poetry](https://python-poetry.org/) for dependency management.

```bash
poetry install
poetry shell
```

---

## 🔑 Credentials

You must provide your own Google Drive OAuth credentials.

- Place client JSON under `json/` (ignored by Git).  
- On first run, the app generates a token file (`token.<name>.pickle`) also ignored by Git.  

⚠️ Do **not** commit these files — GitHub push protection will block it.

---

## 🧪 Running Tests

```bash
poetry run pytest
```

Tests validate CSV normalizations across sources (BMO, Citi, Chase, PayPal).  
All are mapped into a consistent schema:

- `date`  
- `description`  
- `amount`  
- `account` (from filename prefix)  
- `category` (if present)  

---

## 🚀 Running the App

```bash
<fron within root directory of project>
poetry run flask --app financials/web.py run
```

Open: <http://localhost:5000/dashboard>

---

## 📌 Current Status

- ✅ BMO, Citi, Chase, PayPal CSV normalization implemented and unit-tested  
- ⏳ Schwab (investment transactions) not yet normalized  
- ✅ GitHub repo initialized under CohortInsights org  
- ✅ `.gitignore` and README cleaned  
- ✅ Secrets removed from history  

---

## 🗺️ Roadmap

- [x] Normalize CSVs from cashflow accounts  
- [x] Create MongoDB users and DB and verify connection
- [ ] Import financials data on background thread and store in MongoDB collection
- [ ] Build dashboard visualizations (trends, balances, categories)  
- [ ] Add Schwab investment account normalization  
- [ ] Add edit/export features in the UI  
- [ ] CI/CD or GitHub Actions for automated testing  
