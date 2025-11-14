from __future__ import annotations

import re
import datetime
import numpy as np
from pymongo.errors import BulkWriteError
from typing import Dict, List, Optional, Any
from functools import cached_property
from logging import Logger
from io import BytesIO
import hashlib

import pandas as pd
from pymongo.errors import DuplicateKeyError


class FinancialsCalculator:
    """Helper to browse, fetch, and normalize statement files from Google Drive."""

    def __init__(self, drive: "GoogleDrive"):
        self.drive = drive

    def refresh(self) -> None:
        """Invalidate cached data so the next access re-queries Drive."""
        self.__dict__.pop("statement_folders", None)

    @cached_property
    def statement_folders(self) -> Dict[str, Dict[str, Any]]:
        """Cached mapping of folder name → Drive folder object, built from 'Statements'."""
        statement_dir = self.drive.by_name("Statements")
        folder_list = self.drive.child_folders(statement_dir.get("id"))
        return {item.get("name"): item for item in folder_list}

    def get_folder_names(self) -> List[str]:
        names = list(self.statement_folders.keys())
        names.sort(reverse=True)
        return names

    def get_contents_by_year(self, year: str) -> Optional[List[Dict[str, Any]]]:
        item = self.statement_folders.get(year)
        if item is None:
            return None
        return self.drive.in_dir(item.get("id"))

    def get_document_bytes(self, item: Dict[str, Any]) -> bytes:
        return self.drive.download(item.get("id"))

    # ------------------------------------------------------------------
    # Cashflow CSV normalization
    # ------------------------------------------------------------------

    def load_year_data(self, year: str, logger: Logger = None) -> Optional[pd.DataFrame]:
        """Download and normalize all CSVs for a given year into one DataFrame."""
        contents = self.get_contents_by_year(year)
        if not contents:
            return None

        # --- Preload Checks mapping for this year ---
        check_map = None
        for item in contents:
            name = item.get("name", "")
            if name.lower().startswith("checks") and name.lower().endswith(".csv"):
                try:
                    raw = self.get_document_bytes(item)
                    df_checks = pd.read_csv(
                        BytesIO(raw),
                        on_bad_lines="skip",
                        encoding="utf-8-sig",
                        skip_blank_lines=True,
                    )
                    check_map = self._normalize_checks(df_checks)
                    if logger:
                        logger.info(f"Loaded {len(check_map)} check entries from {name}")
                except Exception as e:
                    if logger:
                        logger.error(f"Skipping {name}: {e}")
                break
        # -------------------------------------------------------------

        frames = []
        for item in contents:
            name = item.get("name", "")
            if not name.lower().endswith(".csv"):
                continue
            source = name.split("-")[0]
            try:
                raw = self.get_document_bytes(item)
                df = pd.read_csv(
                    BytesIO(raw),
                    on_bad_lines="skip",
                    encoding="utf-8-sig",
                    skip_blank_lines=True,
                )
                if logger:
                    logger.info(f"Loaded {len(df)} rows from {name}")

                if source.lower() == "bmo":
                    norm = self._normalize_bmo(df, source, check_map)
                else:
                    norm = self.normalize_csv(df, source)

                frames.append(norm)
            except Exception as e:
                if logger:
                    logger.error(f"Skipping {name}: {e}")

        frames = [f for f in frames if not f.empty]
        if not frames:
            return None

        return pd.concat(frames, ignore_index=True)

    def normalize_csv(self, df: pd.DataFrame, source: str) -> pd.DataFrame:
        s = source.lower()
        if s == "bmo":
            return self._normalize_bmo(df, source)
        if s == "citi":
            return self._normalize_citi(df, source)
        if s == "capitolone":
            return self._normalize_capitol_one(df, source)
        if s == "discover":
            return self._normalize_generic_card(df, source)
        if s == "paypal":
            return self._normalize_paypal(df, source)
        if s == "schwab":
            return self._normalize_schwab(df, source)
        if s == "checks":
            # Already handled upstream; skip redundant normalization
            return pd.DataFrame(columns=["date", "source", "description", "amount", "type", "assignment"])
        raise ValueError(f"No normalizer implemented for source {source}")

    # --------------------------
    # Transaction IDs + Persistence
    # --------------------------

    def add_transaction_ids(self, df: pd.DataFrame) -> pd.DataFrame:
        if "id" not in df.columns:
            df["id"] = None

        def make_id(row):
            if pd.notna(row.get("id")) and str(row["id"]).strip() != "":
                return row["id"]

            source = str(row["source"]).lower()
            date = str(row["date"]).lower()
            description = str(row["description"]).lower()
            try:
                amount = f"{float(row['amount']):.2f}"
            except Exception:
                amount = "0.00"

            content = f"{source}{date}{description}{amount}"
            content = re.sub(r"[^a-z0-9.]", "", content)
            h = hashlib.sha256(content.encode("utf-8")).hexdigest()
            return h[-16:]

        df["id"] = df.apply(make_id, axis=1)
        return df

    def save_to_collection(self, df: pd.DataFrame, collection, logger=None):
        collection.create_index("id", unique=True)

        if "date" in df.columns:
            missing_count = df["date"].isna().sum()
            if missing_count > 0 and logger:
                logger.warning(f"⚠️ Skipping {missing_count} rows with missing dates")
            df = df[df["date"].notna()].copy()
            df["date"] = df["date"].apply(
                lambda d: (
                    datetime.datetime.combine(d, datetime.time.min)
                    if isinstance(d, datetime.date) and not isinstance(d, datetime.datetime)
                    else d
                )
            )

        records = df.to_dict(orient="records")
        if not records:
            if logger:
                logger.info("No records to insert")
            return []

        # transaction IDs appear in the df as df["id"]
        df_ids = [rec["id"] for rec in records]

        try:
            result = collection.insert_many(records, ordered=False)
            inserted_count = len(result.inserted_ids)
            inserted_ids = df_ids[:inserted_count]

            if logger:
                logger.info(f"✅ Inserted {inserted_count} new docs, 0 duplicates")

            return inserted_ids

        except BulkWriteError as bwe:
            inserted_count = bwe.details.get("nInserted", 0)
            inserted_ids = df_ids[:inserted_count]

            dup_count = len(bwe.details.get("writeErrors", []))
            if logger:
                logger.warning(f"⚠️ Skipped {dup_count} duplicates, inserted {inserted_count} new docs")

            return inserted_ids

    # --------------------------
    # Normalizers (new + updated)
    # --------------------------

    def _normalize_checks(self, df: pd.DataFrame) -> dict[int, dict[str, str]]:
        """
        Convert Checks CSV into mapping {check_number: {'payee': ..., 'assignment': ...}}.
        Prepends 'Expense.' to all assignments.
        """
        required = {"Check", "Pay To", "Assignment"}
        if not required.issubset(df.columns):
            raise ValueError(f"Checks CSV must include {required}")

        mapping = {}
        for _, row in df.iterrows():
            try:
                check_no = int(str(row["Check"]).strip())
                payee = str(row["Pay To"]).strip()
                assignment = str(row["Assignment"]).strip()
                if assignment and not assignment.lower().startswith("expense."):
                    assignment = f"Expense.{assignment}"
                if check_no and payee:
                    mapping[check_no] = {"payee": payee, "assignment": assignment}
            except ValueError:
                continue
        return mapping

    def _normalize_bmo(
        self,
        df: pd.DataFrame,
        source: str,
        check_map: dict[int, dict[str, str]] | None = None
    ) -> pd.DataFrame:
        """Normalize BMO CSV exports, optionally enriching with check payee names and assignments."""
        out = pd.DataFrame()
        date_col = "POSTED DATE" if "POSTED DATE" in df.columns else df.columns[0]
        out["date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date
        out["source"] = source
        out["description"] = (
            df["DESCRIPTION"]
            if "DESCRIPTION" in df.columns
            else df.loc[:, df.columns[1]].astype(str)
        )
        out["amount"] = pd.to_numeric(
            df["AMOUNT"] if "AMOUNT" in df.columns else df.loc[:, df.columns[2]],
            errors="coerce"
        )
        out["type"] = df["TYPE"] if "TYPE" in df.columns else ""
        out["assignment"] = ""  # always include assignment field

        # --- New enrichment using check reference ---
        if check_map:
            ref_candidates = []
            for col in ["TRANSACTION REFERENCE NUMBER", "FI TRANSACTION REFERENCE"]:
                if col in df.columns:
                    ref_candidates = df[col]
                    break

            if len(ref_candidates) > 0:
                ref_nums = pd.to_numeric(ref_candidates, errors="coerce").fillna(0).astype(int)
                enriched_desc = []
                enriched_assign = []

                for ref, desc in zip(ref_nums, out["description"]):
                    if ref in check_map:
                        enriched_desc.append(check_map[ref]["payee"])
                        enriched_assign.append(check_map[ref]["assignment"])
                    else:
                        enriched_desc.append(desc)
                        enriched_assign.append("")
                out["description"] = enriched_desc
                out["assignment"] = enriched_assign
        # ------------------------------------------------

        return out[
            ["date", "source", "description", "amount", "type", "assignment"]
        ]

    # --------------------------
    # Other Normalizers (unchanged)
    # --------------------------

    def _normalize_schwab(self, raw: pd.DataFrame, source: str) -> pd.DataFrame:
        df = raw.copy()
        if "Date" not in df.columns:
            raise ValueError("Schwab CSV missing 'Date' column.")
        df["date"] = df["Date"].apply(_parse_schwab_date)
        df["description"] = df.get("Description", "").astype(str).str.strip()
        if "Amount" not in df.columns:
            raise ValueError("Schwab CSV missing 'Amount' column.")
        df["amount"] = df["Amount"].apply(_parse_numeric)
        df["action"] = df.get("Action", "").astype(str).str.strip()
        df["symbol"] = df.get("Symbol", "").astype(str).str.strip()
        df["quantity"] = df.get("Quantity", np.nan).apply(_parse_numeric)
        df["price"] = df.get("Price", np.nan).apply(_parse_numeric)

        def _classify(amount):
            if pd.isna(amount):
                return ""
            if amount > 0:
                return "Credit"
            if amount < 0:
                return "Debit"
            return ""

        df["type"] = df["amount"].apply(_classify)
        df["source"] = source

        normalized = df[
            ["date", "source", "description", "amount", "type", "action", "symbol", "quantity", "price"]
        ].dropna(subset=["date"])
        return normalized

    def _normalize_capitol_one(self, df: pd.DataFrame, source: str) -> pd.DataFrame:
        out = pd.DataFrame()
        date_col = "Posted Date" if "Posted Date" in df.columns else df.columns[1]
        out["date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date
        out["source"] = source
        out["description"] = df["Description"].astype(str)
        debit = pd.to_numeric(df["Debit"], errors="coerce").fillna(0)
        credit = pd.to_numeric(df["Credit"], errors="coerce").fillna(0)
        out["amount"] = credit - debit
        out["type"] = ["Credit" if c > 0 else "Debit" if d > 0 else "" for c, d in zip(credit, debit)]
        return out[["date", "source", "description", "amount", "type"]]

    def _normalize_citi(self, df: pd.DataFrame, source: str) -> pd.DataFrame:
        out = pd.DataFrame()
        date_col = "Date" if "Date" in df.columns else df.columns[0]
        out["date"] = pd.to_datetime(df[date_col], format="%m/%d/%Y", errors="coerce").dt.date
        out["source"] = source
        desc_col = "Description" if "Description" in df.columns else df.columns[1]
        out["description"] = df[desc_col].astype(str)
        debit = pd.to_numeric(df["Debit"], errors="coerce").fillna(0) if "Debit" in df.columns else pd.Series(0, index=df.index)
        credit = pd.to_numeric(df["Credit"], errors="coerce").fillna(0) if "Credit" in df.columns else pd.Series(0, index=df.index)
        out["amount"] = credit - debit
        out["type"] = ["Credit" if c > 0 else "Debit" if d > 0 else "" for c, d in zip(credit, debit)]
        return out[["date", "source", "description", "amount", "type"]]

    def _normalize_generic_card(self, df: pd.DataFrame, source: str) -> pd.DataFrame:
        out = pd.DataFrame()
        date_col = "Post Date" if "Post Date" in df.columns else df.columns[0]
        out["date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date
        out["source"] = source
        desc_col = "Description" if "Description" in df.columns else df.columns[1]
        out["description"] = df[desc_col].astype(str)
        amt_col = "Amount" if "Amount" in df.columns else df.columns[2]
        out["amount"] = pd.to_numeric(df[amt_col], errors="coerce")
        out["type"] = df["Category"] if "Category" in df.columns else ""
        return out[["date", "source", "description", "amount", "type"]]

    def _normalize_paypal(self, df: pd.DataFrame, source: str) -> pd.DataFrame:
        out = pd.DataFrame()
        if "Date" in df.columns:
            out["date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
        elif 0 in df.columns:
            out["date"] = pd.to_datetime(df.loc[:, 0], errors="coerce").dt.date
        else:
            raise ValueError("No date column found in PayPal CSV")

        if "Name" in df.columns:
            out["description"] = df["Name"].astype(str)
        elif "Description" in df.columns:
            out["description"] = df["Description"].astype(str)
        elif 3 in df.columns:
            out["description"] = df.loc[:, 3].astype(str)
        else:
            raise ValueError("No description column found in PayPal CSV")

        if "Status" in df.columns:
            status = df["Status"].astype(str)
        elif 5 in df.columns:
            status = df.loc[:, 5].astype(str)
        else:
            raise ValueError("No status column found in PayPal CSV")

        if "Gross" in df.columns:
            out["amount"] = pd.to_numeric(df["Gross"], errors="coerce")
        elif "Amount" in df.columns:
            out["amount"] = pd.to_numeric(df["Amount"], errors="coerce")
        elif 7 in df.columns:
            out["amount"] = pd.to_numeric(df.loc[:, 7], errors="coerce")
        else:
            raise ValueError("No amount column found in PayPal CSV")

        out["source"] = source
        out["type"] = out["amount"].apply(lambda x: "Credit" if x > 0 else "Debit")
        out = out.loc[status.str.lower() == "completed"]
        return out[["date", "source", "description", "amount", "type"]]


def _parse_schwab_date(value: str) -> pd.Timestamp:
    if pd.isna(value):
        return pd.NaT
    text = str(value).strip()
    if " as of " in text:
        text = text.split(" as of ")[0].strip()
    return pd.to_datetime(text, errors="coerce", format="%m/%d/%Y")


def _parse_numeric(value):
    if pd.isna(value):
        return np.nan
    text = str(value).strip()
    if not text:
        return np.nan
    text = text.replace("$", "").replace(",", "")
    try:
        return float(text)
    except ValueError:
        return np.nan
