"""Run the full Session 1 pipeline in the required order."""

from __future__ import annotations

import subprocess
import sys


COMMANDS = [
    [sys.executable, "-m", "pytest", "-q"],
    [sys.executable, "ingestion.py", "fetch-raw", "--config", "config/turkey_sources.json", "--raw-dir", "data/raw"],
    [sys.executable, "ingestion.py", "build-processed", "--raw-dir", "data/raw", "--processed-dir", "data/processed", "--team-names", "data/team_names.csv"],
    [sys.executable, "validation.py", "--raw-dir", "data/raw", "--processed-dir", "data/processed", "--out", "out/validation_report.json"],
    [sys.executable, "describe_data.py", "--raw-dir", "data/raw", "--processed-dir", "data/processed", "--out-dir", "out"],
]


def main() -> None:
    for command in COMMANDS:
        subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
