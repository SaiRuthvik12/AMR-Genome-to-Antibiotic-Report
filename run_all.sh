#!/bin/sh
# Re-run the whole analysis after any data change (e.g. the biotech lead edits breakpoints.csv or drug_marker_map.csv).
#
#   ./run_all.sh            labels -> table -> QC/families -> baseline -> models -> confidence -> final models  (~2 min)
#   ./run_all.sh --genomes  first measure genomes scanned since the last run (size, species, Mash, mlst), appending to
#                           the existing results. Needed only after scanning new genomes. Slow: ~2 h per 6k genomes.
#
# Results land in data/processed/*.csv and data/models/models.pkl. Because those files are in git,
# `git diff data/processed/` afterwards shows exactly how the numbers changed.
set -e
cd "$(dirname "$0")"
PY=.venv/bin/python
BIO=/opt/miniconda3/envs/amr/bin

if [ "$1" = "--genomes" ]; then
  echo "== Measuring new genomes"; sh pipeline/measure_new_genomes.sh
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
