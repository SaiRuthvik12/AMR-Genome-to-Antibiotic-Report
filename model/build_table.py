"""Join AMRFinderPlus scans with lab labels into the ML table.

Outputs (data/processed/):
  labels.csv    genome_id + one column per drug: 1 = resistant, 0 = susceptible, blank = no lab result
  features.csv  genome_id + one 0/1 column per resistance marker (AMR genes and point mutations)
  overview.csv  human-readable: labels + the list of markers each genome carries
"""
import glob
import os

import pandas as pd

DRUGS = ["ampicillin", "cefotaxime", "ciprofloxacin", "gentamicin", "trimethoprim/sulfamethoxazole"]
MIN_GENOMES = 5  # drop markers seen in fewer genomes: too rare to learn from

# Markers: AMR type only (genes + point mutations). Stress/virulence genes are left out for now.
hits = []
for f in glob.glob("data/amrfinder/*.tsv"):
    a = pd.read_csv(f, sep="\t", usecols=["Element symbol", "Type"])
    for m in set(a.loc[a.Type == "AMR", "Element symbol"]):
        hits.append((os.path.basename(f)[:-4], m))
hits = pd.DataFrame(hits, columns=["genome_id", "marker"])
scanned = sorted(os.path.basename(f)[:-4] for f in glob.glob("data/amrfinder/*.tsv"))

# Labels: lab S/R only; a genome x drug with conflicting results is dropped.
d = pd.read_csv("data/raw/bvbrc_ecoli_amr.tsv", sep="\t", dtype=str)
d = d[d.antibiotic.isin(DRUGS) & d.resistant_phenotype.isin(["Resistant", "Susceptible"]) & d.genome_id.isin(scanned)]
lab = d.groupby(["genome_id", "antibiotic"]).resistant_phenotype.agg(lambda s: s.iloc[0] if s.nunique() == 1 else None)
lab = lab.dropna()
if os.path.exists("data/processed/mic_labels.csv"):  # MIC-derived labels fill gaps; reported verdicts win
    mic = pd.read_csv("data/processed/mic_labels.csv", dtype=str).set_index(["genome_id", "antibiotic"]).resistant_phenotype
    mic = mic[mic.index.get_level_values(0).isin(scanned) & ~mic.index.isin(lab.index)]
    lab = pd.concat([lab, mic])
    print(f"added {len(mic)} MIC-derived labels")
labels = (lab == "Resistant").astype(int).unstack().reindex(index=scanned, columns=DRUGS)
labels.index.name = "genome_id"

counts = hits.marker.value_counts()
common = hits[hits.marker.isin(counts[counts >= MIN_GENOMES].index)]
features = pd.crosstab(common.genome_id, common.marker).clip(upper=1).reindex(scanned, fill_value=0)
features.index.name = "genome_id"

word = labels.replace({1: "RESISTANT", 0: "susceptible"})
overview = word.assign(markers=hits.groupby("genome_id").marker.agg(lambda s: "; ".join(sorted(s))).reindex(scanned).fillna(""))

os.makedirs("data/processed", exist_ok=True)
labels.to_csv("data/processed/labels.csv")
features.to_csv("data/processed/features.csv")
overview.to_csv("data/processed/overview.csv")
print(f"{len(scanned)} genomes, {features.shape[1]} markers (of {len(counts)} seen; rest in < {MIN_GENOMES} genomes)")
print(labels.apply(lambda c: f"{int(c.sum())} R / {int((c == 0).sum())} S / {int(c.isna().sum())} no label").to_string())
