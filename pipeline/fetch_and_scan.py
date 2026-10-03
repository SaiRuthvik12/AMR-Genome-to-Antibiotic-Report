"""Overnight job: pick the most-labelled genomes, download each (gzipped), run AMRFinderPlus on it.

Resumable: genomes that already have an AMRFinderPlus output are skipped, so just re-run after a crash.
Usage: caffeinate -is .venv/bin/python pipeline/fetch_and_scan.py [N]
"""
import csv
import gzip
import os
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

DRUGS = {"ampicillin", "cefotaxime", "ciprofloxacin", "gentamicin", "trimethoprim/sulfamethoxazole"}
N = int(sys.argv[1]) if len(sys.argv) > 1 else 6000
WORKERS, THREADS = 8, 2  # 10 cores; downloads leave CPU idle, so oversubscribe a bit
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
    for attempt in range(3):
        try:
            data = urllib.request.urlopen(req, timeout=180).read()
            if not data.startswith(b">") or len(data) < 1_000_000:  # E. coli is ~5 Mb; smaller = broken
                raise ValueError(f"bad genome download ({len(data)} bytes)")
            with gzip.open(path + ".tmp", "wb") as f:
                f.write(data)
            os.rename(path + ".tmp", path)
            return path
        except Exception as e:
            err = e
            time.sleep(5 * (attempt + 1))
    raise err


def process(gid):
    out = f"data/amrfinder/{gid}.tsv"
    if os.path.exists(out):
        return "skip"
    fasta = download(gid)
    subprocess.run([f"{AMR_BIN}/amrfinder", "-n", fasta, "--organism", "Escherichia", "--plus",
                    "--threads", str(THREADS), "-o", out + ".tmp"],
                   check=True, capture_output=True, env={**os.environ, "PATH": f"{AMR_BIN}:{os.environ['PATH']}"})
    os.rename(out + ".tmp", out)
    return "done"


start, done, failed = time.time(), 0, 0
with ThreadPoolExecutor(WORKERS) as pool, open("data/processed/failed.txt", "a") as fail_log:
    for i, (gid, fut) in enumerate([(g, pool.submit(process, g)) for g in genomes], 1):
        try:
            done += fut.result() == "done"
        except Exception as e:
            failed += 1
            fail_log.write(f"{gid}\t{e} {getattr(e, 'stderr', b'')[-300:]!r}\n")
            fail_log.flush()
        if i % 25 == 0 or i == len(genomes):
            mins = (time.time() - start) / 60
            print(f"{i}/{len(genomes)} | new {done} | failed {failed} | {mins:.0f} min elapsed", flush=True)
