"""Errors Kneady catches so the work goes on (errors.py). Each is printed on
the console once, with its traceback, so it can be reported. Otherwise
drawing code would print it every frame, or not at all."""

import contextlib
import io

import bpy  # type: ignore

import rigs


def _printed(fn, times=3):
    """What `fn` prints to the console, run `times` times."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        for _k in range(times):
            fn()
    return out.getvalue()


def test_an_error_is_told_once_with_its_traceback():
    errors = rigs.module("errors")
    errors.forget()

    def fails():
        try:
            {}["missing"]
        except Exception:
            errors.caught("a test")

    text = _printed(fails)
    assert text.count("Kneady: a test failed - KeyError") == 1, text
    assert "Traceback (most recent call last)" in text, "no traceback: %r" % text
    assert errors.times("a test") == 3, "counted %d of 3" % errors.times("a test")

    def other():
        try:
            1 / 0
        except Exception:
            errors.caught("a test")

    text = _printed(other, 2)
    assert text.count("a test failed - ZeroDivisionError") == 1, "a different error at the same place: %r" % text


def test_a_hook_that_fails_is_told_once_and_drawing_goes_on():
    """A hook from another add-on raises inside Kneady's drawing. Kneady
    carries on as if the hook said no, and the error is printed once."""
    core, errors = rigs.kneady(), rigs.module("errors")
    errors.forget()

    def broken(_context):
        raise RuntimeError("a hook's own bug")

    core.add_busy_hook(broken)
    try:
        answers = []
        text = _printed(lambda: answers.append(core.busy()), 5)
    finally:
        core.remove_busy_hook(broken)
    assert answers == [False] * 5, answers
    assert text.count("a busy hook failed") == 1 and "a hook's own bug" in text, text
    assert "Traceback" in text and "broken" in text, "the traceback does not reach the hook: %r" % text


def test_a_broken_path_is_told_once_without_a_traceback():
    """Show When reading a property that is not there (renamed, say). The
    button has no state, and the console names the path once, without a
    traceback, since the cause is the file's data and not Kneady's code."""
    core, errors, menus = rigs.kneady(), rigs.module("errors"), rigs.module("menus")
    errors.forget()
    mesh = bpy.data.objects.new("M", bpy.data.meshes.new("M"))
    bpy.context.scene.collection.objects.link(mesh)
    region = core.new_region(mesh, "R", whole=True)
    button = region.buttons[0]
    button.when_path = '["no_such_property"]'
    states = []
    text = _printed(lambda: states.append(menus.switch_on(region, button, mesh)), 4)
    assert states == [None] * 4, states
    assert text.count('reading Show When\'s property ["no_such_property"] failed') == 1, text
    assert "Traceback" not in text, "a traceback for a data problem: %r" % text
