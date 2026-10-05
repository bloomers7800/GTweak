.PHONY: install test scan serve

install:
	python3 -m pip install -e ".[dev]"

test:
	python3 -m pytest -q

scan:
	python3 -m foldscan.cli scan $(PATH_TO_SCAN)

serve:
	python3 -m foldscan.cli serve $(PATH_TO_SCAN)
