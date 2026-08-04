"""Fail the build when the stylesheets drift from the design contract.

    python tools/lint_tokens.py

Why this exists
---------------
`.claude/skills/nebula-polish/SKILL.md` is a checklist, and a checklist is
guidance - something the model should consider. This is the same rules as
*enforcement*: something the system guarantees whether anyone remembered or not.

That distinction is the whole point. The first cut of the v4 chassis had every
motion value it needed sitting in `design_v3.py`, one function call away, and
used `.16s ease` anyway - because nothing failed when it didn't. A screenshot
cannot see an easing curve. A test of behaviour cannot see a focus ring. The
only thing that catches this class of defect is a rule that runs on every edit.

Four checks:

  1. tokens.css is in sync with design_v3.py (regenerate, compare)
  2. no hard-coded colours in the stylesheets - the token or nothing
  3. no hand-typed durations or easings - `var(--ease)`, `var(--hover-ms)`, ...
  4. nothing animated but transform and opacity (the cost budget the whole
     renderer choice rests on)

Deliberate deviations are allowed and must be *stated*:

    animation: rise var(--speed) linear infinite;   /* lint-allow: constant-speed drift */

which is the same discipline V3-PASS-2.md already applies to the spec.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "spike", "web")
TOKENS = os.path.join(WEB, "tokens.css")
GEN = os.path.join(ROOT, "spike", "gen_tokens.py")

# Deliberately does NOT require the closing `*/` on the same line - a reason
# worth writing is often two lines long, and a linter that silently ignores a
# multi-line justification teaches people to write one-line ones.
ALLOW = re.compile(r"/\*\s*lint-allow:\s*(.+)")

# A hex colour anywhere in a stylesheet that is not tokens.css.
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")

# rgb()/rgba() with literal channel numbers rather than a var().
LITERAL_RGB = re.compile(r"rgba?\(\s*\d")

# A duration in a transition/animation shorthand that is not a var().
DURATION = re.compile(r"(?:transition|animation)(?:-duration)?\s*:[^;]*?(?<![\w-])(\d*\.?\d+m?s)")

# A named or literal easing that is not var(--ease).
EASING = re.compile(
    r"(?:transition|animation)(?:-timing-function)?\s*:[^;]*?"
    r"(?<![\w-])(ease-in-out|ease-in|ease-out|ease|linear|cubic-bezier\([^)]*\))(?![\w-])")

# Only these may be animated. "Never animate width / height / top / left."
ANIMATABLE = {"transform", "opacity", "none"}
# Properties that are cheap enough to transition on a handful of nodes but are
# NOT compositor-only. Allowed on discrete UI controls, never on the backdrop.
PAINT_ONLY = {"background", "background-color", "color", "border-color",
              "box-shadow", "outline", "outline-color", "fill", "stroke"}
TRANSITION_PROP = re.compile(r"transition\s*:\s*([^;]+);")

problems = []


def report(path, lineno, rule, text, detail=""):
    problems.append((os.path.relpath(path, ROOT), lineno, rule, text.strip(), detail))


def check_tokens_in_sync():
    """tokens.css must be exactly what gen_tokens.py produces right now."""
    if not os.path.isfile(TOKENS):
        problems.append(("spike/web/tokens.css", 0, "missing",
                         "run python spike/gen_tokens.py", ""))
        return
    before = open(TOKENS, encoding="utf-8").read()
    subprocess.run([sys.executable, GEN], cwd=ROOT, capture_output=True)
    after = open(TOKENS, encoding="utf-8").read()
    if before != after:
        problems.append(("spike/web/tokens.css", 0, "stale",
                         "tokens.css was out of sync with design_v3.py",
                         "regenerated in place - review and commit"))


def check_stylesheet(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    in_comment = False

    for i, raw in enumerate(lines, 1):
        line = raw

        # Skip block comments - the file explains itself a lot, and the prose
        # mentions values it is telling you not to write.
        stripped = line.strip()
        if in_comment:
            if "*/" in line:
                in_comment = False
            continue
        if stripped.startswith("/*") and "*/" not in line:
            in_comment = True
            continue
        if stripped.startswith("/*") or stripped.startswith("*"):
            continue

        allowed = ALLOW.search(line)
        why = allowed.group(1) if allowed else None
        code = ALLOW.sub("", line)
        # Strip trailing single-line comments so prose never trips a rule.
        code = re.sub(r"/\*.*?\*/", "", code)

        if HEX.search(code) and not why:
            report(path, i, "hard-coded colour", raw,
                   "use a token from tokens.css")

        if LITERAL_RGB.search(code) and not why:
            report(path, i, "literal rgb()", raw,
                   "use rgb(var(--x-rgb) / a)")

        m = DURATION.search(code)
        if m and "var(" not in code and not why:
            report(path, i, "hand-typed duration", raw,
                   "%s - use var(--hover-ms) / var(--press-ms) / var(--pane-change-ms)"
                   % m.group(1))

        m = EASING.search(code)
        if m and not why:
            report(path, i, "hand-typed easing", raw,
                   "%s - use var(--ease)" % m.group(1))

        m = TRANSITION_PROP.search(code)
        if m and not why:
            body = m.group(1)
            # Split on commas outside parens: "a .2s var(--e), b .2s var(--e)".
            parts = re.split(r",(?![^(]*\))", body)
            for part in parts:
                tokens = part.strip().split()
                if not tokens:
                    continue
                prop = tokens[0]
                if prop in ANIMATABLE or prop in PAINT_ONLY or prop.startswith("var("):
                    continue
                if prop in ("width", "height", "top", "left", "right", "bottom",
                            "margin", "padding", "all"):
                    report(path, i, "layout property animated", raw,
                           "'%s' forces layout every frame - transform/opacity only" % prop)


def check_reduced_motion(path):
    """The spec: 'Nothing is removed, nothing goes flat.'

    `animation: none` inside a prefers-reduced-motion block does not pause the
    aurora, it resets every blob to its 0% keyframe - stopping the drift *and*
    rearranging the composition. Only animation-play-state is correct.
    """
    text = open(path, encoding="utf-8").read()
    for block in re.finditer(r"@media[^{]*prefers-reduced-motion[^{]*\{", text):
        start = block.end()
        depth, i = 1, start
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        body = text[start:i]
        base = text[:start].count("\n") + 1
        lines = body.splitlines()

        def allowed_at(idx, lines=lines):
            """lint-allow on the offending line or the three above it.

            A block comment explaining a deviation usually sits above the rule,
            not trailing it, so look back a little rather than demanding the
            marker share a line.
            """
            # `lines` is bound as a default rather than captured: the closure
            # outlives the loop iteration that made it, and a late-bound name
            # would read whatever the last iteration left behind. Same family as
            # the deferred-callback trap in CLAUDE.md.
            for j in range(max(0, idx - 3), idx + 1):
                if ALLOW.search(lines[j]):
                    return True
            return False

        for idx, line in enumerate(lines):
            if re.search(r"animation\s*:\s*none", line) and not allowed_at(idx):
                report(path, base + idx, "reduced-motion resets the layer", line,
                       "use animation-play-state: paused - the spec keeps the colour")
            if re.search(r"display\s*:\s*none", line) and not allowed_at(idx):
                report(path, base + idx, "reduced-motion removes a layer", line,
                       "'Nothing is removed, nothing goes flat'")


# `el.style.width = ...`, `.style.height =`, `.style.top =`, and the
# setProperty spelling of the same thing. Not `+=` or `==`.
JS_LAYOUT_WRITE = re.compile(
    r"\.style\.(width|height|top|left|right|bottom)\s*=(?!=)"
    r"|setProperty\(\s*[\"'](?:width|height|top|left|right|bottom)[\"']")

JS_ALLOW = re.compile(r"//\s*lint-allow:\s*(.+)|/\*\s*lint-allow:\s*(.+)")


def check_script(path):
    """Rule 2 applies to JavaScript too, and this is where it was breaking.

    The stylesheet check catches `transition: width`, but the drop marker never
    animated width - it *assigned* `style.width` and `style.height` on every
    index change, which is the same layout write wearing a costume and cost the
    same forced reflow. A rule that only reads CSS cannot see it.

    Sizing something once, at the start of a gesture, is fine; say so with a
    lint-allow and the reason.
    """
    lines = open(path, encoding="utf-8").read().splitlines()
    # One reason covers the whole run it introduces. Placing a popover or
    # building a node is several of these in a row and they share an argument;
    # demanding the marker per line would only teach people to write it four
    # times without reading it.
    run_allowed = False
    prev_was_write = False
    for idx, line in enumerate(lines):
        if not JS_LAYOUT_WRITE.search(line):
            prev_was_write = False
            continue
        if not prev_was_write:
            run_allowed = any(JS_ALLOW.search(lines[j])
                              for j in range(max(0, idx - 3), idx + 1))
        prev_was_write = True
        if run_allowed:
            continue
        report(path, idx + 1, "layout property written from JS", line.strip(),
               "transform and opacity only - or state why with lint-allow")


def check_hidden_attribute(sheets):
    """An author `display` silently defeats the `hidden` attribute.

    `[hidden] { display: none }` lives in the UA stylesheet, so any author rule
    that sets `display` on the same element outranks it and the element stays
    on screen with its attribute cheerfully set to true. This is not a subtle
    failure - it parks a panel-coloured rectangle over the hero - but it looks
    exactly like a layout mistake, so it costs a debugging session every time.

    Rule: if markup hides an element with `hidden`, and a stylesheet gives its
    class a `display`, that class needs its own `[hidden]` rule.
    """
    html_path = os.path.join(WEB, "index.html")
    if not os.path.exists(html_path):
        return
    html = open(html_path, encoding="utf-8").read()

    # A real `hidden` attribute: whitespace before, and space or `>` after -
    # which is what separates it from `aria-hidden="true"` (followed by `=`)
    # and from the class name `is-hidden` (preceded by a hyphen). Matching
    # \bhidden\b catches all three and the rule cries wolf on working markup.
    hidden_classes = set()
    for tag in re.finditer(r"<\w+\s[^>]*>", html):
        if not re.search(r"\shidden(?=[\s>])", tag.group(0)):
            continue
        found = re.search(r'class="([^"]+)"', tag.group(0))
        if not found:
            continue
        classes = found.group(1).split()
        # Anything already carrying .is-hidden is hidden by that class, so the
        # attribute is belt-and-braces rather than the mechanism.
        if "is-hidden" not in classes:
            hidden_classes.update(classes)

    for path in sheets:
        text = open(path, encoding="utf-8").read()
        for cls in sorted(hidden_classes):
            block = re.search(r"^\.%s\s*\{([^}]*)\}" % re.escape(cls),
                              text, re.M)
            if not block:
                continue
            declared = re.search(r"\bdisplay\s*:\s*([\w-]+)", block.group(1))
            # A base of `display: none` is the same answer the UA rule gives.
            if not declared or declared.group(1) == "none":
                continue
            if re.search(r"\.%s\[hidden\]" % re.escape(cls), text):
                continue
            line = text[:block.start()].count("\n") + 1
            report(path, line, "display defeats [hidden]", ".%s { display: ... }" % cls,
                   "add .%s[hidden] { display: none } - the UA rule loses to this" % cls)


def main():
    check_tokens_in_sync()

    scripts = [os.path.join(WEB, f) for f in sorted(os.listdir(WEB))
               if f.endswith(".js")]
    for path in scripts:
        check_script(path)

    sheets = [os.path.join(WEB, f) for f in sorted(os.listdir(WEB))
              if f.endswith(".css") and f != "tokens.css"]
    if not sheets:
        print("no stylesheets found in %s" % WEB)
        return 0

    for path in sheets:
        check_stylesheet(path)
        check_reduced_motion(path)
    check_hidden_attribute(sheets)

    if not problems:
        print("token lint: clean (%d stylesheet%s, %d script%s)"
              % (len(sheets), "" if len(sheets) == 1 else "s",
                 len(scripts), "" if len(scripts) == 1 else "s"))
        return 0

    print("token lint: %d problem%s\n" % (len(problems), "" if len(problems) == 1 else "s"))
    for rel, lineno, rule, text, detail in problems:
        print("  %s:%s" % (rel, lineno))
        print("    %-28s %s" % (rule, detail))
        if text:
            print("    %s" % text[:100])
    print("\nDeliberate deviations are fine - state them:")
    print("    /* lint-allow: why this one is different */")
    return 1


if __name__ == "__main__":
    sys.exit(main())
