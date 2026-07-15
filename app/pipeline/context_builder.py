"""RetrievalEngine — deterministic context assembly for scene generation.

Given a project directory and a scene ID, the RetrievalEngine reads all
relevant data from disk and assembles a context dict that feeds into the
LLM pipeline. No embedding-based RAG — all filtering is deterministic
via category tags, keyword matching, recency, and importance thresholds.
"""

from __future__ import annotations

from pathlib import Path


class RetrievalEngine:
    """Deterministic context assembler.

    Usage::

        engine = RetrievalEngine()
        context = engine.assemble(project_dir, scene_id="scene-uuid")
    """

    def __init__(self, importance_threshold: int = 3, max_facts: int = 20,
                 max_summaries: int = 5) -> None:
        self._importance_threshold = importance_threshold
        self._max_facts = max_facts
        self._max_summaries = max_summaries

    def assemble(self, project_dir: Path, scene_id: str) -> dict:
        """Assemble the full context dict for a given scene.

        Returns a dict with keys: scene_info, world_rules, characters,
        outline_context, recent_summaries, canon_facts, style_guide.
        """
        scene = self._find_scene(project_dir, scene_id)
        scene_info = self._build_scene_info(project_dir, scene)
        characters, read_points = self._collect_characters(project_dir, scene)
        from app.storage.timeline_repository import load_scene_positions

        scene_orders = {
            position.scene_id: position.scene_order
            for position in load_scene_positions(project_dir)
        }

        return {
            "scene_info": scene_info,
            "world_rules": self._collect_world_rules(project_dir, scene),
            "characters": characters,
            "read_points": read_points,
            "outline_context": self._build_outline_context(project_dir, scene),
            "recent_summaries": self._collect_recent_summaries(
                project_dir, scene_info, scene_orders
            ),
            "canon_facts": self._collect_canon_facts(
                project_dir, scene_info, scene_orders
            ),
            "style_guide": self._collect_style_guide(project_dir),
        }

    # ── Private helpers ───────────────────────────────────────────────────

    def _find_scene(self, project_dir: Path, scene_id: str) -> dict | None:
        """Find a scene by ID across all volumes/chapters, return a flat dict."""
        from app.storage.project_files import load_all_volumes

        volumes = load_all_volumes(project_dir)
        for vol in volumes:
            for ch in vol.chapters:
                for sc in ch.scenes:
                    if sc.id == scene_id:
                        return {
                            "id": sc.id,
                            "chapter_id": sc.chapter_id if sc.chapter_id else ch.id,
                            "volume_id": vol.id,
                            "volume_title": vol.title,
                            "chapter_title": ch.title,
                            "scene_title": sc.title,
                            "location": sc.location,
                            "time": sc.time,
                            "pov_character_id": sc.pov_character_id,
                            "participating_character_ids": sc.participating_character_ids,
                            "scene_goal": sc.scene_goal,
                            "conflict": sc.conflict,
                            "required_plot_beats": sc.required_plot_beats,
                            "emotional_turn": sc.emotional_turn,
                            "ending_hook": sc.ending_hook,
                            "constraints": sc.constraints,
                        }
        return {}

    def _build_scene_info(self, project_dir: Path, scene: dict | None) -> dict:
        if scene is None:
            return {}
        if not scene:
            return scene

        from app.storage.project_files import load_all_characters

        chars_by_id = {char.core.id: char for char in load_all_characters(project_dir)}
        pov_id = scene.get("pov_character_id", "")
        participant_ids = scene.get("participating_character_ids", [])
        referenced_ids = [cid for cid in [pov_id, *participant_ids] if cid]
        missing = sorted({cid for cid in referenced_ids if cid not in chars_by_id})
        if missing:
            raise ValueError("Scene references missing character IDs: " + ", ".join(missing))

        scene_info = dict(scene)
        scene_info["pov_character"] = chars_by_id[pov_id].core.name if pov_id else ""
        scene_info["participating_characters"] = [
            chars_by_id[cid].core.name for cid in participant_ids
        ]
        return scene_info

    def _collect_world_rules(self, project_dir: Path, scene: dict | None) -> dict:
        from app.storage.project_files import load_project

        project = load_project(project_dir)
        world = project.world_setting

        return {
            "geography": world.geography,
            "factions": world.factions,
            "history": world.history,
            "rules": world.rules,
            "taboos": world.taboos,
            "technology_level": world.technology_level,
            "social_structure": world.social_structure,
            "terminology": world.terminology,
            "power_system": world.power_system.model_dump(mode="json") if world.power_system else {},
        }

    def _collect_characters(self, project_dir: Path, scene: dict | None) -> tuple[dict, dict]:
        from app.storage.timeline_repository import load_character_context_for_scene

        scene = scene or {}
        character_ids = list(dict.fromkeys([
            scene.get("pov_character_id", ""),
            *scene.get("participating_character_ids", []),
        ]))
        character_ids = [character_id for character_id in character_ids if character_id]
        scene_id = scene.get("id", "")
        all_chars, read_points = load_character_context_for_scene(
            project_dir, scene_id, character_ids
        )

        major: list[dict] = []
        supporting: list[dict] = []
        background: list[dict] = []

        for char in all_chars:
            if char.core.id not in character_ids:
                continue

            if char.core.tier.value == "major":
                major.append({
                    "core": char.core.model_dump(mode="json"),
                    "state": char.state.model_dump(mode="json"),
                })
            elif char.core.tier.value == "supporting":
                relationships = char.state.current_relationships
                rel_line = ", ".join(f"{k}:{v}" for k, v in relationships.items()) if relationships else ""
                supporting.append({
                    "name": char.core.name,
                    "tier": "supporting",
                    "relationship": rel_line,
                    "personality": char.core.personality[:120] if char.core.personality else "",
                })
            else:
                background.append({"name": char.core.name, "tier": "background"})

        return {"major": major, "supporting": supporting, "background": background}, read_points

    def _build_outline_context(self, project_dir: Path, scene: dict | None) -> dict:
        if not scene or not scene.get("volume_id"):
            return {}

        from app.storage.project_files import load_volume_outline

        try:
            volume = load_volume_outline(project_dir, scene["volume_id"])
        except (FileNotFoundError, ValueError):
            return {}

        return {
            "volume_title": volume.title,
            "volume_summary": volume.summary,
            "chapter_title": scene.get("chapter_title", ""),
        }

    def _collect_recent_summaries(
        self,
        project_dir: Path,
        scene: dict | None,
        scene_orders: dict[str, int],
    ) -> list[dict]:
        from app.storage.project_files import load_scene_summaries

        summaries = load_scene_summaries(project_dir)
        current_order = scene_orders.get((scene or {}).get("id", ""))
        if current_order is not None:
            summaries = [
                summary for summary in summaries
                if scene_orders.get(summary.scene_id, current_order) < current_order
            ]
            summaries.sort(key=lambda summary: scene_orders[summary.scene_id])
        recent = summaries[-self._max_summaries:]
        return [s.model_dump(mode="json") for s in recent]

    def _collect_canon_facts(
        self,
        project_dir: Path,
        scene: dict | None,
        scene_orders: dict[str, int],
    ) -> list[dict]:
        from app.storage.project_files import load_canon_facts

        facts = load_canon_facts(project_dir)
        current_order = scene_orders.get((scene or {}).get("id", ""))
        if current_order is not None:
            facts = [
                fact for fact in facts
                if not fact.source_scene_id
                or scene_orders.get(fact.source_scene_id, current_order) < current_order
            ]

        # Build a keyword set from the scene outline
        scene_keywords = set()
        if scene:
            location_parts = scene.get("location", "").split()
            scene_keywords.update(location_parts)
            scene_keywords.update(scene.get("required_plot_beats", []))
            scene_keywords.update(scene.get("participating_characters", []))
            conflict_parts = scene.get("conflict", "").split()
            scene_keywords.update(conflict_parts)

        filtered: list = []
        for fact in facts:
            # Always include facts above the importance threshold
            if fact.importance >= self._importance_threshold:
                filtered.append(fact)
                continue

            # Include facts whose tags overlap with scene keywords
            if scene_keywords:
                fact_tags_lower = {t.lower() for t in fact.tags}
                scene_kw_lower = {k.lower() for k in scene_keywords}
                if fact_tags_lower & scene_kw_lower:
                    filtered.append(fact)
                    continue

                # Also match substrings: a tag "落云宗" should match a keyword "落云宗广场"
                matched = False
                for tag in fact_tags_lower:
                    for kw in scene_kw_lower:
                        if tag in kw or kw in tag:
                            filtered.append(fact)
                            matched = True
                            break
                    if matched:
                        break
                if matched:
                    continue

            # Include facts with keyword match against description
            fact_text = fact.description.lower()
            for kw in scene_keywords:
                if kw.lower() in fact_text:
                    filtered.append(fact)
                    break

        # Sort by created_at descending (newest first), then cap
        filtered.sort(key=lambda f: f.created_at, reverse=True)
        capped = filtered[:self._max_facts]

        return [f.model_dump(mode="json") for f in capped]

    def _collect_style_guide(self, project_dir: Path) -> dict:
        from app.storage.project_files import load_project

        project = load_project(project_dir)
        style = project.style_guide
        return style.model_dump(mode="json")
