"""Unit tests for the upload validation and signed-download boundary."""

import pytest
from fastapi import HTTPException

from app import storage


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
