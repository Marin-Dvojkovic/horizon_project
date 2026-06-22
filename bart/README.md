# BART error injection

Artifacts behind the injected datasets in `datasets/{table}/injected/`.

- `*_changes.csv` — the change logs BART produced, one row per (cell, FD-constraint),
  headerless: `{rowid}.{attribute}, dirty_value, clean_value` (`rowid` is 1-based;
  column 3 is the clean value, column 2 the injected dirty value).
- `hospital_egtasks/`, `insurance_claims_egtasks/` — the original BART **EGTask**
  configuration folders, one per dataset, included verbatim so the exact injection
  setup behind each changes file is reproducible.

## File naming

Both the changes files and the EGTask XMLs encode the same four fields:

```
{table}_{etype}_{rate}[_{level}]_changes.csv        e.g. hospital_2k_e1_10_high_changes.csv
{table}-egtask-{etype}-{rate}[-{level}].xml         e.g. hospital_2k-egtask-e1-10-high.xml
```

- **table** — `hospital_2k` or `insurance_claims_2k`, the 2000-row clean table the errors
  were injected into.
- **etype** — error-generation strategy:
  - `e1` — structured (typo / active-domain) errors driven by the FD constraints.
  - `e2` — random errors.
- **rate** — nominal error rate as a percentage (`5`, `10`, `15`, `20`, `25`, `30`).
- **level** — **repairability** of the injected errors relative to the FD they target,
  present for `e1` only (`e2` random has no level). For an FD `LHS → RHS`:
  - `low` — the error only violates the **LHS** (the determinant is wrong, so the FD
    gives no leverage to repair it — low repairability).
  - `med` — the error violates **both** the LHS and the RHS.
  - `high` — the error only violates the **RHS** (the LHS is intact, so the FD + correct
    LHS pins down the right value — high repairability).

  This is visible in the EGTask `vioGenQuery` comparisons: `high` uses only RHS attributes
  with `!=`, `low` uses only LHS attributes with `==`, and `med` pairs an RHS `!=` with an
  LHS `==`.

So `insurance_claims_2k_e1_5_med_changes.csv` is the 5% structured run on the 2k insurance
table where errors break both sides of the FD, and `hospital_2k_e2_20_changes.csv` is the
random 20% run on the 2k hospital table.
