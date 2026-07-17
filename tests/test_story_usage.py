from app.domain.story_usage import StoryUsageKind, StoryUsageService
from app.storage.bible_models import FactionElement, LocationElement
from app.storage.bible_repository import WorldBibleService
from app.storage.models import (
    ChapterOutline,
    Project,
    SceneGenerationRecord,
    SceneOutline,
    VolumeOutline,
)
from app.storage.project_files import (
    create_project,
    save_scene_generation_record,
    set_active_scene_prose_version,
    save_volume_outline,
)


def _project_with_scene(tmp_path, scene: SceneOutline):
    project_dir = create_project(tmp_path, Project(title="Story", genre="Fantasy"))
    save_volume_outline(
        project_dir,
        VolumeOutline(
            id="volume-1",
            chapters=[ChapterOutline(id="chapter-1", scenes=[scene])],
        ),
    )
    return project_dir


def test_element_usage_reports_explicit_outline_reference(tmp_path):
    project_dir = _project_with_scene(
        tmp_path,
        SceneOutline(
            id="scene-1",
            chapter_id="chapter-1",
            title="At the gate",
            world_element_ids=["faction-1"],
        ),
    )
    WorldBibleService(project_dir).save_element(
        FactionElement(id="faction-1", name="Cloud Sect")
    )

    summary = StoryUsageService(project_dir).element_usage("faction-1")

    assert summary.element_id == "faction-1"
    assert len(summary.scenes) == 1
    usage = summary.scenes[0]
    assert (
        usage.scene_id,
        usage.chapter_id,
        usage.scene_order,
        usage.scene_title,
    ) == ("scene-1", "chapter-1", 1, "At the gate")
    assert usage.usage_kinds == frozenset({StoryUsageKind.EXPLICIT_OUTLINE})
    assert usage.generated_element_revision is None
    assert usage.current_element_revision == 1


def test_element_usage_merges_active_generation_context_and_revision_mismatch(tmp_path):
    project_dir = _project_with_scene(
        tmp_path,
        SceneOutline(id="scene-1", title="At the gate", world_element_ids=["faction-1"]),
    )
    bible = WorldBibleService(project_dir)
    element = bible.save_element(FactionElement(id="faction-1", name="Cloud Sect"))
    bible.save_element(element.model_copy(update={"summary": "Changed after generation"}))
    save_scene_generation_record(
        project_dir,
        SceneGenerationRecord(
            scene_id="scene-1",
            revision_id="revision-1",
            generated_with={
                "bible_elements": {
                    "faction-1": {
                        "revision": 1,
                        "selection_reasons": ["explicit_scene_reference", "name_match"],
                    }
                }
            },
        ),
    )

    usage = StoryUsageService(project_dir).element_usage("faction-1").scenes[0]

    assert usage.usage_kinds == frozenset({
        StoryUsageKind.EXPLICIT_OUTLINE,
        StoryUsageKind.GENERATION_CONTEXT,
    })
    assert usage.selection_reasons == ("explicit_scene_reference", "name_match")
    assert usage.generated_element_revision == 1
    assert usage.current_element_revision == 2


def test_element_usage_matches_alias_in_active_prose_only(tmp_path):
    project_dir = _project_with_scene(
        tmp_path, SceneOutline(id="scene-1", title="Arrival")
    )
    WorldBibleService(project_dir).save_element(
        FactionElement(
            id="faction-1",
            name="Cloud Sect",
            aliases=["Sky Order"],
        )
    )
    chapter_dir = project_dir / "scenes" / "chapter-1"
    chapter_dir.mkdir(parents=True)
    (chapter_dir / "scene-1.v1.md").write_text(
        "Cloud Sect appears only in the old prose.", encoding="utf-8"
    )
    (chapter_dir / "scene-1.v2.md").write_text(
        "The SKY ORDER arrives.", encoding="utf-8"
    )
    set_active_scene_prose_version(project_dir, "chapter-1", "scene-1", "v2")

    usage = StoryUsageService(project_dir).element_usage("faction-1").scenes[0]

    assert usage.usage_kinds == frozenset({StoryUsageKind.PROSE_MENTION})
    assert usage.matched_alias == "Sky Order"


def test_character_presence_is_derived_at_explicit_location(tmp_path):
    project_dir = _project_with_scene(
        tmp_path,
        SceneOutline(
            id="scene-1",
            title="Homecoming",
            pov_character_id="character-1",
            world_element_ids=["location-1"],
        ),
    )
    WorldBibleService(project_dir).save_element(
        LocationElement(id="location-1", name="Cloud Peak")
    )
    service = StoryUsageService(project_dir)

    character_usage = service.character_presence("character-1")
    location_usage = service.location_presence("location-1")
    element_usage = service.element_usage("location-1").scenes[0]

    assert [usage.scene_id for usage in character_usage] == ["scene-1"]
    assert [usage.scene_id for usage in location_usage] == ["scene-1"]
    assert character_usage[0].usage_kinds == frozenset({
        StoryUsageKind.CHARACTER_PRESENCE
    })
    assert character_usage[0].location_label == "Cloud Peak"
    assert character_usage[0].location_reason == "Explicit location element"
    assert element_usage.usage_kinds == frozenset({
        StoryUsageKind.EXPLICIT_OUTLINE,
        StoryUsageKind.CHARACTER_PRESENCE,
    })


def test_location_presence_uses_exact_normalized_scene_location_fallback(tmp_path):
    project_dir = _project_with_scene(
        tmp_path,
        SceneOutline(
            id="scene-1",
            title="Homecoming",
            location="ＳＫＹ ＨＯＭＥ",
            participating_character_ids=["character-1"],
        ),
    )
    WorldBibleService(project_dir).save_element(
        LocationElement(
            id="location-1",
            name="Cloud Peak",
            aliases=["Sky Home"],
        )
    )

    usages = StoryUsageService(project_dir).location_presence("location-1")

    assert [usage.scene_id for usage in usages] == ["scene-1"]


def test_character_presence_reports_scene_location_match_reason(tmp_path):
    project_dir = _project_with_scene(
        tmp_path,
        SceneOutline(
            id="scene-1",
            location="ＳＫＹ ＨＯＭＥ",
            participating_character_ids=["character-1"],
        ),
    )
    WorldBibleService(project_dir).save_element(
        LocationElement(id="location-1", name="Cloud Peak", aliases=["Sky Home"])
    )

    usage = StoryUsageService(project_dir).character_presence("character-1")[0]

    assert usage.location_label == "Cloud Peak"
    assert usage.location_reason == "Matched scene location text"


def test_element_usage_ignores_inactive_generation_records(tmp_path):
    project_dir = create_project(tmp_path, Project(title="Story", genre="Fantasy"))
    save_volume_outline(
        project_dir,
        VolumeOutline(
            id="volume-1",
            chapters=[ChapterOutline(
                id="chapter-1",
                scenes=[
                    SceneOutline(id="scene-1"),
                    SceneOutline(id="scene-2"),
                ],
            )],
        ),
    )
    WorldBibleService(project_dir).save_element(
        FactionElement(id="faction-1", name="Cloud Sect")
    )
    save_scene_generation_record(
        project_dir,
        SceneGenerationRecord(
            scene_id="scene-1",
            revision_id="active-revision",
            revision_number=1,
        ),
    )
    save_scene_generation_record(
        project_dir,
        SceneGenerationRecord(
            scene_id="scene-1",
            revision_id="draft-revision",
            revision_number=2,
            status="draft",
            generated_with={"bible_elements": {"faction-1": {"revision": 1}}},
        ),
    )
    set_active_scene_prose_version(
        project_dir,
        "chapter-1",
        "scene-1",
        "v1",
        revision_id="active-revision",
    )
    save_scene_generation_record(
        project_dir,
        SceneGenerationRecord(
            scene_id="scene-2",
            revision_id="old-revision",
            status="superseded",
            generated_with={"bible_elements": {"faction-1": {"revision": 1}}},
        ),
    )

    summary = StoryUsageService(project_dir).element_usage("faction-1")

    assert summary.scenes == ()


def test_all_element_counts_counts_scenes_not_usage_kinds(tmp_path):
    project_dir = _project_with_scene(
        tmp_path,
        SceneOutline(id="scene-1", world_element_ids=["used"]),
    )
    bible = WorldBibleService(project_dir)
    bible.save_element(FactionElement(id="used", name="Cloud Sect"))
    bible.save_element(FactionElement(id="unused", name="Moon Sect"))
    save_scene_generation_record(
        project_dir,
        SceneGenerationRecord(
            scene_id="scene-1",
            generated_with={"bible_elements": {"used": {"revision": 1}}},
        ),
    )

    counts = StoryUsageService(project_dir).all_element_counts()

    assert counts == {"used": 1, "unused": 0}


def test_all_element_counts_reads_each_scene_once(tmp_path, monkeypatch):
    project_dir = _project_with_scene(
        tmp_path,
        SceneOutline(id="scene-1", world_element_ids=["used"]),
    )
    bible = WorldBibleService(project_dir)
    bible.save_element(FactionElement(id="used", name="Cloud Sect"))
    bible.save_element(FactionElement(id="unused", name="Moon Sect"))
    from app.domain import story_usage

    calls = {name: 0 for name in (
        "load_all_volumes",
        "load_scene_generation_record",
        "load_scene_active_marker",
        "load_scene_prose",
    )}
    for name in calls:
        original = getattr(story_usage, name)

        def counted(*args, _name=name, _original=original, **kwargs):
            calls[_name] += 1
            return _original(*args, **kwargs)

        monkeypatch.setattr(story_usage, name, counted)

    assert StoryUsageService(project_dir).all_element_counts() == {
        "used": 1,
        "unused": 0,
    }
    assert calls == {
        "load_all_volumes": 1,
        "load_scene_generation_record": 1,
        "load_scene_active_marker": 1,
        "load_scene_prose": 1,
    }


def test_location_presence_uses_active_generation_context(tmp_path):
    project_dir = _project_with_scene(
        tmp_path,
        SceneOutline(id="scene-1", participating_character_ids=["character-1"]),
    )
    WorldBibleService(project_dir).save_element(
        LocationElement(id="location-1", name="Cloud Peak")
    )
    save_scene_generation_record(
        project_dir,
        SceneGenerationRecord(
            scene_id="scene-1",
            generated_with={
                "bible_elements": {
                    "location-1": {
                        "revision": 1,
                        "selection_reasons": ["location_match"],
                    }
                }
            },
        ),
    )

    usages = StoryUsageService(project_dir).location_presence("location-1")

    assert [usage.scene_id for usage in usages] == ["scene-1"]
    assert usages[0].generated_element_revision == 1


def test_character_presence_reports_generation_context_location(tmp_path):
    project_dir = _project_with_scene(
        tmp_path,
        SceneOutline(id="scene-1", participating_character_ids=["character-1"]),
    )
    WorldBibleService(project_dir).save_element(
        LocationElement(id="location-1", name="Cloud Peak")
    )
    save_scene_generation_record(
        project_dir,
        SceneGenerationRecord(
            scene_id="scene-1",
            generated_with={"bible_elements": {"location-1": {"revision": 1}}},
        ),
    )

    usage = StoryUsageService(project_dir).character_presence("character-1")[0]

    assert usage.location_label == "Cloud Peak"
    assert usage.location_reason == "Generation-context location"


def test_prose_matching_uses_safe_latin_boundaries_and_chinese_substrings(tmp_path):
    project_dir = _project_with_scene(tmp_path, SceneOutline(id="scene-1"))
    bible = WorldBibleService(project_dir)
    bible.save_element(FactionElement(id="latin", name="Lin", aliases=["X"]))
    bible.save_element(FactionElement(id="chinese", name="青云宗"))
    chapter_dir = project_dir / "scenes" / "chapter-1"
    chapter_dir.mkdir(parents=True)
    (chapter_dir / "scene-1.v1.md").write_text(
        "Berlin stood before 青云宗山门. X waited.", encoding="utf-8"
    )
    set_active_scene_prose_version(project_dir, "chapter-1", "scene-1", "v1")
    service = StoryUsageService(project_dir)

    latin = service.element_usage("latin")
    chinese = service.element_usage("chinese")

    assert latin.scenes == ()
    assert chinese.scenes[0].matched_alias == "青云宗"
