# real_data_tests/bp930_battery/download_bp930_battery.py
# Added 2026-10-27 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Downloads the "Small Satellite Power Simulation" (BP930 battery)
dataset into a local, gitignored data/ folder. Item 4b of the
26 October 2026 round (Ccode update.txt) -- the OTHER dataset named
in that item. The Li-ion Battery Aging Datasets, also named in 4b,
are explicitly SKIPPED this round -- on hold per Jay's own
instruction, after hitting the same NASA DASHlink access obstacle
documented in real_data_tests/adapt/'s profile. This is a genuinely
separate dataset (small-satellite pack cycling, not individual-cell
ageing-to-failure) and is hosted on data.nasa.gov directly, not
DASHlink -- reachable, unlike that one.

Dataset: NASA Prognostics Center of Excellence (PCoE), "Small
Satellite Power Simulation" -- data from BP930 battery packs cycled
on a MACCOR test system, per a satellite loading profile. Cite:
Cameron, Z., Kulkarni, C., Guarneros, A., Goebel, K., Poll, S. "A
Battery Certification Testbed for Small Satellite Missions,"
AUTOTESTCON 2015. Publisher: PCoE (contact: Chetan Kulkarni,
chetan.s.kulkarni@nasa.gov). Licence: US government works
(https://www.usa.gov/government-works). Source:
https://data.nasa.gov/dataset/small-satellite-power-simulation

Small (~4.9 MB) -- one request, no chunking needed.

Run from the repo root:

    python -m real_data_tests.bp930_battery.download_bp930_battery
"""
import os

import requests

URL = "https://data.nasa.gov/docs/legacy/ames/16.Small_Satellite_Power_Simulation.zip"
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
FILENAME = "Small_Satellite_Power_Simulation.zip"


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, FILENAME)
    if os.path.exists(path):
        print(f"{FILENAME}: already present ({os.path.getsize(path)} bytes), skipping.")
        return
    print(f"Downloading {FILENAME}...")
    r = requests.get(URL, timeout=(30, 90))
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)
    print(f"{FILENAME}: {os.path.getsize(path)} bytes.")


if __name__ == "__main__":
    main()
