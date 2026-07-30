"""Merge data/am/*.json into the single minified/80-weahadu.json bundle.

This is the v1 (Amharic-only) pipeline. New work should use data/bible; see
docs/RELEASING.md.
"""
import json
import os
import glob
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import repo, rel  # noqa: E402


def merge_json_files():
    """
    Merges all JSON files from data/am/ into a single file
    at minified/80-weahadu.json.
    """
    output_data = []

    # Anchored at the repo root so the script works from any directory.
    json_files = sorted(glob.glob(repo("data", "am", "*.json")))

    if len(json_files) != 81:
        print(f"Warning: Found {len(json_files)} files, but expected 81.")

    for file_path in json_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                output_data.append(data)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from file {file_path}: {e}")
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")

    # Create the output directory if it doesn't exist
    os.makedirs(repo("minified"), exist_ok=True)

    # Write the combined data to the output file
    output_file = repo("minified", "80-weahadu.json")
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False,
                      indent=None, separators=(',', ':'))
        print(
            f"Successfully merged {len(output_data)} files into {rel(output_file)}")
    except Exception as e:
        print(f"Error writing to file {output_file}: {e}")


if __name__ == "__main__":
    merge_json_files()
