# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-09

### Added
- `dataset-cleaner` command that cleans a scraped CSV and writes the result to `--output`.
- Column-name normalisation with collision-safe renaming (`email`, `email_2`, ...).
- Whitespace trimming, empty-row removal and exact or column-based duplicate removal.
- Email normalisation (trim + lowercase) and URL normalisation that preserves paths,
  query strings and fragments.
- Syntax-only email and URL validation with counts, an optional per-cell listing
  (`--validate`), and explicit `--remove-invalid-emails` / `--remove-invalid-urls`.
- `--drop-columns`, `--email-columns`, `--url-columns`, `--add-missing-scheme`,
  `--strip-url-params` and `--keep-duplicates` options.
- Rich terminal summary, `--json` stdout output and `--report` JSON file.
- Safety checks for missing, empty, malformed, non-UTF-8 and unsupported files, and
  for output paths that would overwrite the input.
