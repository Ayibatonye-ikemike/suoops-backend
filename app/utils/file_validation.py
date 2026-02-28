"""File upload validation utilities.

Validates uploaded files by checking magic bytes (file signatures)
in addition to Content-Type headers to prevent malicious uploads
with spoofed MIME types.
"""

from __future__ import annotations

# Magic byte signatures for allowed file types
# Reference: https://en.wikipedia.org/wiki/List_of_file_signatures
_MAGIC_BYTES: dict[str, list[bytes]] = {
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/gif": [b"GIF87a", b"GIF89a"],
    "image/webp": [b"RIFF"],  # Full check: RIFF....WEBP
    "image/bmp": [b"BM"],
    "application/pdf": [b"%PDF"],
    "image/svg+xml": [b"<?xml", b"<svg"],  # SVG can start with XML declaration or svg tag
}

# Map of allowed extensions per content type
_ALLOWED_EXTENSIONS: dict[str, set[str]] = {
    "image/jpeg": {"jpg", "jpeg"},
    "image/jpg": {"jpg", "jpeg"},
    "image/png": {"png"},
    "image/gif": {"gif"},
    "image/webp": {"webp"},
    "image/bmp": {"bmp"},
    "image/svg+xml": {"svg"},
    "application/pdf": {"pdf"},
}


def validate_file_magic_bytes(content: bytes, claimed_content_type: str) -> bool:
    """Validate that file content matches the claimed Content-Type via magic bytes.

    Args:
        content: Raw file bytes.
        claimed_content_type: The Content-Type header value from the upload.

    Returns:
        True if the magic bytes match the claimed type; False otherwise.
    """
    if not content:
        return False

    signatures = _MAGIC_BYTES.get(claimed_content_type)
    if signatures is None:
        # Unknown type — reject by default
        return False

    # Special handling for WebP: must be RIFF....WEBP
    if claimed_content_type == "image/webp":
        return content[:4] == b"RIFF" and content[8:12] == b"WEBP"

    # Special handling for SVG: content may start with whitespace/BOM
    if claimed_content_type == "image/svg+xml":
        # Strip whitespace and BOM for SVG detection
        stripped = content.lstrip(b"\xef\xbb\xbf \t\n\r")
        return stripped[:5] == b"<?xml" or stripped[:4] == b"<svg"

    return any(content[: len(sig)] == sig for sig in signatures)


def get_safe_extension(filename: str | None, content_type: str) -> str:
    """Extract file extension from filename, validated against allowed extensions.

    Falls back to a safe default based on content_type if the filename's
    extension is missing or not in the allowlist.

    Args:
        filename: Original filename from the upload (may be None).
        content_type: The Content-Type of the upload.

    Returns:
        A safe, validated file extension (without dot).
    """
    # Default extensions per content type
    defaults = {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "image/gif": "gif",
        "image/webp": "webp",
        "image/bmp": "bmp",
        "image/svg+xml": "svg",
        "application/pdf": "pdf",
    }

    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower().strip()
        allowed = _ALLOWED_EXTENSIONS.get(content_type, set())
        if ext in allowed:
            return ext

    return defaults.get(content_type, "bin")
