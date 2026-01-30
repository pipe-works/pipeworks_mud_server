# Makefile for mkdocs documentation
# This provides compatibility with Sphinx-style build commands

.PHONY: html clean help

html:
	@cd .. && PYTHONPATH=src mkdocs build

clean:
	@cd .. && rm -rf site

help:
	@echo "Please use 'make <target>' where <target> is one of:"
	@echo "  html       to build the documentation using mkdocs"
	@echo "  clean      to remove the build directory"
