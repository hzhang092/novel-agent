# Approve guided planning before canonical writes

Status: accepted

Story Brief, approved Story Proposal, revision metadata, and one resumable planning draft live in root `planning.yaml`; generated planning does not use parallel simplified story files. Proposal approval changes only the planning baseline and an accepted project title, while Story Bootstrap approval atomically writes the existing canonical Bible, character, style, and outline models. Later Story Designer changes are revision-checked structured patches, so regeneration cannot silently overwrite author edits or published work.

This keeps guided ideation resumable without making unapproved AI output canonical. Existing non-empty projects receive targeted patches rather than a bootstrap merge system.
