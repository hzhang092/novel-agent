from app.application.project_context import build_project_application
from app.events.bus import EventBus
from app.storage.models import Project
from app.storage.project_files import create_project


def test_project_context_shares_services_and_event_bus(tmp_path):
    project_dir = create_project(tmp_path, Project(title="Story", genre="Fantasy"))
    event_bus = EventBus()

    context = build_project_application(project_dir, event_bus=event_bus)

    assert context.project_dir == project_dir
    assert context.characters._event_bus is event_bus
    assert context.outlines._characters is context.characters
    assert context.outlines._story_bible is context.story_bible
