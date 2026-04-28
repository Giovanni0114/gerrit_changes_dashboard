# 020 — Clickable Links in Comments

## Problem

Users frequently paste URLs into change comments — links to Jira tickets,
related Gerrit changes, CI runs, internal docs. Today those URLs are
rendered as raw text in the `Comments` column (`display.py::enumerate_comments`
returns a plain `str` joined with newlines). Two issues:

1. **Long URLs eat horizontal space.** A 90-character Jira link squeezes the
   actual comment off-screen on common terminal widths.
2. **Not actionable.** Even though Rich supports OSC-8 hyperlinks via the
   `link <url>` style (already used for the change number column at
   `display.py:103`), comments don't use it. The user has to copy/paste the
   URL into a browser manually.

## Solution

Detect URLs in comment text. Render each detected URL as a Rich-styled link
displaying only the URL's hostname (or a short host+path fragment), backed
by a `link <full-url>` style so terminals that support OSC-8 hyperlinks
make it clickable. Non-URL text in the comment stays untouched.

This matches what FEATURES.md asks for:
> *"if comment contains a link, it should display just hostname and generates
> clickable link just like number is clickable."*

## Display behaviour

Before:

```
 Comments
 fix related to https://jira.example.com/browse/PROJ-12345 — see also
 https://gerrit.example.com/c/foo/+/9876 for the parent
```

After (rendered, with terminal hyperlink support — the angle-brackets are
visual cues only, not literal):

```
 Comments
 fix related to ⌜jira.example.com⌝ — see also ⌜gerrit.example.com⌝ for the parent
```

Each replaced span is one Rich `Text` segment with style
`"link https://jira.example.com/browse/PROJ-12345"` (full URL preserved
in the link target; only hostname shown).

In terminals without OSC-8 support the user sees plain `jira.example.com`.
That's a strict improvement over a 90-character raw URL even without the
clickable behaviour.

## Detection rules

A "URL" for this feature is restricted to `http://` and `https://` schemes
to avoid false positives (`file://`, `git://`, `ftp://` would all need
manual testing).

Match boundaries:
- Start: `\bhttps?://`
- End: first whitespace character or end-of-string. The trailing
  punctuation pruning rule below handles "https://x.com/path." correctly.

Trailing punctuation pruning:
- After matching the URL run, strip trailing characters from the set
  `.,;:!?)]}>` *one at a time* until none remain. This keeps URLs like
  `https://x.com/foo.html` intact but trims sentence-ending `.` or `,`.
- Mirror this for trailing closing brackets `)]}>` only when there is no
  matching opener inside the URL — a simple "trim if URL has no `(`,
  `[`, `{`, `<`" check is good enough for v1.

A small regex in `display.py` is sufficient:

```python
import re
_URL_RE = re.compile(r"https?://\S+")
```

Then trim trailing punctuation in Python (cleaner than a complex regex).

### Display text

For a matched URL, the visible text is its **hostname** (`urllib.parse.urlparse(url).hostname`).
- If `hostname` is `None` (malformed): fall back to the full matched URL
  string. Better to show ugly than to silently drop it.
- If `hostname` starts with `www.`: strip the `www.` prefix.

No path/query/fragment is shown. The full URL is what the link target
points to, so clicking still navigates to the right place.

### Style

Reuse the existing pattern from `display.py:103`:

```python
link_style = f"link {url}"
```

No additional colour or underline — Rich+terminals already render
hyperlinks with their own conventional styling (often underlined cyan).
Adding our own style would clash.

When the row is `disabled` / `deleted`, comments today get `dim` /
`dim strike` styles applied at the row level (`display.py:138-141`). The
link style composes with those — a struck-through dim hyperlink is fine
visually and matches the intent.

## Code changes

### `display.py`

Replace `enumerate_comments` (currently returns `str`) with a function that
returns a `rich.text.Text`:

```python
def enumerate_comments(comments: list[str]) -> Text:
    if not comments:
        return Text("")

    if len(comments) == 1:
        return _comment_to_text(comments[0])

    out = Text()
    for idx, comment in enumerate(comments, 1):
        out.append(f"{idx}. ")
        out.append_text(_comment_to_text(comment))
        out.append("\n")
    out = out[:-1]  # drop trailing newline (matches today's behaviour)
    return out


def _comment_to_text(comment: str) -> Text:
    out = Text()
    pos = 0
    for match in _URL_RE.finditer(comment):
        url = _trim_trailing_punct(match.group(0))
        if not url:
            continue
        if match.start() > pos:
            out.append(comment[pos:match.start()])
        out.append(_render_link(url))
        pos = match.start() + len(url)
    if pos < len(comment):
        out.append(comment[pos:])
    return out


def _render_link(url: str) -> Text:
    parsed = urlparse(url)
    host = parsed.hostname or url
    if host.startswith("www."):
        host = host[4:]
    return Text(host, style=f"link {url}")
```

`_trim_trailing_punct` is a small helper as described above.

### Caller in `build_table`

Today:

```python
comments_text = comments_text or enumerate_comments(ch.comments)
...
table.add_row(
    ...,
    Text(comments_text, style=styles["comments"]),
    ...,
)
```

Two adjustments:

- `enumerate_comments` now returns a `Text`, so wrap-with-`Text(..., style=...)`
  no longer works. Apply the style in-place via `Text.stylize` or by setting
  `comments_text.style` after construction:

```python
if not comments_text:  # error path leaves a string
    comments_text = enumerate_comments(ch.comments)
    if styles["comments"]:
        comments_text.stylize(styles["comments"])
```

- The error branch (`comments_text = f"ERROR: {ch.error}"`) still produces a
  plain string. Coerce to `Text` consistently:

```python
if ch.error:
    comments_text = Text(f"ERROR: {ch.error}", style="red")
elif ch.approvals:
    ...
...
if not comments_text:
    comments_text = enumerate_comments(ch.comments)
    if styles["comments"]:
        comments_text.stylize(styles["comments"])
table.add_row(..., comments_text, ...)
```

This is a small refactor of `build_table`'s comment cell construction
(`display.py:108-164`); functional behaviour for non-link comments is
identical.

### `models.py` / `app.py` / `changes.py`

No changes. Detection is purely a render-time concern; comments stay raw
strings on disk and in `TrackedChange.comments`.

## Edge cases

### Comment is just a URL

`https://example.com/foo` becomes a single hyperlink showing `example.com`.
The leading numbering ("`1. `") still applies when there are multiple
comments; the link sits to the right of the number.

### Multiple URLs in one comment

Each match is independently rendered as its own `Text` segment with its own
`link` style. Surrounding text is preserved.

### URL inside parentheses: `see (https://x.com/foo) for details`

`finditer` matches `https://x.com/foo)`. `_trim_trailing_punct` strips the
trailing `)` because the matched URL contains no `(`. Resulting visible
text: `see (x.com) for details`, with `x.com` linking to
`https://x.com/foo`. The user-typed `(` and `)` remain visible.

### URL ending in `.` at end of sentence

`see https://x.com/.` — match is `https://x.com/.`, trailing `.` is
stripped. Visible: `see x.com.`, link target `https://x.com/`. Sentence
punctuation preserved.

### URL with intentional trailing `)` as part of the path

`https://en.wikipedia.org/wiki/Foo_(bar)` — match contains `(`, so the
"only trim closing brackets when no opener inside" rule keeps the trailing
`)`. Link target preserved correctly.

### Malformed URL (`https://`)

`urlparse("https://").hostname` is `None`. Fallback path renders the raw
matched string — visually noisy but correct. We don't try to "fix up"
malformed URLs.

### Punycode / IDN hostnames

`urlparse(...).hostname` returns the ACE-encoded form
(`xn--bcher-kva.example`). Acceptable for v1 — real users virtually never
hit this, and decoding adds an `idna` dependency.

### Very long path with no hostname (`https:///path`)

`hostname` is `None` → fallback to full URL (which is also weird-looking
but at least informative). Same as malformed-URL path.

### URLs in error messages

The error branch (`f"ERROR: {ch.error}"`) is rendered with `style="red"`
and bypasses comment-link processing. SSH error strings rarely contain
URLs and we don't want a hyperlink hidden inside a red error line. Leave
unchanged.

## Files changed

| File         | Change                                                            |
|--------------|-------------------------------------------------------------------|
| `display.py` | Replace `enumerate_comments` to return `Text`; add `_comment_to_text`, `_render_link`, `_trim_trailing_punct`, `_URL_RE`. Adjust the comment cell in `build_table` to apply style on the returned `Text`. |

No new dependencies. `urllib.parse.urlparse` and `re` are stdlib.

## Acceptance Criteria

- A comment containing `https://jira.example.com/browse/PROJ-1` renders the
  visible text `jira.example.com`, styled as an OSC-8 hyperlink whose target
  is the full URL.
- The hostname-only display strips a leading `www.`.
- Trailing sentence punctuation (`.`, `,`, `;`, `:`, `!`, `?`) on a URL is
  preserved as text and not folded into the link target.
- A URL inside `(...)` does not include the closing `)` in the link target,
  unless the URL itself contains an opening bracket.
- Multiple URLs in one comment each become independent links with the
  correct target.
- Comment text without URLs renders identically to today (no regression in
  layout, wrapping, or row styles).
- Disabled / deleted row styling (`dim`, `dim strike`) still applies to
  the surrounding comment text, including link spans (style composes).
- Multi-comment numbering (`"1. ..."`, `"2. ..."`) still works.
- The error-message branch (`ERROR: ...`) is unaffected.

## Out of Scope

- Detecting bare hostnames without scheme (`example.com/foo`). Adds false
  positives (`v1.2.3`, `myfile.py`); revisit if users ask.
- Custom display text (`[label](url)` Markdown-style). Today's storage
  format is plain string; introducing markdown parsing is a bigger
  feature.
- Per-host display rules (e.g. *"Jira links should show the ticket key,
  not the hostname"*). That's reasonable but config-shaped — defer.
- Detecting Gerrit change references (e.g. `Iabcd1234...` change-ids,
  `crrev/...` shorthands). These are not URLs — separate feature if ever.
- Linkifying URLs inside the `Subject` column. Subject lines are short
  and rarely contain URLs; not worth the complexity for v1.

## Open Questions

1. **Length cap on the visible hostname.** A long subdomain chain
   (`a.b.c.d.e.example.com`) could still be wide. Truncate to e.g. 30 chars
   with `…`? Initial take: no, hostnames are bounded enough in practice.
2. **Show path for very short hostnames.** e.g. `j.mp/abc` is more
   informative than `j.mp`. Consider showing `host + first-path-segment`
   when the hostname alone is < 8 chars? Defer — heuristic territory.
3. **OSC-8 hyperlink terminal compatibility.** Same concern as the
   change-number column already in the codebase — assumed OK because that
   feature ships today. No new exposure.
