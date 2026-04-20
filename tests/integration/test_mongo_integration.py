from __future__ import annotations

import os
from datetime import datetime, timezone


def test_mongo_profile_round_trip(mongo_db):
    profile = {
        "id": "profile-1",
        "username": "mongo_ci_user",
        "bio": "Mongo integration profile",
        "joined_at": datetime.now(timezone.utc),
        "user_id": "user-1",
    }

    mongo_db["profiles"].insert_one(profile)
    stored = mongo_db["profiles"].find_one({"username": "mongo_ci_user"})

    assert stored is not None
    assert stored["bio"] == "Mongo integration profile"
    assert stored["user_id"] == "user-1"


def test_get_mongo_db_dependency_yields_live_database(monkeypatch, mongo_client):
    from AINDY.db import mongo_setup

    monkeypatch.setattr(mongo_setup, "_client", mongo_client)

    dependency = mongo_setup.get_mongo_db()
    db = next(dependency)

    assert db.name == os.environ.get("MONGO_DB_NAME", "aindy_test")
    assert db.client is mongo_client


def test_mongo_posts_round_trip_supports_retrieval(mongo_db):
    created_at = datetime.now(timezone.utc)
    post = {
        "id": "post-1",
        "author_id": "author-1",
        "author_username": "mongo_author",
        "content": "Hello from Mongo integration coverage",
        "tags": ["social", "mongo"],
        "trust_tier_required": "observer",
        "created_at": created_at,
        "impressions": 0,
        "clicks": 0,
        "likes": 0,
        "boosts": 0,
        "comments_count": 0,
    }

    mongo_db["posts"].insert_one(post)
    docs = list(mongo_db["posts"].find({"tags": "mongo"}))

    assert len(docs) == 1
    assert docs[0]["content"].startswith("Hello from Mongo")
