"""Pure mutations and lookups for the outline aggregate."""

from __future__ import annotations

from collections.abc import Sequence

from app.storage.models import ChapterOutline, SceneOutline, VolumeOutline


def add_volume(
    volumes: Sequence[VolumeOutline], volume: VolumeOutline
) -> tuple[VolumeOutline, ...]:
    return (*_copy(volumes), volume.model_copy(deep=True))


def add_chapter(
    volumes: Sequence[VolumeOutline], target_id: str, chapter: ChapterOutline
) -> tuple[VolumeOutline, ...]:
    updated = _copy(volumes)
    for volume in updated:
        if volume.id == target_id:
            volume.chapters.append(chapter.model_copy(deep=True))
            return updated
        for index, existing in enumerate(volume.chapters):
            if existing.id == target_id:
                volume.chapters.insert(index + 1, chapter.model_copy(deep=True))
                return updated
    raise ValueError(f"Chapter insertion target not found: {target_id}")


def add_scene(
    volumes: Sequence[VolumeOutline], target_id: str, scene: SceneOutline
) -> tuple[VolumeOutline, ...]:
    updated = _copy(volumes)
    for volume in updated:
        for chapter in volume.chapters:
            if chapter.id == target_id:
                chapter.scenes.append(scene.model_copy(deep=True))
                return updated
            for index, existing in enumerate(chapter.scenes):
                if existing.id == target_id:
                    chapter.scenes.insert(index + 1, scene.model_copy(deep=True))
                    return updated
    raise ValueError(f"Scene insertion target not found: {target_id}")


def delete_node(
    volumes: Sequence[VolumeOutline], node_id: str
) -> tuple[VolumeOutline, ...]:
    updated = _copy(volumes)
    if any(volume.id == node_id for volume in updated):
        return tuple(volume for volume in updated if volume.id != node_id)
    for volume in updated:
        if any(chapter.id == node_id for chapter in volume.chapters):
            volume.chapters = [
                chapter for chapter in volume.chapters if chapter.id != node_id
            ]
            return updated
        for chapter in volume.chapters:
            if any(scene.id == node_id for scene in chapter.scenes):
                chapter.scenes = [
                    scene for scene in chapter.scenes if scene.id != node_id
                ]
                return updated
    return updated


def move_node(
    volumes: Sequence[VolumeOutline], node_id: str, offset: int
) -> tuple[VolumeOutline, ...]:
    updated = list(_copy(volumes))
    if _move(updated, node_id, offset):
        return tuple(updated)
    for volume in updated:
        if _move(volume.chapters, node_id, offset):
            return tuple(updated)
        for chapter in volume.chapters:
            if _move(chapter.scenes, node_id, offset):
                return tuple(updated)
    return tuple(updated)


def find_next_scene(
    volumes: Sequence[VolumeOutline], scene_id: str
) -> SceneOutline | None:
    scenes = [
        scene
        for volume in volumes
        for chapter in volume.chapters
        for scene in chapter.scenes
    ]
    for index, scene in enumerate(scenes):
        if scene.id == scene_id:
            return scenes[index + 1] if index + 1 < len(scenes) else None
    return None


def find_volume(
    volumes: Sequence[VolumeOutline], volume_id: str
) -> VolumeOutline | None:
    return next((volume for volume in volumes if volume.id == volume_id), None)


def find_chapter(
    volumes: Sequence[VolumeOutline], chapter_id: str
) -> ChapterOutline | None:
    return next(
        (
            chapter
            for volume in volumes
            for chapter in volume.chapters
            if chapter.id == chapter_id
        ),
        None,
    )


def find_scene(
    volumes: Sequence[VolumeOutline], scene_id: str
) -> SceneOutline | None:
    return next(
        (
            scene
            for volume in volumes
            for chapter in volume.chapters
            for scene in chapter.scenes
            if scene.id == scene_id
        ),
        None,
    )


def _copy(volumes: Sequence[VolumeOutline]) -> tuple[VolumeOutline, ...]:
    return tuple(volume.model_copy(deep=True) for volume in volumes)


def _move(items: list, node_id: str, offset: int) -> bool:
    for index, item in enumerate(items):
        if item.id != node_id:
            continue
        target = index + offset
        if 0 <= target < len(items):
            items.insert(target, items.pop(index))
        return True
    return False
