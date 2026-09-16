import hashlib
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import boto3

from app import adapters


def test_presigned_objects_use_regional_endpoint_and_signed_integrity(monkeypatch):
    session = boto3.Session(aws_access_key_id="testing", aws_secret_access_key="testing")
    monkeypatch.setattr(adapters.boto3, "client", session.client)
    monkeypatch.setattr(
        adapters,
        "settings",
        lambda: SimpleNamespace(mode="aws", region="ap-south-1", bucket="talyn-synthetic-test"),
    )
    checksum = hashlib.sha256(b"synthetic").hexdigest()
    upload = adapters.storage.upload_url("org/application/resume.docx", "application/octet-stream", 9, checksum)
    parsed = urlsplit(upload["url"])
    assert parsed.hostname == "talyn-synthetic-test.s3.ap-south-1.amazonaws.com"
    query = parse_qs(parsed.query)
    assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert "/ap-south-1/s3/aws4_request" in query["X-Amz-Credential"][0]
    signed = query["X-Amz-SignedHeaders"][0].split(";")
    assert {"content-length", "content-type", "x-amz-checksum-sha256"}.issubset(signed)
    assert query["X-Amz-Expires"] == ["300"]
    download = urlsplit(adapters.storage.download_url("org/application/resume.docx"))
    assert download.hostname == parsed.hostname
    assert parse_qs(download.query)["X-Amz-Expires"] == ["120"]
