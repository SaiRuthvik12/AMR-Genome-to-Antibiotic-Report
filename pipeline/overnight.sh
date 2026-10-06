#!/bin/sh
# Overnight chain: download every labelled genome not scanned yet (3 passes, to catch network drops) -> scan them
# (offline) -> measure the new ones -> re-run the analysis.
# Start with:  nohup caffeinate -is pipeline/overnight.sh > data/raw/overnight.log 2>&1 &
# Each step is resumable, so if anything stops, just start it again.
set -e
cd "$(dirname "$0")/.."
for pass in 1 2 3; do
  echo "== $(date '+%H:%M') download pass $pass"; .venv/bin/python -u pipeline/fetch_and_scan.py 100000 --download-only
done
echo "== $(date '+%H:%M') scan";      .venv/bin/python -u pipeline/fetch_and_scan.py 100000
echo "== $(date '+%H:%M') measure";   sh pipeline/measure_new_genomes.sh
echo "== $(date '+%H:%M') analysis";  ./run_all.sh
echo "== $(date '+%H:%M') done"
