# AMR genome-to-antibiotic report (hackathon, Oct 4–10 2026)

Upload an E. coli genome → per-antibiotic susceptible/resistant call, calibrated confidence,
an UNCERTAIN flag (confirm with lab AST), and the genetic evidence. Research prototype, decision support only.

Full plan (source of truth for scope and roles): https://claude.ai/code/artifact/7dbc4cdf-5882-4763-9f38-e686a4678c90

## Rules
- Diagnostic/decision support only. Reports describe resistance evidence and uncertainty; no treatment or dosing advice.
- Numbers and calls in reports come from code. The LLM only writes the narrative summary.
- Evaluate on lineage-held-out splits (group by Mash cluster). Never use sequence type as a model feature.
- Biology claims get checked by the biotech lead before they go in the pitch.
- Keep it simple: one script per step, flat layout. Ask before changing scope.

## Layout
- `pipeline/` (biotech lead): data download, QC, MLST, Mash, AMRFinderPlus → small CSVs in `data/processed/`
- `model/` (AI lead): features, splits, models, calibration/conformal, evaluation
- `report.py`, `app.py`: report builder + Streamlit app
- `data/raw`, `data/genomes`: large, gitignored, live only on the AI lead's laptop. Commit `data/processed/*.csv`.

## Environments
- Bioinformatics tools (x86 via Rosetta on Apple Silicon):
  `CONDA_SUBDIR=osx-64 conda create -n amr --override-channels -c conda-forge -c bioconda python=3.11 ncbi-amrfinderplus mlst mash seqkit`
  then `amrfinder -u`. Use with `PATH=/opt/miniconda3/envs/amr/bin:$PATH` (or `conda activate amr`).
- Python/ML: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`

## Data facts (verified Oct 4)
- BV-BRC API: `https://www.bv-brc.org/api/genome_amr/` (RQL queries, max 25k rows per call, rejects the default
  Python user agent → set a custom User-Agent). The ftp.bvbrc.org host timed out.
- Genomes: `https://www.bv-brc.org/api/genome_sequence/?eq(genome_id,<id>)&limit(25000)` with
  `Accept: application/dna+fasta`. ~5.5 MB each, ~1.8 MB gzipped. AMRFinderPlus reads .gz directly.
- `pipeline/fetch_labels.py` → `data/raw/bvbrc_ecoli_amr.tsv`: 243k lab-measured rows, 12,627 genomes.
  94k rows have S/R labels; 148k have only an MIC value (convert with EUCAST breakpoints).
- AMRFinderPlus 4.2.7, DB 2026-08-07.1: ~18 s/genome (4 threads, under Rosetta).
  Output columns include `Element symbol`, `Type`, `Subtype`, `Class`, `Subclass`.
