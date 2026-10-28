# real_data_tests/cmapss_turbofan/download_cmapss_turbofan.py
# Added 2026-10-27 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Downloads the classic C-MAPSS Turbofan Engine Degradation
Simulation dataset (FD001 only this round) into a local, gitignored
data/ folder. Addendum to Item 4 of the 26 October 2026 round (Ccode
update.txt) -- profile only, for ageing/drift tests later.

**THIS IS AN AIRCRAFT ENGINE SIMULATION, NOT A SPACECRAFT ONE.**
Say so every time this dataset is mentioned -- Jay's own instruction
flagged this as an easy mislabelling risk.

Dataset: Saxena, A., Goebel, K. (2008). "Turbofan Engine Degradation
Simulation Data Set," NASA Ames Prognostics Data Repository. Produced
by C-MAPSS (Commercial Modular Aero-Propulsion System Simulation), a
NASA engine simulator -- NOT real flight data, a physics-based
simulation of engine degradation to failure. NASA's own primary host
for this (DASHlink / c3.nasa.gov) is unreachable from this machine --
same obstacle documented in real_data_tests/adapt/'s profile. NASA
itself also states the C-MAPSS SIMULATOR tool is currently
unavailable (per Jay's own instruction); the already-generated
dataset sitting in the repository is what's wanted, not the
simulator.

Fetched instead from a reachable, publicly-listed (non-gated)
Hugging Face mirror that reproduces the same four FD00X sub-datasets:
https://huggingface.co/datasets/SoyVitou/NASA-C-MAPSS-Turbofan-Engine
-- Parquet format, not the original DASHlink .txt format, but
confirmed by loading it directly this round to have the exact
expected structure (100 units, 3 operating-condition settings, 21
sensor channels with their standard C-MAPSS names, a RUL
run-to-failure column). Licence on that mirror: "other" (unspecified)
-- the underlying NASA data is a US government work; treat the
mirror's own repackaging as unlicensed/unclear if ever cited formally,
and prefer NASA's own files if DASHlink becomes reachable again.

Only FD001 (one operating condition, one fault mode -- the simplest
of the four) is fetched here. FD002-FD004 follow the same URL
pattern if needed later.

Run from the repo root:

    python -m real_data_tests.cmapss_turbofan.download_cmapss_turbofan
"""
import os

import requests

BASE = "https://huggingface.co/datasets/SoyVitou/NASA-C-MAPSS-Turbofan-Engine/resolve/main/processed/FD001"
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
FILES = ["train.parquet", "test.parquet"]


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    for name in FILES:
        filename = f"FD001_{name}"
        path = os.path.join(DATA_DIR, filename)
        if os.path.exists(path):
            print(f"{filename}: already present ({os.path.getsize(path)} bytes), skipping.")
            continue
        print(f"Downloading {filename}...")
        r = requests.get(f"{BASE}/{name}", timeout=(30, 60))
        r.raise_for_status()
        with open(path, "wb") as f:
            f.write(r.content)
        print(f"{filename}: {os.path.getsize(path)} bytes.")


if __name__ == "__main__":
    main()
