#!/usr/bin/env python3
"""Remove duplicate log rows that share the same datetime value."""

from __future__ import annotations

import argparse
import csv
import os
import tempfile
from pathlib import Path


def deduplicate_csv(input_path: Path, output_path: Path) -> tuple[int, int]:
    """Write the first row for each datetime and return kept/removed counts."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None

    try:
        with input_path.open(newline='', encoding='utf-8-sig') as input_file:
            reader = csv.reader(input_file)
            header = next(reader, None)
            if not header or 'datetime' not in header:
                raise ValueError("The input CSV does not contain a 'datetime' column")
            datetime_index = header.index('datetime')

            with tempfile.NamedTemporaryFile(
                mode='w',
                newline='',
                encoding='utf-8',
                prefix=f'.{output_path.name}.',
                suffix='.tmp',
                dir=output_path.parent,
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                writer = csv.writer(temporary_file)
                writer.writerow(header)

                seen_datetimes: set[str] = set()
                kept = 0
                removed = 0

                for record_number, row in enumerate(reader, start=2):
                    if len(row) <= datetime_index:
                        raise ValueError(
                            f'CSV record {record_number} has no datetime value'
                        )

                    timestamp = row[datetime_index]
                    if timestamp in seen_datetimes:
                        removed += 1
                        continue

                    seen_datetimes.add(timestamp)
                    writer.writerow(row)
                    kept += 1

        os.replace(temporary_path, output_path)
        return kept, removed
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'input_csv',
        nargs='?',
        default='data.philiplessner.com/log_robots.csv',
        help='CSV to deduplicate (default: data.philiplessner.com/log_robots.csv)',
    )
    parser.add_argument(
        '--output',
        help='Optional output path; defaults to safely replacing the input CSV',
    )
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    output_path = Path(args.output) if args.output else input_path
    kept, removed = deduplicate_csv(input_path, output_path)

    print(f'Kept {kept} rows, removed {removed} duplicates, wrote {output_path}')


if __name__ == '__main__':
    main()
