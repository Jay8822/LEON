# real_data_tests/rosetta_reaction_wheel/download_rosetta_reaction_wheel.py
# Added 2026-10-27 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Downloads a small SAMPLE of the Rosetta Reaction Wheel Engineering
Data (not the full ~1.6 GB bundle -- profile only, for LUNAE later,
per Item 4d of the 26 October 2026 round, Ccode update.txt). One
quarter's label+table pair for one wheel's direction parameter and
one wheel's speed parameter -- enough to confirm format and content,
not a full dataset fetch.

Dataset: O'Rourke, L., Heather, D., Andres, R. "Rosetta Spacecraft
Reaction Wheel Engineering Data," RO-X-HK-3-RWL-V1.0, ESA Planetary
Science Archive and NASA Planetary Data System, 2020.
https://pds-smallbodies.astro.umd.edu/holdings/ro-x-hk-3-rwl-v1.0/
Licence: US government works (per its data.gov catalog listing).

PDS3 format: one .lbl (label, plain text metadata) + .tab (ASCII
table: "TIME OF MEASUREMENT", "VALUE") pair per wheel per parameter
per calendar quarter. Five parameter types (rwl_est_frict_torque,
rwl_frict_coeff, rwl_meas_ang_mom, rwl_wheel_direction,
rwl_wheel_speed), four wheels each, data/<parameter>/<year>_q<N>/.

The full bundle is fetchable later from the same base URL if a real
test against this data is ever planned -- see aareadme.txt at the
dataset's own root for the complete file listing. Not attempted here.

Run from the repo root:

    python -m real_data_tests.rosetta_reaction_wheel.download_rosetta_reaction_wheel
"""
import os

import requests

BASE = "https://pds-smallbodies.astro.umd.edu/holdings/ro-x-hk-3-rwl-v1.0/data"
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# (parameter folder, wheel product id, quarter)
SAMPLES = [
    ("rwl_wheel_direction", "ros_hk_naad6011_2016_q1", "2016_q1"),
    ("rwl_wheel_speed", "ros_hk_nacg0014_2016_q1", "2016_q1"),
]


def _fetch(url, path):
    r = requests.get(url, timeout=(30, 90))
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    for param, product_id, quarter in SAMPLES:
        for ext in ("lbl", "tab"):
            filename = f"{product_id}.{ext}"
            path = os.path.join(DATA_DIR, filename)
            if os.path.exists(path):
                print(f"{filename}: already present, skipping.")
                continue
            url = f"{BASE}/{param}/{quarter}/{product_id.upper()}.{ext.upper()}"
            # PDS file servers are case-sensitive on the server side but
            # the holdings site accepts lower-case paths too -- try the
            # lower-case form first (what was confirmed reachable this
            # round), fall back to upper-case if that 404s.
            try:
                _fetch(f"{BASE}/{param}/{quarter}/{filename}", path)
            except requests.HTTPError:
                _fetch(url, path)
            print(f"{filename}: {os.path.getsize(path)} bytes.")


if __name__ == "__main__":
    main()
