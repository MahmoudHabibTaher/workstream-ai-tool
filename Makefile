.DEFAULT_GOAL := help
.PHONY: help test test-real audit

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

test: ## Run the test suite (stdlib only)
	PYTHONPATH=src python3 -B -m unittest discover -s tests -t .

test-real: ## Also adopt small real projects with the toolchains installed here
	WS_REAL_TOOLS=1 PYTHONPATH=src python3 -B -m unittest tests.test_adoption tests.test_adapt

audit: ## Check every role's context against its limit
	PYTHONPATH=src python3 -B -m workstream audit context
