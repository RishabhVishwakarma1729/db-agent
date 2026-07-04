import os                          # read env vars for every setting below
from pathlib import Path           # cross-platform path handling
from dotenv import load_dotenv     # loads the .env file into os.environ

# Explicit path — works regardless of working directory
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_DIR = Path(__file__).resolve().parent.parent   # project root, one level up from config/

# Falls back to an obviously-fake key so local dev works without a .env file;
# always set DJANGO_SECRET_KEY explicitly in any real deployment.
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-secret-change-in-production")
DEBUG = os.getenv("DEBUG", "true").lower() == "true"                        # "true"/"false" string from the env, coerced to bool
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost 127.0.0.1 0.0.0.0").split()   # space-separated hostnames

# Railway injects this for services with a generated public domain — add it
# automatically so ALLOWED_HOSTS doesn't need manual upkeep after each deploy.
_railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
if _railway_domain:
    ALLOWED_HOSTS.append(_railway_domain)

# Render sets this to the service's *.onrender.com hostname — same idea as
# RAILWAY_PUBLIC_DOMAIN above, so Django doesn't 400 with DisallowedHost.
_render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME")
if _render_hostname:
    ALLOWED_HOSTS.append(_render_hostname)

INSTALLED_APPS = [
    "django.contrib.staticfiles",   # required for STATIC_URL below, even though we serve no local static assets
    "chat",                          # our one app: views, urls, templates for the whole product
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",     # sets a few security-related response headers
    "django.middleware.common.CommonMiddleware",         # basic request/response housekeeping (e.g. URL normalisation)
    "django.middleware.clickjacking.XFrameOptionsMiddleware",  # blocks the site from being framed by other origins
]

ROOT_URLCONF = "config.urls"   # points to config/urls.py, which delegates to chat/urls.py

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],                # no project-level template dir — each app supplies its own
        "APP_DIRS": True,          # look for templates inside chat/templates/
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",     # exposes {{ debug }} in templates
                "django.template.context_processors.request",   # exposes {{ request }} in templates
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"   # entry point used by runserver/gunicorn/etc.

# No Django ORM — we manage our own SQLite connection in src/database.py
DATABASES = {}

STATIC_URL = "/static/"                                   # required by staticfiles app even though nothing is served from it
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"      # default PK type for any future models (none currently defined)
