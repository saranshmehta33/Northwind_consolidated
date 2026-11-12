"""
Configuration and constants for Northwind Group Consolidation (FY2024).
Bundle ID: NWG-D0BC
"""

from pathlib import Path

# Repository root directory
ROOT_DIR = Path(__file__).resolve().parent.parent

# Data directory
DATA_DIR = ROOT_DIR / "data"

# Output directory
OUTPUT_DIR = ROOT_DIR / "output"

# Transcripts directory
TRANSCRIPTS_DIR = ROOT_DIR / "transcripts"

# Bundle and Reporting Constants
BUNDLE_ID = "NWG-D0BC"
PRESENTATION_CURRENCY = "GBP"
REPORTING_YEAR = 2024
REPORTING_PERIOD_END = "2024-12-31"

# Author Initials for Control Figures
AUTHOR_INITIALS = "sm"
