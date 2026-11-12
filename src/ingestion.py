"""
Data Ingestion and Normalization Layer.
Loads raw files from data/, parses diverse ERP export formats (NetSuite, Sage 50, Tally Prime),
and constructs normalized internal representations with exact source row tracking.
"""

import csv
import json
from pathlib import Path
from typing import Dict, List, Any, Tuple

from src.models import TrialBalanceRow, JournalEntry, JournalLine
from src.config import DATA_DIR


class DataIngestor:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir

    def load_entities(self) -> Dict[str, Dict[str, Any]]:
        path = self.data_dir / "entities.csv"
        with open(path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return {row["entity_id"]: row for row in reader}

    def load_group_coa(self) -> Dict[str, Dict[str, Any]]:
        path = self.data_dir / "group_coa.csv"
        with open(path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return {row["account_code"]: row for row in reader}

    def load_fx_rates(self) -> List[Dict[str, Any]]:
        path = self.data_dir / "fx_rates.csv"
        with open(path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [
                {
                    "base_currency": row["base_currency"],
                    "quote_currency": row["quote_currency"],
                    "rate_type": row["rate_type"],
                    "rate": float(row["rate"]),
                    "as_of": row["as_of"],
                    "convention": row["convention"],
                    "source_line": idx + 2,
                }
                for idx, row in enumerate(reader)
            ]

    def load_prior_year_group(self) -> Dict[str, float]:
        path = self.data_dir / "prior_year_group.csv"
        with open(path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return {row["group_account"]: float(row["amount_gbp"]) for row in reader}

    def load_subledger_controls(self) -> List[Dict[str, Any]]:
        path = self.data_dir / "subledger_controls.csv"
        with open(path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [
                {
                    "entity_id": row["entity_id"],
                    "ledger": row["ledger"],
                    "currency": row["currency"],
                    "control_total": float(row["control_total"]),
                    "as_of": row["as_of"],
                    "source_line": idx + 2,
                }
                for idx, row in enumerate(reader)
            ]

    def load_uk_mapping(self) -> Tuple[Dict[str, str], List[Dict[str, Any]]]:
        """Returns mapping dictionary and raw rows with line numbers."""
        path = self.data_dir / "map_uk.csv"
        mapping = {}
        raw_rows = []
        with open(path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader):
                mapping[row["local_code"]] = row["group_code"]
                raw_rows.append({**row, "source_line": idx + 2})
        return mapping, raw_rows

    def load_in_mapping(self) -> Tuple[Dict[str, str], List[Dict[str, Any]]]:
        path = self.data_dir / "map_in.csv"
        mapping = {}
        raw_rows = []
        with open(path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader):
                mapping[row["local_code"]] = row["group_code"]
                raw_rows.append({**row, "source_line": idx + 2})
        return mapping, raw_rows

    def load_tb_us(self) -> List[TrialBalanceRow]:
        """Parse NetSuite trial balance (tb_us.csv)."""
        path = self.data_dir / "tb_us.csv"
        rows = []
        with open(path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader):
                debit = float(row["debit"])
                credit = float(row["credit"])
                rows.append(
                    TrialBalanceRow(
                        entity="US",
                        account_code=row["account_code"],
                        account_name=row["account_name"],
                        debit=debit,
                        credit=credit,
                        currency="USD",
                        source_file="tb_us.csv",
                        source_line=idx + 2,
                    )
                )
        return rows

    def load_tb_uk(self) -> List[TrialBalanceRow]:
        """Parse Sage 50 trial balance (tb_uk.csv)."""
        path = self.data_dir / "tb_uk.csv"
        rows = []
        with open(path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader):
                bal = float(row["balance"])
                debit = bal if bal > 0 else 0.0
                credit = -bal if bal < 0 else 0.0
                extra = {
                    "cost_centre": row.get("cost_centre", ""),
                    "txn_currency": row.get("txn_currency", ""),
                    "txn_amount": float(row["txn_amount"]) if row.get("txn_amount") else None,
                }
                rows.append(
                    TrialBalanceRow(
                        entity="UK",
                        account_code=row["nominal_code"],
                        account_name=row["description"],
                        debit=debit,
                        credit=credit,
                        currency="GBP",
                        source_file="tb_uk.csv",
                        source_line=idx + 2,
                        extra=extra,
                    )
                )
        return rows

    def load_tb_in(self) -> List[TrialBalanceRow]:
        """Parse Tally Prime trial balance (tb_in.csv)."""
        path = self.data_dir / "tb_in.csv"
        rows = []
        with open(path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader):
                amount = float(row["amount"])
                dr_cr = row["dr_cr"].strip()
                debit = amount if dr_cr == "Dr" else 0.0
                credit = amount if dr_cr == "Cr" else 0.0
                rows.append(
                    TrialBalanceRow(
                        entity="IN",
                        account_code=row["ledger_code"],
                        account_name=row["ledger_name"],
                        debit=debit,
                        credit=credit,
                        currency="INR",
                        source_file="tb_in.csv",
                        source_line=idx + 2,
                        extra={"period": row.get("period", "")},
                    )
                )
        return rows

    def load_in_pl_monthly(self) -> List[Dict[str, Any]]:
        path = self.data_dir / "in_pl_monthly.csv"
        rows = []
        with open(path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader):
                amount = float(row["amount"])
                dr_cr = row["dr_cr"].strip()
                rows.append(
                    {
                        "ledger_code": row["ledger_code"],
                        "ledger_name": row["ledger_name"],
                        "month": row["month"],
                        "amount": amount,
                        "dr_cr": dr_cr,
                        "debit": amount if dr_cr == "Dr" else 0.0,
                        "credit": amount if dr_cr == "Cr" else 0.0,
                        "source_line": idx + 2,
                    }
                )
        return rows

    def load_intercompany_invoices(self) -> List[Dict[str, Any]]:
        path = self.data_dir / "intercompany.csv"
        rows = []
        with open(path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader):
                rows.append(
                    {
                        "reporting_entity": row["reporting_entity"],
                        "counterparty": row["counterparty"],
                        "doc_ref": row["doc_ref"],
                        "doc_date": row["doc_date"],
                        "doc_currency": row["doc_currency"],
                        "doc_amount": float(row["doc_amount"]),
                        "booked_currency": row["booked_currency"],
                        "booked_amount": float(row["booked_amount"]),
                        "description": row["description"],
                        "source_line": idx + 2,
                    }
                )
        return rows

    def load_adjustments(self) -> List[JournalEntry]:
        path = self.data_dir / "adjustments.json"
        with open(path, mode="r", encoding="utf-8") as f:
            data = json.load(f)

        # Estimate line numbers by searching in the raw file
        with open(path, mode="r", encoding="utf-8") as f:
            raw_lines = f.readlines()

        id_to_line = {}
        for line_num, line_str in enumerate(raw_lines, start=1):
            for entry in data.get("entries", []):
                if f'"{entry["id"]}"' in line_str:
                    id_to_line[entry["id"]] = line_num

        entries = []
        for entry in data.get("entries", []):
            lines = [
                JournalLine(
                    account=line["account"],
                    debit=float(line.get("debit", 0.0)),
                    credit=float(line.get("credit", 0.0)),
                    memo=line.get("memo"),
                )
                for line in entry.get("lines", [])
            ]
            entries.append(
                JournalEntry(
                    id=entry["id"],
                    entity=entry["entity"],
                    date=entry["date"],
                    description=entry["description"],
                    prepared_by=entry["prepared_by"],
                    lines=lines,
                    source_file="adjustments.json",
                    source_line=id_to_line.get(entry["id"], 1),
                )
            )
        return entries
