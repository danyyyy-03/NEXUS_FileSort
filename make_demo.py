"""Create a harmless test folder next to this script, without overwriting files."""
from __future__ import annotations

import base64
import io
import zipfile
from pathlib import Path


def create_pdf() -> bytes:
    """Produce a minimal valid one-page PDF using only the standard library."""
    parts = [b"%PDF-1.4\n"]
    offsets = [0]
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length 50 >>\nstream\nBT /F1 16 Tf 30 100 Td (NEXUS FileSort demo) Tj ET\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i, content in enumerate(objects, 1):
        offsets.append(sum(map(len, parts)))
        parts.append(f"{i} 0 obj\n".encode() + content + b"\nendobj\n")
    cross_ref_start = sum(map(len, parts))
    parts.append(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        parts.append(f"{offset:010d} 00000 n \n".encode())
    parts.append(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{cross_ref_start}\n%%EOF\n".encode())
    return b"".join(parts)


def main():
    folder = Path(__file__).resolve().parent / "_TEST_FOLDER"
    folder.mkdir(exist_ok=True)
    data = {
        "notes.txt": b"Hello! Test file for NEXUS FileSort.\n",
        "data.csv": b"item,amount\napples,3\npears,5\n",
        "report.pdf": create_pdf(),
        "photo.png": base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lV8AAAAASUVORK5CYII="
        ),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "NEXUS FileSort demo")
    data["archive.zip"] = buffer.getvalue()

    created = 0
    for name, content in data.items():
        try:
            with (folder / name).open("xb") as stream:
                stream.write(content)
            created += 1
        except FileExistsError:
            print(f"Already exists, skipped: {name}")
    print(f"Demo folder: {folder}")
    print(f"New files created: {created}. Existing files were not modified.")
    print("Open FileSort, select the folder above, then click Preview Files.")


if __name__ == "__main__":
    main()
