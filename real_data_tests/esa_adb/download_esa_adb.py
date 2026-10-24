# real_data_tests/esa_adb/download_esa_adb.py
# Added 2026-10-25 — Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Downloads the ESA Anomaly Dataset ("ESA-ADB") into a local,
gitignored data/ folder. SPEC.md's "Real-data testing" section: "Do
not commit raw data to the repo. Use a download script, and cite
every dataset properly." Also: "ESA-ADB is large. The laptop has 6 GB
of memory, so read it in chunks... expect slow runs."

Dataset: De Canio, G., Kotowski, K. & Haskamp, C. (contributors:
Andrzejewski, J., Ruszczak, B., Nalepa, J., Lakey, D., Collins, P.,
Kolmas, A., Bartesaghi, M. & Martinez-Heras, J.) "ESA Anomaly Dataset"
(2024). https://doi.org/10.5281/zenodo.12528696
Licence: CC BY 3.0 IGO.

Companion paper: Kotowski et al., "European Space Agency Benchmark for
Anomaly Detection in Satellite Telemetry," arXiv:2406.17826 (2024).

Only Missions 1 and 2 -- the two the ESA-ADB benchmark actually uses.
Mission3 is excluded deliberately: per the benchmark paper, it has
too few anomalies and too many communication gaps to be useful, and
isn't part of the benchmark at all. 7.9 GB total (sizes/MD5s below are
exactly what Zenodo publishes for this record -- confirmed by reading
the record directly, not assumed from secondary sources, which
disagreed with each other on total size).

THIS SCRIPT ONLY DOWNLOADS. Per Jay's instruction: no unpacking, no
profiling, no loading into memory here -- that comes later, and on a
6 GB machine, only ever in chunks. Downloads are streamed straight to
disk (requests' streaming mode), never held whole in memory, even
though each file is ~4 GB -- the opposite would risk exhausting RAM
on its own, before any analysis even starts.

Resumable: the first real attempt hit a socket read timeout partway
through Mission1 (Zenodo's connection stalled on one chunk, not a
hard rejection). Three-GB-plus downloads over a long background run
will hit transient stalls like this, so this script retries through
them instead of restarting from zero -- on a dropped connection, it
re-requests the file with an HTTP Range header starting from however
many bytes are already on disk, and only gives up after several
consecutive failed attempts.

Run from the repo root (this will take a long time -- intended to run
in the background):

    python -m real_data_tests.esa_adb.download_esa_adb
"""

import hashlib
import os
import time

import requests

MAX_ATTEMPTS = 10
RETRY_BACKOFF_SECONDS = 10
# (connect timeout, read timeout) -- a stall longer than the read
# timeout on any single chunk raises, and gets retried/resumed above.
REQUEST_TIMEOUT = (30, 60)
PROGRESS_STEP_BYTES = 200 * 1024 * 1024  # print progress every ~200 MB, not every 8 MB chunk

ZENODO_RECORD = "https://zenodo.org/records/12528696"

# (filename, download URL, MD5 Zenodo publishes for this file, size for progress messages)
FILES = [
    (
        "ESA-Mission1.zip",
        "https://zenodo.org/records/12528696/files/ESA-Mission1.zip?download=1",
        "80750189d171f5f398fb3d96c49df12b",
        "3.8 GB",
    ),
    (
        "ESA-Mission2.zip",
        "https://zenodo.org/records/12528696/files/ESA-Mission2.zip?download=1",
        "0b7505b7f0731ca037ee889ca2a520ce",
        "4.1 GB",
    ),
]

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB -- streamed to disk, never held whole in memory


def md5sum(path):
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(filename, url, expected_md5, size_label):
    os.makedirs(DATA_DIR, exist_ok=True)
    dest = os.path.join(DATA_DIR, filename)

    if os.path.exists(dest) and md5sum(dest) == expected_md5:
        print(f"{filename}: already present and MD5-verified, skipping download.")
        return

    session = requests.Session()
    attempt = 0
    while True:
        attempt += 1
        existing = os.path.getsize(dest) if os.path.exists(dest) else 0
        headers = {"Range": f"bytes={existing}-"} if existing else {}
        if existing:
            print(f"{filename}: attempt {attempt}, resuming from {existing / (1024**3):.2f} GB")
        else:
            print(f"{filename}: downloading from {url} ({size_label}, streamed to disk)")

        try:
            with session.get(url, headers=headers, stream=True, timeout=REQUEST_TIMEOUT) as response:
                if existing and response.status_code == 200:
                    # Server ignored the Range request and is sending the
                    # whole file again from the start -- restart clean
                    # rather than appending a full copy onto a partial one.
                    existing = 0
                response.raise_for_status()
                mode = "ab" if existing else "wb"
                downloaded = existing
                next_progress_at = downloaded + PROGRESS_STEP_BYTES
                with open(dest, mode) as f:
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if downloaded >= next_progress_at:
                            print(f"  {filename}: {downloaded / (1024**3):.2f} GB written")
                            next_progress_at = downloaded + PROGRESS_STEP_BYTES
            print(f"  {filename}: {downloaded / (1024**3):.2f} GB written (stream complete)")
            break
        except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError,
                requests.exceptions.Timeout) as exc:
            if attempt >= MAX_ATTEMPTS:
                raise RuntimeError(
                    f"{filename}: gave up after {attempt} attempts -- last error: {exc!r}"
                ) from exc
            print(f"  {filename}: connection issue ({exc!r}), retrying from where it left off "
                  f"in {RETRY_BACKOFF_SECONDS}s...")
            time.sleep(RETRY_BACKOFF_SECONDS)
            continue

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
    print(f"ESA-ADB -- {ZENODO_RECORD}")
    print("Licence: CC BY 3.0 IGO. Cite: De Canio, Kotowski & Haskamp et al. (2024), "
          "https://doi.org/10.5281/zenodo.12528696")
    print("Download only -- no unpacking, no profiling, no loading into memory here.")
    for filename, url, expected_md5, size_label in FILES:
        download_file(filename, url, expected_md5, size_label)


if __name__ == "__main__":
    main()
