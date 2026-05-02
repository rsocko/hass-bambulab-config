"""Pytest configuration for E2E tests with Playwright"""

import pytest

# Configure pytest-asyncio for E2E tests to work with pytest-playwright
pytest_plugins = ("pytest_asyncio",)


def pytest_collection_modifyitems(items):
    """Automatically mark async test functions with pytest.mark.asyncio"""
    for item in items:
        if item.get_closest_marker("asyncio") is None:
            # Check if test is async by looking at the function
            if hasattr(item, "obj") and hasattr(item.obj, "__code__"):
                if item.obj.__code__.co_flags & 0x100:  # CO_COROUTINE flag
                    item.add_marker(pytest.mark.asyncio)
