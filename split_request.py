#!/usr/bin/env python3
"""Split the Apache-style request column into method, endpoint, and HTTP version."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def split_request_column(df: pd.DataFrame) -> pd.DataFrame:
    """Expand the request field into request_type, endpoint, and http_version."""
    parsed = df["request"].astype(str).str.extract(
        r"^\s*(GET|POST)\s+(\S+)\s+(HTTP/\d\.\d)\s*$",
        expand=True,
    )
    parsed.columns = ["request_type", "endpoint", "http_version"]

    for column in parsed.columns:
        df[column] = parsed[column]

    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input_csv",
        nargs="?",
        default="data.philiplessner.com/log_clean.csv",
        help="Path to the CSV file to update",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path for the updated CSV output; defaults to overwriting the input file",
    )
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    output_path = Path(args.output) if args.output else input_path

    df = pd.read_csv(input_path)
    if "request" not in df.columns:
        raise ValueError("The input CSV does not contain a 'request' column")

    df = split_request_column(df)
    df = df.drop(columns=['request'])
    df = df[['ip_address', 'datetime', 'request_type', 'endpoint', 'http_version', 'status_code', 'user_agent', 'country', 'countryCode', 'region', 'regionName', 'city', 'zip', 'lat', 'lon', 'timezone']]
    df.to_csv(output_path, index=False)

    print(f"Updated {len(df)} rows and wrote to {output_path}")


if __name__ == "__main__":
    main()
