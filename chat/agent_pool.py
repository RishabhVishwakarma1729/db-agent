"""
agent_pool.py — Lazy singleton for the Database and DatabaseAgent.

Why a singleton?
  Creating a Groq client and opening a DB connection on every HTTP request would
  be slow and wasteful. Instead, we initialise once on the first request and reuse
  the same objects for the lifetime of the Django process.

Thread safety note:
  Two concurrent first-requests could both enter the if-None block and create two
  agents. For a single-worker dev/portfolio server this is harmless — the second
  assignment just overwrites the first with an identical object. For multi-worker
  production, a threading.Lock() would be needed.
"""

from src.database import Database        # our SQLite connection wrapper
from src.agent import DatabaseAgent      # the ReAct agent loop


class _Pool:
    """
    Internal pool class — only one instance (pool) is exported from this module.
    Holds references to the shared Database and DatabaseAgent objects.
    """

    def __init__(self):
        self.db: Database | None = None          # SQLite wrapper (initialised on first use)
        self.agent: DatabaseAgent | None = None  # ReAct agent (initialised on first use)

    def get(self) -> "_Pool":
        """
        Return self after ensuring both db and agent are initialised.
        Calling get() multiple times is safe — subsequent calls are a cheap None check.
        """
        if self.agent is None:
            self.db    = Database()              # open the SQLite file
            self.agent = DatabaseAgent(db=self.db)  # create the Groq client + validator
        return self


# Module-level singleton — imported directly by views.py
pool = _Pool()
