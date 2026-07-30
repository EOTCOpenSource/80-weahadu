"""Write one minified JSON file per book into minified/singleChapter/, plus an
index for building menus.

This is the v1 (Amharic-only) pipeline. New work should use data/bible; see
docs/RELEASING.md.
"""
import argparse
import glob
import json
import os
import re
import sys
from typing import List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import repo  # noqa: E402


def extract_order(file_path: str) -> int:
    """Extract the numeric prefix used for canonical chapter ordering."""
    name = os.path.basename(file_path)
    match = re.match(r"^(\d+)-", name)
    if not match:
        return 10**9
    return int(match.group(1))


def collect_input_files(input_dir: str) -> List[str]:
    files = glob.glob(os.path.join(input_dir, "*.json"))
    files.sort(key=lambda path: (extract_order(
        path), os.path.basename(path).lower()))
    return files


def minify_chapters(input_dir: str, output_dir: str, index_name: str) -> Tuple[int, int]:
    os.makedirs(output_dir, exist_ok=True)

    input_files = collect_input_files(input_dir)
    if not input_files:
        print(f"No JSON files found in {input_dir}")
        return 0, 0

    index_entries = []
    written_count = 0

    for src_path in input_files:
        file_name = os.path.basename(src_path)
        order = extract_order(src_path)
        dst_path = os.path.join(output_dir, file_name)

        try:
            with open(src_path, "r", encoding="utf-8") as src_file:
                data = json.load(src_file)

            with open(dst_path, "w", encoding="utf-8") as dst_file:
                json.dump(data, dst_file, ensure_ascii=False,
                          separators=(",", ":"))

            index_entries.append(
                {
                    "book_number": data.get("book_number", order),
                    "book_name_am": data.get("book_name_am", ""),
                    "book_name_en": data.get("book_name_en", ""),
                    "book_short_name_am": data.get("book_short_name_am", ""),
                    "book_short_name_en": data.get("book_short_name_en", ""),
                    "testament": data.get("testament", ""),
                    "file": file_name,
                }
            )
            written_count += 1
        except json.JSONDecodeError as exc:
            print(f"Skipping {src_path}: invalid JSON ({exc})")
        except OSError as exc:
            print(f"Skipping {src_path}: file error ({exc})")

    index_path = os.path.join(output_dir, index_name)
    index_payload = {
        "count": written_count,
        "files": index_entries,
    }

    with open(index_path, "w", encoding="utf-8") as index_file:
        json.dump(index_payload, index_file,
                  ensure_ascii=False, separators=(",", ":"))

    return len(input_files), written_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create minified single-chapter JSON files and an index file."
    )
    # Defaults are anchored at the repo root so the script works from anywhere.
    parser.add_argument("--input-dir", default=repo("data", "am"),
                        help="Directory with source JSON files")
    parser.add_argument(
        "--output-dir",
        default=repo("minified", "singleChapter"),
        help="Directory where minified chapter files are written",
    )
    parser.add_argument(
        "--index-file",
        default="index.json",
        help="Index filename to create inside the output directory",
    )

    args = parser.parse_args()
    total_files, written_files = minify_chapters(
        args.input_dir, args.output_dir, args.index_file)

    print(
        f"Processed {total_files} files from {args.input_dir}; "
        f"wrote {written_files} minified files to {args.output_dir} and index {args.index_file}."
    )


if __name__ == "__main__":
    main()
