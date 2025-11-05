from __future__ import annotations

import re
import datetime
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
        """
        Initialize with an authenticated GoogleDrive instance.

        Parameters
        ----------
        drive : GoogleDrive
            Drive client used for all queries and downloads.
        """
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
        """List the names of statement folders (reverse-sorted)."""
        names = list(self.statement_folders.keys())
        names.sort(reverse=True)
        return names

    def get_contents_by_year(self, year: str) -> Optional[List[Dict[str, Any]]]:
        """Get the files within a specific year folder."""
        item = self.statement_folders.get(year)
        if item is None:
            return None
        return self.drive.in_dir(item.get("id"))

    def get_document_bytes(self, item: Dict[str, Any]) -> bytes:
        """Download a Drive file into memory."""
        return self.drive.download(item.get("id"))

    # ------------------------------------------------------------------
    # Cashflow CSV normalization
    # ------------------------------------------------------------------

    def load_year_data(self, year: str, logger : Logger  = None) -> Optional[pd.DataFrame]:
        """Download and normalize all CSVs for a given year into one DataFrame."""
        contents = self.get_contents_by_year(year)
        if not contents:
            return None

        frames = []
        for item in contents:
            name = item.get("name", "")
            if not name.lower().endswith(".csv"):
                continue
            source = name.split("-")[0]  # prefix before -YEAR
            try:
                raw = self.get_document_bytes(item)
                df = pd.read_csv(BytesIO(raw))
                if logger:
                    logger.info(f"Loaded {len(df)} rows from {name}")
                norm = self.normalize_csv(df, source)
                frames.append(norm)
            except Exception as e:
                logger.error(f"Skipping {name}: {e}")

        if not frames:
            return None

        return pd.concat(frames, ignore_index=True)

    def normalize_csv(self, df: pd.DataFrame, source: str) -> pd.DataFrame:
        """Normalize one bank/account CSV to the common schema."""
        s = source.lower()
        if s == "bmo":
            return self._normalize_bmo(df, source)
        if s == "citi":
            return self._normalize_citi(df, source)
        if s in ["discover", "capitalone"]:
            return self._normalize_generic_card(df, source)
        if s == "paypal":
            return self._normalize_paypal(df, source)

        raise ValueError(f"No normalizer implemented for source {source}")

    # --------------------------
    # Transaction IDs + Persistence
    # --------------------------

    def add_transaction_ids(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add a stable transaction ID to each row if not already present.

        ID = last 16 hex digits of sha256(source|date|description|amount)
             with all characters normalized to lowercase and only [a-z0-9] kept.
        """
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

            # Keep only letters and digits
            content = re.sub(r"[^a-z0-9.]", "", content)

            h = hashlib.sha256(content.encode("utf-8")).hexdigest()
            return h[-16:]

        df["id"] = df.apply(make_id, axis=1)
        return df

    def save_to_collection(self, df: pd.DataFrame, collection, logger=None):
        """
        Ensure unique index on 'id', then insert rows (skip duplicates).
        Converts datetime.date -> datetime.datetime so Mongo can store it.

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame of normalized transactions
        collection : pymongo.collection.Collection
            MongoDB collection
        logger : logging.Logger or None
            Logger to use for messages. If None, no logging is performed.
        """
        # Ensure unique index
        collection.create_index("id", unique=True)

        # Fix date serialization: convert datetime.date → datetime.datetime
        if "date" in df.columns:
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
            return 0

        try:
            result = collection.insert_many(records, ordered=False)
            inserted = len(result.inserted_ids)
            if logger:
                logger.info(f"✅ Inserted {inserted} new docs, 0 duplicates")
            return inserted
        except BulkWriteError as bwe:
            inserted = bwe.details.get("nInserted", 0)
            dup_count = len(bwe.details.get("writeErrors", []))
            if logger:
                logger.warning(f"⚠️ Skipped {dup_count} duplicates, inserted {inserted} new docs")
            return inserted

    # --------------------------
    # Normalizers (unchanged)
    # --------------------------

    def _normalize_bmo(self, df: pd.DataFrame, source: str) -> pd.DataFrame:
        out = pd.DataFrame()
        date_col = "POSTED DATE" if "POSTED DATE" in df.columns else df.columns[0]
        out["date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date
        out["source"] = source
        out["description"] = df["DESCRIPTION"] if "DESCRIPTION" in df.columns else df.loc[:, df.columns[1]].astype(str)
        out["amount"] = pd.to_numeric(df["AMOUNT"] if "AMOUNT" in df.columns else df.loc[:, df.columns[2]], errors="coerce")
        out["type"] = df["TYPE"] if "TYPE" in df.columns else ""
        return out[["date", "source", "description", "amount", "type"]]

    def _normalize_citi(self, df: pd.DataFrame, source: str) -> pd.DataFrame:
        out = pd.DataFrame()
        date_col = "Date" if "Date" in df.columns else df.columns[0]
        out["date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date
        out["source"] = source
        desc_col = "Description" if "Description" in df.columns else df.columns[1]
        out["description"] = df[desc_col].astype(str)
        debit_col = "Debit" if "Debit" in df.columns else None
        credit_col = "Credit" if "Credit" in df.columns else None
        debit = pd.to_numeric(df[debit_col], errors="coerce").fillna(0) if debit_col else 0
        credit = pd.to_numeric(df[credit_col], errors="coerce").fillna(0) if credit_col else 0
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
