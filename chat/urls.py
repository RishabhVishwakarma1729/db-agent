from django.urls import path
from . import views

urlpatterns = [
    path("",              views.index,      name="index"),
    path("api/health/",   views.api_health, name="api_health"),
    path("api/schema/",   views.api_schema, name="api_schema"),
    path("api/query/",    views.api_query,  name="api_query"),
    path("api/reset/",    views.api_reset,  name="api_reset"),
]
