# UI component contracts

NovelForge UI components communicate across composition boundaries through public
semantic methods, read-only properties, and Qt signals.

This document is introduced with the encapsulation migration. The final checkpoint
will document the completed Bible editor, outline, and writing-workspace contracts,
testing policy, and AST enforcement rule.

## Migration rule

- Parent to child: public methods and read-only properties.
- Child to parent: Qt signals connected once during UI construction.
- Siblings: coordinated by their parent.
- Event handlers and embedded widgets remain private.

The temporary baseline is recorded in
`docs/architecture/ui-encapsulation-progress.md`. No new baseline entries are
allowed, and all entries must be removed before completion.
