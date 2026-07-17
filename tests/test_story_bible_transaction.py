import pytest

from app.storage.bible_models import FactionElement
from app.storage.bible_repository import WorldBibleService
from app.storage.character_definition_service import CharacterDefinitionService
from app.storage.models import CharacterCore, Project
from app.storage.project_files import create_project
from app.storage.story_bible_transaction import StoryBibleTransaction


def test_transaction_restores_bible_and_character_definition_on_failure(
    tmp_path, monkeypatch
):
    project_dir = create_project(tmp_path, Project(title="故事", genre="玄幻"))
    bible = WorldBibleService(project_dir)
    bible.load()
    characters = CharacterDefinitionService(project_dir)
    characters.save(CharacterCore(id="hero", name="林风"))
    before = {
        path: path.read_bytes()
        for path in (
            project_dir / "bible" / "manifest.yaml",
            project_dir / "project.yaml",
            project_dir / "world.md",
            characters.definition_path("hero"),
        )
    }

    def fail_save(_core):
        raise OSError("disk full")

    monkeypatch.setattr(characters, "save", fail_save)

    with pytest.raises(OSError, match="disk full"):
        StoryBibleTransaction(bible, characters).apply(
            bible.load().overview,
            [FactionElement(id="sect", name="赤云宗")],
            [CharacterCore(id="hero", name="林风")],
        )

    assert all(path.read_bytes() == content for path, content in before.items())
    assert not (project_dir / "bible" / "elements" / "sect.yaml").exists()
