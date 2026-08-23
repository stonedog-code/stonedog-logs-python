"""The version the package reports, and the choice not to override somebody else.

Both were found while adopting this package rather than by using it: nothing
compared `__version__` to the distribution, and consumers were writing their own
"configure only if nobody else has" because the library did not offer one.
"""

from __future__ import annotations

import logging
from importlib.metadata import version

import pytest

import stonedog_logs
from stonedog_logs import configure, logging_is_configured

# ── the version ──────────────────────────────────────────────────────────────


def test_the_reported_version_is_the_installed_one() -> None:
    """They drifted: the package said 0.1.0 while the distribution said 0.2.0.

    That is not cosmetic. A bug report quotes `__version__`, so it named a
    release that did not contain the code the reporter ran — and nobody could
    reproduce it. There is one number now, kept by the build; this is what makes
    a second copy impossible to reintroduce silently.
    """
    assert stonedog_logs.__version__ == version("stonedog-logs")


def test_the_version_is_a_real_version_rather_than_the_fallback() -> None:
    """The fallback exists for running from a source tree with nothing
    installed. Seeing it in a test run means the metadata lookup broke, which is
    exactly the failure the test above would otherwise pass straight over."""
    assert stonedog_logs.__version__ != "0.0.0+unknown"
    assert stonedog_logs.__version__[0].isdigit()


# ── not overriding somebody else's logging ───────────────────────────────────


@pytest.fixture
def isolated():
    """A logger built DIRECTLY, not fetched from the global manager.

    `logging.getLogger(name)` registers the logger, and pytest's logging plugin
    then attaches a capture handler to everything it is registered alongside —
    so a named logger is never "unconfigured" inside a test and every assertion
    below would be meaningless. Measured, not guessed: a freshly cleared named
    logger came back holding two `LogCaptureHandler`s.

    Constructing the object skips the manager entirely, which is also why
    `configure` and `logging_is_configured` accept a logger object as well as a
    name — a caller holding a logger should not need to know its name.
    """
    logger = logging.Logger("stonedog_logs.test.isolated")
    logger.propagate = False
    return logger


def test_it_configures_when_nothing_has(isolated) -> None:
    assert logging_is_configured(isolated) is False
    assert configure(base_logger=isolated, only_if_unconfigured=True) is True
    assert isolated.handlers


def test_it_does_NOTHING_when_something_else_already_did(isolated) -> None:
    """The behaviour consumers were hand-rolling.

    Without it, calling `configure` in a process whose logging is already set up
    installs a second handler and every line appears twice — which is how a
    diagnostic becomes noise people filter out.
    """
    theirs = logging.StreamHandler()
    isolated.addHandler(theirs)

    assert configure(base_logger=isolated, only_if_unconfigured=True) is False
    assert isolated.handlers == [theirs], "it replaced a handler it did not install"


def test_without_the_flag_it_still_configures_unconditionally(isolated) -> None:
    """The other direction. The flag must be opt-in — a library that silently
    stopped configuring would break every caller relying on it to configure."""
    theirs = logging.StreamHandler()
    isolated.addHandler(theirs)

    assert configure(base_logger=isolated) is True
    assert len(isolated.handlers) == 2


def test_configuring_twice_does_not_stack_this_librarys_handlers(isolated) -> None:
    """Idempotency and the flag answer DIFFERENT questions, and this pins the
    difference: idempotency stops this library stacking on itself, the flag
    stops it overriding somebody else."""
    configure(base_logger=isolated)
    configure(base_logger=isolated)

    assert len(isolated.handlers) == 1


def test_logging_is_configured_reports_both_answers(isolated) -> None:
    assert logging_is_configured(isolated) is False
    isolated.addHandler(logging.NullHandler())
    assert logging_is_configured(isolated) is True
