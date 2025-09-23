# Financials

A Flask + Google Drive–based tool for downloading, normalizing, and analyzing my personal financial statement data.

## 📂 Project Structure

```
financials/
├── financials/
│   ├── calculator.py       # Normalizes CSVs from multiple financial sources
│   ├── drive.py            # Handles Google Drive API access
│   ├── web.py              # Flask entry point (routes, dashboard)
│   └── templates/          # HTML/CSS/JS for dashboard
├── tests/
│   └── test_calculator.py  # Unit tests for normalization logic
├── pyproject.toml          # Poetry dependencies + config
├── README.md               # Project documentation
└── .gitignore              # Ignores secrets and junk
```

## ⚙️ Setup

This project uses [Poetry](https://python-poetry.org/) for dependency management.

```bash
poetry install
poetry shell
```

## 🔑 Credentials

You must provide your own Google Drive OAuth credentials.

- Place your client JSON file under `json/` (ignored by Git).  
- On first run, the app will generate a token file (`token.<name>.pickle`) also ignored by Git.  

⚠️ Do **not** commit these files — they are secrets.

## 🧪 Running Tests

```bash
poetry run pytest
```

## 🚀 Running the App

```bash
poetry run flask --app financials/web.py run
```

Then open: <http://localhost:5000/dashboard>

## 📝 Notes

- All financial sources (BMO, Citi, CapitalOne/Discover, PayPal, etc.) are normalized into a consistent schema:

  - `date`
  - `source` (derived from filename prefix)
  - `description`
  - `amount`
  - `type` (e.g., category, “Credit/Debit”, etc.)

- Use `FinancialsCalculator` for programmatic access to normalized data.

## 📌 Roadmap

- [x] Normalize CSVs from cashflow accounts  
- [ ] Add Schwab investment account normalization  
- [ ] Build dashboard visualizations (trends, balances, categories)  
- [ ] Add edit/export features in the UI
