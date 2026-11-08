.DEFAULT_GOAL := help
.PHONY: help test test-real test-mod test-vscode vsix test-jetbrains jetbrains-zip verify-jetbrains audit eval

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

test: ## Run the test suite (stdlib only), or some of it: make test TESTS=tests.test_cli
	PYTHONPATH=src python3 -B -m unittest $(or $(TESTS),discover -s tests -t .)

test-real: ## Also adopt small real projects with the toolchains installed here
	WS_REAL_TOOLS=1 PYTHONPATH=src python3 -B -m unittest tests.test_adoption tests.test_adapt

test-mod: ## Check the Claude Code pane (needs the claude CLI; local only, like eval)
	claude plugin validate ui/mod
	claude plugin test ui/mod

test-vscode: ## Build the VS Code extension and run its tests in the installed VS Code (local only, like test-mod)
	cd ui/vscode && npm run build && npm run test:integration

vsix: ## Package the VS Code extension as ui/vscode/workstreams.vsix
	cd ui/vscode && npm run build && npm run vsix

test-jetbrains: ## Build the JetBrains plugin and run its JUnit and headless IDE tests (local only, like test-vscode)
	cd ui/jetbrains && ./gradlew test

jetbrains-zip: ## Package the JetBrains plugin under ui/jetbrains/build/distributions
	cd ui/jetbrains && ./gradlew buildPlugin

verify-jetbrains: ## Check the JetBrains plugin against the local IntelliJ IDEA and Android Studio
	cd ui/jetbrains && ./gradlew verifyPlugin

audit: ## Check every role's context against its limit
	PYTHONPATH=src python3 -B -m workstream audit context

eval: ## Run real agents against a sample repo: make eval AGENT=<agent> [SCENARIOS=a,b] [CAP=n] [MODEL=m] [ACCOUNT=login]
	PYTHONPATH=src python3 -B -m evals.harness --agent $(AGENT) $(if $(SCENARIOS),--scenarios $(SCENARIOS)) $(if $(CAP),--cap $(CAP)) $(if $(MODEL),--model $(MODEL)) $(if $(ACCOUNT),--account $(ACCOUNT)) $(if $(KEEP),--keep $(KEEP))
