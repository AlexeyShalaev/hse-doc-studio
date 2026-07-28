# Scripts Makefile
# Aggregates all script-related commands

# Include all sub-Makefiles
include scripts/dev/Makefile
include scripts/tests/Makefile

.PHONY: scripts-help

scripts-help:
	@echo.
	@echo ==========================================
	@echo   hse-doc-studio Scripts Management
	@echo ==========================================
	@echo.
	@$(MAKE) -s dev-help
	@$(MAKE) -s tests-help
