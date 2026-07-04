import os                                          # used to set the settings module env var
from django.core.wsgi import get_wsgi_application  # builds the WSGI callable servers invoke

# Tell Django which settings module to use before anything else imports it
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
# `application` is the standard WSGI entry point name — gunicorn/uwsgi/runserver all look for it
application = get_wsgi_application()
