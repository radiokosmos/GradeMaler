# Grade Mailer

Simple script to send course grades from Google Sheets through the Gmail API.

## What It Does

The script:

1. Reads rows from a selected Google Sheets worksheet.
2. Uses the `Name`, `email`, `Grade`, and `Send` columns.
3. Sends an email through Gmail to each student whose send flag is still empty.
4. Writes `sent` back to the status column after a successful send.

## Expected Sheet Format

The first row must contain headers.

Recommended headers:

- `Name`
- `email`
- `Grade`
- `Send`

The script still accepts several aliases, but keeping the sheet in this format is simpler.

## Google Setup

You need one OAuth client credentials file named `credentials.json` from Google Cloud.

In your Google Cloud project:

1. Enable `Google Sheets API`.
2. Enable `Gmail API`.
3. Create an `OAuth client ID` for a Desktop app.
4. Download the credentials file and place it next to the script as `credentials.json`.
5. Make sure the Google account you authorize has access to the target spreadsheet.

On the first run, the script opens a Google authorization flow and creates `token.json`. Later runs reuse that token automatically.

## Install

```bash
uv sync
```

## `.env`

The script automatically loads settings from `.env`.

Current project settings already include:

- your spreadsheet URL
- worksheet name `VeryFirstTest`
- email subject
- email template path

Example:

```bash
GOOGLE_OAUTH_CREDENTIALS_JSON="/path/to/credentials.json"
GOOGLE_OAUTH_TOKEN_JSON="/path/to/token.json"
GOOGLE_SHEETS_SPREADSHEET_URL="https://docs.google.com/spreadsheets/d/.../edit?gid=0#gid=0"
GOOGLE_SHEETS_WORKSHEET="VeryFirstTest"
EMAIL_SUBJECT="Your grade for {sheet_name}"
EMAIL_BODY_TEMPLATE_FILE="email_template.txt"
```

If you prefer selecting a worksheet by `gid`, use `GOOGLE_SHEETS_WORKSHEET_GID` instead of `GOOGLE_SHEETS_WORKSHEET`.

## Run

Dry run:

```bash
uv run send_grades.py --dry-run
```

Real run:

```bash
uv run send_grades.py
```

If `credentials.json` is next to the script, you do not need to set `GOOGLE_OAUTH_CREDENTIALS_JSON`.

## Email Template

The default template lives in `email_template.txt`.

Available placeholders:

- `{name}`
- `{grade}`
- `{sheet_name}`

You can point to another template file if needed:

```bash
uv run send_grades.py --body-template-file custom_template.txt
```
