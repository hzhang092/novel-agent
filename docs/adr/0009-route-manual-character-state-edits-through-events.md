# Route manual character state edits through events

Manual author edits to Character State must be persisted as State Events, not only as State Snapshots. The character editor keeps one save action, but saves Character Definition fields through definition storage and routes changed Character State fields through the event commit path so replay, invalidation, history, and snapshots stay consistent.
