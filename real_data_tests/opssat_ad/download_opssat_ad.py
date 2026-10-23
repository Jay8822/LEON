# real_data_tests/opssat_ad/download_opssat_ad.py
# Added 2026-10-23 — Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Downloads the OPSSAT-AD dataset into a local, gitignored data/
folder. SPEC.md's "Real-data testing" section: "Do not commit raw
data to the repo. Use a download script, and cite every dataset
properly."

Dataset: Ruszczak, B., Kotowski, K., Nalepa, J. & Evans, D.
"OPSSAT-AD — anomaly detection dataset for satellite telemetry"
(2024). https://doi.org/10.5281/zenodo.12588359
Licence: CC-BY-4.0.

Companion paper: Ruszczak, Kotowski, Nalepa & Evans, "The OPS-SAT
benchmark for detecting anomalies in satellite telemetry,"
arXiv:2407.04730 (2024).

Fetches the two files Zenodo publishes for this record and verifies
each against the MD5 checksum Zenodo itself lists, so a corrupted or
partial download is caught rather than silently used.

Run from the repo root:

    python -m real_data_tests.opssat_ad.download_opssat_ad
"""

import hashlib
import os

import requests

ZENODO_RECORD = "https://zenodo.org/records/12588359"

# (filename, download URL, MD5 Zenodo publishes for this file)
FILES = [
    (
        "segments.csv",
        "https://zenodo.org/records/12588359/files/segments.csv?download=1",
        "1f4b6ffd0359efac96a6698ff557e0f9",
    ),
    (
        "dataset.csv",
        "https://zenodo.org/records/12588359/files/dataset.csv?download=1",
        "c12fb83863afa4463dec07303a20bb14",
    ),
]

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def md5sum(path):
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(filename, url, expected_md5):
    os.makedirs(DATA_DIR, exist_ok=True)
    dest = os.path.join(DATA_DIR, filename)

    if os.path.exists(dest) and md5sum(dest) == expected_md5:
        print(f"{filename}: already present and MD5-verified, skipping download.")
        return

    print(f"{filename}: downloading from {url}")
    response = requests.get(url, timeout=120)
    response.raise_for_status()

    with open(dest, "wb") as f:
        f.write(response.content)

    actual_md5 = md5sum(dest)
    if actual_md5 != expected_md5:
        os.remove(dest)
        raise RuntimeError(
            f"{filename}: MD5 mismatch after download "
            f"(expected {expected_md5}, got {actual_md5}). "
            f"Deleted the partial/corrupt file -- re-run to retry."
        )
    print(f"{filename}: downloaded and MD5-verified ({expected_md5}).")


def main():
    print(f"OPSSAT-AD -- {ZENODO_RECORD}")
    print("Licence: CC-BY-4.0. Cite: Ruszczak, Kotowski, Nalepa & Evans (2024), "
          "https://doi.org/10.5281/zenodo.12588359")
    for filename, url, expected_md5 in FILES:
        download_file(filename, url, expected_md5)


if __name__ == "__main__":
    main()
