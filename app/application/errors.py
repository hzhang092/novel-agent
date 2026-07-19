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
