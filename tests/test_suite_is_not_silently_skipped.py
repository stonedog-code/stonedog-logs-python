"""Guard: the main test module must never skip itself wholesale (NEH-272).

``tests/test_stonedog_logs.py`` used to call ``pytest.importorskip`` at module
level to guard the two OTLP tests at the bottom of the file. A module-level
``importorskip`` raises ``Skipped`` *during import*, so pytest skipped the
entire file — all ~21 unrelated tests with it — whenever the optional ``otlp``
extra was missing. The run then reported "1 skipped" while asserting nothing.

This test collects that module in a subprocess and asserts a real suite comes
back. It fails (0 collected) against the pre-fix code and passes after, and it
does so identically whether or not the ``otlp`` extra is installed — which is
the whole point.
"""

import pathlib
import subprocess
import sys

MAIN_SUITE = pathlib.Path(__file__).with_name("test_stonedog_logs.py")
REPO_ROOT = MAIN_SUITE.parent.parent

# The module had 23 tests when this guard was written. Assert a floor rather
# than an exact count so adding tests does not fail the guard, but deleting the
# suite (or skipping it away again) does.
MIN_EXPECTED_TESTS = 20

# These two are the ones that legitimately need the extra. They must still be
# COLLECTED either way — conditionally skipped at run time, not made to vanish.
OTLP_TESTS = (
    "test_build_otlp_handler_returns_handler",
    "test_configure_installs_otlp_handler_when_extra_present",
)


def _collect_main_suite() -> list:
    """Return the node ids pytest collects from the main test module."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            # Drop the inherited addopts: this nested run must not start a
            # second coverage session or re-apply the --cov-fail-under gate.
            "-o",
            "addopts=",
            str(MAIN_SUITE),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    # 5 is pytest's "no tests collected" — exactly the regression this guards,
    # so let the count assertion below report it rather than failing here.
    assert proc.returncode in (0, 5), (
        "collecting the main suite failed:\n" + proc.stdout + proc.stderr
    )
    return [line.strip() for line in proc.stdout.splitlines() if "::" in line]


def test_main_suite_is_collected_whatever_extras_are_installed():
    collected = _collect_main_suite()
    assert len(collected) >= MIN_EXPECTED_TESTS, (
        "the main test module collected only "
        f"{len(collected)} tests (expected >= {MIN_EXPECTED_TESTS}); "
        "a module-level skip is swallowing the suite"
    )


def test_otlp_tests_are_collected_and_only_conditionally_skipped():
    collected = "\n".join(_collect_main_suite())
    for name in OTLP_TESTS:
        assert name in collected, f"{name} is no longer collected"
