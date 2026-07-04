"""
database.py — SQLite connection layer and query executor.

Wraps Python's built-in sqlite3 module to provide:
  - Schema introspection (get_schema)   — used by the LLM to understand table structure
  - Row sampling (get_sample_rows)      — used by the LLM to learn value formats
  - Query execution (execute)           — used to run the final SELECT queries
"""

import sqlite3                        # Python's built-in SQLite driver (no install needed)
import os                             # read DB_PATH env override if provided
from dataclasses import dataclass, field   # typed return value — avoids passing raw tuples
from pathlib import Path              # cross-platform file path handling
from typing import Any                # for type hints on row data

# Default location: db/ecommerce.db — relative to the project root, not this file
# Using __file__ makes this work regardless of the current working directory
DEFAULT_DB_PATH = Path(__file__).parent.parent / "db" / "ecommerce.db"


@dataclass
class QueryResult:
    """
    Structured result from any database operation.
    Avoids returning raw tuples — callers pattern-match on success/error.
    """
    success: bool                              # True if the query ran without error
    data: list[dict] = field(default_factory=list)     # rows as list of {column: value} dicts
    columns: list[str] = field(default_factory=list)   # column names in order
    row_count: int = 0                         # total rows returned
    error: str | None = None                   # error message if success=False


class Database:
    """
    Thin wrapper around sqlite3 that handles connection lifecycle and result formatting.
    Each query opens and closes its own connection (safe for multi-threaded Django).
    """

    def __init__(self, db_path: str | None = None):
        # Allow overriding the DB path via env var (useful for testing or Docker volumes)
        self.db_path = db_path or os.getenv("DB_PATH", str(DEFAULT_DB_PATH))

    def _connect(self) -> sqlite3.Connection:
        """Open a new SQLite connection with row_factory so rows behave like dicts."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row   # makes row["column_name"] work instead of row[0]
        conn.execute("PRAGMA foreign_keys = ON")  # enforce FK constraints on every connection
        return conn

    def get_schema(self) -> str:
        """
        Return the full database schema as a formatted string for the LLM.

        Includes: table names, columns with types, PK/nullable flags,
        foreign key relationships, and distinct enum-like values for key columns.
        """
        conn = self._connect()
        lines: list[str] = ["DATABASE SCHEMA\n" + "=" * 50]

        # Query sqlite_master to get all user-created tables (skip sqlite internal tables)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()

        fk_map: dict[str, list[str]] = {}   # accumulate foreign key relationships across tables

        for (table_name,) in tables:
            # PRAGMA table_info returns one row per column with name, type, notnull, pk flags
            cols = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            # PRAGMA foreign_key_list returns FK relationships defined on this table
            fks = conn.execute(f"PRAGMA foreign_key_list({table_name})").fetchall()

            lines.append(f"\nTable: {table_name}")
            for col in cols:
                pk_flag   = " [PRIMARY KEY]" if col["pk"] else ""
                # INTEGER PRIMARY KEY is implicitly NOT NULL in SQLite — skip nullable tag
                null_flag = "" if col["notnull"] or col["pk"] else " [NULLABLE]"
                lines.append(f"  - {col['name']} ({col['type']}){pk_flag}{null_flag}")

            # Collect FK relationships to print in one block at the end
            for fk in fks:
                rel = f"  {table_name}.{fk['from']} -> {fk['table']}.{fk['to']}"
                fk_map.setdefault("relationships", []).append(rel)

        # Print all FK relationships together so the LLM can follow JOIN paths
        if fk_map.get("relationships"):
            lines.append("\nFOREIGN KEY RELATIONSHIPS")
            lines.extend(fk_map["relationships"])

        # Add distinct values for categorical columns — helps LLM use correct WHERE clauses
        lines.append("\nKEY COLUMN VALUES")
        for table, col in [("orders", "status"), ("customers", "segment"), ("products", "category")]:
            try:
                rows   = conn.execute(f"SELECT DISTINCT {col} FROM {table} ORDER BY {col}").fetchall()
                values = ", ".join(r[0] for r in rows)
                lines.append(f"  {table}.{col}: {values}")
            except Exception:
                pass   # silently skip if the column doesn't exist in a given DB variant

        conn.close()
        return "\n".join(lines)

    def get_sample_rows(self, table_name: str, n: int = 3) -> QueryResult:
        """
        Return n sample rows from a table so the LLM can learn the data format.
        The table name is sanitised to prevent SQL injection via the tool argument.
        """
        # Whitelist only alphanumeric and underscore characters — prevents SQL injection
        safe_name = "".join(c for c in table_name if c.isalnum() or c == "_")
        return self.execute(f"SELECT * FROM {safe_name} LIMIT {n}")

    def execute(self, query: str) -> QueryResult:
        """
        Execute a raw SQL query and return a structured QueryResult.

        Returns a QueryResult with success=False and an error message on any exception
        so the caller (agent loop) can return the error to the LLM for self-correction.
        """
        try:
            conn    = self._connect()
            cursor  = conn.execute(query)            # run the query
            rows    = cursor.fetchall()              # fetch all result rows
            # cursor.description is None for non-SELECT statements (INSERT etc.)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            # Convert sqlite3.Row objects to plain dicts for JSON serialisation
            data    = [dict(zip(columns, row)) for row in rows]
            conn.close()
            return QueryResult(
                success=True,
                data=data,
                columns=columns,
                row_count=len(data),
            )
        except sqlite3.Error as e:
            # SQLite-level errors (syntax, missing table, type mismatch)
            return QueryResult(success=False, error=str(e))
        except Exception as e:
            # Catch-all for unexpected errors (permissions, disk full, etc.)
            return QueryResult(success=False, error=f"Unexpected error: {e}")
