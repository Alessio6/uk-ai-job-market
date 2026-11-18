"""Consistent chart style + a few reusable chart builders for the analysis notebook."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
import seaborn as sns

from uk_ai_job_market.config import FIGURES_DIR

PRIMARY = "#1f4e79"
ACCENT = "#d95f02"
SOURCE_NOTE = "Source: Adzuna API job postings, UK"


def set_style() -> None:
    sns.set_theme(style="whitegrid", context="notebook")
    plt.rcParams.update(
        {
            "figure.figsize": (9, 5.5),
            "figure.dpi": 110,
            "savefig.dpi": 200,
            "savefig.bbox": "tight",
            "axes.titlesize": 14,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "font.size": 11,
        }
    )


def gbp_k(ax, axis: str = "x") -> None:
    """Format an axis as £k."""
    fmt = mticker.FuncFormatter(lambda v, _: f"£{v / 1000:,.0f}k")
    (ax.xaxis if axis == "x" else ax.yaxis).set_major_formatter(fmt)


def footnote(fig, n: int | None = None, extra: str = "") -> None:
    """Source line + sample size at the bottom of every chart (always report n)."""
    parts = [SOURCE_NOTE]
    if n is not None:
        parts.append(f"n = {n:,} postings")
    if extra:
        parts.append(extra)
    fig.text(0.01, -0.02, " · ".join(parts), ha="left", va="top", fontsize=9, color="grey")


def save(fig, name: str, folder: Path = FIGURES_DIR) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.png"
    fig.savefig(path)
    return path


def barh_pct(data: pd.DataFrame, label: str, value: str = "pct", title: str = "", n: int | None = None, top: int = 20):
    """Horizontal bar chart of percentages, largest at the top."""
    d = data.nlargest(top, value).iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, max(4, 0.32 * len(d) + 1)))
    ax.barh(d[label], d[value], color=PRIMARY)
    ax.xaxis.set_major_formatter(mticker.PercentFormatter(decimals=0))
    ax.set_xlabel("% of postings")
    ax.set_ylabel("")
    ax.set_title(title)
    footnote(fig, n)
    return fig, ax


def ci_dotplot(
    data: pd.DataFrame,
    label: str,
    mid: str = "median",
    lo: str = "ci_low",
    hi: str = "ci_high",
    title: str = "",
    money: bool = True,
    zero_line: bool = False,
):
    """Point estimate with 95% CI whiskers; one row per group. Shows n next to each label if present."""
    d = data.sort_values(mid).reset_index(drop=True)
    labels = d[label].astype(str)
    if "n" in d:
        labels = labels + "  (n=" + d["n"].map("{:,}".format) + ")"
    elif "n_with" in d:
        labels = labels + "  (n=" + d["n_with"].map("{:,}".format) + ")"
    fig, ax = plt.subplots(figsize=(9, max(4, 0.35 * len(d) + 1)))
    ax.errorbar(
        d[mid],
        range(len(d)),
        xerr=[d[mid] - d[lo], d[hi] - d[mid]],
        fmt="o",
        color=PRIMARY,
        ecolor="#9bb5cf",
        elinewidth=3,
        capsize=0,
    )
    ax.set_yticks(range(len(d)), labels)
    if zero_line:
        ax.axvline(0, color="grey", lw=1, ls="--")
    if money:
        gbp_k(ax, "x")
    ax.set_title(title)
    footnote(fig, extra="bars = 95% bootstrap CI")
    return fig, ax
