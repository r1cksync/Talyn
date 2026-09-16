"""Run one authorized AWS/CDK command with CSV credentials only in the child environment."""

import argparse
import csv
import os
import shutil
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("--credential-csv", required=True)
parser.add_argument("--region", default="ap-south-1")
parser.add_argument("command", nargs=argparse.REMAINDER)
args = parser.parse_args()
command = args.command[1:] if args.command[:1] == ["--"] else args.command
if not command:
    parser.error("Provide a command after --")
with open(args.credential_csv, encoding="utf-8-sig") as handle:
    row = next(csv.DictReader(handle))
environment = dict(os.environ)
environment.update(
    AWS_ACCESS_KEY_ID=row["Access key ID"],
    AWS_SECRET_ACCESS_KEY=row["Secret access key"],
    AWS_DEFAULT_REGION=args.region,
    AWS_REGION=args.region,
    AWS_PAGER="",
)
environment.pop("AWS_SESSION_TOKEN", None)
command[0] = shutil.which(command[0]) or command[0]
raise SystemExit(subprocess.run(command, env=environment).returncode)
