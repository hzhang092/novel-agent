# Share one engine across creation experiences

Status: accepted

Quick Creation and Deep Creation are separate top-level presentations over the same canonical project data, `ProjectApplicationContext`, Scene Workflow, generation pipeline, and publication seam. Experience is project-local Editor Layout state: switching preserves the nearest equivalent context and never converts, duplicates, or hides data from generation. This avoids a second simplified model drifting from the continuity-aware engine while allowing each presentation to optimize its own workflow.

The first release keeps exactly one scene per chapter in both experiences. Multi-scene compatibility and migration are deliberately excluded because supporting chapter-level generation and publication would introduce a second transaction boundary without a current user need.
