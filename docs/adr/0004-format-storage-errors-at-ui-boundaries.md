# Format storage errors at UI boundaries

Status: accepted

Storage code should raise precise technical errors that include paths and identifiers; UI and API boundaries should turn those into user-facing repair messages. This keeps filesystem validation separate from presentation while still making corrupt project files visible to authors.
