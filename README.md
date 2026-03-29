# Fragrantica to Parfumo Migrator

A command-line tool that migrates your fragrance data from [Fragrantica](https://www.fragrantica.com) to [Parfumo](https://www.parfumo.com). Currently supports migrating reviews, with the architecture designed to support ratings, collections, and wishlists in the future.

No Fragrantica login is required — the tool reads your public profile page. A Parfumo account is required for submission.

## Requirements

- Python 3.11+
- Mozilla Firefox (used by Selenium for browser automation)

## Installation

Install directly from the repository:

```bash
pip install git+https://github.com/yourname/fragrantica-to-parfumo-migrator.git
```

Or clone and install locally:

```bash
git clone https://github.com/yourname/fragrantica-to-parfumo-migrator.git
cd fragrantica-to-parfumo-migrator
pip install .
```

## Usage

```bash
fragrantica-migrator \
  --profile-url https://www.fragrantica.com/member/YOUR_ID \
  --parfumo-user your@email.com \
  --parfumo-pass yourpassword
```

### All options

| Flag | Required | Default | Description |
|---|---|---|---|
| `--profile-url` | yes | — | Your Fragrantica profile URL |
| `--parfumo-user` | yes | — | Your Parfumo username |
| `--parfumo-pass` | yes | — | Your Parfumo password |
| `--data-type` | no | `reviews` | Type of data to migrate |
| `--confidence` | no | `80` | Fuzzy match threshold (0–100). Lower values match more loosely. |
| `--output` | no | — | File path to save the migration report |
| `--headless` | no | off | Run the browser without a visible window |
| `--browser` | no | `firefox` | Browser to use (`firefox` or `chrome`) |

### Examples

Run with a visible browser window (useful for first-time use to see what's happening):

```bash
fragrantica-migrator \
  --profile-url https://www.fragrantica.com/member/12345 \
  --parfumo-user myusername \
  --parfumo-pass hunter2
```

Run headlessly and save the report:

```bash
fragrantica-migrator \
  --profile-url https://www.fragrantica.com/member/12345 \
  --parfumo-user you@example.com \
  --parfumo-pass hunter2 \
  --headless \
  --output migration-report.txt
```

Relax the match threshold if too many fragrances are being skipped:

```bash
fragrantica-migrator \
  --profile-url https://www.fragrantica.com/member/12345 \
  --parfumo-user you@example.com \
  --parfumo-pass hunter2 \
  --confidence 70
```

## How it works

1. The tool opens your Fragrantica profile and scrolls through all your reviews, loading them lazily as they appear.
2. For each review, it searches Parfumo's autocomplete for the fragrance name and uses fuzzy matching to find the best match.
3. If a match meets the confidence threshold, it navigates to that fragrance page and submits your review.
4. At the end, a summary report is printed showing how many reviews were migrated, skipped, or failed — with reasons for any that weren't submitted.

## Fuzzy matching

Fragrantica and Parfumo sometimes list the same brand under slightly different names (e.g. "By Kilian", "Kilian Paris", "Kilian"). The tool uses fuzzy string matching to handle these variations. The `--confidence` threshold (default: 80 out of 100) controls how strict the match needs to be. If a fragrance is being skipped unexpectedly, try lowering it slightly.

## Output

A summary is always printed to stdout:

```
Migration complete.
  Scraped:     42
  Submitted:   38
  Skipped:      3
  Failed:       1

Skipped:
  - Light Blue by Dolce & Gabbana — no candidate met confidence threshold (best: 74)

Failed:
  - Aventus by Creed — review textarea not found on page
```

If `--output` is set, the same content is written to that file.

## Development

Install with dev dependencies:

```bash
pip install -e ".[dev]"
```

Run the test suite:

```bash
pytest
```

Integration tests (require a real browser and network) are excluded by default. To run them:

```bash
pytest -m integration
```

## Notes

- Your Parfumo password is never stored or logged. It is held in memory only for the duration of the run.
- Reviews that already exist on Parfumo may result in a submission error — the tool will log these as failed and continue.
- The tool requires Firefox (default) or Chrome to be installed. The correct driver is downloaded automatically via `webdriver-manager`.
