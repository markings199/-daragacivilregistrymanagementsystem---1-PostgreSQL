"""Compatibility launcher. Prefer: python scripts/seed_sample_documents.py"""
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().parent / "scripts" / "seed_sample_documents.py"), run_name="__main__")
