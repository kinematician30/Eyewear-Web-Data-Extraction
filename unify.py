"""
Unify the per-retailer scraper exports into one analysis-ready file.

Four jobs, done in this order, each in its own function:
  1. validate   - a file must match the agreed schema or it is reported and
                   skipped (never crashed on, never half-merged in silently)
  2. clean      - text normalised, prices coerced to numbers, discounts
                   turned into a numeric percentage, unusable rows dropped
  3. deduplicate- true repeats within a source removed; the same product
                   appearing on more than one source is labelled, not deleted
  4. attribute  - every row is stamped with its retailer, keeps its own
                   product link, and carries a collection date

Run with:  python unify.py
"""

import glob
import os
import re
from datetime import datetime

import pandas as pd

INPUT_DIR = "./extracted_data"
OUTPUT_CSV = os.path.join(INPUT_DIR, "unified_eyewear.csv")

# The contract every scraper is supposed to honour. Nothing below trusts a
# file until it has been checked against this list.
SCHEMA = ["source", "brand", "name", "former_price", "current_price",
          "discount", "product_link", "page"]

# The exact column set and order the output file must have, so app.py (and
# anything else downstream) always sees the same schema.
OUTPUT_COLUMNS = SCHEMA + ["discount_pct", "price_ok", "match_key",
                           "sold_by_n_sites", "savings", "on_sale", "scraped_at"]


# ============================================================ 1. VALIDATE ===
def load_valid_files(input_dir):
    """Read every *_data.csv, keep only the ones whose columns match SCHEMA."""
    files = []
    for path in sorted(glob.glob(os.path.join(input_dir, "*_data.csv"))):
        filename = os.path.basename(path)
        df = pd.read_csv(path)

        # MUST KNOW: set subtraction is the one-line way to ask "which
        # columns does SCHEMA expect that this dataframe doesn't have?"
        missing = set(SCHEMA) - set(df.columns)
        if missing:
            print(f"SKIPPED {filename}: missing columns {sorted(missing)}")
            continue

        print(f"loaded {filename}: {len(df)} rows")
        files.append((filename, df[SCHEMA].copy()))

    if not files:
        raise SystemExit(f"No valid scraper files found in {input_dir}")
    return files


# =============================================================== 2. CLEAN ===
def tidy_text(value):
    """Collapse repeated whitespace and strip edges; leave missing values as None."""
    if pd.isna(value):
        return None
    return re.sub(r"\s+", " ", str(value)).strip() or None


def discount_to_percent(value):
    """'30%' or '30% off' -> 30.0 ; missing or unparsable -> None."""
    if pd.isna(value):
        return None
    # MUST KNOW: pull the first number out of a messy text field with a
    # regex instead of chasing individual characters like "%" or "off".
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    return float(match.group()) if match else None


def clean(df):
    for col in ("brand", "name", "product_link"):
        df[col] = df[col].apply(tidy_text)

    # MUST KNOW: pd.to_numeric(..., errors="coerce") turns anything that
    # isn't a number into NaN instead of raising - the standard way to
    # force a column numeric when you don't fully trust the source.
    for col in ("former_price", "current_price"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["discount_pct"] = df["discount"].apply(discount_to_percent)

    # A row with no name and no price can't be filtered, sorted, or charted -
    # drop it rather than carrying dead weight into the merged file.
    before = len(df)
    df = df[df["name"].notna() & df["current_price"].notna()].copy()
    print(f"  dropped {before - len(df)} rows with no name or no current price")

    # Flag (don't drop) rows where the "was" price isn't actually above the
    # "now" price - that's bad data, not a real discount, and a human
    # should decide whether to trust the rest of the row.
    df["price_ok"] = ~(df["former_price"].notna()
                        & (df["former_price"] <= df["current_price"]))
    flagged = int((~df["price_ok"]).sum())
    if flagged:
        print(f"  flagged {flagged} rows where former_price <= current_price")

    return df


# ========================================================== 3. DEDUPLICATE ==
def deduplicate(df):
    # MUST KNOW: drop_duplicates(subset=...) removes exact repeats on a key,
    # keeping the first occurrence. product_link is unique per item on a
    # single site, so it's the natural within-source key.
    before = len(df)
    df = df.drop_duplicates(subset=["source", "product_link"], keep="first")
    print(f"dropped {before - len(df)} within-source duplicates")

    # The same frame can legitimately be sold by more than one retailer at a
    # different price - that's a comparison worth keeping, so it gets
    # labelled instead of removed.
    df["match_key"] = (df["brand"].fillna("").str.lower().str.strip() + "|"
                        + df["name"].fillna("").str.lower().str.strip())
    # MUST KNOW: groupby(...).nunique() + map() attaches a per-group count
    # back onto every row of that group, without collapsing the dataframe
    # the way groupby(...).agg() alone would.
    df["sold_by_n_sites"] = df["match_key"].map(
        df.groupby("match_key")["source"].nunique())
    multi = int((df["sold_by_n_sites"] > 1).sum())
    print(f"{multi} rows are products listed on more than one source")

    return df


# ============================================================= 4. ATTRIBUTE =
def attribute(filename, df, input_dir):
    """
    Stamp every row with which retailer it came from, confirm it still
    carries its own product link, and record when the file was collected.

    A scraper's own "source" column can be blank or wrong - that is exactly
    what happened to framesdirect_data.csv, whose source column was empty
    and so got dropped everywhere downstream. The filename is the one thing
    we control and trust, so it - not the column - is the source of truth.
    """
    # MUST KNOW: strip a known suffix off a filename with an anchored regex
    # ("_data" at the end) to recover a clean identifier from it.
    source_name = re.sub(r"_data$", "", os.path.splitext(filename)[0]).lower()
    df["source"] = source_name

    missing_link = int(df["product_link"].isna().sum())
    if missing_link:
        print(f"  WARNING {filename}: {missing_link} rows have no product_link")

    # Use the file's own last-modified time as its collection date, so
    # merging files scraped on different days doesn't misdate the old ones
    # as "today".
    collected_on = datetime.fromtimestamp(
        os.path.getmtime(os.path.join(input_dir, filename))
    ).strftime("%Y-%m-%d")
    df["scraped_at"] = collected_on

    return df


# ================================================================== MAIN ====
def main():
    print(f"Data unification run - {datetime.now():%Y-%m-%d %H:%M}")
    print("=" * 60)

    files = load_valid_files(INPUT_DIR)

    cleaned = []
    for filename, df in files:
        print(f"\n{filename}")
        df = clean(df)
        df = attribute(filename, df, INPUT_DIR)
        cleaned.append(df)

    # MUST KNOW: pd.concat stacks same-shaped dataframes into one - the
    # standard "combine many files into one table" move in pandas.
    data = pd.concat(cleaned, ignore_index=True)
    print(f"\ncombined: {len(data)} rows from {len(cleaned)} files")

    data = deduplicate(data)

    data["savings"] = (data["former_price"] - data["current_price"]).round(2)
    data["on_sale"] = data["former_price"].notna() & (data["former_price"] > data["current_price"])

    data = data.sort_values(["source", "brand", "name"]).reset_index(drop=True)

    # MUST KNOW: reindexing columns by an explicit list locks in the output
    # schema regardless of the order each step happened to add columns in -
    # anything reading this file can rely on that exact column set and order.
    data = data[OUTPUT_COLUMNS]

    data.to_csv(OUTPUT_CSV, index=False)
    print(f"\nwrote {len(data)} rows to {OUTPUT_CSV}")

    print("\n" + "=" * 60)
    print("QUALITY REPORT")
    print("=" * 60)

    print("\nRows per source")
    print(data["source"].value_counts().to_string())

    print("\nNull rate by column (%)")
    print((data[SCHEMA].isna().mean() * 100).round(1).to_string())

    print("\nCurrent price by source")
    print(data.groupby("source")["current_price"]
          .agg(["count", "min", "median", "max"]).round(2).to_string())

    print("\nShare on sale by source (%)")
    print((data.groupby("source")["on_sale"].mean() * 100).round(1).to_string())

    print("\nTop 10 brands by listing count")
    print(data["brand"].value_counts().head(10).to_string())


if __name__ == "__main__":
    main()
