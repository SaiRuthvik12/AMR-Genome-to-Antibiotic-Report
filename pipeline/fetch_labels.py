"""Download all lab-measured E. coli AMR phenotypes from the BV-BRC API (paged, 25k rows max per call)."""
import csv
import io
import urllib.request

URL = ("https://www.bv-brc.org/api/genome_amr/?and(eq(taxon_id,562),eq(evidence,%22Laboratory%20Method%22))"
       "&select(genome_id,genome_name,antibiotic,resistant_phenotype,measurement_sign,measurement_value,"
       "measurement_unit,laboratory_typing_method,testing_standard,testing_standard_year)"
       "&sort(+id)&limit(25000,{offset})")
OUT = "data/raw/bvbrc_ecoli_amr.tsv"

with open(OUT, "w", newline="") as f:
    writer, offset = None, 0
    while True:
        req = urllib.request.Request(URL.format(offset=offset), headers={"Accept": "text/tsv", "User-Agent": "amr-hackathon/0.1"})  # default urllib UA gets 403
        rows = list(csv.reader(io.StringIO(urllib.request.urlopen(req, timeout=300).read().decode()), delimiter="\t"))
        header, body = rows[0], rows[1:]
        if writer is None:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(header)
        writer.writerows(body)
        print(f"offset {offset}: {len(body)} rows")
        if len(body) < 25000:
            break
        offset += 25000
