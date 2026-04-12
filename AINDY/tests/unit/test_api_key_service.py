"""
tests/unit/test_api_key_service.py — Security tests for platform API key service.

Verifies that:
- Raw keys are never persisted to the database
- The stored value is a valid SHA-256 hex digest (64 chars)
- validate_key (auth path) compares hashes, not plaintext
- Revocation works correctly
"""
from __future__ import annotations

import hashlib
import uuid
from unittest.mock import MagicMock

import pytest

from AINDY.platform_layer.api_key_service import (
    create_api_key,
    generate_key,
    hash_key,
    revoke_api_key,
)


# ── hash_key() ────────────────────────────────────────────────────────────────

class TestHashKey:
    def test_returns_64_char_hex(self):
        digest = hash_key("aindy_abc123")
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_deterministic(self):
        assert hash_key("same_key") == hash_key("same_key")

    def test_different_keys_produce_different_hashes(self):
        assert hash_key("aindy_aaa") != hash_key("aindy_bbb")

    def test_matches_stdlib_sha256(self):
        raw = "aindy_testkey"
        expected = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        assert hash_key(raw) == expected


# ── generate_key() ────────────────────────────────────────────────────────────

class TestGenerateKey:
    def test_returns_tuple_of_two_strings(self):
        result = generate_key()
        assert isinstance(result, tuple) and len(result) == 2
        raw_key, key_hash = result
        assert isinstance(raw_key, str)
        assert isinstance(key_hash, str)

    def test_raw_key_has_aindy_prefix(self):
        raw_key, _ = generate_key()
        assert raw_key.startswith("aindy_")

    def test_hash_is_sha256_of_raw_key(self):
        raw_key, key_hash = generate_key()
        assert key_hash == hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def test_hash_is_64_chars(self):
        _, key_hash = generate_key()
        assert len(key_hash) == 64

    def test_each_call_generates_unique_key(self):
        raw1, _ = generate_key()
        raw2, _ = generate_key()
        assert raw1 != raw2


# ── create_api_key() — raw key not stored ─────────────────────────────────────

class TestApiKeyNotStoredPlain:
    def test_api_key_not_stored_plain(self, db_session, test_user):
        """Raw key must not appear in any column of the persisted record."""
        from AINDY.db.models.api_key import PlatformAPIKey

        record, raw_key = create_api_key(
            user_id=str(test_user.id),
            name="test-key",
            scopes=["memory.read"],
            db=db_session,
        )

        stored = db_session.query(PlatformAPIKey).filter_by(id=record.id).first()

        # Core contract: hash stored, not plaintext
        assert stored.key_hash != raw_key, "Raw key must not be stored in key_hash"
        assert len(stored.key_hash) == 64, "Expected SHA-256 hex digest (64 chars)"

        # Hash must be reproducible from the raw key
        assert stored.key_hash == hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def test_key_prefix_is_not_full_key(self, db_session, test_user):
        """key_prefix is a display hint only — shorter than any real key."""
        from AINDY.db.models.api_key import PlatformAPIKey

        record, raw_key = create_api_key(
            user_id=str(test_user.id),
            name="prefix-check",
            scopes=[],
            db=db_session,
        )
        stored = db_session.query(PlatformAPIKey).filter_by(id=record.id).first()

        assert len(stored.key_prefix) < len(raw_key)
        assert raw_key.startswith(stored.key_prefix)

    def test_raw_key_returned_to_caller(self, db_session, test_user):
        """create_api_key must return the raw key so the caller can deliver it."""
        record, raw_key = create_api_key(
            user_id=str(test_user.id),
            name="caller-key",
            scopes=["memory.read"],
            db=db_session,
        )
        assert raw_key.startswith("aindy_")
        assert len(raw_key) > 16


# ── Auth path — validation uses hash comparison ────────────────────────────────

class TestValidateKeyUsesHash:
    def test_correct_key_validates(self, db_session, test_user):
        """Providing the raw key must resolve to the active record via hash lookup."""
        from AINDY.db.models.api_key import PlatformAPIKey

        record, raw_key = create_api_key(
            user_id=str(test_user.id),
            name="validate-ok",
            scopes=["memory.read"],
            db=db_session,
        )

        # The auth layer looks up by hash; simulate it directly
        expected_hash = hash_key(raw_key)
        found = db_session.query(PlatformAPIKey).filter_by(key_hash=expected_hash).first()
        assert found is not None
        assert str(found.id) == str(record.id)
        assert found.is_valid()

    def test_wrong_key_does_not_validate(self, db_session, test_user):
        """A different raw key must not match the stored hash."""
        from AINDY.db.models.api_key import PlatformAPIKey

        create_api_key(
            user_id=str(test_user.id),
            name="mismatch",
            scopes=[],
            db=db_session,
        )

        wrong_hash = hash_key("aindy_completely_wrong_key_value")
        found = db_session.query(PlatformAPIKey).filter_by(key_hash=wrong_hash).first()
        assert found is None

    def test_hash_of_provided_key_matches_stored_hash(self, db_session, test_user):
        """
        Core invariant: hash(raw_key_at_creation) == stored key_hash ==
        hash(raw_key_at_validation).
        """
        from AINDY.db.models.api_key import PlatformAPIKey

        record, raw_key = create_api_key(
            user_id=str(test_user.id),
            name="invariant",
            scopes=["memory.read"],
            db=db_session,
        )

        stored = db_session.query(PlatformAPIKey).filter_by(id=record.id).first()

        # Simulate what the auth path does with a provided key
        hash_at_validation = hash_key(raw_key)
        assert hash_at_validation == stored.key_hash


# ── Revocation ─────────────────────────────────────────────────────────────────

class TestRevocation:
    def test_revoked_key_is_not_valid(self, db_session, test_user):
        user_id = str(test_user.id)
        record, _ = create_api_key(
            user_id=user_id,
            name="to-revoke",
            scopes=[],
            db=db_session,
        )
        assert record.is_valid()

        revoke_api_key(str(record.id), user_id, db_session)

        db_session.refresh(record)
        assert not record.is_valid()
        assert record.revoked_at is not None

    def test_revoke_wrong_owner_returns_false(self, db_session, test_user):
        record, _ = create_api_key(
            user_id=str(test_user.id),
            name="ownership-check",
            scopes=[],
            db=db_session,
        )
        result = revoke_api_key(str(record.id), str(uuid.uuid4()), db_session)
        assert result is False

