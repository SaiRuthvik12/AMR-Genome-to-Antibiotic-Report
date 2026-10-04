"""Turn raw MIC numbers into S/R labels using the biotech lead's EUCAST cutoffs (pipeline/breakpoints.csv).

Only rows without a reported verdict are converted; reported verdicts always win (see model/build_table.py).
Rows that already have both are used to check agreement between old verdicts and today's cutoffs.
Drugs whose cutoffs are still blank are skipped, so this is safe to run before the CSV is filled in.

Conservative defaults (biotech lead can change them):
- Only dilution methods (MIC / broth / agar). Disk diffusion is skipped: its "mg/L" values look like zone sizes in mm.
- Values between the S and R cutoffs (intermediate zone) are dropped.
- Censored values (">8", "<=0.25") are kept only when the cutoff settles them, e.g. ">8" with an R cutoff of 8 -> R.
- Trimethoprim/sulfamethoxazole values like "1/19" use the trimethoprim part (first number), as EUCAST does.
Output: data/processed/mic_labels.csv (genome_id, antibiotic, resistant_phenotype)
"""
import pandas as pd

bp = pd.read_csv("pipeline/breakpoints.csv").dropna(subset=["susceptible_if_mic_le_mg_per_L", "resistant_if_mic_gt_mg_per_L"])
bp = bp.set_index("antibiotic")
d = pd.read_csv("data/raw/bvbrc_ecoli_amr.tsv", sep="\t", dtype=str)
d = d[d.antibiotic.isin(bp.index) & d.measurement_value.notna() & (d.measurement_unit == "mg/L")
      & d.laboratory_typing_method.isin(["MIC", "Broth dilution", "Agar dilution"])].copy()
d["mic"] = pd.to_numeric(d.measurement_value.str.split("/").str[0], errors="coerce")
d["sign"] = d.measurement_sign.fillna("=")
d = d.dropna(subset=["mic"])


def verdict(r):
    s_max, r_above = bp.loc[r.antibiotic, "susceptible_if_mic_le_mg_per_L"], bp.loc[r.antibiotic, "resistant_if_mic_gt_mg_per_L"]
    if r.sign in ("=", "=="):
        return "Susceptible" if r.mic <= s_max else "Resistant" if r.mic > r_above else None
    if r.sign == ">":  # true MIC is above the value
        return "Resistant" if r.mic >= r_above else None
    if r.sign == ">=":
        return "Resistant" if r.mic > r_above else None
    if r.sign in ("<", "<="):  # true MIC is at or below the value
        return "Susceptible" if r.mic <= s_max else None
    return None


d["converted"] = d.apply(verdict, axis=1) if len(d) else []
both = d[d.resistant_phenotype.isin(["Resistant", "Susceptible"]) & d.converted.notna()]
for drug, b in both.groupby("antibiotic"):
    print(f"{drug}: reported vs today's cutoffs agree on {(b.resistant_phenotype == b.converted).mean():.1%} of {len(b)} results")
new = d[d.resistant_phenotype.isna() & d.converted.notna()]
new = new.groupby(["genome_id", "antibiotic"]).converted.agg(lambda s: s.iloc[0] if s.nunique() == 1 else None).dropna()
new.rename("resistant_phenotype").reset_index().to_csv("data/processed/mic_labels.csv", index=False)
print(f"Drugs with cutoffs: {list(bp.index) or 'none yet'} | new labels from MIC: {len(new)} "
      f"across {new.index.get_level_values(0).nunique()} genomes")
