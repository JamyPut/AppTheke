# Changelog

All notable changes to AppTheke are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-11-05

First release: a portable Windows app with a window.

### Added

- Catalog of tools with name, version, description and install notes.
- One category per tool and any number of tags.
- Search by name.
- Tool detail page, with edit and delete.
- Download button: fetches a setup or executable from the tool's saved link into a chosen folder, with a progress bar. It never overwrites existing files and rejects links that return a web page.
- Launch button: starts an installed program from its saved path. Paths can use Windows variables such as `%ProgramFiles%` or be relative to the AppTheke folder.
- Portable storage: the catalog (`apptheke.db`) sits next to the program.
- Error log (`apptheke-error.log`) and an error message when something goes wrong, because the packaged program has no console.
- A clear message when the catalog cannot be opened, for example in a read-only folder.
- Build script (`build.bat`) that packages the app as a single `AppTheke.exe`.
