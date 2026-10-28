# real_data_tests/adapt/download_adapt.py
# Added 2026-10-27 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Downloads what's reachable of the ADAPT (Advanced Diagnostics and
Prognostics Testbed) dataset into a local, gitignored data/ folder,
per Item 4a of the 26 October 2026 round (Ccode update.txt).

Dataset: Poll, S., Patterson-Hine, A., Camisa, J., Garcia, D., Hall,
D., Lee, C., Mengshoel, O.J., Neukom, C., Nishikawa, D., Ossenfort,
J., Sweet, A., Yentus, S., Roychoudhury, I., Daigle, M., Biswas, G.,
Koutsoukos, X. "Advanced Diagnostics and Prognostics Testbed" (DX'07,
2007). Companion benchmarking paper: Kurtoglu, T., Narasimhan, S.,
Poll, S., Garcia, D., Wright, S. "Benchmarking Diagnostic Algorithms
on an Electrical Power System Testbed" (PHM Society Annual
Conference, 2009), NASA Technical Reports Server doc ID 20110011109.
Hosted by NASA Ames Research Center (DASHlink / data.nasa.gov).
Licence: listed public on data.gov; the catalog page itself states no
explicit licence text is provided -- treat as public-domain US
government work (standard for NASA technical data) but note the
absence of an explicit licence statement in any write-up.

HONEST STATUS (checked directly, not assumed -- same obstacle already
documented for the NASA Li-ion Battery Aging dataset this session):
every file on NASA's DASHlink host (c3.nasa.gov / c3.ndc.nasa.gov)
timed out on repeated attempts from this machine, across several
different paths on that host, not just one broken link. The primary
ADAPT data files below (dataset_text.zip, dataset_matlab.zip, the
diagrams and experiment log) could NOT be downloaded this round.
This script still lists and attempts them -- cheap to retry later,
and documents exactly what was tried -- but do not expect it to
succeed until that host is reachable again.

What COULD be reached and downloaded (a different NASA host,
ntrs.nasa.gov, which responds normally): the companion benchmarking
paper's PDF, already fetched and included below. It is NOT the
dataset itself -- it is the documentation that this project's ADAPT
profile (real_data_tests/adapt/PROFILE.md) is based on.

Run from the repo root:

    python -m real_data_tests.adapt.download_adapt
"""

import hashlib
import os
import time

import requests

MAX_ATTEMPTS = 5
RETRY_BACKOFF_SECONDS = 10
REQUEST_TIMEOUT = (15, 25)  # (connect, read) -- short, since this host has been consistently unreachable
CHUNK_SIZE = 8 * 1024 * 1024

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# (filename, URL, expected_md5_or_None, approx size, note)
# The five primary files live on NASA DASHlink -- unreachable from
# this machine as of 2026-10-27 (see module docstring). No published
# MD5s found for these (unlike ESA-ADB's Zenodo record), so integrity
# isn't checked here -- only presence/size once a download succeeds.
FILES = [
    ("BNandADAPTv18.pdf", "https://c3.nasa.gov/dashlink/static/media/dataset/BNandADAPTv18.pdf",
     None, "unknown (small, a PDF)", "ADAPT system documentation"),
    ("AdaptHTMLdiagrams.zip", "https://c3.nasa.gov/dashlink/static/media/dataset/AdaptHTMLdiagrams.zip",
     None, "unknown", "EPS schematic diagrams, HTML"),
    ("Experiment_Log.xls", "https://c3.nasa.gov/dashlink/static/media/dataset/Experiment_Log.xls",
     None, "unknown", "per-run experiment log"),
    ("dataset_matlab.zip", "https://c3.nasa.gov/dashlink/static/media/dataset/dataset_matlab.zip",
     None, "unknown", "sensor/command data, MATLAB environment format"),
    ("dataset_text.zip", "https://c3.nasa.gov/dashlink/static/media/dataset/dataset_text.zip",
     None, "unknown", "sensor/command data, tab-delimited text, 2 Hz, 128 sensors"),
]

# Reachable (ntrs.nasa.gov, not DASHlink) -- the benchmarking paper
# itself, already fetched once this round via curl; re-fetched here
# too so this script alone can reproduce the whole profile's sources.
COMPANION_PAPER = (
    "kurtoglu2009_benchmarking.pdf",
    "https://ntrs.nasa.gov/api/citations/20110011109/downloads/20110011109.pdf",
    "7823525",  # bytes, confirmed via Content-Length this round
)


def _download_resumable(filename, url, expected_md5):
    path = os.path.join(DATA_DIR, filename)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        existing = os.path.getsize(path) if os.path.exists(path) else 0
        headers = {"Range": f"bytes={existing}-"} if existing else {}
        try:
            with requests.get(url, headers=headers, stream=True, timeout=REQUEST_TIMEOUT) as r:
                if r.status_code not in (200, 206):
                    print(f"  {filename}: HTTP {r.status_code}, giving up this attempt")
                    raise requests.RequestException(f"HTTP {r.status_code}")
                mode = "ab" if existing and r.status_code == 206 else "wb"
                with open(path, mode) as f:
                    for chunk in r.iter_content(CHUNK_SIZE):
                        f.write(chunk)
            if expected_md5:
                actual = hashlib.md5(open(path, "rb").read()).hexdigest()
                if actual != expected_md5:
                    raise ValueError(f"MD5 mismatch: expected {expected_md5}, got {actual}")
            print(f"  {filename}: done ({os.path.getsize(path)} bytes)")
            return True
        except Exception as exc:
            print(f"  {filename}: attempt {attempt}/{MAX_ATTEMPTS} failed -- {exc!r}")
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_BACKOFF_SECONDS)
    print(f"  {filename}: FAILED after {MAX_ATTEMPTS} attempts -- host unreachable, see module docstring")
    return False


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    print("Primary ADAPT dataset files (NASA DASHlink -- expected to fail, see module docstring):")
    any_primary_ok = False
    for filename, url, md5, size_note, note in FILES:
        print(f"  {filename} ({size_note}, {note})")
        if _download_resumable(filename, url, md5):
            any_primary_ok = True
    if not any_primary_ok:
        print("  None of the primary ADAPT files could be reached this run.")

    print("Companion benchmarking paper (ntrs.nasa.gov -- reachable):")
    name, url, _size = COMPANION_PAPER
    _download_resumable(name, url, None)


if __name__ == "__main__":
    main()
