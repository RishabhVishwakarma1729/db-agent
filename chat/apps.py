from django.apps import AppConfig   # base class every Django app's config inherits from


class ChatConfig(AppConfig):
    # Must match the app's package name — this is how INSTALLED_APPS in
    # config/settings.py resolves "chat" to this app.
    name = "chat"
