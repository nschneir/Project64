"""What `pytest_collection_modifyitems` in tests/conftest.py skips, and when.

Same shape as the other `test_conftest_*` files: the hook is called directly
with fake items, so no collection run — and no emulator — is involved. The
display half matters because the live tests are validated on hosts this suite
never sees: on a display-less Linux box `Session.launch` refuses, and a `vice`
test that launches its own machine would error where a skip is honest.
"""

import pytest

from tests import conftest as ct


class _FakeItem:
    """The two attributes the hook touches, plus a record of what it added."""

    def __init__(self, *keywords):
        self.keywords = set(keywords)
        self.marks = []

    def add_marker(self, mark):
        self.marks.append(mark)

    @property
    def reasons(self):
        return [m.kwargs["reason"] for m in self.marks]


@pytest.fixture
def usable_host(monkeypatch):
    """The green-path host: both binaries present, a display available."""
    monkeypatch.setattr(ct, "HAVE_C1541", True)
    monkeypatch.setattr(ct, "HAVE_X64SC", True)
    monkeypatch.setattr(ct, "_display_available", lambda: True)


def test_no_skips_on_a_usable_host(usable_host):
    """The macOS no-op: nothing is marked when everything is available."""
    items = [_FakeItem("vice"), _FakeItem("needs_c1541")]
    ct.pytest_collection_modifyitems(None, items)
    assert [i.marks for i in items] == [[], []]


def test_vice_tests_skip_when_x64sc_has_no_display(usable_host, monkeypatch):
    monkeypatch.setattr(ct, "_display_available", lambda: False)
    vice, plain = _FakeItem("vice"), _FakeItem("needs_cc65")
    ct.pytest_collection_modifyitems(None, [vice, plain])
    assert vice.reasons == [
        "x64sc needs a display (set DISPLAY or run under xvfb-run)"]
    assert plain.marks == []                # not a live test; nothing to skip


def test_no_display_skip_when_x64sc_is_not_installed(usable_host, monkeypatch):
    """The per-file skipif that names the missing binary is the better reason
    there; two skips for one absent tool would just bury it."""
    monkeypatch.setattr(ct, "HAVE_X64SC", False)
    monkeypatch.setattr(ct, "_display_available", lambda: False)
    vice = _FakeItem("vice")
    ct.pytest_collection_modifyitems(None, [vice])
    assert vice.marks == []


def test_c1541_skip_still_applies_alongside_the_display_skip(usable_host,
                                                             monkeypatch):
    """The two gates are independent: adding the display one must not have
    swallowed the c1541 one, and a test carrying both markers gets both."""
    monkeypatch.setattr(ct, "HAVE_C1541", False)
    monkeypatch.setattr(ct, "_display_available", lambda: False)
    both = _FakeItem("needs_c1541", "vice")
    ct.pytest_collection_modifyitems(None, [both])
    assert both.reasons == [
        "c1541 (VICE) not installed",
        "x64sc needs a display (set DISPLAY or run under xvfb-run)",
    ]
