#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import os
import re
import sys
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable

DEFAULT_ALIASES = {
    "name": ["имя", "name", "student", "student_name"],
    "email": ["email", "e-mail", "почта", "емейл", "элпочта"],
    "grade": ["оценка", "grade", "score", "балл", "result"],
    "sent": ["отправлено", "sent", "send", "status", "is_sent"],
}

TRUE_VALUES = {"1", "true", "yes", "y", "done", "sent", "отправлено", "да"}
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/gmail.send",
]


@dataclass
class Config:
    credentials_json: str
    token_json: str
    spreadsheet_id: str
    spreadsheet_url: str
    worksheet_name: str
    worksheet_gid: int | None
    subject: str
    body_template: str
    name_column: str
    email_column: str
    grade_column: str
    sent_column: str
    sent_value: str
    dry_run: bool


def parse_args() -> Config:
    load_dotenv_file()
    parser = argparse.ArgumentParser(
        description="Send grades to students from a Google Sheets worksheet using Gmail API."
    )
    parser.add_argument(
        "--credentials-json",
        default=os.getenv("GOOGLE_OAUTH_CREDENTIALS_JSON", "credentials.json"),
        help="Path to OAuth client credentials JSON from Google Cloud.",
    )
    parser.add_argument(
        "--token-json",
        default=os.getenv("GOOGLE_OAUTH_TOKEN_JSON", "token.json"),
        help="Path to cached OAuth token JSON. Will be created on first run.",
    )
    parser.add_argument(
        "--spreadsheet-id",
        default=os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID"),
        help="Google Sheets spreadsheet ID.",
    )
    parser.add_argument(
        "--spreadsheet-url",
        default=os.getenv("GOOGLE_SHEETS_SPREADSHEET_URL"),
        help="Full Google Sheets URL. Spreadsheet ID can be extracted from it automatically.",
    )
    parser.add_argument(
        "--worksheet",
        default=os.getenv("GOOGLE_SHEETS_WORKSHEET", ""),
        help="Worksheet title inside the spreadsheet.",
    )
    parser.add_argument(
        "--worksheet-gid",
        type=int,
        default=parse_optional_int(os.getenv("GOOGLE_SHEETS_WORKSHEET_GID")),
        help="Worksheet gid from the Google Sheets URL.",
    )
    parser.add_argument(
        "--subject",
        default=os.getenv("EMAIL_SUBJECT", "Your course grade"),
        help="Email subject. Supports {name} and {grade}.",
    )
    parser.add_argument(
        "--body-template-file",
        default=os.getenv("EMAIL_BODY_TEMPLATE_FILE", "email_template.txt"),
        help="Path to a text file with email body template.",
    )
    parser.add_argument(
        "--name-column",
        default=os.getenv("NAME_COLUMN", "name"),
        help="Column header for the student's name.",
    )
    parser.add_argument(
        "--email-column",
        default=os.getenv("EMAIL_COLUMN", "email"),
        help="Column header for the student's email.",
    )
    parser.add_argument(
        "--grade-column",
        default=os.getenv("GRADE_COLUMN", "grade"),
        help="Column header for the student's grade.",
    )
    parser.add_argument(
        "--sent-column",
        default=os.getenv("SENT_COLUMN", "send"),
        help="Column header for the sent flag.",
    )
    parser.add_argument(
        "--sent-value",
        default=os.getenv("SENT_VALUE", "sent"),
        help="Value to write after a successful send.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be sent without sending emails or updating the sheet.",
    )
    args = parser.parse_args()

    if args.body_template_file:
        body_template = Path(args.body_template_file).read_text(encoding="utf-8")
    else:
        raise SystemExit(
            "Missing email template file: set EMAIL_BODY_TEMPLATE_FILE or pass --body-template-file."
        )

    config = Config(
        credentials_json=args.credentials_json,
        token_json=args.token_json,
        spreadsheet_id=args.spreadsheet_id or extract_spreadsheet_id(args.spreadsheet_url or ""),
        spreadsheet_url=args.spreadsheet_url or "",
        worksheet_name=args.worksheet,
        worksheet_gid=args.worksheet_gid,
        subject=args.subject,
        body_template=body_template,
        name_column=args.name_column,
        email_column=args.email_column,
        grade_column=args.grade_column,
        sent_column=args.sent_column,
        sent_value=args.sent_value,
        dry_run=args.dry_run,
    )
    validate_config(config)
    return config


def validate_config(config: Config) -> None:
    missing = []
    required = {
        "GOOGLE_OAUTH_CREDENTIALS_JSON": config.credentials_json,
        "GOOGLE_SHEETS_SPREADSHEET_ID": config.spreadsheet_id,
    }
    for key, value in required.items():
        if not value:
            missing.append(key)
    if missing:
        raise SystemExit("Missing required configuration: " + ", ".join(missing))
    if not Path(config.credentials_json).exists():
        raise SystemExit(
            f"Credentials file not found: {config.credentials_json}"
        )
    if config.worksheet_gid is None and not config.worksheet_name:
        raise SystemExit(
            "Missing worksheet selector: set GOOGLE_SHEETS_WORKSHEET_GID or GOOGLE_SHEETS_WORKSHEET."
        )


def load_dotenv_file(dotenv_path: str = ".env") -> None:
    path = Path(dotenv_path)
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def parse_optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def extract_spreadsheet_id(url: str) -> str:
    if not url:
        return ""
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
    if not match:
        raise SystemExit(f"Could not extract spreadsheet ID from URL: {url}")
    return match.group(1)


def normalize_header(value: str) -> str:
    return "".join(value.strip().lower().split())


NORMALIZED_TRUE_VALUES = {normalize_header(item) for item in TRUE_VALUES}


def find_header_index(headers: list[str], requested_name: str, aliases: Iterable[str]) -> int:
    normalized_headers = {normalize_header(header): index for index, header in enumerate(headers)}
    candidates = [requested_name, *aliases]
    for candidate in candidates:
        index = normalized_headers.get(normalize_header(candidate))
        if index is not None:
            return index
    available = ", ".join(headers)
    raise SystemExit(
        f"Could not find column '{requested_name}'. Available columns: {available}"
    )


def load_google_credentials(config: Config):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    token_path = Path(config.token_json)
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    if creds and creds.valid:
        return creds

    flow = InstalledAppFlow.from_client_secrets_file(config.credentials_json, SCOPES)
    creds = flow.run_local_server(port=0)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def open_worksheet(config: Config, credentials):
    import gspread

    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_key(config.spreadsheet_id)
    if config.worksheet_gid is not None:
        return spreadsheet.get_worksheet_by_id(config.worksheet_gid)
    return spreadsheet.worksheet(config.worksheet_name)


def gmail_service(credentials):
    from googleapiclient.discovery import build

    return build("gmail", "v1", credentials=credentials)


def get_rows(worksheet):
    values = worksheet.get_all_values()
    if not values:
        raise SystemExit("Worksheet is empty.")
    return values[0], values[1:]


def is_marked_sent(value: str) -> bool:
    return normalize_header(value) in NORMALIZED_TRUE_VALUES


def build_message(config: Config, student_name: str, email: str, grade: str) -> EmailMessage:
    sheet_name = config.worksheet_name or (str(config.worksheet_gid) if config.worksheet_gid is not None else "this assignment")
    message = EmailMessage()
    message["To"] = email
    template_vars = {
        "name": student_name,
        "grade": grade,
        "sheet_name": sheet_name,
    }
    message["Subject"] = config.subject.format(**template_vars)
    message.set_content(config.body_template.format(**template_vars))
    return message


def encode_message(message: EmailMessage) -> dict[str, str]:
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    return {"raw": raw}


def process_rows(config: Config) -> int:
    credentials = load_google_credentials(config)
    worksheet = open_worksheet(config, credentials)
    headers, rows = get_rows(worksheet)

    name_idx = find_header_index(headers, config.name_column, DEFAULT_ALIASES["name"])
    email_idx = find_header_index(headers, config.email_column, DEFAULT_ALIASES["email"])
    grade_idx = find_header_index(headers, config.grade_column, DEFAULT_ALIASES["grade"])
    sent_idx = find_header_index(headers, config.sent_column, DEFAULT_ALIASES["sent"])

    service = None if config.dry_run else gmail_service(credentials)
    sent_count = 0

    for row_number, row in enumerate(rows, start=2):
        padded_row = row + [""] * (len(headers) - len(row))
        student_name = padded_row[name_idx].strip() or "student"
        email = padded_row[email_idx].strip()
        grade = padded_row[grade_idx].strip()
        sent_flag = padded_row[sent_idx].strip()

        if not email:
            print(f"[SKIP] Row {row_number}: empty email", file=sys.stderr)
            continue
        if is_marked_sent(sent_flag):
            print(f"[SKIP] Row {row_number}: already marked as sent")
            continue

        message = build_message(config, student_name, email, grade)
        if config.dry_run:
            print(
                f"[DRY RUN] Row {row_number}: would send to {email} "
                f"for '{student_name}' with grade '{grade}'"
            )
            continue

        try:
            service.users().messages().send(
                userId="me",
                body=encode_message(message),
            ).execute()
            worksheet.update_cell(row_number, sent_idx + 1, config.sent_value)
            sent_count += 1
            print(f"[OK] Row {row_number}: sent to {email}")
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] Row {row_number}: {email}: {exc}", file=sys.stderr)

    return sent_count


def main() -> None:
    config = parse_args()
    sent_count = process_rows(config)
    if config.dry_run:
        print("Dry run finished.")
    else:
        print(f"Finished. Sent {sent_count} email(s).")


if __name__ == "__main__":
    main()
