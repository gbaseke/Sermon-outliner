#!/usr/bin/env python3
"""
Message Search
==============
Build a SQLite index from sermon transcript markdown files and search it
with FTS5 MATCH queries.

Commands
--------
  python main.py build           Build (or rebuild) the index
  python main.py search <query>  Search paragraphs

FTS5 query examples (use --raw to pass operators directly):
  python main.py search "faith"
  python main.py search "faith healing"          # phrase search (default)
  python main.py search --raw "faith AND heal*"  # FTS5 operators
  python main.py search --raw "NEAR(faith heal, 5)"
"""

import re
import sys
import sqlite3
from pathlib import Path

import click
import sqlite_vec


# ── defaults ────────────────────────────────────────────────────────────────

DEFAULT_DB   = "messages.db"
DEFAULT_DIR  = "TheMessage"


# ── database helpers ─────────────────────────────────────────────────────────

def open_db(db_path: str | Path) -> sqlite3.Connection:
    """Return a connection with sqlite-vec loaded and Row factory set."""
    db = sqlite3.connect(db_path)
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    db.row_factory = sqlite3.Row
    return db


def init_schema(db: sqlite3.Connection) -> None:
    db.executescript("""
        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT    NOT NULL,
            title       TEXT    NOT NULL,
            filename    TEXT    NOT NULL,
            day_of_week TEXT,
            location    TEXT,
            duration    TEXT,
            author      TEXT
        );

        CREATE TABLE IF NOT EXISTS paragraphs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id    INTEGER NOT NULL REFERENCES messages(id),
            paragraph_num INTEGER NOT NULL,
            text          TEXT    NOT NULL
        );

        -- FTS5 virtual table
        -- 'text' is the indexed column; the rest are stored but not indexed.
        -- tokenize='porter unicode61' enables stemming so that e.g. "heal"
        -- also matches "healing", "healed", "healer".
        CREATE VIRTUAL TABLE IF NOT EXISTS paragraphs_fts USING fts5(
            text,
            message_id    UNINDEXED,
            paragraph_num UNINDEXED,
            tokenize = 'porter unicode61'
        );

        -- sqlite-vec: vector table (ready for embedding-based semantic search).
        -- Populate message_id + embedding after running an embedding model.
        -- Dimension 0 = placeholder; change to match your model's output size.
        -- CREATE VIRTUAL TABLE IF NOT EXISTS vec_paragraphs USING vec0(
        --     message_id    INTEGER,
        --     paragraph_num INTEGER,
        --     embedding     float[768]
        -- );
    """)
    db.commit()


# ── markdown parsing ─────────────────────────────────────────────────────────

def parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Split YAML-like frontmatter (between --- markers) from the body."""
    if not content.startswith("---"):
        return {}, content
    end = content.find("---", 3)
    if end == -1:
        return {}, content

    fm: dict[str, str] = {}
    for line in content[3:end].splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()

    return fm, content[end + 3:].strip()


# Matches  **42**  followed by paragraph text up to the next **N** marker or EOF.
_PARA_RE = re.compile(r"\*\*(\d+)\*\*\s+(.*?)(?=\n\s*\*\*\d+\*\*|\Z)", re.DOTALL)


def parse_paragraphs(body: str) -> list[tuple[int, str]]:
    """Return [(paragraph_num, cleaned_text), …] for every **N** paragraph."""
    result = []
    for m in _PARA_RE.finditer(body):
        text = re.sub(r"\s+", " ", m.group(2)).strip()
        if text:
            result.append((int(m.group(1)), text))
    return result


# ── CLI commands ─────────────────────────────────────────────────────────────

@click.group()
def cli() -> None:
    """Message Search – index and query sermon transcripts."""


@cli.command()
@click.option("--messages-dir", default=DEFAULT_DIR, show_default=True,
              help="Root folder containing year sub-folders with .md files.")
@click.option("--db", "db_path", default=DEFAULT_DB, show_default=True,
              help="SQLite database file to create/overwrite.")
def build(messages_dir: str, db_path: str) -> None:
    """Parse all markdown files and build the full-text search index."""
    root = Path(messages_dir)
    if not root.exists():
        click.echo(f"Error: '{root}' not found.", err=True)
        sys.exit(1)

    db = open_db(db_path)
    init_schema(db)

    # Full rebuild – wipe existing rows
    db.execute("DELETE FROM paragraphs_fts")
    db.execute("DELETE FROM paragraphs")
    db.execute("DELETE FROM messages")
    db.commit()

    md_files = sorted(root.rglob("*.md"))
    click.echo(f"Found {len(md_files)} files – indexing …\n")

    skipped = 0
    with click.progressbar(md_files, label="Indexing") as bar:
        for md_file in bar:
            try:
                content = md_file.read_text(encoding="utf-8", errors="replace")
                fm, body = parse_frontmatter(content)

                date  = fm.get("Date",  "").strip()
                title = fm.get("Title", md_file.stem).strip()

                if not date:
                    skipped += 1
                    continue

                cur = db.execute(
                    """INSERT INTO messages
                           (date, title, filename, day_of_week, location, duration, author)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        date,
                        title,
                        str(md_file.relative_to(root)),
                        fm.get("DayOfTheWeek", ""),
                        fm.get("Location",     ""),
                        fm.get("Duration",     ""),
                        fm.get("Author",       ""),
                    ),
                )
                message_id = cur.lastrowid

                for num, text in parse_paragraphs(body):
                    db.execute(
                        "INSERT INTO paragraphs (message_id, paragraph_num, text)"
                        " VALUES (?, ?, ?)",
                        (message_id, num, text),
                    )
                    db.execute(
                        "INSERT INTO paragraphs_fts (text, message_id, paragraph_num)"
                        " VALUES (?, ?, ?)",
                        (text, message_id, num),
                    )

                db.commit()

            except Exception as exc:
                click.echo(f"\n  ! {md_file.name}: {exc}", err=True)

    msg_count  = db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    para_count = db.execute("SELECT COUNT(*) FROM paragraphs").fetchone()[0]
    note = f"  ({skipped} skipped – no date)" if skipped else ""
    click.echo(f"\nDone.  {msg_count} messages · {para_count} paragraphs indexed{note}")
    db.close()


@cli.command()
@click.argument("query")
@click.option("--db", "db_path", default=DEFAULT_DB, show_default=True,
              help="SQLite database to search.")
@click.option("--limit", default=10, show_default=True,
              help="Maximum results to return.")
@click.option("--snippet-len", default=500, show_default=True,
              help="Max characters shown per paragraph.")
@click.option("--raw", is_flag=True,
              help="Pass QUERY directly to FTS5 (enables operators like AND, OR, NEAR, *).")
def search(query: str, db_path: str, limit: int, snippet_len: int, raw: bool) -> None:
    """
    Search paragraphs and print  Date – Title – ¶N – Text.

    \b
    By default multi-word queries are treated as exact phrases:
      python main.py search "faith healing"

    Use --raw for FTS5 operators:
      python main.py search --raw "faith AND heal*"
      python main.py search --raw "NEAR(faith healing, 5)"
      python main.py search --raw "faith OR grace"
    """
    db_file = Path(db_path)
    if not db_file.exists():
        click.echo(f"Database '{db_path}' not found. Run 'build' first.", err=True)
        sys.exit(1)

    db       = open_db(db_file)
    fts_expr = query if raw else _to_fts_expr(query)

    try:
        rows = db.execute(
            """
            SELECT m.date, m.title, pf.paragraph_num, pf.text
            FROM   paragraphs_fts pf
            JOIN   messages m ON m.id = pf.message_id
            WHERE  paragraphs_fts MATCH ?
            ORDER  BY rank
            LIMIT  ?
            """,
            (fts_expr, limit),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        click.echo(f"Query error: {exc}", err=True)
        click.echo(
            "Tip: use --raw for FTS5 operators, or check your query syntax.",
            err=True,
        )
        sys.exit(1)

    if not rows:
        click.echo(f"No results for '{fts_expr}'.")
        db.close()
        return

    click.echo(f"\n{len(rows)} result(s) for '{fts_expr}':\n")
    sep = click.style("-" * 72, fg="bright_black")

    for row in rows:
        text = row["text"]
        if len(text) > snippet_len:
            text = text[:snippet_len] + "…"

        click.echo(sep)
        click.echo(
            f"{click.style(row['date'], fg='cyan')}  –  "
            f"{click.style(row['title'], fg='bright_white')}  –  "
            f"¶{row['paragraph_num']}"
        )
        click.echo(f"  {text}")

    click.echo(sep)
    db.close()


# ── query helpers ─────────────────────────────────────────────────────────────

def _to_fts_expr(query: str) -> str:
    """
    Convert a plain user query to an FTS5 MATCH expression.

    Rules:
    - Already contains FTS5 syntax (quotes, *, ^, parens, operators) → pass through.
    - Single word → pass through (FTS5 + porter stemmer handle it).
    - Multiple words → wrap in double-quotes → exact phrase search.
    """
    s = query.strip()

    # Detect explicit FTS5 syntax and leave it untouched
    has_syntax = any(c in s for c in ('"', "*", "^", "(", ")"))
    upper = s.upper()
    has_operator = any(
        f" {op} " in upper for op in ("AND", "OR", "NOT", "NEAR")
    ) or upper.startswith(("AND ", "OR ", "NOT ", "NEAR("))

    if has_syntax or has_operator:
        return s

    words = s.split()
    return s if len(words) == 1 else f'"{s}"'


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
