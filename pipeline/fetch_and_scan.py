"""Overnight job: pick the most-labelled genomes, download each (gzipped), run AMRFinderPlus on it.

Resumable: genomes that already have an AMRFinderPlus output are skipped, so just re-run after a crash.
Usage: caffeinate -is .venv/bin/python pipeline/fetch_and_scan.py [N] [--download-only]
--download-only fetches the DNA files without scanning, so the part that needs the internet finishes quickly;
the scan pass afterwards then runs offline.
"""
import csv
import gzip
import os
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

DRUGS = {"ampicillin", "cefotaxime", "ciprofloxacin", "gentamicin", "trimethoprim/sulfamethoxazole"}
DOWNLOAD_ONLY = "--download-only" in sys.argv
N = next((int(a) for a in sys.argv[1:] if a.isdigit()), 6000)
WORKERS, THREADS = (16, 2) if DOWNLOAD_ONLY else (8, 2)  # downloads are network-bound; scans use the 10 cores
AMR_BIN = "/opt/miniconda3/envs/amr/bin"
GENOME_URL = "https://www.bv-brc.org/api/genome_sequence/?eq(genome_id,{})&limit(25000)"
os.makedirs("data/genomes", exist_ok=True)
os.makedirs("data/amrfinder", exist_ok=True)
os.makedirs("data/processed", exist_ok=True)

# Genomes ranked by how many of our 5 drugs have an S/R label (most useful first).
pairs = set()
with open("data/raw/bvbrc_ecoli_amr.tsv") as f:
    for r in csv.DictReader(f, delimiter="\t"):
        if r["antibiotic"] in DRUGS and r["resistant_phenotype"] in ("Resistant", "Susceptible"):
            pairs.add((r["genome_id"], r["antibiotic"]))
if os.path.exists("data/processed/mic_labels.csv"):  # genomes labelled via the biotech lead's MIC cutoffs
    with open("data/processed/mic_labels.csv") as f:
        pairs |= {(r["genome_id"], r["antibiotic"]) for r in csv.DictReader(f) if r["antibiotic"] in DRUGS}
counts = Counter(g for g, _ in pairs)
genomes = sorted(counts, key=lambda g: (-counts[g], g))[:N]
with open("data/processed/genome_list.csv", "w") as f:
    f.write("genome_id,n_drugs_labelled\n" + "".join(f"{g},{counts[g]}\n" for g in genomes))


def download(gid):
    path = f"data/genomes/{gid}.fna.gz"
    if os.path.exists(path):
        return path
    req = urllib.request.Request(GENOME_URL.format(gid), headers={
        "Accept": "application/dna+fasta", "User-Agent": "amr-hackathon/0.1"})
    for attempt in range(9):  # network errors back off 15 s, 30 s, ... up to 10 min (~30 min total), riding out outages
        try:
            data = urllib.request.urlopen(req, timeout=180).read()
        except OSError as e:  # DNS failure, connection reset, timeout: wait for the network to come back
            err = e
            time.sleep(min(15 * 2 ** attempt, 600))
            continue
        if not data.startswith(b">") or len(data) < 1_000_000:  # E. coli is ~5 Mb; smaller = broken in the database
            raise ValueError(f"bad genome download ({len(data)} bytes)")
        with gzip.open(path + ".tmp", "wb") as f:
            f.write(data)
        os.rename(path + ".tmp", path)
        return path
    raise err


def process(gid):
    out = f"data/amrfinder/{gid}.tsv"
    if os.path.exists(out):
        return "skip"
    fasta = download(gid)
    if DOWNLOAD_ONLY:
        return "done"
    subprocess.run([f"{AMR_BIN}/amrfinder", "-n", fasta, "--organism", "Escherichia", "--plus",
                    "--threads", str(THREADS), "-o", out + ".tmp"],
                   check=True, capture_output=True, env={**os.environ, "PATH": f"{AMR_BIN}:{os.environ['PATH']}"})
    os.rename(out + ".tmp", out)
    return "done"


start, done, failed = time.time(), 0, 0
with ThreadPoolExecutor(WORKERS) as pool, open("data/processed/failed.txt", "a") as fail_log:
    futures = {pool.submit(process, g): g for g in genomes}
    for i, fut in enumerate(as_completed(futures), 1):  # report in finishing order, so the count is real progress
        try:
            done += fut.result() == "done"
        except Exception as e:
            failed += 1
            fail_log.write(f"{futures[fut]}\t{e} {getattr(e, 'stderr', b'')[-300:]!r}\n")
            fail_log.flush()
        if i % 25 == 0 or i == len(genomes):
            mins = (time.time() - start) / 60
            print(f"{i}/{len(genomes)} | new {done} | failed {failed} | {mins:.0f} min elapsed", flush=True)
