# real_data_tests/express_hall_thruster/download_express_hall_thruster.py
# Added 2026-10-27 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Downloads one representative part of the Express-A2/A3 Hall
Effect Thruster telemetry report series into a local, gitignored
data/ folder. Item 4f of the 26 October 2026 round (Ccode
update.txt) -- profile only, for ETHAN (propulsion) later.

Dataset: Sitnikova, N., Volkov, D., Maximov, I., Petrusevich, V.,
Allen, D. "Hall Effect Thruster Interactions Data From the Russian
Express-A2 and Express-A3 Satellites," NASA/CR-2003-212005, a 12-part
NASA Glenn contractor report series (NPO PM / Schafer Corporation,
under NASA contract NAS3-99151), hosted on the NASA Technical Reports
Server (ntrs.nasa.gov). Real GEO communications satellites (launched
2000), real SPT-100 Hall thruster stationkeeping telemetry. Licence:
"Unclassified-Unlimited" per the report's own distribution statement
-- a US government technical report, no further restriction stated.

Only Part 3 is fetched here (the one profiled this round -- Express-
A3 SPT-100 propulsion telemetry, June-September 2000). The other 11
parts share the same NTRS citation pattern; fetching them is left for
a later round if a real test against this data is ever planned.

Run from the repo root:

    python -m real_data_tests.express_hall_thruster.download_express_hall_thruster
"""
import os

import requests

URL = "https://ntrs.nasa.gov/api/citations/20030064312/downloads/20030064312.pdf"
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
FILENAME = "NASA-CR-2003-212005-PT3.pdf"


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
