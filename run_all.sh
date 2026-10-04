#!/bin/sh
# Re-run the whole analysis after any data change (e.g. the biotech lead edits breakpoints.csv or drug_marker_map.csv).
#
#   ./run_all.sh            labels -> table -> QC/families -> baseline -> models -> confidence -> final models  (~2 min)
#   ./run_all.sh --genomes  first re-measure every genome (size, species, Mash families, mlst). Needed only after
#                           new genomes were scanned. Slow: hours for 10k+ genomes, so run it overnight.
#
# Results land in data/processed/*.csv and data/models/models.pkl. Because those files are in git,
# `git diff data/processed/` afterwards shows exactly how the numbers changed.
set -e
cd "$(dirname "$0")"
PY=.venv/bin/python
BIO=/opt/miniconda3/envs/amr/bin

if [ "$1" = "--genomes" ]; then
  echo "== Re-measuring genomes"
  ls data/genomes/*.fna.gz > data/mash/files.txt
  "$BIO/seqkit" stats -a -T -j 8 $(cat data/mash/files.txt) > data/processed/qc_stats.tsv
  "$BIO/mash" sketch -p 8 -s 10000 -o data/mash/all -l data/mash/files.txt
  "$BIO/mash" dist -p 2 data/mash/all.msh data/mash/ref_ecoli.msh | cut -f1,3 > data/processed/species_dist.tsv
  "$BIO/mash" dist -p 8 -d 0.01 data/mash/all.msh data/mash/all.msh > data/mash/pairs.tsv
  # --scheme is required: autodetect breaks ties at random (see CLAUDE.md gotchas)
  PATH="$BIO:$PATH" xargs -n 50 -P 8 "$BIO/mlst" --quiet --scheme ecoli_achtman_4 < data/mash/files.txt > data/processed/mlst_raw.tsv
fi

echo "== 1. MIC -> labels (biotech lead's cutoffs)";  $PY pipeline/apply_breakpoints.py
echo "== 2. ML table";                               $PY model/build_table.py
echo "== 3. Quality check + families";               $PY pipeline/qc_and_lineage.py
echo "== 4. Rule baseline";                          PYTHONPATH=model $PY model/baseline_rules.py
echo "== 5. Models vs rules";                        PYTHONPATH=model $PY model/train.py
echo "== 6. Confidence / UNCERTAIN flag";            PYTHONPATH=model $PY model/confidence.py
echo "== 7. Final models + explanations";            PYTHONPATH=model $PY model/final.py
echo
echo "Done. Compare with the last commit:  git diff --stat data/processed/  (and git diff data/processed/results_*.csv)"
