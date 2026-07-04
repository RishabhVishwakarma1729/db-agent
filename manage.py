#!/usr/bin/env python
import os   # set the settings-module env var before Django loads
import sys  # forward CLI args (runserver, migrate, etc.) to Django's command dispatcher

if __name__ == "__main__":
    # Point Django at config/settings.py — must happen before importing anything from django.*
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line  # imported late so the env var above takes effect
    execute_from_command_line(sys.argv)   # dispatches e.g. `python manage.py runserver`
