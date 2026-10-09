appname = django-eveonline-sde
package = eve_sde

# Default goal
.DEFAULT_GOAL := help

# Help
.PHONY: help
help:
	@echo ""
	@echo "$(appname) Makefile"
	@echo ""
	@echo "Usage:"
	@echo "  make [command]"
	@echo ""
	@echo "Commands:"
	@echo "  build_test              Build the package"
	@echo "  coverage                Run tests and create a coverage report"
	@echo "  graph_models            Create a graph of the models"
	@echo "  load_sde                Load the SDE into ../myauth"
	@echo "  load_test               Run the SDE load test with tox"
	@echo "  pre-commit-checks       Run pre-commit checks"
	@echo "  tox_tests               Run tests with tox"
	@echo "  translations            Create or update translation files"
	@echo "  compile_translations    Compile translation files"
	@echo ""

# Translation files
.PHONY: translations
translations:
	@echo "Creating or updating translation files"
	@cd $(package) && django-admin makemessages \
		-l en \
		--keep-pot \
		--ignore 'build/*'

# Compile translation files
.PHONY: compile_translations
compile_translations:
	@echo "Compiling translation files"
	@cd $(package) && django-admin compilemessages

# Graph models
.PHONY: graph_models
graph_models:
	@echo "Creating a graph of the models"
	@python ../myauth/manage.py \
		graph_models \
		$(package) \
		--arrow-shape normal \
		-o $(appname)-models.png

# Load the SDE
.PHONY: load_sde
load_sde:
	@echo "Test load the SDE"
	@python ../myauth/manage.py \
		esde_load_sde

# Coverage
.PHONY: coverage
coverage:
	@echo "Running tests and creating a coverage report"
	@rm -rf htmlcov
	@coverage run ../myauth/manage.py \
		test \
		$(package) \
		--keepdb \
		--failfast; \
	coverage html; \
	coverage report -m

# Build test
.PHONY: build_test
build_test:
	@echo "Building the package"
	@rm -rf dist
	@python3 -m hatch build

# Tox tests
.PHONY: tox_tests
tox_tests:
	@echo "Running tests with tox"
	@export USE_MYSQL=False; \
	tox -v; \
	rm -rf .tox/

# SDE load test
.PHONY: load_test
load_test:
	@echo "Running the SDE load test with tox"
	@tox -v -c tox_import.ini

# Pre-commit checks
.PHONY: pre-commit-checks
pre-commit-checks:
	@echo "Running pre-commit checks"
	@pre-commit run --all-files
