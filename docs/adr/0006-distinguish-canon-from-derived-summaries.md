# Distinguish canon from derived summaries

Status: accepted

Canon facts are required project truth once present, so corrupt `canon/facts.yaml` must fail visibly. Scene summaries are derived aids; corruption should fail only when a summary is explicitly used for context or export, unless it can be regenerated from authoritative project files.
