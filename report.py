"""Genome file -> report: QC, species check, AMRFinderPlus markers, per-drug calls with evidence, LLM summary.

The calls, probabilities and evidence come from code (model/final.py). The LLM only turns that JSON into a short
plain-language summary, and the summary is dropped if it contradicts a call. No treatment or dosing advice.
"""
import json
import os
import pickle
import subprocess
import sys

import pandas as pd

sys.path[:0] = ["model", "pipeline"]
from final import MODEL_PATH, predict  # noqa: E402
from qc_and_lineage import reason  # noqa: E402

BIO = "/opt/miniconda3/envs/amr/bin"
REF_SKETCH = "data/models/ref_ecoli.msh"
ENV = {**os.environ, "PATH": f"{BIO}:{os.environ['PATH']}"}
DRUG_INFO = {  # display name, drug class
    "ampicillin": ("Ampicillin", "Penicillin"),
    "cefotaxime": ("Cefotaxime", "3rd-generation cephalosporin"),
    "ciprofloxacin": ("Ciprofloxacin", "Fluoroquinolone"),
    "gentamicin": ("Gentamicin", "Aminoglycoside"),
    "trimethoprim/sulfamethoxazole": ("Trimethoprim-sulfamethoxazole", "Folate pathway inhibitor"),
}
CALL_WORD = {"R": "resistant", "S": "susceptible", "UNCERTAIN": "uncertain"}
LLM_MODEL = "claude-opus-5-5"


def load_models():
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


def _run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, env=ENV).stdout


def analyze_genome(fasta_path, cached_amrfinder=None):
    """QC numbers + resistance markers for one assembled genome (FASTA, optionally .gz)."""
    stats = _run([f"{BIO}/seqkit", "stats", "-a", "-T", fasta_path]).splitlines()
    row = dict(zip(stats[0].split("\t"), stats[1].split("\t")))
    dist = float(_run([f"{BIO}/mash", "dist", REF_SKETCH, fasta_path]).split("\t")[2])
    qc = pd.Series({"size_mb": round(int(row["sum_len"]) / 1e6, 2), "contigs": int(row["num_seqs"]),
                    "n50": int(row["N50"]), "dist_to_ecoli": round(dist, 4)})
    qc["qc_reason"] = reason(qc)

    amr_tsv = cached_amrfinder
    if amr_tsv is None:
        amr_tsv = fasta_path + ".amrfinder.tsv"
        _run([f"{BIO}/amrfinder", "-n", fasta_path, "--organism", "Escherichia", "--plus", "--threads", "4", "-o", amr_tsv])
    hits = pd.read_csv(amr_tsv, sep="\t")
    hits = hits[hits.Type == "AMR"][["Element symbol", "Element name", "Class", "Subclass"]].drop_duplicates("Element symbol")
    return qc, hits


def build_report(fasta_path, alpha=0.02, cached_amrfinder=None, models=None):
    models = models or load_models()
    qc, hits = analyze_genome(fasta_path, cached_amrfinder)
    names = dict(zip(hits["Element symbol"], hits["Element name"]))
    drugs = predict(models, set(hits["Element symbol"]), alpha) if not qc.qc_reason else {}
    for drug, r in drugs.items():
        r["evidence"] = [{"marker": m, "weight": w, "name": names.get(m, ""),
                          "known_mechanism": m in models["linked"][drug]} for m, w in r["evidence"].items()]
    return {"qc": qc.to_dict(), "markers": hits, "drugs": drugs}


SYSTEM_PROMPT = """You write a short plain-language summary of an antimicrobial resistance prediction report for a \
clinician. The report was produced by a research prototype from a bacterial genome; you receive it as JSON.

Rules:
- Use only facts in the JSON. Never change, soften or add a call. "UNCERTAIN" means the model is not confident; \
say lab confirmation is needed for it.
- Mention each antibiotic once, grouped by call. Name the key genetic markers behind resistant calls when the JSON \
lists them, especially those marked known_mechanism.
- No treatment, drug choice or dosing recommendations. Do not say which drug to give.
- 3 to 5 sentences, no headings, no bullet points, no markdown."""


def llm_summary(report):
    """Plain-language summary from Claude, or (None, reason) when unavailable or inconsistent with the calls."""
    try:
        import anthropic
        client = anthropic.Anthropic()
        payload = {DRUG_INFO[d][0]: {"call": CALL_WORD[r["call"]], "probability_resistant": round(r["p_resistant"], 2),
                                     "evidence": [{k: e[k] for k in ("marker", "name", "known_mechanism")} for e in r["evidence"][:4]]}
                   for d, r in report["drugs"].items()}
        response = client.beta.messages.create(
            model=LLM_MODEL, max_tokens=2000,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",  # retry on another model if declined
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(payload, indent=1)}],
        )
    except Exception as e:  # no credentials, no network, API error: the report works without the summary
        if "authentication" in str(e).lower():
            return None, "AI summary is off: set ANTHROPIC_API_KEY (in your shell or a .env file) to turn it on."
        return None, f"AI summary unavailable ({type(e).__name__})."
    if response.stop_reason == "refusal":
        return None, "AI summary unavailable (request declined)."
    text = " ".join(b.text for b in response.content if b.type == "text").strip()
    # Guard: every antibiotic must be mentioned, so a dropped or invented call is caught.
    missing = [DRUG_INFO[d][0] for d in report["drugs"] if DRUG_INFO[d][0].split("-")[0].lower() not in text.lower()]
    if missing:
        return None, f"AI summary hidden: it did not cover {', '.join(missing)}."
    return text, None


if __name__ == "__main__":
    rep = build_report("demo/562.100082.fna.gz", cached_amrfinder="demo/562.100082.amrfinder.tsv")
    print(rep["qc"])
    for d, r in rep["drugs"].items():
        print(f"{d:30} {r['call']:9} {r['p_resistant']:.2f} {[(e['marker'], e['known_mechanism']) for e in r['evidence']]}")
    print(llm_summary(rep))
