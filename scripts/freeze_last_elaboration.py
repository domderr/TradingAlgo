import argparse
import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "mosaic_dev" / "output"
ARCHIVE_ROOT = OUTPUT_DIR / "elaborazioni_precedenti"

SOURCES = [
    (ROOT / "reports", "reports"),
    (ROOT / "reports_html", "reports_html"),
    (ROOT / "mosaic_dev" / "market_data", "market_data"),
    (OUTPUT_DIR / "all_market_reports_data_from_csv.json", "mosaic_dev_output/all_market_reports_data_from_csv.json"),
    (OUTPUT_DIR / "html_data", "mosaic_dev_output/html_data"),
]


def read_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def default_label():
    latest_prices = ROOT / "reports" / "latest_prices.json"
    if latest_prices.exists():
        data = read_json(latest_prices)
        dates = [
            str(item.get("as_of", "")).strip()
            for item in data.values()
            if isinstance(item, dict) and item.get("as_of")
        ]
        if dates:
            return max(dates)

    return datetime.now().strftime("%Y-%m-%d")


def git_value(*args):
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        return result.stdout.strip()
    except Exception:
        return None


def copy_source(source, destination):
    if source.is_dir():
        # Google Drive for desktop can reject Windows metadata replication for
        # some generated PNG files even though copying their contents works.
        # Snapshot integrity depends on file contents, so avoid copy2/copystat.
        shutil.copytree(
            source,
            destination,
            copy_function=shutil.copyfile,
            dirs_exist_ok=True,
        )
    elif source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    else:
        return False
    return True


def count_files(path):
    if path.is_file():
        return 1
    return sum(1 for item in path.rglob("*") if item.is_file())


def remove_tree(path):
    def handle_error(function, item, _exc_info):
        try:
            os.chmod(item, 0o700)
            function(item)
        except OSError:
            pass

    for attempt in range(5):
        shutil.rmtree(path, onerror=handle_error)
        if not path.exists():
            return
        time.sleep(1 + attempt)

    raise RuntimeError(f"Could not remove existing archive: {path}")


def main():
    parser = argparse.ArgumentParser(
        description="Freeze the latest published Mosaic elaboration before running a new weekly pipeline."
    )
    parser.add_argument(
        "--label",
        default=default_label(),
        help="Archive folder name. Defaults to the max as_of date in reports/latest_prices.json.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing archive with the same label.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume an incomplete archive that does not yet have a freeze manifest.",
    )
    args = parser.parse_args()

    archive_dir = ARCHIVE_ROOT / args.label
    if archive_dir.exists():
        manifest_path = archive_dir / "freeze_manifest.json"
        if args.resume:
            if manifest_path.exists():
                raise SystemExit(f"Archive is already complete: {archive_dir}")
        elif not args.force:
            raise SystemExit(
                f"Archive already exists: {archive_dir}. Use --force only if you really want to replace it."
            )
        else:
            remove_tree(archive_dir)

    archive_dir.mkdir(parents=True, exist_ok=args.resume)
    copied = []
    missing = []

    for source, relative_destination in SOURCES:
        destination = archive_dir / relative_destination
        if copy_source(source, destination):
            copied.append(
                {
                    "source": str(source.relative_to(ROOT)),
                    "destination": str(destination.relative_to(archive_dir)),
                    "files": count_files(destination),
                }
            )
        else:
            missing.append(str(source.relative_to(ROOT)))

    manifest = {
        "label": args.label,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": str(ROOT),
        "git_commit": git_value("rev-parse", "HEAD"),
        "git_branch": git_value("branch", "--show-current"),
        "copied": copied,
        "missing": missing,
    }
    with (archive_dir / "freeze_manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")

    print(f"Frozen latest elaboration in: {archive_dir}")
    for item in copied:
        print(f"- {item['destination']}: {item['files']} files")
    if missing:
        print("Missing optional sources:")
        for item in missing:
            print(f"- {item}")


if __name__ == "__main__":
    main()
