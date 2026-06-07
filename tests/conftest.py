"""Shared test fixtures."""

import pytest

from app.storage.models import Project


@pytest.fixture
def sample_project() -> Project:
    return Project(title="测试小说", genre="玄幻", llm_provider="ollama")
