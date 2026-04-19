"""Pytest configuration — configure Django settings for test session."""

import django
from django.conf import settings as django_settings


def pytest_configure(config):
    """Configure minimal Django settings before test collection."""
    if not django_settings.configured:
        django_settings.configure(
            INSTALLED_APPS=[],
            DATABASES={},
            GEMINI_API_KEY="test-key",
        )
        django.setup()
