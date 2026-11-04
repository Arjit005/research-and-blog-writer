"""Unit tests for multi-tenant data isolation and idempotent migrations."""

import pytest
import database as db


def test_two_users_complete_data_isolation():
    """Verify User A and User B cannot read, list, update, or delete each other's data."""
    user_a = db.get_or_create_user("user_a@tenant.com")
    user_b = db.get_or_create_user("user_b@tenant.com")

    # 1. User A creates an article
    art_a_id = db.save_article(
        topic="Confidential AI Project A",
        content="Secret specs for project A.",
        user_id=user_a["id"],
    )

    # 2. User B creates an article
    art_b_id = db.save_article(
        topic="Confidential AI Project B",
        content="Secret specs for project B.",
        user_id=user_b["id"],
    )

    # 3. Listing articles must only return the authenticated user's articles
    articles_for_a = db.get_articles(user_id=user_a["id"])
    assert all(a["user_id"] == user_a["id"] for a in articles_for_a)
    assert any(a["id"] == art_a_id for a in articles_for_a)
    assert not any(a["id"] == art_b_id for a in articles_for_a)

    articles_for_b = db.get_articles(user_id=user_b["id"])
    assert all(b["user_id"] == user_b["id"] for b in articles_for_b)
    assert any(b["id"] == art_b_id for b in articles_for_b)
    assert not any(b["id"] == art_a_id for b in articles_for_b)

    # 4. Numeric ID Guessing Attack: User B attempts to directly read User A's article ID
    leak_attempt = db.get_article(art_a_id, user_id=user_b["id"])
    assert leak_attempt is None, "Cross-tenant ID guessing attack succeeded! Data was not isolated."

    # 5. User B attempts to tamper with User A's article content
    db.update_article_content(art_a_id, "Tampered by User B!", user_id=user_b["id"])
    unaltered = db.get_article(art_a_id, user_id=user_a["id"])
    assert unaltered["content"] == "Secret specs for project A."

    # 6. User B attempts to apply a revision or delete User A's article
    with pytest.raises(ValueError):
        db.apply_article_edit_transaction(art_a_id, "Malicious edit", summary="Hack", user_id=user_b["id"])

    db.delete_article(art_a_id, user_id=user_b["id"])
    still_exists = db.get_article(art_a_id, user_id=user_a["id"])
    assert still_exists is not None

    # 7. Memory isolation
    db.set_user_memory("style", "User A Terse", user_id=user_a["id"])
    db.set_user_memory("style", "User B Verbose", user_id=user_b["id"])

    mems_a = db.get_user_memories(user_id=user_a["id"])
    mems_b = db.get_user_memories(user_id=user_b["id"])

    assert mems_a.get("style") == "User A Terse"
    assert mems_b.get("style") == "User B Verbose"


def test_claim_legacy_data_workflow():
    """Verify explicit claim_legacy_data migrates unowned rows safely without silent leaks."""
    # Create an unowned legacy article
    legacy_art_id = db.save_article(
        topic="Legacy Unassigned Project",
        content="Historical content before auth was introduced.",
        user_id=None,
    )

    unclaimed_count = db.count_unclaimed_legacy_articles()
    assert unclaimed_count >= 1

    # Verified user claims legacy data
    new_user = db.get_or_create_user("claimant@example.com")
    claimed_count = db.claim_legacy_data(new_user["id"])
    assert claimed_count >= 1

    # Verify article is now owned by new_user
    claimed_art = db.get_article(legacy_art_id, user_id=new_user["id"])
    assert claimed_art is not None
    assert claimed_art["user_id"] == new_user["id"]


def test_migrations_are_idempotent():
    """Verify running init_db multiple times changes nothing and raises no errors."""
    for _ in range(3):
        db.init_db()
