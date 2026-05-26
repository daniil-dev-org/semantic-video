"""
run_import_dataset.py  -  Import datasets via adapters.

Usage:
  python run_import_dataset.py --source youtube_trending --input data/youtube_trending --output samples/input/metadata_snapshots.csv
  python run_import_dataset.py --source generic_csv --input data/raw.csv --mapping config/mapping.yaml --output samples/input/metadata_snapshots.csv
"""

import argparse
import logging
from pathlib import Path
import yaml

from stp.datasets import (
    import_youtube_trending, 
    import_generic_csv,
    import_youtube_api_snapshot,
    import_kuairand
)
from stp.utils import setup_logging

def main():
    parser = argparse.ArgumentParser(description="STP - Dataset Importer")
    parser.add_argument("--source", required=True, choices=["youtube_trending", "generic_csv", "youtube_api_snapshot", "kuairand"])
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mapping", type=Path, help="Path to mapping.yaml for generic_csv")
    args = parser.parse_args()

    setup_logging()
    
    if args.source == "youtube_trending":
        import_youtube_trending(args.input, args.output)
    elif args.source == "generic_csv":
        if not args.mapping:
            raise ValueError("--mapping required for generic_csv")
        with open(args.mapping, "r", encoding="utf-8") as f:
            mapping = yaml.safe_load(f)
        import_generic_csv(args.input, args.output, mapping)
    elif args.source == "youtube_api_snapshot":
        import_youtube_api_snapshot(args.input, args.output)
    elif args.source == "kuairand":
        import_kuairand(args.input, args.output)

if __name__ == "__main__":
    main()
