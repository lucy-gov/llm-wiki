"""Shared exception type. Tools print its message and exit nonzero."""


class WikiError(Exception):
    """A failure with a message meant for a human reading the terminal."""
