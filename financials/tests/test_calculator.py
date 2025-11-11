import pytest
import io
import pandas as pd
import numpy as np
from financials.calculator import FinancialsCalculator, _parse_schwab_date


# Fake GoogleDrive stub (not used in normalization tests)
class DummyDrive:
    def __init__(self):
        pass


@pytest.fixture
def calc():
    return FinancialsCalculator(DummyDrive())


def assert_schema(df: pd.DataFrame):
    """Check that normalized dataframe matches the required schema."""
    expected_cols = ["date", "source", "description", "amount", "type"]
    assert list(df.columns) == expected_cols

    assert pd.api.types.is_datetime64_any_dtype(
        pd.to_datetime(df["date"], errors="coerce")
    ) or pd.api.types.is_object_dtype(df["date"])  # date objects
    assert df["source"].dtype == object
    assert df["description"].dtype == object
    assert pd.api.types.is_numeric_dtype(df["amount"])
    assert df["type"].dtype == object


def test_bmo_normalization(calc):
    raw = pd.DataFrame({
        "POSTED DATE": ["09/02/2025", "08/29/2025"],
        "DESCRIPTION": ["Deposit", "Check"],
        "AMOUNT": [801.25, -140],
        "TYPE": ["Credit", "Debit"],
    })
    df = calc._normalize_bmo(raw, "BMO")
    assert_schema(df)
    assert df.loc[0, "amount"] == 801.25
    assert df.loc[1, "type"] == "Debit"


def test_citi_normalization(calc):
    raw = pd.DataFrame({
        "Date": ["08/31/2025", "08/31/2025"],
        "Description": ["Rodan+Fields", "Apple"],
        "Debit": [183.57, None],
        "Credit": [None, 10.54],
    })
    df = calc._normalize_citi(raw, "Citi")
    assert_schema(df)
    assert df.loc[0, "amount"] == -183.57
    assert df.loc[1, "amount"] == 10.54


def test_generic_card_normalization(calc):
    raw = pd.DataFrame({
        "Post Date": ["03/13/2025", "03/14/2025"],
        "Description": ["Caseys", "McDonalds"],
        "Amount": [2.10, 9.59],
        "Category": ["Gasoline", "Restaurants"],
    })
    df = calc._normalize_generic_card(raw, "Discover")
    assert_schema(df)
    assert "Gasoline" in df["type"].values


def test_paypal_normalization(calc):
    raw = pd.DataFrame({
        0: ["01/01/2025", "01/15/2025"],
        3: ["StubHub", "Apple Services"],
        5: ["Completed", "Pending"],
        7: [351.00, -0.99],
    })
    df = calc._normalize_paypal(raw, "PayPal")
    assert_schema(df)
    # Only "Completed" row should remain
    assert len(df) == 1
    assert df.iloc[0]["amount"] == 351.00
    assert df.iloc[0]["type"] == "Credit"


def test_normalize_schwab_basic(monkeypatch):
    """Ensure Schwab CSVs normalize cleanly and produce expected columns/types."""

    # --- Prepare sample CSV ---
    csv_data = """Date,Action,Symbol,Description,Quantity,Price,Fees & Comm,Amount
08/15/2025,MoneyLink Transfer,,Transfer to Checking,,,$0.00,-$500.00
08/18/2025 as of 08/15/2025,Bank Interest,,SCHWAB BANK INT,,,$0.00,$1.23
08/20/2025,Buy,AAPL,Apple Inc,5,175.35,$0.00,-$876.75
08/25/2025,Dividend,AAPL,Dividend Received,,,,$10.00
"""
    df_raw = pd.read_csv(io.StringIO(csv_data))

    # --- Run through normalizer directly ---
    calc = FinancialsCalculator(drive=None)
    df_norm = calc._normalize_schwab(df_raw, "Schwab")

    # --- Column validation ---
    expected_cols = [
        "date",
        "source",
        "description",
        "amount",
        "type",
        "action",
        "symbol",
        "quantity",
        "price",
    ]
    for col in expected_cols:
        assert col in df_norm.columns, f"Missing column {col}"

    # --- Basic data checks ---
    assert (df_norm["source"] == "Schwab").all()
    assert not df_norm["date"].isna().any(), "Dates should all parse correctly"
    assert df_norm["amount"].dtype.kind in "fi", "Amount should be numeric"

    # --- Specific content checks ---
    # The 'as of' date should parse as 2025-08-18
    parsed = _parse_schwab_date("08/18/2025 as of 08/15/2025")
    assert str(parsed.date()) == "2025-08-18"

    # Check classification logic
    debit_rows = df_norm[df_norm["type"] == "Debit"]
    credit_rows = df_norm[df_norm["type"] == "Credit"]
    assert len(debit_rows) > 0 and len(credit_rows) > 0

    # Trade row check
    trade = df_norm.loc[df_norm["action"] == "Buy"].iloc[0]
    assert trade["symbol"] == "AAPL"
    assert np.isclose(trade["quantity"], 5.0)
    assert np.isclose(trade["price"], 175.35)
    assert trade["amount"] < 0
