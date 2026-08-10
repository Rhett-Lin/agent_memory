"""Shared bootstrap for the tau-bench smoke gate (Part VI-0).

Adds the vendor tau-bench repo to sys.path so we use the REAL vendor modules
(env, tools, verifier) rather than re-implementing them.
"""
from __future__ import annotations

import sys
from pathlib import Path

SMOKE_DIR = Path(__file__).resolve().parent
SURVEY_DIR = SMOKE_DIR.parent
VENDOR_REPO = SURVEY_DIR / "vendor" / "tau-bench"
OUT_DIR = Path("/work1/zixuan/outputs/agent_memory/tau_smoke")

MODEL_PATH = (
    "/work1/zixuan/cache/huggingface/hub/models--Qwen--Qwen2.5-7B-Instruct/"
    "snapshots/a09a35458c702b33eeacc393d103063234e8bc28"
)

if str(VENDOR_REPO) not in sys.path:
    sys.path.insert(0, str(VENDOR_REPO))

CURRENT_TIME_ISO = "2024-05-15T15:00:00"  # wiki.md:3 (EST)
