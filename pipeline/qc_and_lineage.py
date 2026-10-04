"""Quality check + lineage (family) grouping for every scanned genome.

Inputs (made by shell commands, see CLAUDE.md):
  data/processed/qc_stats.tsv   seqkit stats -a -T   (size, contigs, N50)
  data/processed/mlst_raw.tsv   mlst --quiet --scheme ecoli_achtman_4   (sequence type; scheme is fixed
                                because autodetect breaks score ties at random, e.g. E. coli ST131 vs Salmonella)
  data/processed/species_dist.tsv  mash dist to one confirmed E. coli (562.100001); > 0.05 = other species
  data/mash/pairs.tsv           mash dist -d 0.01     (DNA distance for every close pair)
Outputs:
  data/processed/qc.csv         genome_id, size_mb, contigs, n50, ST, dist_to_ecoli, qc_pass, qc_reason
  data/processed/lineage.csv    genome_id, ST, cluster   (only genomes that pass QC)
"""
import os
import sys

import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

MASH_CUTOFF = float(sys.argv[1]) if len(sys.argv) > 1 else 0.005  # ~99.5% identical DNA = same family
gid = lambda path: os.path.basename(path).removesuffix(".fna.gz")

# 1. Quality check
q = pd.read_csv("data/processed/qc_stats.tsv", sep="\t")
qc = pd.DataFrame({"genome_id": q.file.map(gid), "size_mb": (q.sum_len / 1e6).round(2),
                   "contigs": q.num_seqs, "n50": q.N50})
m = pd.read_csv("data/processed/mlst_raw.tsv", sep="\t", header=None, usecols=[0, 1, 2], names=["file", "mlst_scheme", "ST"])
qc = qc.merge(m.assign(genome_id=m.file.map(gid)).drop(columns=["file", "mlst_scheme"]), on="genome_id", how="left")
sp = pd.read_csv("data/processed/species_dist.tsv", sep="\t", header=None, names=["file", "dist_to_ecoli"])
qc = qc.merge(sp.assign(genome_id=sp.file.map(gid)).drop(columns="file"), on="genome_id", how="left")


def reason(r):
    if not 4.5 <= r.size_mb <= 6.0:
        return "size outside 4.5-6.0 Mb"  # too small = incomplete, too big = likely two genomes mixed
    if r.contigs > 500:
        return "over 500 contigs (too fragmented)"
    if r.dist_to_ecoli > 0.05:  # ~95% DNA identity = the usual species boundary
        return "not E. coli (Mash distance > 0.05)"
    return ""


qc["qc_reason"] = qc.apply(reason, axis=1)
qc["qc_pass"] = qc.qc_reason == ""
qc.to_csv("data/processed/qc.csv", index=False)

# 2. Lineage clusters: link any two genomes closer than the cutoff, then each connected group = one family
ok = qc[qc.qc_pass].reset_index(drop=True)
idx = {g: i for i, g in enumerate(ok.genome_id)}
p = pd.read_csv("data/mash/pairs.tsv", sep="\t", header=None, usecols=[0, 1, 2], names=["a", "b", "dist"])
p = p[p.dist <= MASH_CUTOFF]
p = p.assign(a=p.a.map(gid).map(idx), b=p.b.map(gid).map(idx)).dropna()
graph = coo_matrix(([1] * len(p), (p.a.astype(int), p.b.astype(int))), shape=(len(ok), len(ok)))
_, ok["cluster"] = connected_components(graph, directed=False)
ok[["genome_id", "ST", "cluster"]].to_csv("data/processed/lineage.csv", index=False)

sizes = ok.cluster.value_counts()
print(f"QC: {qc.qc_pass.sum()} pass, {(~qc.qc_pass).sum()} fail")
print(qc[~qc.qc_pass].qc_reason.str.split(" \\(").str[0].value_counts().to_string())
print(f"Lineage @ {MASH_CUTOFF}: {len(sizes)} clusters | largest {sizes.iloc[0]} genomes "
      f"({sizes.iloc[0] / len(ok):.0%}) | top 5 {sizes.head().tolist()} | singletons {(sizes == 1).sum()}")
