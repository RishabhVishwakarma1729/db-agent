from django.urls import path   # registers a single URL pattern to a view function
from . import views            # the view functions defined in chat/views.py

urlpatterns = [
    path("",              views.index,      name="index"),       # GET  /             — the Bootstrap chat page
    path("api/health/",   views.api_health, name="api_health"),  # GET  /api/health/  — liveness check for the status dot
    path("api/schema/",   views.api_schema, name="api_schema"),  # GET  /api/schema/  — DB schema shown in the sidebar
    path("api/query/",    views.api_query,  name="api_query"),   # POST /api/query/   — run a question through the agent
    path("api/reset/",    views.api_reset,  name="api_reset"),   # POST /api/reset/   — drop a session's conversation history
]
