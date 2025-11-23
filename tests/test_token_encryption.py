"""Tests for token encryption utilities."""
from unittest.mock import patch
import pytest

from app.utils.token_encryption import encrypt_token, decrypt_token


def test_encrypt_decrypt_token_with_key():
    """Test token encryption and decryption with encryption key."""
    with patch("app.utils.token_encryption.ENCRYPTION_KEY", "test_key_that_is_32_bytes_long"):
        token = "test_access_token_value"
        encrypted = encrypt_token(token)
        
        # Should be encrypted (different from original)
        assert encrypted != token
        
        # Should decrypt back to original
        decrypted = decrypt_token(encrypted)
        assert decrypted == token


def test_encrypt_token_without_key():
    """Test token encryption without key returns plaintext."""
    with patch("app.utils.token_encryption.ENCRYPTION_KEY", None):
        token = "test_token"
        encrypted = encrypt_token(token)
        assert encrypted == token


def test_decrypt_token_without_key():
    """Test token decryption without key returns ciphertext."""
    with patch("app.utils.token_encryption.ENCRYPTION_KEY", None):
        token = "encrypted_token"
        decrypted = decrypt_token(token)
        assert decrypted == token


def test_encrypt_none_token():
    """Test encrypting None token."""
    result = encrypt_token(None)
    assert result is None


def test_decrypt_none_token():
    """Test decrypting None token."""
    result = decrypt_token(None)
    assert result is None


def test_encrypt_empty_token():
    """Test encrypting empty string token."""
    with patch("app.utils.token_encryption.ENCRYPTION_KEY", "test_key_that_is_32_bytes_long"):
        token = ""
        encrypted = encrypt_token(token)
        # Empty string should still be processable
        assert encrypted is not None


def test_decrypt_invalid_token():
    """Test decrypting invalid ciphertext."""
    with patch("app.utils.token_encryption.ENCRYPTION_KEY", "test_key_that_is_32_bytes_long"):
        invalid = "not_a_valid_encrypted_token"
        # Should return original if decryption fails
        result = decrypt_token(invalid)
        assert result == invalid


def test_encrypt_long_token():
    """Test encrypting a long token."""
    with patch("app.utils.token_encryption.ENCRYPTION_KEY", "test_key_that_is_32_bytes_long"):
        long_token = "a" * 1000
        encrypted = encrypt_token(long_token)
        decrypted = decrypt_token(encrypted)
        assert decrypted == long_token


def test_encrypt_special_characters():
    """Test encrypting token with special characters."""
    with patch("app.utils.token_encryption.ENCRYPTION_KEY", "test_key_that_is_32_bytes_long"):
        token = "token!@#$%^&*()_+-={}[]|:;<>?,./"
        encrypted = encrypt_token(token)
        decrypted = decrypt_token(encrypted)
        assert decrypted == token


def test_encrypt_unicode_token():
    """Test encrypting token with unicode characters."""
    with patch("app.utils.token_encryption.ENCRYPTION_KEY", "test_key_that_is_32_bytes_long"):
        token = "token_with_unicode_🔐🔑"
        encrypted = encrypt_token(token)
        decrypted = decrypt_token(encrypted)
        assert decrypted == token
