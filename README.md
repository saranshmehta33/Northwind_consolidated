# Northwind Group Financial Consolidation Engine (FY2024)

**Plainflow AI Agentic Engineer Take-Home Assignment (v2)**  
**Bundle ID:** `NWG-D0BC`  
**Author:** Saransh Mehta (`sm`) | **Email:** `saranshmehta3333@gmail.com`  
**Presentation Currency:** GBP (£) | **Period Ended:** 31 December 2024

---

## 1. Quick Start (Single Command Run)

This prototype runs with zero external pip dependencies using Python standard library (Python 3.10+):

```bash
# Clone the repository
git clone https://github.com/saranshmehta33/Northwind_consolidated.git
cd Northwind_TakeHome_v2

# Run end-to-end consolidation (single command)
python run.py

# Run the automated verification test suite
python -m unittest discover tests
```

Every figure is produced dynamically by code and written to `/output`. No numbers are hand-edited.

---

## 2. Deliverables Checklist

All 6 required submission items are included in this repository:

1. **Architecture Document:** [`ARCHITECTURE.md`](ARCHITECTURE.md) (System topology, deterministic vs LLM boundaries, failure modes, validation/self-correction loops, auditor lineage; max 6 pages).
2. **Working Prototype & Git History:** Full granular commit history preserved (no squashing) in this Git repository.
3. **Design Decisions:** [`DECISIONS.md`](DECISIONS.md) (6 key architectural decisions detailing options considered, chosen approach, trade-offs, and AI suggestions evaluated/rejected).
4. **Validation Report:** [`VALIDATION.md`](VALIDATION.md) (Mathematical proofs, independent reconciliations, and 3 specific AI bugs caught with fixing commits).
5. **AI Transcripts:** Located in [`transcripts/`](transcripts/) (complete unedited agent session transcript).
6. **One-Page Reflection:** [`REFLECTION.md`](REFLECTION.md) (3-month product roadmap, scale breaking points, and domain complexities).

---

## 3. Required Outputs in `/output`

Running `python run.py` generates the following files in `output/`:

| Output File | Description |
| :--- | :--- |
| [`output/consolidated_tb.csv`](output/consolidated_tb.csv) | Consolidated trial balance in GBP with row-level source provenance (`US`, `UK`, `IN`, `ELIM`). |
| [`output/balance_sheet.json`](output/balance_sheet.json) | Group balance sheet in GBP, including non-controlling interest and translation reserve. |
| [`output/profit_and_loss.json`](output/profit_and_loss.json) | Group profit and loss statement in GBP, showing profit attributable to owners and NCI. |
| [`output/changes_in_equity.json`](output/changes_in_equity.json) | Consolidated statement of changes in equity walk from 2023-12-31 to 2024-12-31. |
| [`output/eliminations.csv`](output/eliminations.csv) | Every elimination entry with category, debit/credit amounts, description, and source rows. |
| [`output/issues.json`](output/issues.json) | Complete audit log of every problem found (file, line, amount affected, action: blocked/assumed/flagged). |
| [`output/control_figures_sm.json`](output/control_figures_sm.json) | All 12 control figures specified in the assignment appendix. |
| [`output/control_figures.json`](output/control_figures.json) | Standard control figures duplicate for automated evaluators. |

---

## 4. Summary of Control Figures

All figures in GBP, rounded to 2 decimal places at reporting presentation per Group Policy 7:

```json
{
  "group_revenue": 28301607.81,
  "group_profit": 2832780.96,
  "profit_owners": 2771922.90,
  "profit_nci": 60858.06,
  "nci_closing": 1325107.53,
  "goodwill_closing": 1375815.07,
  "translation_reserve_movement": 43706.70,
  "total_assets": 28575272.93,
  "total_equity": 18407835.06,
  "intercompany_difference": {
    "total_usd": 10160.0,
    "timing_in_transit_gbp": 8108.54,
    "fx_retranslation_gbp": 11957.88,
    "pl_elimination_fx_difference_gbp": 1966.21
  },
  "sgd_bank_gbp": {
    "value": null,
    "reason": "Missing closing exchange rate for GBP/SGD at 31 Dec 2024 in fx_rates.csv. Per Group Policy 3, foreign currency monetary bank balances must be retranslated at closing rate, but neither a direct GBP/SGD closing rate nor synthetic cross-rate is provided in inputs."
  },
  "journals": {
    "posted": 16,
    "rejected": 2,
    "held_for_review": 2
  }
}
```

---

## 5. Deliberate Traps Neutralized

1. **Adversarial Prompt Injection in JE-006:** The line memo instructed automated tools to skip balance checks and suppress issue reporting. The pipeline enforced an airgapped security filter, isolated the text as inert data, and blocked the entry because debits ($51,200) did not equal credits ($50,000).
2. **Missing SGD Closing Rate:** Rather than hallucinating or guessing a market closing rate for 40,000 SGD, the system returned an honest `null` per Section 4 instructions.
3. **Mid-Year India Acquisition:** Prevented revenue overstatement by carving out 3 months of pre-acquisition earnings (INR 18M) using `in_pl_monthly.csv`, consolidating only H2 post-acquisition results.
4. **UK Deferred Income Mapping Trap:** Detected nominal code 2310 ("Deferred income", a liability credit) mapped to 4100 ("Revenue"), automatically remapped to 2300, and logged a £180,000 assumed correction.
5. **Sage 50 Multi-Cost-Centre Nominal Codes:** Prevented silent line dropping on duplicate nominal codes (7000 Gross Wages for CC-OPS and CC-SALES, £812,500 each) via accumulating dictionary aggregation.
6. **Intercompany Goods-in-Transit:** Identified missing invoice `INV-US-2291` ($10,160), recorded it at closing rate (£8,108.54) in UK books, retranslated monetary liabilities (£11,957.88 FX loss), and eliminated intercompany positions to exact £0.00.
