#!/usr/bin/env python3
"""
stats.py

A clean, modular, well-documented statistical toolkit aligned with 
"Fundamentals of Statistical Reasoning in Education" (Coladarci et al.).

Designed for EduPulse radio analysis validation and PhD dissertation research.

Core principles:
- Accuracy: Matches textbook mathematical definitions and standard procedures.
- Repeatability: Deterministic results on same input.
- Pipeline-friendly: Pandas-centric, returns structured dicts/DataFrames easy to log, 
  serialize, compare across thresholds/days, and embed in reports.
- Minimal dependencies: pandas, numpy, scipy.stats, pingouin (preferred for rich tables), 
  statsmodels (for detailed models/power), matplotlib/seaborn (viz only).

Usage in EduPulse:
- Validation: chi-square for auto vs human category agreement (Ch. 18), 
  paired t-test for human vs auto duration bias (Ch. 12), usable yield CIs (Ch. 7/12).
- Substantive: category frequency tables over time, time-since-lunch effects on load 
  (ANOVA or t on rates/durations), correlation between acoustic features and incidents.
- All functions support DataFrames from manifests, sidecars, or validation CSVs.

See validate_edupulse.py for integration patterns.

When textbook shows explicit steps (e.g. expected frequencies, sum of squares), 
thin wrappers expose intermediates while delegating reliable computation to libraries.

=============================================================================
USAGE FOR EDUPULSE VALIDATION & ANALYSES (with concrete examples)
=============================================================================

This module is meant to be imported in your validation and analysis scripts.
All functions accept pandas DataFrames (from your JSONL manifests, sidecars,
or validation/aligned_validation_data.csv etc.) and return dicts or DataFrames
ready for reports, JSON logging, or further processing.

Quick examples using real project data patterns:

import pandas as pd
import textbook_stats as ts

# Load validation data or processed sidecars
df = pd.read_csv("validation/aligned_validation_data.csv")

# 1. Category agreement (Chi-square test of independence, Ch. 18)
#    Perfect for auto vs human category validation
cat_result = ts.category_agreement_chi2(df, "auto_category", "human_category")
print(cat_result)
# {'test': 'chi_square_independence', 'statistic': 33.5961, 'df': 12.0,
#  'p_value': 0.000781, 'effect_size': {'cramers_v': 0.5916}, ...}

# 2. Duration bias (paired t-test, Ch. 13)
#    Human-coded vs auto-extracted durations
dur_result = ts.duration_bias_paired_ttest(df)
print(dur_result)

# 3. Time-since-lunch / time-of-day effects
#    Bin by hour from start_iso, then ANOVA or t-test on duration or acoustic load
df["hour"] = pd.to_datetime(df["start_iso"]).dt.hour
df["time_bin"] = df["hour"].apply(lambda h: "AM" if h < 12 else "PM")
time_anova = ts.one_way_anova(df, "auto_duration_sec", "time_bin")
print(time_anova)

# 4. Usable yield with CI (Ch. 7/12)
yield_ci = ts.usable_yield_ci(n_total=151, n_usable=120, confidence=0.95)
print(yield_ci)

# 5. Descriptives + correlation on acoustic features
#    (load from sidecars or merged data)
desc = ts.descriptive_stats(df, ["whisper_conf", "auto_duration_sec"])
corr = ts.pearson_correlation(df["auto_duration_sec"], df["whisper_conf"])
print(desc, corr)

# 6. Frequency tables for categories over time (Ch. 2-3)
freq = ts.frequency_table(df, "auto_category")
print(freq.head())

See the function docstrings for full parameter options and textbook chapter references.
For batch work on many days/thresholds, pass DataFrames built from your manifests.
"""

from __future__ import annotations
import warnings
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

# Core reliable engines
import scipy.stats as sp_stats

# Rich educational output (effect sizes, CIs, power) - preferred for dissertation tables
try:
    import pingouin as pg
    _HAS_PINGOUIN = True
except ImportError:
    _HAS_PINGOUIN = False
    warnings.warn("pingouin not available; falling back to scipy for some rich outputs. "
                  "Install with: pip install pingouin")

# Detailed modeling, power, formulas
try:
    import statsmodels.stats.power as sm_power
    import statsmodels.stats.proportion as sm_prop
    from statsmodels.formula.api import ols
    import statsmodels.api as sm
    _HAS_STATSMODELS = True
except ImportError:
    _HAS_STATSMODELS = False
    warnings.warn("statsmodels not available; some power/CI details limited.")

# Viz (optional, keep light)
try:
    import matplotlib.pyplot as plt
    import seaborn as sns
    _HAS_VIZ = True
except ImportError:
    _HAS_VIZ = False


# =============================================================================
# OUTPUT STANDARDIZATION (for pipeline logging, reports, comparison)
# =============================================================================

def _standard_result(
    test_name: str,
    statistic: float,
    df: Optional[Union[int, Tuple[int, int]]] = None,
    p_value: Optional[float] = None,
    effect_size: Optional[Dict[str, float]] = None,
    ci: Optional[Tuple[float, float]] = None,
    n: Optional[int] = None,
    **extras: Any
) -> Dict[str, Any]:
    """
    Standardize all test outputs for easy comparison, serialization, and reporting.
    Follows textbook reporting: stat, df, p, effect size, CI where applicable.
    """
    result = {
        "test": test_name,
        "statistic": round(statistic, 4) if isinstance(statistic, (int, float)) else statistic,
        "df": df,
        "p_value": round(p_value, 6) if p_value is not None else None,
        "n": n,
    }
    if effect_size:
        result["effect_size"] = {k: round(v, 4) for k, v in effect_size.items()}
    if ci:
        result["ci_low"] = round(ci[0], 4)
        result["ci_high"] = round(ci[1], 4)
    result.update({k: v for k, v in extras.items() if v is not None})
    return result


# =============================================================================
# DESCRIPTIVE STATISTICS (Ch. 2-5: distributions, central tendency, variability)
# =============================================================================

def frequency_table(
    df: pd.DataFrame,
    column: str,
    normalize: bool = True,
    sort: bool = True
) -> pd.DataFrame:
    """
    Textbook-style frequency distribution (absolute, relative, cumulative).

    Matches Ch. 2-3 procedures for categorical or binned continuous data.
    Returns DataFrame with columns: category, frequency, relative_frequency, 
    percent, cumulative_frequency, cumulative_percent.

    For EduPulse: category frequencies (Logistics, Discipline, etc.) by day or time bin.
    """
    if column not in df.columns:
        raise ValueError(f"Column {column} not in DataFrame")

    freq = df[column].value_counts(dropna=False)
    if sort:
        freq = freq.sort_values(ascending=False)

    table = pd.DataFrame({
        "category": freq.index,
        "frequency": freq.values
    })

    if normalize:
        n = len(df)
        table["relative_frequency"] = table["frequency"] / n
        table["percent"] = table["relative_frequency"] * 100
        table["cumulative_frequency"] = table["frequency"].cumsum()
        table["cumulative_percent"] = (table["cumulative_frequency"] / n * 100).round(2)

    table["frequency"] = table["frequency"].astype(int)
    return table.reset_index(drop=True)


def descriptive_stats(
    df: pd.DataFrame,
    columns: Optional[List[str]] = None,
    include: str = "numeric"
) -> pd.DataFrame:
    """
    Central tendency + variability (Ch. 4-5).

    Returns DataFrame with: count, mean, median, mode (approx), std, var, 
    min, max, range, IQR, 25%, 75%, skewness, kurtosis (where applicable).

    For acoustic features (speech_ratio, onset_rate, duration) or durations in validation.
    """
    if columns is None:
        if include == "numeric":
            columns = df.select_dtypes(include=[np.number]).columns.tolist()
        else:
            columns = df.columns.tolist()

    stats_list = []
    for col in columns:
        if col not in df.columns:
            continue
        s = df[col].dropna()
        if len(s) == 0:
            continue

        q1, q3 = s.quantile([0.25, 0.75])
        iqr = q3 - q1

        desc = {
            "variable": col,
            "n": len(s),
            "mean": round(s.mean(), 4),
            "median": round(s.median(), 4),
            "std": round(s.std(ddof=1), 4),  # sample sd (textbook default)
            "variance": round(s.var(ddof=1), 4),
            "min": round(s.min(), 4),
            "max": round(s.max(), 4),
            "range": round(s.max() - s.min(), 4),
            "iqr": round(iqr, 4),
            "q25": round(q1, 4),
            "q75": round(q3, 4),
        }

        # Mode (first most frequent for multimodal)
        try:
            mode_val = s.mode().iloc[0]
            desc["mode"] = round(mode_val, 4) if isinstance(mode_val, (int, float)) else mode_val
        except:
            desc["mode"] = None

        if len(s) > 2:
            desc["skew"] = round(s.skew(), 4)
            desc["kurtosis"] = round(s.kurtosis(), 4)

        stats_list.append(desc)

    return pd.DataFrame(stats_list)


# =============================================================================
# BIVARIATE RELATIONSHIPS (Ch. 6-8: correlation, regression)
# =============================================================================

def pearson_correlation(
    x: pd.Series,
    y: pd.Series,
    alternative: str = "two-sided"
) -> Dict[str, Any]:
    """
    Pearson r (Ch. 6-7) with significance test and CI (large n approx via z or pingouin).

    Returns r, p, n, ci (if possible), r_squared.
    Uses scipy + pingouin for CI when available.
    """
    x = pd.to_numeric(x, errors="coerce").dropna()
    y = pd.to_numeric(y, errors="coerce").dropna()
    common = x.index.intersection(y.index)
    x, y = x.loc[common], y.loc[common]

    if len(x) < 3:
        return _standard_result("pearson_correlation", np.nan, n=len(x), p_value=np.nan)

    if _HAS_PINGOUIN:
        res = pg.corr(x, y, method="pearson", alternative=alternative)
        r = res["r"].iloc[0]
        p = res["p-val"].iloc[0]
        ci_low, ci_high = res["CI95%"].iloc[0]
    else:
        r, p = sp_stats.pearsonr(x, y)
        # Fisher z approx for CI
        z = np.arctanh(r)
        se = 1 / np.sqrt(len(x) - 3)
        z_crit = sp_stats.norm.ppf(1 - 0.025) if alternative == "two-sided" else sp_stats.norm.ppf(1 - 0.05)
        ci_low = np.tanh(z - z_crit * se)
        ci_high = np.tanh(z + z_crit * se)

    return _standard_result(
        "pearson_correlation",
        r,
        p_value=p,
        effect_size={"r_squared": round(r**2, 4)},
        ci=(ci_low, ci_high),
        n=len(x),
        alternative=alternative,
    )


def simple_linear_regression(
    df: pd.DataFrame,
    x_col: str,
    y_col: str
) -> Dict[str, Any]:
    """
    Simple linear regression (Ch. 8): slope, intercept, predictions, residuals, r2.

    Textbook style: uses OLS, reports b, a, r2, residual stats.
    """
    data = df[[x_col, y_col]].dropna()
    x = data[x_col].values
    y = data[y_col].values

    if len(x) < 3:
        raise ValueError("Need at least 3 observations for regression")

    # Use statsmodels for full textbook-aligned table if available
    if _HAS_STATSMODELS:
        X = sm.add_constant(x)
        model = sm.OLS(y, X).fit()
        slope = model.params[1]
        intercept = model.params[0]
        r2 = model.rsquared
        resid = model.resid
        summary = {
            "slope": round(slope, 6),
            "intercept": round(intercept, 6),
            "r_squared": round(r2, 4),
            "n": len(x),
            "residual_mean": round(resid.mean(), 4),
            "residual_std": round(resid.std(ddof=1), 4),
        }
    else:
        slope, intercept, r_value, _, _ = sp_stats.linregress(x, y)
        r2 = r_value**2
        y_pred = slope * x + intercept
        resid = y - y_pred
        summary = {
            "slope": round(slope, 6),
            "intercept": round(intercept, 6),
            "r_squared": round(r2, 4),
            "n": len(x),
            "residual_mean": round(resid.mean(), 4),
            "residual_std": round(resid.std(ddof=1), 4),
        }

    summary["predictions"] = (slope * data[x_col] + intercept).round(4).tolist()[:5]  # sample
    return summary


# =============================================================================
# INFERENTIAL TESTS (Ch. 9-18)
# =============================================================================

def one_sample_ttest(
    data: pd.Series,
    popmean: float = 0.0,
    alternative: str = "two-sided"
) -> Dict[str, Any]:
    """One-sample t-test (Ch. 11, σ unknown). Returns t, df, p, d, CI."""
    data = pd.to_numeric(data, errors="coerce").dropna()
    if _HAS_PINGOUIN:
        res = pg.ttest(data, popmean, alternative=alternative)
        p_key = 'p-val' if 'p-val' in res.columns else 'pval'
        return _standard_result(
            "one_sample_ttest",
            res["T"].iloc[0],
            df=int(res["dof"].iloc[0]),
            p_value=res[p_key].iloc[0],
            effect_size={"cohen_d": res["cohen-d"].iloc[0]},
            ci=(res["CI95%"].iloc[0][0], res["CI95%"].iloc[0][1]),
            n=len(data),
        )
    else:
        t, p = sp_stats.ttest_1samp(data, popmean, alternative=alternative)
        d = (data.mean() - popmean) / data.std(ddof=1)
        return _standard_result("one_sample_ttest", t, df=len(data)-1, p_value=p, effect_size={"cohen_d": round(d, 4)}, n=len(data))


def independent_ttest(
    group1: pd.Series,
    group2: pd.Series,
    equal_var: bool = False,
    alternative: str = "two-sided"
) -> Dict[str, Any]:
    """Independent samples t-test (Ch. 12)."""
    g1 = pd.to_numeric(group1, errors="coerce").dropna()
    g2 = pd.to_numeric(group2, errors="coerce").dropna()
    if _HAS_PINGOUIN:
        res = pg.ttest(g1, g2, paired=False, alternative=alternative, correction=not equal_var)
        return _standard_result(
            "independent_ttest",
            res["T"].iloc[0],
            df=res["dof"].iloc[0],
            p_value=res["p-val"].iloc[0],
            effect_size={"cohen_d": res["cohen-d"].iloc[0]},
            ci=(res["CI95%"].iloc[0][0], res["CI95%"].iloc[0][1]),
            n1=len(g1), n2=len(g2),
        )
    else:
        t, p = sp_stats.ttest_ind(g1, g2, equal_var=equal_var, alternative=alternative)
        d = (g1.mean() - g2.mean()) / np.sqrt(((len(g1)-1)*g1.var(ddof=1) + (len(g2)-1)*g2.var(ddof=1)) / (len(g1)+len(g2)-2))
        return _standard_result("independent_ttest", t, df=len(g1)+len(g2)-2, p_value=p, effect_size={"cohen_d": round(d, 4)}, n1=len(g1), n2=len(g2))


def paired_ttest(
    before: pd.Series,
    after: pd.Series,
    alternative: str = "two-sided"
) -> Dict[str, Any]:
    """Dependent/paired t-test (Ch. 13, e.g. human vs auto duration in validation)."""
    b = pd.to_numeric(before, errors="coerce").dropna()
    a = pd.to_numeric(after, errors="coerce").dropna()
    common = b.index.intersection(a.index)
    b, a = b.loc[common], a.loc[common]
    if _HAS_PINGOUIN:
        res = pg.ttest(b, a, paired=True, alternative=alternative)
        p_key = 'p_val' if 'p_val' in res.columns else ('p-val' if 'p-val' in res.columns else 'pval')
        ci_key = 'CI95' if 'CI95' in res.columns else 'CI95%'
        return _standard_result(
            "paired_ttest",
            res["T"].iloc[0],
            df=int(res["dof"].iloc[0]),
            p_value=res[p_key].iloc[0],
            effect_size={"cohen_d": res["cohen_d"].iloc[0]},
            ci=(res[ci_key].iloc[0][0], res[ci_key].iloc[0][1]) if pd.notna(res[ci_key].iloc[0][0]) else None,
            n=len(b),
        )
    else:
        t, p = sp_stats.ttest_rel(b, a, alternative=alternative)
        diff = b - a
        d = diff.mean() / diff.std(ddof=1)
        return _standard_result("paired_ttest", t, df=len(b)-1, p_value=p, effect_size={"cohen_d": round(d, 4)}, n=len(b))


def one_way_anova(
    df: pd.DataFrame,
    dv: str,
    between: str
) -> Dict[str, Any]:
    """One-way ANOVA (Ch. 15). Returns F, df, p, eta-squared if pingouin available."""
    data = df[[dv, between]].dropna()
    if _HAS_PINGOUIN:
        res = pg.anova(data=data, dv=dv, between=between, detailed=True)
        return _standard_result(
            "one_way_anova",
            res["F"].iloc[0],
            df=(int(res["ddof1"].iloc[0]), int(res["ddof2"].iloc[0])),
            p_value=res["p-unc"].iloc[0],
            effect_size={"eta_squared": res["np2"].iloc[0] if "np2" in res else None},
            n=len(data),
        )
    else:
        groups = [g[dv].values for _, g in data.groupby(between)]
        f, p = sp_stats.f_oneway(*groups)
        return _standard_result("one_way_anova", f, df=(len(groups)-1, len(data)-len(groups)), p_value=p, n=len(data))


def chi_square_goodness_of_fit(
    observed: Union[pd.Series, List[int]],
    expected: Optional[Union[pd.Series, List[float]]] = None,
    categories: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Chi-square goodness-of-fit (Ch. 17).
    If expected=None, assumes equal proportions (textbook default for many cases).
    """
    obs = pd.Series(observed).value_counts().sort_index()
    if expected is None:
        exp = np.full(len(obs), obs.sum() / len(obs))
    else:
        exp = np.array(expected) * (obs.sum() / sum(expected))  # scale if proportions

    chi2, p = sp_stats.chisquare(f_obs=obs.values, f_exp=exp)
    dof = len(obs) - 1
    return _standard_result(
        "chi_square_goodness_of_fit",
        chi2,
        df=dof,
        p_value=p,
        effect_size={"cramers_v": None},  # GOF often doesn't use
        observed=obs.to_dict(),
        expected=dict(zip(obs.index, np.round(exp, 2))),
    )


def chi_square_independence(
    df: pd.DataFrame,
    row_var: str,
    col_var: str,
    correction: bool = True
) -> Dict[str, Any]:
    """
    Chi-square test of independence (Ch. 18) for category agreement (auto vs human).
    Returns observed, expected tables, chi2, p, dof, Cramer's V (effect size).
    """
    table = pd.crosstab(df[row_var], df[col_var])
    if _HAS_PINGOUIN:
        # pingouin gives nice observed/expected
        expected, observed, stats = pg.chi2_independence(df, row_var, col_var, correction=correction)
        chi2 = stats["chi2"].iloc[0]
        p = stats["pval"].iloc[0]
        dof = stats["dof"].iloc[0]
        # Cramer's V
        n = table.sum().sum()
        k = min(table.shape) - 1
        v = np.sqrt(chi2 / (n * k))
    else:
        chi2, p, dof, expected = sp_stats.chi2_contingency(table, correction=correction)
        n = table.sum().sum()
        k = min(table.shape) - 1
        v = np.sqrt(chi2 / (n * k))
        observed = table
        expected = pd.DataFrame(expected, index=table.index, columns=table.columns)

    return _standard_result(
        "chi_square_independence",
        chi2,
        df=dof,
        p_value=p,
        effect_size={"cramers_v": round(v, 4)},
        observed_table=observed.to_dict() if hasattr(observed, "to_dict") else observed,
        expected_table=expected.round(2).to_dict() if hasattr(expected, "to_dict") else expected,
        n=n,
    )


def correlation_significance(
    r: float,
    n: int,
    method: str = "pearson",
    alternative: str = "two-sided"
) -> Dict[str, Any]:
    """
    Test significance of Pearson r (Ch. 7/19 inference about correlation).
    Uses Fisher z transform for p-value (textbook procedure).
    """
    if n < 3:
        return _standard_result("correlation_significance", r, n=n, p_value=np.nan)
    z = 0.5 * np.log((1 + r) / (1 - r))
    se = 1 / np.sqrt(n - 3)
    z_crit = sp_stats.norm.ppf(1 - 0.025) if alternative == "two-sided" else sp_stats.norm.ppf(1 - 0.05)
    if alternative == "two-sided":
        p = 2 * (1 - sp_stats.norm.cdf(abs(z) / se))
    else:
        p = 1 - sp_stats.norm.cdf(z / se)
    return _standard_result(
        f"{method}_r_significance",
        r,
        p_value=p,
        n=n,
        effect_size={"r_squared": round(r**2, 4)},
    )


# =============================================================================
# ESTIMATION (Ch. 7, 12, 13: CIs)
# =============================================================================

def confidence_interval_mean(
    data: pd.Series,
    confidence: float = 0.95
) -> Dict[str, Any]:
    """CI for mean (Ch. 7). Uses t or z depending on n (pingouin preferred)."""
    data = pd.to_numeric(data, errors="coerce").dropna()
    if _HAS_PINGOUIN:
        res = pg.mean(data, confidence=confidence)
        return {
            "mean": round(res["mean"].iloc[0], 4),
            "ci_low": round(res["CI95%"].iloc[0][0], 4),
            "ci_high": round(res["CI95%"].iloc[0][1], 4),
            "n": len(data),
        }
    else:
        m = data.mean()
        se = data.std(ddof=1) / np.sqrt(len(data))
        t_crit = sp_stats.t.ppf((1 + confidence) / 2, len(data) - 1)
        return {
            "mean": round(m, 4),
            "ci_low": round(m - t_crit * se, 4),
            "ci_high": round(m + t_crit * se, 4),
            "n": len(data),
        }


def confidence_interval_proportion(
    count: int,
    nobs: int,
    confidence: float = 0.95
) -> Dict[str, Any]:
    """CI for proportion (usable yield, Ch. 7/12). Wilson or normal approx."""
    if _HAS_STATSMODELS:
        ci_low, ci_high = sm_prop.proportion_confint(count, nobs, alpha=1-confidence, method="wilson")
    else:
        p = count / nobs
        se = np.sqrt(p * (1 - p) / nobs)
        z = sp_stats.norm.ppf((1 + confidence) / 2)
        ci_low, ci_high = p - z * se, p + z * se
    return {
        "proportion": round(count / nobs, 4),
        "ci_low": round(ci_low, 4),
        "ci_high": round(ci_high, 4),
        "n": nobs,
        "count": count,
    }


# =============================================================================
# POWER (basic, Ch. 19/appendix)
# =============================================================================

def power_one_sample_ttest(
    effect_size: float,
    nobs: int,
    alpha: float = 0.05,
    alternative: str = "two-sided"
) -> float:
    """Basic power for one-sample t (using statsmodels if available)."""
    if _HAS_STATSMODELS:
        return sm_power.tt_solve_power(effect_size, nobs=nobs, alpha=alpha, alternative=alternative)
    # Fallback approximation (very basic)
    return np.nan  # encourage install


# =============================================================================
# NONPARAMETRIC (Epilogue)
# =============================================================================

def spearman_correlation(x: pd.Series, y: pd.Series) -> Dict[str, Any]:
    """Spearman's rho (rank correlation, nonparametric)."""
    x = pd.to_numeric(x, errors="coerce").dropna()
    y = pd.to_numeric(y, errors="coerce").dropna()
    common = x.index.intersection(y.index)
    rho, p = sp_stats.spearmanr(x.loc[common], y.loc[common])
    return _standard_result("spearman_correlation", rho, p_value=p, n=len(common))


def mann_whitney_u(group1: pd.Series, group2: pd.Series) -> Dict[str, Any]:
    """Mann-Whitney U (nonparametric independent groups)."""
    u, p = sp_stats.mannwhitneyu(group1.dropna(), group2.dropna(), alternative="two-sided")
    return _standard_result("mann_whitney_u", u, p_value=p, n1=len(group1.dropna()), n2=len(group2.dropna()))


# =============================================================================
# EDUPULSE-SPECIFIC CONVENIENCE WRAPPERS (validation & time analyses)
# =============================================================================

def category_agreement_chi2(
    df: pd.DataFrame,
    auto_col: str = "auto_category",
    human_col: str = "human_category"
) -> Dict[str, Any]:
    """
    Convenience for validation: chi-square test of independence between 
    automated and human categories (Ch. 18).
    """
    return chi_square_independence(df, auto_col, human_col)


def duration_bias_paired_ttest(
    df: pd.DataFrame,
    human_col: str = "human_duration_sec",
    auto_col: str = "auto_duration_sec"
) -> Dict[str, Any]:
    """
    Convenience for validation: paired t-test on human vs auto durations 
    (bias analysis, Ch. 13). Works with validation CSVs (prefixed columns) 
    or raw sidecar DataFrames.
    Falls back to common column names if exact match not found.
    """
    # Robust column lookup for different data sources
    h_col = human_col if human_col in df.columns else next((c for c in df.columns if 'human' in c.lower() and 'duration' in c.lower()), None)
    a_col = auto_col if auto_col in df.columns else next((c for c in df.columns if 'duration' in c.lower() and 'human' not in c.lower()), None)
    if not h_col or not a_col:
        raise KeyError(f"Could not find duration columns. Available: {list(df.columns)[:10]}...")
    return paired_ttest(df[h_col], df[a_col])


def usable_yield_ci(
    n_total: int,
    n_usable: int,
    confidence: float = 0.95
) -> Dict[str, Any]:
    """Usable yield proportion with textbook-aligned CI (Ch. 7/12)."""
    return confidence_interval_proportion(n_usable, n_total, confidence)


# Example runner for EduPulse data
# =============================================================================
# MINIMAL CLI (for shell batch use + future man page)
# Run as: python -m textbook_stats <command> [options]
# This makes the toolkit usable from the command line for quick validation
# runs, and positions it for a proper man page if desired.
# =============================================================================

def main():
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="textbook_stats",
        description="Textbook-aligned statistical toolkit (Coladarci et al.). "
                    "Use for EduPulse validation (chi-square category agreement, "
                    "paired t-tests on durations, yield CIs, time-bin analyses) "
                    "and dissertation reporting. Matches textbook procedures exactly.",
        epilog="Examples:\n"
               "  python -m textbook_stats chi2 --input validation/aligned_validation_data.csv "
               "--row auto_category --col human_category\n"
               "  python -m textbook_stats paired-ttest --input validation/aligned_validation_data.csv "
               "--before human_duration_sec --after auto_duration_sec\n"
               "  python -m textbook_stats yield-ci --count 120 --nobs 151\n\n"
               "For full power use the Python API: import textbook_stats as ts"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Chi-square for category agreement (most common validation use)
    p_chi2 = subparsers.add_parser("chi2", help="Chi-square test of independence (Ch. 18)")
    p_chi2.add_argument("--input", required=True, help="CSV or JSONL file")
    p_chi2.add_argument("--row", default="auto_category", help="Row variable (e.g. auto_category)")
    p_chi2.add_argument("--col", default="human_category", help="Column variable (e.g. human_category)")
    p_chi2.add_argument("--format", default="human", choices=["human", "json"], help="Output format")

    # Paired t-test for duration bias (common in validation)
    p_paired = subparsers.add_parser("paired-ttest", help="Paired t-test (Ch. 13, e.g. human vs auto duration)")
    p_paired.add_argument("--input", required=True)
    p_paired.add_argument("--before", default="human_duration_sec")
    p_paired.add_argument("--after", default="auto_duration_sec")
    p_paired.add_argument("--format", default="human", choices=["human", "json"])

    # One-way ANOVA (time bins, category load, etc.)
    p_anova = subparsers.add_parser("anova", help="One-way ANOVA (Ch. 15)")
    p_anova.add_argument("--input", required=True)
    p_anova.add_argument("--dv", required=True, help="Dependent variable (e.g. duration_sec)")
    p_anova.add_argument("--between", required=True, help="Grouping variable (e.g. time_bin or category)")
    p_anova.add_argument("--format", default="human", choices=["human", "json"])

    # Usable yield CI
    p_yield = subparsers.add_parser("yield-ci", help="Confidence interval for proportion (Ch. 7/12)")
    p_yield.add_argument("--count", type=int, required=True, help="Number of usable events")
    p_yield.add_argument("--nobs", type=int, required=True, help="Total events")
    p_yield.add_argument("--confidence", type=float, default=0.95)
    p_yield.add_argument("--format", default="human", choices=["human", "json"])

    # Descriptive stats
    p_desc = subparsers.add_parser("describe", help="Descriptive statistics (Ch. 4-5)")
    p_desc.add_argument("--input", required=True)
    p_desc.add_argument("--columns", nargs="+", default=["duration_sec", "whisper_conf"])
    p_desc.add_argument("--format", default="human", choices=["human", "json"])

    args = parser.parse_args()

    try:
        df = pd.read_csv(args.input) if hasattr(args, "input") and args.input else None
    except Exception:
        df = None

    if args.command == "chi2":
        if df is None:
            print("Error: --input required for chi2")
            sys.exit(1)
        res = chi_square_independence(df, args.row, args.col)
        if args.format == "json":
            print(pd.Series(res).to_json())
        else:
            print(f"Chi-square independence: χ²({res.get('df')}) = {res.get('statistic'):.3f}, "
                  f"p = {res.get('p_value'):.4f}, Cramér's V = {res.get('effect_size',{}).get('cramers_v')}")
            if "observed_table" in res:
                print("Observed table available in full output (use --format json for details)")

    elif args.command == "paired-ttest":
        if df is None:
            print("Error: --input required")
            sys.exit(1)
        res = paired_ttest(df[args.before], df[args.after])
        if args.format == "json":
            print(pd.Series(res).to_json())
        else:
            print(f"Paired t-test: t({res.get('df')}) = {res.get('statistic'):.3f}, "
                  f"p = {res.get('p_value'):.4f}, Cohen's d = {res.get('effect_size',{}).get('cohen_d')}")

    elif args.command == "anova":
        if df is None:
            print("Error: --input required")
            sys.exit(1)
        res = one_way_anova(df, args.dv, args.between)
        if args.format == "json":
            print(pd.Series(res).to_json())
        else:
            print(f"One-way ANOVA: F({res.get('df')}) = {res.get('statistic'):.3f}, "
                  f"p = {res.get('p_value'):.4f}")

    elif args.command == "yield-ci":
        res = confidence_interval_proportion(args.count, args.nobs, args.confidence)
        if args.format == "json":
            print(pd.Series(res).to_json())
        else:
            print(f"Proportion = {res['proportion']:.4f}, "
                  f"{int(args.confidence*100)}% CI = [{res['ci_low']:.4f}, {res['ci_high']:.4f}]")

    elif args.command == "describe":
        if df is None:
            print("Error: --input required")
            sys.exit(1)
        res = descriptive_stats(df, args.columns)
        if args.format == "json":
            print(res.to_json(orient="records"))
        else:
            print(res.to_string(index=False))

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
