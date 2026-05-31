# BART error injection

Artifacts behind the injected datasets in `datasets/{table}/injected/`.

- `*_changes.csv` — the change logs BART produced, one row per (cell, FD-constraint),
  headerless: `{rowid}.{attribute}, dirty_value, clean_value` (`rowid` is 1-based;
  column 3 is the clean value, column 2 the injected dirty value).
- `hospital_egtasks/`, `insurance_claims_egtasks/` — the original BART **EGTask**
  configuration folders, one per dataset, included verbatim so the exact injection
  setup behind each changes file is reproducible.
- `dedup_report.md` — the per-file duplicate-drop numbers, **regenerated on every run**
  of `notebooks/build_injected.ipynb`. This README is static; that file is the output.

The build only reads the named `*_changes.csv` files and rewrites `dedup_report.md`;
it never lists or touches the EGTask folders, so they can be added by hand safely.

## Why duplicates instead of unique changes

A changes file logs several rows for the same cell when one cell is implicated by
several FD constraints — same clean value, different candidate dirty values. A dirty
table holds one value per cell, so the build keeps the last occurrence and drops the
rest.

BART has an option to emit only unique changes (one error per cell), but enabling it
pushed injection runtime so high that we could not generate the datasets at all. We
disabled that option and drop the duplicates afterwards, documenting the effect in
`dedup_report.md` so it stays transparent rather than hidden.

This lowers the realized error rate below the nominal label (`e1_5` etc.): the realized
number of dirty cells is `applied_cells`, not `change_rows`. That is fine for our use of
the sweep — it exists to show how **runtime scales with the error rate**, and
`applied_cells` still increases monotonically (roughly linearly) from one rate to the
next, so the sweep remains a valid runtime-vs-error-rate benchmark.
