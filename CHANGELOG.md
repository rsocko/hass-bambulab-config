# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- `# Docs:` reference comments in ~100 YAML files linking to relevant documentation (#572)
  - All 14 loader YAML files
  - All 11 bambuddy standalone YAML files
  - Automations, scripts, template sensors, dashboard cards, and config files across all 18 feature packages
  - Where possible, links point to the specific doc page (e.g., `SMART_STATUS.md`, `skip-objects.md`) rather than just the feature README
- `CHANGELOG.md` at repo root to track changes (#572)

### Changed

- Bambuddy YAML headers now use `# Docs:` / `# Setup:` comments instead of inline prose references
- Verbose `description:` blocks in bambuddy automations trimmed — setup info moved to header comments

## Documentation

- [Quick Start](docs/repo/QUICK_START.md)
- [Deployment Structure](docs/repo/DEPLOYMENT_STRUCTURE.md)
- [Repo Layout](docs/repo/REPO_LAYOUT.md)
- [Feature Docs](docs/features/)
