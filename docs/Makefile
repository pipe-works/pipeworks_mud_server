# Makefile wrapper for MkDocs documentation
# This allows the docs build to work with the pipe-works CI workflow
# which expects a Sphinx-style "make html" command

.PHONY: help html clean

help:
	@echo "Please use 'make <target>' where <target> is one of"
	@echo "  html       to build documentation using MkDocs"
	@echo "  clean      to remove built documentation"

html:
	@echo "Building documentation with MkDocs..."
	cd .. && mkdocs build

clean:
	@echo "Cleaning built documentation..."
	cd .. && rm -rf site/
