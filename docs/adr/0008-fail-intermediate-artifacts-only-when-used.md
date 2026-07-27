# Fail intermediate artifacts only when used

Status: accepted

Generated intermediate files such as scene plans, intents, reviews, and generation records are not project truth. Corruption in these files should not fail project load, but must surface when a pipeline resume, debug view, or explicit load depends on the corrupt artifact.
