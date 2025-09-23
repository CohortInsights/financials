import pandas as pd
import pytest
from financials.calculator import FinancialsCalculator


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
