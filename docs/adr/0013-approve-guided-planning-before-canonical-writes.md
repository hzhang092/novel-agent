# Approve guided planning before canonical writes

Status: accepted

Story Brief, approved Story Proposal, revision metadata, and one resumable planning draft live in root `planning.yaml`; generated planning does not use parallel simplified story files. Proposal approval changes only the planning baseline and an accepted project title, while Story Bootstrap approval atomically writes the existing canonical Bible, character, style, and outline models.

This keeps guided ideation resumable without making unapproved AI output canonical. Existing non-empty projects use their canonical data directly in Quick; advanced canonical changes remain available in Deep Creation rather than through a bootstrap merge or targeted-patch system.
