# Remote dataset management (Hugging Face). Pass tables via TABLES="tbl1 tbl2".
.PHONY: list-datasets upload download

list-datasets:  ## list datasets available in the HF repo with their sizes
	uv run python remote_data/fetch.py --list

upload:  ## upload local tables, e.g. make upload TABLES="hospital_170k insurance_claims_58k"
	@$(if $(TABLES),,$(error set TABLES, e.g. make upload TABLES="hospital_170k"))
	uv run python remote_data/upload.py $(TABLES)

download:  ## download tables into datasets_temp/, e.g. make download TABLES="hospital_170k"
	@$(if $(TABLES),,$(error set TABLES, e.g. make download TABLES="hospital_170k"))
	uv run python remote_data/fetch.py $(TABLES)
