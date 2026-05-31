"""Remote dataset provisioning — fetch tables from / upload tables to Hugging Face.

Data lives in a HF dataset repo (off GitHub) mirroring the `datasets/` layout;
`fetch` pulls tables onto a server at deploy time, `upload` populates the repo.
"""

from remote_data.fetch import available_tables, fetch_table, fetch_tables
from remote_data.upload import upload_table, upload_tables

__all__ = [
    "available_tables",
    "fetch_table",
    "fetch_tables",
    "upload_table",
    "upload_tables",
]
