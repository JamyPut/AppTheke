# Changelog

All notable changes to AppTheke are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- "Fill from program": reads the name, version and description (with the publisher) from the chosen program and fills them in, together with its icon. Choosing a program with **Browse...** fills only the fields that are still empty; the button replaces them, which is handy for updating the version after an upgrade.

## [1.1.0] - 2026-11-12

### Added

- Websites tab: keep websites you use as tools, with category, tags and description, and open them in your browser.
- Icons for every entry: read from the program, fetched from the website, or chosen from a picture. New entries get one looked up automatically. Entries without an icon show their first letter.
- App icon for `AppTheke.exe` and its window.
- `tools/make_icon.py` to rebuild the app icon from `assets/icon.png`.

### Changed

- Pillow is now a dependency (for icons), so the program is a few MB larger.
- Existing catalogs are upgraded automatically the first time the new version opens them.

## [1.0.1] - 2026-11-05

### Added

- Splash screen while the portable program starts.

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
