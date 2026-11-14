"""
One command for the whole offline pipeline (no API key needed):

  python run_all.py

dataset -> simulated analyst shortlist -> rubric scoring -> evaluation ->
held-out tuning -> outreach drafts -> LLM comparison (only if an LLM run exists).
Every step is deterministic, so re-running reproduces the committed outputs.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STEPS = [
    ["src/generate_dataset.py"],
    ["src/make_shortlist.py"],
    ["src/scoring.py"],
    ["src/evaluate.py"],
    ["src/tune_rubric.py"],
    ["src/outreach.py", "--top", "20"],
    ["src/compare.py"],
    ["src/export_site.py"],
]


def main() -> None:
    for step in STEPS:
        print(f"\n=== python {' '.join(step)} ===", flush=True)
        result = subprocess.run([sys.executable, *step], cwd=ROOT)
        if result.returncode != 0:
            sys.exit(f"Step failed: {' '.join(step)}")
    print("\nPipeline complete. Dashboard: open site/index.html  (or: streamlit run app.py)")


if __name__ == "__main__":
    main()
