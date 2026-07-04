"""
validator.py — SQL safety layer that blocks destructive operations before execution.

Why this matters: the LLM generates SQL autonomously. Without validation, a
hallucinated or injected query could DELETE rows, DROP tables, or exfiltrate data
via stacked statements. This validator enforces a strict SELECT-only policy.

Defence layers:
  1. Regex scan — catches stacked queries and suspicious comment patterns
  2. sqlparse token walk — confirms the statement type is SELECT and no blocked keywords appear
"""

import re                            # regex for pattern-based checks
import sqlparse                      # SQL parser — tokenises and classifies SQL statements
from sqlparse.sql import Statement   # type for a single parsed SQL statement
from sqlparse.tokens import Keyword, DDL, DML   # token type constants

# Any query containing these keywords is immediately rejected
BLOCKED_KEYWORDS = {
    "DROP", "DELETE", "UPDATE", "INSERT", "CREATE", "ALTER",
    "TRUNCATE", "REPLACE", "MERGE", "EXEC", "EXECUTE",
    "GRANT", "REVOKE", "ATTACH", "DETACH", "PRAGMA",
}

# Regex patterns that indicate injection attempts or abuse
SUSPICIOUS_PATTERNS = [
    r";\s*(drop|delete|update|insert|create|alter)",  # stacked queries after a semicolon
    r"--\s*$",                                          # trailing single-line comment (injection hint)
    r"/\*.*\*/",                                        # block comment (may hide blocked keywords)
    r"xp_\w+",                                          # SQL Server extended stored procedures
]


class SQLValidator:
    """Stateless validator — call validate() before executing any LLM-generated SQL."""

    def validate(self, query: str) -> tuple[bool, str]:
        """
        Check whether a SQL query is safe to execute.

        Args:
            query: raw SQL string from the LLM

        Returns:
            (True, "OK")            — safe to run
            (False, reason_string)  — blocked, reason explains why
        """
        # Reject empty or whitespace-only queries immediately
        if not query or not query.strip():
            return False, "Empty query."

        lowered = query.lower()   # lowercase once for case-insensitive checks

        # ── Layer 1: regex scan for suspicious patterns ────────────────────────
        for pattern in SUSPICIOUS_PATTERNS:
            if re.search(pattern, lowered, re.IGNORECASE | re.DOTALL):
                return False, f"Suspicious pattern detected: {pattern}"

        # ── Layer 2: sqlparse token-level inspection ───────────────────────────
        parsed = sqlparse.parse(query.strip())   # returns a tuple of Statement objects
        if not parsed:
            return False, "Could not parse SQL."

        for statement in parsed:
            stmt_type = statement.get_type()     # "SELECT", "INSERT", "UPDATE", etc.

            # Reject anything that isn't explicitly a SELECT
            if stmt_type != "SELECT":
                return False, f"Only SELECT queries are allowed. Got: {stmt_type or 'UNKNOWN'}"

            # Walk every token in the statement and block forbidden keywords
            for token in statement.flatten():    # flatten() yields leaf tokens (no nesting)
                token_val = token.value.upper()
                if token_val in BLOCKED_KEYWORDS:
                    return False, f"Forbidden keyword detected: {token_val}"

        return True, "OK"   # passed all checks — safe to execute
