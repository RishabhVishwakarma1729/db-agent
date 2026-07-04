from django.urls import path, include   # path() registers a route; include() delegates a prefix to another urls.py

urlpatterns = [
    # Delegate every URL under the site root to chat/urls.py, which defines
    # the actual page and API routes (/, /api/health/, /api/query/, etc.).
    path("", include("chat.urls")),
]
