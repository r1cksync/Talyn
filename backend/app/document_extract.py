"""No Office/PDF execution; parsing runs in a bounded subprocess in the worker."""

import io
import json
import os
import subprocess
import sys
import zipfile

from defusedxml.ElementTree import fromstring
from pypdf import PdfReader


def extract(data: bytes, kind: str):
    sources, warnings = [], []
    page_count = 0
    if kind == "application/pdf":
        if not data.startswith(b"%PDF-"):
            raise ValueError("PDF signature missing")
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ValueError("Encrypted PDFs are unsupported")
        if len(reader.pages) > 50:
            raise ValueError("Document exceeds 50-page limit")
        page_count = len(reader.pages)
        if any(key in reader.trailer.get("/Root", {}) for key in ("/OpenAction", "/AA")):
            warnings.append("Interactive PDF actions ignored")
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            sources.append({"ref": f"page:{i + 1}", "text": text[:20000]})
    else:
        if not data.startswith(b"PK"):
            raise ValueError("DOCX signature missing")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 1000 or sum(e.file_size for e in entries) > 30000000:
                raise ValueError("Expanded document exceeds limit")
            if any("vbaproject" in e.filename.lower() or "embeddings/" in e.filename.lower() for e in entries):
                raise ValueError("Embedded objects or macros are unsupported")
            if "word/document.xml" not in archive.namelist():
                raise ValueError("Not a Word document")
            root = fromstring(archive.read("word/document.xml"))
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            for i, p in enumerate(root.findall(".//w:p", ns)):
                text = "".join(t.text or "" for t in p.findall(".//w:t", ns))
                if text.strip():
                    sources.append({"ref": f"paragraph:{i + 1}", "text": text[:20000]})
    text = "\n".join(s["text"] for s in sources)
    if len(text) > 150000:
        raise ValueError("Extracted text exceeds limit")
    if len(text.strip()) < 30:
        warnings.append("Insufficient text; scanned PDF may require Textract")
    return {"text": text, "sources": sources, "warnings": warnings, "page_count": page_count}


def isolated_extract(data: bytes, kind: str):
    result = subprocess.run(
        [sys.executable, "-m", "app.document_extract", kind],
        input=data,
        capture_output=True,
        timeout=30,
        check=False,
        env={k: v for k, v in os.environ.items() if k.upper() in {"PATH", "SYSTEMROOT", "TEMP", "TMP", "LANG"}},
    )
    if result.returncode != 0:
        raise ValueError("Document parser rejected this file")
    return json.loads(result.stdout)


if __name__ == "__main__":
    if sys.platform != "win32":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    try:
        print(json.dumps(extract(sys.stdin.buffer.read(10485761), sys.argv[1])))
    except Exception:
        sys.exit(2)
