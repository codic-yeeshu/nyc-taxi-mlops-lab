#!/usr/bin/env python3
"""Prompt for S6 credentials and send them directly to AWS Secrets Manager."""

import argparse
import getpass
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit
import warnings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=("wiki", "langfuse"))
    parser.add_argument("aws_credentials_file", type=Path, nargs="?")
    args = parser.parse_args()

    env = dict(os.environ)
    if args.aws_credentials_file:
        keys = {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"}
        credentials = {}
        for line in args.aws_credentials_file.expanduser().read_text().splitlines():
            key, _, value = line.partition("=")
            key = key.strip().upper()
            if key in keys:
                credentials[key] = value.strip().strip("'\"")
        if set(credentials) != keys or not all(credentials.values()):
            parser.error("the AWS credentials file must contain all three Learner Lab values")
        env.update(credentials)

    warnings.simplefilter("error", getpass.GetPassWarning)
    base_url = input(f"{args.service.capitalize()} HTTPS base URL: ").strip().rstrip("/")
    url = urlsplit(base_url)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
        parser.error("enter the HTTPS base URL without credentials, a query, or a fragment")
    if args.service == "wiki":
        values = {"url": base_url, "token": getpass.getpass("Wiki bearer token: ").strip()}
    else:
        values = {
            "host": base_url,
            "public_key": input("Langfuse public key: ").strip(),
            "secret_key": getpass.getpass("Langfuse secret key: ").strip(),
        }
    if not all(values.values()):
        parser.error("every field is required")

    subprocess.run(
        ["aws", "secretsmanager", "put-secret-value", "--region", "us-east-1",
         "--secret-id", f"lab/{args.service}", "--secret-string", "file:///dev/stdin",
         "--query", "VersionId", "--output", "text", "--no-cli-pager"],
        input=json.dumps(values),
        text=True,
        env=env,
        check=True,
    )


if __name__ == "__main__":
    main()
