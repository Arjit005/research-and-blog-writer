import os

with open("database.py", "r", encoding="utf-8") as f:
    text = f.read()

funcs = '''
# ---------------------------------------------------------------------------
# Visual Research System: Visuals, Charts, and Evidence Links
# ---------------------------------------------------------------------------

def save_research_visual(
    user_id: int,
    visual_type: str,
    origin_type: str,
    title: str,
    article_id: Optional[int] = None,
    run_id: Optional[str] = None,
    caption: Optional[str] = None,
    description: Optional[str] = None,
    source_url: Optional[str] = None,
    source_title: Optional[str] = None,
    publisher: Optional[str] = None,
    author: Optional[str] = None,
    publication_date: Optional[str] = None,
    license_information: Optional[str] = None,
    usage_restrictions: Optional[str] = None,
    alt_text: Optional[str] = None,
    dimensions: Optional[str] = None,
    file_format: Optional[str] = None,
    media_content: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    metadata_json: Optional[Dict[str, Any]] = None,
) -> int:
    meta_str = json.dumps(metadata_json) if metadata_json else None
    with get_connection() as (conn, is_tidb):
        cur = _exec(
            conn, is_tidb,
            """
            INSERT INTO research_visuals (
                user_id, article_id, run_id, visual_type, origin_type,
                title, caption, description, source_url, source_title,
                publisher, author, publication_date, license_information,
                usage_restrictions, alt_text, dimensions, file_format,
                media_content, thumbnail_url, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, article_id, run_id, visual_type, origin_type,
                title, caption, description, source_url, source_title,
                publisher, author, publication_date, license_information,
                usage_restrictions, alt_text, dimensions, file_format,
                media_content, thumbnail_url, meta_str,
            ),
        )
        return int(cur.lastrowid)


def get_research_visual(visual_id: int, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cur = _exec(conn, is_tidb, "SELECT * FROM research_visuals WHERE id = ? AND user_id = ?", (visual_id, user_id))
        else:
            cur = _exec(conn, is_tidb, "SELECT * FROM research_visuals WHERE id = ?", (visual_id,))
        row = cur.fetchone()
        if not row:
            return None
        d = _row_to_dict(row)
        if d.get("metadata_json") and isinstance(d["metadata_json"], str):
            try:
                d["metadata_json"] = json.loads(d["metadata_json"])
            except Exception:
                pass
        return d


def list_research_visuals(
    user_id: int,
    article_id: Optional[int] = None,
    visual_type: Optional[str] = None,
    origin_type: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "recent",
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    safe_limit = _clamp_limit(limit, default=50, maximum=100)
    safe_offset = max(0, offset)
    clauses = ["user_id = ?"]
    params: List[Any] = [user_id]
    if article_id is not None:
        clauses.append("article_id = ?")
        params.append(article_id)
    if visual_type:
        clauses.append("visual_type = ?")
        params.append(visual_type)
    if origin_type:
        clauses.append("origin_type = ?")
        params.append(origin_type)
    if search:
        clauses.append("(title LIKE ? OR caption LIKE ? OR alt_text LIKE ?)")
        wildcard = f"%{search}%"
        params.extend([wildcard, wildcard, wildcard])
    where_sql = " AND ".join(clauses)
    with get_connection() as (conn, is_tidb):
        count_cur = _exec(conn, is_tidb, f"SELECT COUNT(*) FROM research_visuals WHERE {where_sql}", tuple(params))
        crow = count_cur.fetchone()
        total = int(crow[0] if not isinstance(crow, dict) else list(crow.values())[0])
        order_sql = "title ASC" if sort_by == "title" else "created_at DESC, id DESC"
        query_params = list(params) + [safe_limit, safe_offset]
        cur = _exec(conn, is_tidb, f"SELECT * FROM research_visuals WHERE {where_sql} ORDER BY {order_sql} LIMIT ? OFFSET ?", tuple(query_params))
        rows = cur.fetchall()
        items = []
        for r in rows:
            d = _row_to_dict(r)
            if d.get("metadata_json") and isinstance(d["metadata_json"], str):
                try:
                    d["metadata_json"] = json.loads(d["metadata_json"])
                except Exception:
                    pass
            items.append(d)
        return items, total


def delete_research_visual(visual_id: int, user_id: int) -> bool:
    with get_connection() as (conn, is_tidb):
        cur = _exec(conn, is_tidb, "DELETE FROM research_visuals WHERE id = ? AND user_id = ?", (visual_id, user_id))
        rowcount = getattr(cur, "rowcount", None)
        return bool(rowcount and rowcount > 0)


def save_research_chart(
    user_id: int,
    title: str,
    chart_type: str,
    structured_data: Dict[str, Any],
    article_id: Optional[int] = None,
    description: Optional[str] = None,
    data_source: Optional[str] = None,
    units: Optional[str] = None,
    methodology: Optional[str] = None,
) -> int:
    struct_str = json.dumps(structured_data)
    with get_connection() as (conn, is_tidb):
        cur = _exec(
            conn, is_tidb,
            """
            INSERT INTO research_charts (
                user_id, article_id, title, description,
                chart_type, structured_data, data_source, units, methodology
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, article_id, title, description, chart_type, struct_str, data_source, units, methodology),
        )
        return int(cur.lastrowid)


def list_research_charts(user_id: int, article_id: Optional[int] = None) -> List[Dict[str, Any]]:
    with get_connection() as (conn, is_tidb):
        if article_id is not None:
            cur = _exec(conn, is_tidb, "SELECT * FROM research_charts WHERE user_id = ? AND article_id = ? ORDER BY id ASC", (user_id, article_id))
        else:
            cur = _exec(conn, is_tidb, "SELECT * FROM research_charts WHERE user_id = ? ORDER BY id DESC", (user_id,))
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = _row_to_dict(r)
            if d.get("structured_data") and isinstance(d["structured_data"], str):
                try:
                    d["structured_data"] = json.loads(d["structured_data"])
                except Exception:
                    pass
            result.append(d)
        return result


def link_visual_evidence(
    user_id: int,
    visual_id: int,
    claim_id: Optional[str] = None,
    article_id: Optional[int] = None,
    report_section: Optional[str] = None,
    evidence_status: str = "verified",
    citation_url: Optional[str] = None,
) -> int:
    with get_connection() as (conn, is_tidb):
        cur = _exec(
            conn, is_tidb,
            """
            INSERT INTO visual_evidence_links (
                user_id, visual_id, claim_id, article_id,
                report_section, evidence_status, citation_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, visual_id, claim_id, article_id, report_section, evidence_status, citation_url),
        )
        return int(cur.lastrowid)


def get_visual_evidence_links(visual_id: int, user_id: int) -> List[Dict[str, Any]]:
    with get_connection() as (conn, is_tidb):
        cur = _exec(conn, is_tidb, "SELECT * FROM visual_evidence_links WHERE visual_id = ? AND user_id = ? ORDER BY id ASC", (visual_id, user_id))
        rows = cur.fetchall()
        return [_row_to_dict(r) for r in rows]
'''

target = "# init_db() is called explicitly by:"
if target in text:
    new_text = text.replace(target, funcs.strip() + "\n\n\n" + target, 1)
    with open("database.py", "w", encoding="utf-8") as f:
        f.write(new_text)
    print("Injected functions cleanly into database.py")
else:
    print("Target comment not found!")
