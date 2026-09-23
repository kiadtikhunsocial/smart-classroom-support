"""Unit tests for the upload validation and signed-download boundary."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import storage
from app.main import app


PNG = b"\x89PNG\r\n\x1a\nminimal-payload"


def test_upload_requires_matching_extension_and_mime():
    assert storage.validate_upload(PNG, "photo.png", "image/png") == ".png"

    with pytest.raises(HTTPException) as mismatch:
        storage.validate_upload(PNG, "photo.jpg", "image/jpeg")
    assert mismatch.value.status_code == 415


def test_upload_rejects_unknown_content_even_with_image_extension():
    with pytest.raises(HTTPException) as unsupported:
        storage.validate_upload(b"not an image", "photo.png", "image/png")
    assert unsupported.value.status_code == 415


def test_signed_url_is_bound_to_exact_generated_name():
    name = "0123456789abcdef0123456789abcdef.png"
    signature = storage.sign_upload_name(name)
    assert storage.verify_upload_signature(name, signature)
    assert not storage.verify_upload_signature("f" * 32 + ".png", signature)
    assert storage.is_servable_upload_name(name)
    assert not storage.is_servable_upload_name("../" + name)


def test_public_image_upload_is_available_without_login_but_general_upload_is_not(monkeypatch):
    monkeypatch.setattr(
        "app.main.save_upload",
        lambda content, filename, content_type: {"url": "/uploads/signed.png"},
    )
    client = TestClient(app)

    public = client.post(
        "/api/public/uploads",
        files={"file": ("photo.png", PNG, "image/png")},
    )
    protected = client.post(
        "/api/uploads",
        files={"file": ("photo.png", PNG, "image/png")},
    )

    assert public.status_code == 201
    assert protected.status_code == 401


def test_public_upload_rejects_non_image_and_files_over_5mb(monkeypatch):
    monkeypatch.setattr(
        "app.main.save_upload",
        lambda content, filename, content_type: {"url": "/unused"},
    )
    client = TestClient(app)

    unsupported = client.post(
        "/api/public/uploads",
        files={"file": ("document.pdf", b"%PDF-1.7 payload", "application/pdf")},
    )
    too_large = client.post(
        "/api/public/uploads",
        files={"file": ("photo.png", PNG + b"0" * (5 * 1024 * 1024), "image/png")},
    )

    assert unsupported.status_code == 415
    assert too_large.status_code == 413
