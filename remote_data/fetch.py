"""Fetch dataset tables from a Hugging Face dataset repo.

Data is kept off GitHub and pulled on the server at deploy time. The HF repo
mirrors the local `datasets/` layout (one folder per table, as in
`harness/datasets.md`), so each table is a subfolder like `hospital_170k/clean.csv`.

Pick which tables to pull — some are large and not every deployment needs them.
Downloads land in `datasets_temp/`, never `datasets/`, so a fetch can't clobber
working data; move a table into `datasets/` by hand once you've checked it.

Set the repo with the `HORIZON_HF_REPO` env var or pass `repo_id=`.

    from remote_data.fetch import available_tables, fetch_table
    available_tables()                 # which tables the repo offers
    fetch_table("hospital_170k")       # -> datasets_temp/hospital_170k/

Or from the server shell:
    uv run python remote_data/fetch.py --list        # available tables + sizes
    uv run python remote_data/fetch.py hospital_170k  # download into datasets_temp/
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import HfApi, snapshot_download

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "datasets_temp"

load_dotenv(ROOT / ".env")


def _repo(repo_id: str | None) -> str:
    repo_id = repo_id or os.environ.get("HORIZON_HF_REPO")
    if not repo_id:
        raise ValueError("no repo: set HORIZON_HF_REPO or pass repo_id=")
    return repo_id


def available_tables(repo_id: str | None = None) -> list[str]:
    """Top-level table folders available in the HF dataset repo."""
    files = HfApi().list_repo_files(_repo(repo_id), repo_type="dataset")
    return sorted({f.split("/")[0] for f in files if "/" in f})


def table_sizes(repo_id: str | None = None) -> dict[str, int]:
    """Each available table mapped to its total size in bytes."""
    info = HfApi().repo_info(_repo(repo_id), repo_type="dataset", files_metadata=True)
    sizes: dict[str, int] = {}
    for f in info.siblings:
        if "/" in f.rfilename:
            top = f.rfilename.split("/")[0]
            sizes[top] = sizes.get(top, 0) + (f.size or 0)
    return sizes


def fetch_table(table: str, repo_id: str | None = None, dest: Path = DEST) -> Path:
    """Download one table's whole folder into `datasets_temp/`. Returns the local path.

    Move it into `datasets/` yourself once verified — fetch never writes there.
    """
    snapshot_download(
        repo_id=_repo(repo_id),
        repo_type="dataset",
        allow_patterns=f"{table}/**",
        local_dir=dest,
    )
    out = dest / table
    if not out.exists():
        raise ValueError(f"{table!r} not in repo; see available_tables()")
    return out


def fetch_tables(tables: list[str], repo_id: str | None = None, dest: Path = DEST) -> list[Path]:
    """Download several tables. Returns their local paths."""
    return [fetch_table(t, repo_id, dest) for t in tables]


def _print_catalog() -> None:
    sizes = table_sizes()
    if not sizes:
        print("no tables in repo")
        return
    for table in sorted(sizes):
        local = "  [local]" if (ROOT / "datasets" / table).is_dir() else ""
        print(f"{table:32} {sizes[table] / 1e6:9.1f} MB{local}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] in ("-l", "--list", "list"):
        _print_catalog()
    else:
        for path in fetch_tables(args):
            print(f"fetched {path}  (move into datasets/ when ready)")

# TODO: it shouldnt load into datasets_temp. it should just fail if the table is already in datasets and instead load into datasets. this and the readme need to be adjusted
