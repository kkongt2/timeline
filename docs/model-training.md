# Historical KRA model research

This pipeline uses official daily KRA result reports, not the 44 current race cards used for application regression testing.

## Reproduce

```bash
python -m pip install requests beautifulsoup4 numpy scipy
python scripts/model-research/collect.py --end 20260910
python scripts/model-research/train.py --input training/history.jsonl --output data
```

The `Train KRA historical model` GitHub Actions workflow performs these steps and preserves the compressed dataset, source manifest, fitted coefficients and evaluation report on `main`. Model outputs are not automatically promoted to the Pages branch.

## Data and evaluation boundaries

- Source: the official `dacom11` daily result downloads linked by `https://race.kra.co.kr/dbdata/textDataList.do`.
- Collection starts January 2024. This first year is historical warm-up.
- Training: January 2025–May 2026.
- Validation for regularization selection: June 1–July 15, 2026.
- Final test, excluded from training and regularization selection: July 16–September 10, 2026.
- All horses in a race stay in the same split. Features use races on strictly earlier dates, including earlier test-period results when they would already have been known. Model weights remain fixed throughout testing.
- Features use declared rating, burden and published body weight plus earlier horse/jockey/trainer records. The same race's finish, final odds, sectional times and prize money are not inputs.
- Input order is sorted by horse number. Finish order cannot break ties in the model's favor.
- Race date, distinct starter numbers, complete finish sequence and official place payout winners must agree. Ambiguous/DNF/DQ/dead-heat fields are excluded and recorded in the manifest.

## Model and promotion

A regularized linear Plackett–Luce model is fitted to the first three finishers. Ten feature formulas match the browser's feature extraction. The original hand-weighted v4 model is the comparator, evaluated on the same reconstructed historical records.

The report includes all-eligible-race top-choice place and quinella-place hit rates, place-probability Brier score, per-venue results, and a paired bootstrap resampling entire dates. Promotion requires both aggregate hit rates to be no worse, a better Brier score, and a positive lower 95% bootstrap bound for the mean of the two hit-rate improvements. Venue activation additionally requires at least 100 final-test races and non-degradation of both hit rates and Brier score at that venue.

The final test is a one-time acceptance check, not another optimization set. Do not repeatedly adjust features against it. Reserve a later untouched period for future changes. Newly fitted outputs remain candidates until the evaluation is inspected.

## Limits

This is a historical replay, not a prospective validation of the live site. Historical records are reconstructed using earlier available reports; current KRA aggregates may use different reporting windows. Horse identity uses venue and name, so renames are not linked. Distance history begins at the collection start, not at each horse's birth. Excluding ambiguous result fields narrows the evaluated population. Abstention rules and betting returns are not validated by this report. Displayed probability improvements do not establish a profitable betting strategy.

The source manifest and SHA-256 dataset checksum support auditing the reported counts. The number of horse starts must never be presented as the number of independent races.
