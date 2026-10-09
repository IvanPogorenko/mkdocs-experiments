.PHONY: build clean

build:
	python scripts/process_experiments.py
	mkdocs build --strict

clean:
	rm -rf site