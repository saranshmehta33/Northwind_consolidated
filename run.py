#!/usr/bin/env python3
"""
Northwind Group Consolidation Runner (FY2024).
Executes the consolidation pipeline end-to-end and writes all outputs to /output.

Usage:
    python run.py
"""

import sys
import json
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from src.consolidation import ConsolidationEngine
from src.config import BUNDLE_ID, AUTHOR_INITIALS


def main():
    print("=" * 70)
    print(f"Northwind Group Financial Consolidation Pipeline (FY2024)")
    print(f"Bundle ID: {BUNDLE_ID} | Author Initials: {AUTHOR_INITIALS}")
    print("=" * 70)

    engine = ConsolidationEngine()
    control_figures = engine.run()

    print("\n Consolidation executed successfully.")
    print(" Outputs written to /output:")
    print("   - consolidated_tb.csv")
    print("   - balance_sheet.json")
    print("   - profit_and_loss.json")
    print("   - changes_in_equity.json")
    print("   - eliminations.csv")
    print("   - issues.json")
    print(f"   - control_figures_{AUTHOR_INITIALS}.json")
    print("   - control_figures.json")

    print("\n Control Figures Summary:")
    print(f"   * Group Revenue:                 £{control_figures['group_revenue']:,.2f}")
    print(f"   * Group Profit:                  £{control_figures['group_profit']:,.2f}")
    print(f"   * Profit to Owners:              £{control_figures['profit_owners']:,.2f}")
    print(f"   * Profit to NCI:                 £{control_figures['profit_nci']:,.2f}")
    print(f"   * Closing NCI:                   £{control_figures['nci_closing']:,.2f}")
    print(f"   * Closing Goodwill:              £{control_figures['goodwill_closing']:,.2f}")
    print(f"   * Translation Reserve Movement:  £{control_figures['translation_reserve_movement']:,.2f}")
    print(f"   * Total Assets:                  £{control_figures['total_assets']:,.2f}")
    print(f"   * Total Equity:                  £{control_figures['total_equity']:,.2f}")
    print(f"   * Journals (P/R/H):              {control_figures['journals']}")
    print(f"   * SGD Bank Balance (GBP):        {control_figures['sgd_bank_gbp']['value']} (documented null)")
    print("=" * 70)


if __name__ == "__main__":
    main()
