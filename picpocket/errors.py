"""Custom errors"""


class PicPocketError(Exception):
    """Base Error class"""


class DataIntegrityError(PicPocketError):
    """Errors caused when an action would delete data"""


class InputValidationError(PicPocketError, ValueError):
    """Errors based on user input"""


class InvalidPathError(PicPocketError, IOError):
    """Errors based on invalid files"""


class UnknownItemError(PicPocketError, KeyError):
    """Items that don't exist within PicPocket"""
