"""Upload local dataset tables to the Hugging Face dataset repo.

Run from your machine to populate the repo that `fetch.py` pulls from. Mirrors
the `datasets/` layout: each table folder is uploaded under its own path, so it
lands as `{repo}/{table}/clean.csv` etc. The repo is created on first upload.

Needs a **write** token (`HF_TOKEN`) and the repo (`HORIZON_HF_REPO` or `repo_id=`).
`huggingface_hub` reads `HF_TOKEN` from the environment automatically.

    uv run python remote_data/upload.py hospital_170k insurance_claims_58k
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import HfApi, upload_folder

ROOT = Path(__file__).resolve().parent.parent
DATASETS = ROOT / "datasets"

load_dotenv(ROOT / ".env")

# don't ship caches / build junk even when uploading the whole folder
IGNORE = ["**/.cache/**", "**/__pycache__/**", "*.tmp", "*.bak"]


def _repo(repo_id: str | None) -> str:
    repo_id = repo_id or os.environ.get("HORIZON_HF_REPO")
    if not repo_id:
        raise ValueError("no repo: set HORIZON_HF_REPO or pass repo_id=")
    return repo_id


def upload_table(table: str, repo_id: str | None = None, src: Path = DATASETS) -> str:
    """Upload `datasets/{table}/` to the HF repo under `{table}/`. Returns the repo path."""
    folder = src / table
    if not folder.is_dir():
        raise ValueError(f"{folder} not found")

    repo = _repo(repo_id)
    HfApi().create_repo(repo, repo_type="dataset", exist_ok=True)
    upload_folder(
        repo_id=repo,
        repo_type="dataset",
        folder_path=str(folder),
        path_in_repo=table,
        ignore_patterns=IGNORE,
        commit_message=f"Add/update {table}",
    )
    return f"{repo}/{table}"


def upload_tables(tables: list[str], repo_id: str | None = None, src: Path = DATASETS) -> list[str]:
    """Upload several tables. Returns their repo paths."""
    return [upload_table(t, repo_id, src) for t in tables]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python remote_data/upload.py TABLE [TABLE ...]")
    for path in upload_tables(sys.argv[1:]):
        print(f"uploaded {path}")
