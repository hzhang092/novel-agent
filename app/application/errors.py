"""Expected application-layer failures."""


class ApplicationError(Exception):
    pass


class ApplicationValidationError(ApplicationError):
    pass


class ApplicationNotFoundError(ApplicationError):
    pass


class OperationBlockedError(ApplicationError):
    pass


class ConcurrentModificationError(ApplicationError):
    pass


class StoryDesignerProviderError(RuntimeError):
    """The configured Story Designer provider could not produce a proposal."""

    pass
