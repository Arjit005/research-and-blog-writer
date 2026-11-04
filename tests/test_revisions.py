"""Unit tests for revisions, atomic apply/rollback transactions, and diff generation."""

import pytest
from unittest.mock import patch, MagicMock
import database as db
from core.revisions import calculate_diff_stats, generate_inline_diff_html


def test_apply_and_rollback_roundtrip():
    """Verify that applying an edit snapshots revision and rollback restores exact text."""
    # 1. Create initial article
    initial_content = "# Version 1.0\n\nInitial technical draft."
    article_id = db.save_article("Test Architecture", initial_content)

    # 2. Apply revision 1
    rev1_content = "# Version 1.1\n\nInitial technical draft with added benchmarks."
    rev_num = db.apply_article_edit_transaction(article_id, rev1_content, summary="Added benchmarks")
    assert rev_num == 1

    # Verify article table content updated
    current_art = db.get_article(article_id)
    assert current_art["content"] == rev1_content

    # Verify revision was recorded
    revs = db.get_article_revisions(article_id)
    assert len(revs) == 1
    assert revs[0]["content"] == initial_content  # snapshot of V1.0
    assert revs[0]["revision_num"] == 1

    # 3. Apply revision 2
    rev2_content = "# Version 1.2\n\nCompletely rewritten section on vLLM."
    rev_num_2 = db.apply_article_edit_transaction(article_id, rev2_content, summary="Rewrote vLLM")
    assert rev_num_2 == 2

    revs_after = db.get_article_revisions(article_id)
    assert len(revs_after) == 2

    # 4. Rollback to first revision (which held initial_content)
    target_rev_id = revs[0]["id"]
    success = db.rollback_article_revision_transaction(article_id, target_rev_id)
    assert success is True

    # Current article content must match exact initial_content
    restored_art = db.get_article(article_id)
    assert restored_art["content"] == initial_content

    # Revisions history should now have 3 revisions (including snapshot before rollback)
    revs_final = db.get_article_revisions(article_id)
    assert len(revs_final) == 3
    assert "Before rollback" in revs_final[0]["summary"]


def test_diff_identical_text():
    """Diff of identical text must report zero changes and clean notice."""
    text = "# Same content\nLine 1\nLine 2"
    stats = calculate_diff_stats(text, text)
    assert stats["additions"] == 0
    assert stats["deletions"] == 0
    assert stats["total_changes"] == 0

    diff_html = generate_inline_diff_html(text, text)
    assert "No differences found" in diff_html


def test_diff_modified_text():
    """Diff of modified text must count additions/deletions and render colored markup."""
    old_text = "Line 1\nLine 2"
    new_text = "Line 1\nLine 2 modified\nLine 3 added"

    stats = calculate_diff_stats(old_text, new_text)
    assert stats["additions"] == 2
    assert stats["deletions"] == 1

    diff_html = generate_inline_diff_html(old_text, new_text)
    assert "diff-add" in diff_html
    assert "diff-del" in diff_html
    assert "+Line 3 added" in diff_html


def test_apply_transaction_failure_leaves_article_intact():
    """If an error occurs midway, the transaction should rollback leaving content unchanged."""
    article_id = db.save_article("Safety Test", "Untouched original text")

    with patch("database._exec") as mock_exec:
        # First call succeeds (SELECT content), second call raises
        mock_exec.side_effect = [
            MagicMock(fetchone=lambda: {"content": "Untouched original text"}),
            Exception("Simulated disk error"),
        ]

        with pytest.raises(Exception):
            db.apply_article_edit_transaction(article_id, "Bad text that shouldn't save")

    # Verify article is still untouched
    art = db.get_article(article_id)
    assert art["content"] == "Untouched original text"
