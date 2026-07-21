# stats(1) — Textbook-aligned statistical toolkit

**NAME**  
stats — Clean, modular, textbook-accurate statistics for hypothesis testing, estimation, and descriptive analysis (Coladarci et al., *Fundamentals of Statistical Reasoning in Education*).

**Note**: The module file is `stats.py` (import as `import stats`). The previous `textbook_stats.py` name was shortened at user request for convenience.

**SYNOPSIS**  
Python API (primary usage):  
```python
import stats as ts
import pandas as pd

df = pd.read_csv("validation/aligned_validation_data.csv")
res = ts.chi_square_independence(df, "auto_category", "human_category")
res = ts.paired_ttest(df["human_duration_sec"], df["auto_duration_sec"])
res = ts.one_way_anova(df, "auto_duration_sec", "time_bin")
ci  = ts.usable_yield_ci(n_total=151, n_usable=120)
```

CLI (for batch/pipeline work):  
```bash
python -m stats chi2 --input validation/aligned_validation_data.csv \
    --row auto_category --col human_category

python -m stats paired-ttest --input validation/aligned_validation_data.csv \
    --before human_duration_sec --after auto_duration_sec

python -m stats yield-ci --count 120 --nobs 151

python -m stats anova --input df.csv --dv duration_sec --between time_bin

python -m stats describe --input df.csv --columns duration_sec whisper_conf
```

**DESCRIPTION**  
`textbook_stats` provides a focused set of functions that implement the major procedures from the textbook using reliable open-source libraries (pandas, NumPy, scipy.stats, pingouin, statsmodels).  

All calculations follow textbook definitions and produce repeatable results. Functions return structured dictionaries or DataFrames suitable for logging, comparison across experimental conditions/thresholds, and direct inclusion in dissertation tables/figures.

The module is deliberately minimal and pipeline-oriented: it accepts pandas DataFrames (directly from EduPulse JSONL manifests, sidecar data, or validation CSVs) and returns outputs that are easy to serialize or embed.

Supported areas (textbook chapters referenced in docstrings):
- Descriptive statistics (Ch. 2–5)
- Bivariate relationships (Ch. 6–8)
- Inferential tests: one-sample z/t, independent & paired t, one-way ANOVA, χ² goodness-of-fit & independence, significance test on r (Ch. 9–18)
- Estimation / confidence intervals (Ch. 7, 12–13)
- Basic power analysis
- Nonparametric alternatives (Epilogue): Spearman, Mann–Whitney U

**OPTIONS (CLI)**  
See `python -m textbook_stats --help` for the current list.  
Common subcommands:
- `chi2` — χ² test of independence (category agreement)
- `paired-ttest` — Paired t-test (duration bias, etc.)
- `anova` — One-way ANOVA (time-bin or category effects)
- `yield-ci` — Proportion confidence interval (usable yield)
- `describe` — Descriptive statistics

**EXAMPLES (EduPulse / dissertation use cases)**

Category agreement (validation, Ch. 18):  
```bash
python -m textbook_stats chi2 \
  --input validation/aligned_validation_data.csv \
  --row auto_category --col human_category
```

Duration bias (Ch. 13):  
```bash
python -m textbook_stats paired-ttest \
  --input validation/aligned_validation_data.csv \
  --before human_duration_sec --after auto_duration_sec
```

Time-since-lunch effects (bin by hour from start_iso, then ANOVA on duration or acoustic load):  
```python
df = pd.read_csv("validation/aligned_validation_data.csv")
df["hour"] = pd.to_datetime(df["start_iso"]).dt.hour
df["time_bin"] = ["AM" if h < 12 else "PM" for h in df["hour"]]
print(ts.one_way_anova(df, "auto_duration_sec", "time_bin"))
```

Usable yield with CI (Ch. 7/12):  
```bash
python -m textbook_stats yield-ci --count 120 --nobs 151 --confidence 0.95
```

Acoustic feature descriptives + correlation (from sidecar-derived data):  
```python
desc = ts.descriptive_stats(df, ["speech_ratio", "onset_rate", "duration_sec"])
corr = ts.pearson_correlation(df["speech_ratio"], df["onset_rate"])
```

**PYTHON API**  
All functions are importable and return consistent dicts (with `statistic`, `df`, `p_value`, `effect_size`, `ci_low`/`ci_high`, `n`, plus test-specific keys such as `observed_table`/`expected_table` for χ²).

Key functions (see source docstrings for full signatures and chapter references):
- `frequency_table`, `descriptive_stats`
- `pearson_correlation`, `simple_linear_regression`
- `one_sample_ttest`, `independent_ttest`, `paired_ttest`
- `one_way_anova`
- `chi_square_goodness_of_fit`, `chi_square_independence`
- `correlation_significance`
- `confidence_interval_mean`, `confidence_interval_proportion`
- `power_one_sample_ttest`
- `spearman_correlation`, `mann_whitney_u`
- Convenience wrappers: `category_agreement_chi2`, `duration_bias_paired_ttest`, `usable_yield_ci`

**SEE ALSO**  
- Coladarci et al., *Fundamentals of Statistical Reasoning in Education* (the source textbook)
- `z_table_coladarci_appendix_c.py` (exact normal-curve lookups from the same textbook's Appendix C, Table A)
- EduPulse `validation/validate_edupulse.py` (integration examples)

**AUTHOR / CITATION**  
Generic, textbook-aligned toolkit written for reproducible dissertation research.  
Cite the module + the specific Coladarci chapter/procedure used.

**COPYRIGHT**  
The procedures and numerical expectations follow the referenced textbook. Library implementations are from the listed mature open-source packages.
