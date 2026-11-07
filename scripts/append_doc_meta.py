with open("database.py", "rb") as f:
    text = f.read().decode("utf-8")

methods = """

# ---------------------------------------------------------------------------
# Report & Document Studio: Document Metadata & Settings
# ---------------------------------------------------------------------------

def save_document_metadata(
    article_id: int,
    user_id: int,
    title: Optional[str] = None,
    abstract: Optional[str] = None,
    keywords: Optional[str] = None,
    authors: Optional[str] = None,
    institution: Optional[str] = None,
    citation_style: str = "IEEE",
    version_tag: str = "v1.0",
    layout_settings: Optional[Dict[str, Any]] = None,
) -> bool:
    \"\"\"Upsert structured academic document metadata for an article.\"\"\"
    layout_str = json.dumps(layout_settings) if layout_settings is not None else None
    legacy = _legacy_sql()
    with get_connection() as (conn, is_tidb):
        art_cur = _exec(
            conn, is_tidb,
            f"SELECT id FROM articles WHERE id = ? AND (user_id = ?{legacy})",
            (article_id, user_id),
        )
        if not art_cur.fetchone():
            return False

        if is_tidb:
            sql = \"\"\"
                INSERT INTO document_metadata (
                    article_id, user_id, title, abstract, keywords,
                    authors, institution, citation_style, version_tag, layout_settings
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE
                    title = VALUES(title),
                    abstract = VALUES(abstract),
                    keywords = VALUES(keywords),
                    authors = VALUES(authors),
                    institution = VALUES(institution),
                    citation_style = VALUES(citation_style),
                    version_tag = VALUES(version_tag),
                    layout_settings = VALUES(layout_settings),
                    updated_at = NOW()
            \"\"\"
        else:
            sql = \"\"\"
                INSERT INTO document_metadata (
                    article_id, user_id, title, abstract, keywords,
                    authors, institution, citation_style, version_tag, layout_settings
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(article_id) DO UPDATE SET
                    title = excluded.title,
                    abstract = excluded.abstract,
                    keywords = excluded.keywords,
                    authors = excluded.authors,
                    institution = excluded.institution,
                    citation_style = excluded.citation_style,
                    version_tag = excluded.version_tag,
                    layout_settings = excluded.layout_settings,
                    updated_at = datetime('now')
            \"\"\"
        _exec(
            conn, is_tidb, sql,
            (
                article_id, user_id, title, abstract, keywords,
                authors, institution, citation_style, version_tag, layout_str
            ),
        )
        return True


def get_document_metadata(article_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    \"\"\"Retrieve structured academic document metadata for an article.\"\"\"
    legacy = _legacy_sql()
    with get_connection() as (conn, is_tidb):
        cur = _exec(
            conn, is_tidb,
            f"SELECT * FROM document_metadata WHERE article_id = ? AND (user_id = ?{legacy})",
            (article_id, user_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        res = _row_to_dict(row)
        if res.get("layout_settings"):
            try:
                res["layout_settings"] = json.loads(res["layout_settings"])
            except Exception:
                pass
        return res
"""

target = "def get_visual_evidence_links(visual_id: int, user_id: int) -> List[Dict[str, Any]]:"
idx = text.find(target)
end_of_func = text.find("\n\n\n# init_db()", idx)
if end_of_func == -1:
    end_of_func = text.find("\n# init_db()", idx)

if end_of_func != -1:
    new_text = text[:end_of_func] + methods + text[end_of_func:]
    with open("database.py", "wb") as f:
        f.write(new_text.encode("utf-8"))
    print("Appended successfully at end_of_func:", end_of_func)
else:
    print("Could not find end of get_visual_evidence_links")
