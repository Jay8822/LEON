# real_data_tests/mars_express_power/download_mars_express_power.py
# Added 2026-10-27 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Downloads the ESA Mars Express Power Challenge dataset into a
local, gitignored data/ folder. Item 4c of the 26 October 2026 round
(Ccode update.txt).

Dataset: "Mars Express Power Challenge," ESA Advanced Mission
Concepts team, hosted on the Kelvins competition platform
(https://kelvins.esa.int/mars-express-power-challenge/, now archived
at https://live.kelvins.esa.int/mars-express-power-challenge/data/),
mirrored on Zenodo: https://zenodo.org/records/6327379 (one file,
mars-express-power-3years.zip, 153,724,228 bytes, MD5
6ec708bfb25a124d8333f3e9f21a05a3 -- confirmed against Zenodo's own
published checksum after download, same discipline as
real_data_tests/esa_adb/'s download script). Licence: not explicitly
stated on the Kelvins page; this is a published ESA research
competition dataset, used here for research/educational profiling
only, same treatment as every other dataset in this project where no
explicit licence text is given.

Small enough (~154 MB compressed) to fetch in one request -- no
chunked/resumable logic needed, unlike ESA-ADB's multi-GB files.

Run from the repo root:

    python -m real_data_tests.mars_express_power.download_mars_express_power
"""
import hashlib
import os

import requests

ZENODO_URL = "https://zenodo.org/records/6327379/files/mars-express-power-3years.zip?download=1"
EXPECTED_MD5 = "6ec708bfb25a124d8333f3e9f21a05a3"
EXPECTED_SIZE = 153724228

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
FILENAME = "mars-express-power-3years.zip"


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, FILENAME)
    if os.path.exists(path) and os.path.getsize(path) == EXPECTED_SIZE:
        print(f"{FILENAME}: already present at the expected size, skipping (resume).")
    else:
        print(f"Downloading {FILENAME} ({EXPECTED_SIZE} bytes)...")
        with requests.get(ZENODO_URL, stream=True, timeout=(30, 120)) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(8 * 1024 * 1024):
                    f.write(chunk)

    actual_md5 = hashlib.md5(open(path, "rb").read()).hexdigest()
    if actual_md5 != EXPECTED_MD5:
        raise SystemExit(f"MD5 mismatch: expected {EXPECTED_MD5}, got {actual_md5} -- do not trust this file.")
    print(f"{FILENAME}: {os.path.getsize(path)} bytes, MD5 verified against Zenodo's published checksum.")


if __name__ == "__main__":
    main()
