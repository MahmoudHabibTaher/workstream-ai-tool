.DEFAULT_GOAL := help
.PHONY: help test

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

test: ## Run the test suite (stdlib only)
	PYTHONPATH=src python3 -B -m unittest discover -s tests -t .
