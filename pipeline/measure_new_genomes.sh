#!/bin/sh
# Measure only genomes that haven't been measured yet, and append them to the existing results.
# Incremental on purpose: old DNA files may have been deleted to save disk, but their measurements are kept.
#   size/pieces -> data/processed/qc_stats.tsv     species -> data/processed/species_dist.tsv
#   fingerprints -> data/mash/all.msh             close pairs -> data/mash/pairs.tsv
#   sequence type -> data/processed/mlst_raw.tsv  (--scheme is required: autodetect breaks ties at random)
set -e
cd "$(dirname "$0")/.."
BIO=/opt/miniconda3/envs/amr/bin
export PATH="$BIO:$PATH"
NEW=data/mash/new_files.txt

ls data/genomes/*.fna.gz | sort > data/mash/on_disk.txt
tail -n +2 data/processed/qc_stats.tsv | cut -f1 | sort > data/mash/measured.txt
comm -23 data/mash/on_disk.txt data/mash/measured.txt > "$NEW"
echo "genomes to measure: $(wc -l < "$NEW")"
[ -s "$NEW" ] || exit 0

# Everything goes to temp files first and is appended only at the end, so an interrupted run leaves no half-update.
T=data/mash/tmp_; rm -f ${T}*
seqkit stats -a -T -j 8 --infile-list "$NEW" | tail -n +2 > ${T}stats.tsv
mash sketch -p 8 -s 10000 -o ${T}new -l "$NEW"
mash dist -p 2 ${T}new.msh data/models/ref_ecoli.msh | cut -f1,3 > ${T}species.tsv
mash paste ${T}combined data/mash/all.msh ${T}new.msh
# new genomes vs everything (old + new); old-vs-old pairs are already in pairs.tsv
mash dist -p 8 -d 0.01 ${T}combined.msh ${T}new.msh > ${T}pairs.tsv
xargs -n 50 -P 8 mlst --quiet --scheme ecoli_achtman_4 < "$NEW" 2>/dev/null > ${T}mlst.tsv

cat ${T}species.tsv >> data/processed/species_dist.tsv
cat ${T}pairs.tsv >> data/mash/pairs.tsv
cat ${T}mlst.tsv >> data/processed/mlst_raw.tsv
mv ${T}combined.msh data/mash/all.msh
cat ${T}stats.tsv >> data/processed/qc_stats.tsv  # last: this file marks genomes as measured
rm -f ${T}*
echo "measured: $(wc -l < "$NEW") genomes"
