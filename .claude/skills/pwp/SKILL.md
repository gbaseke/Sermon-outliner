---
name: pwp
description: Create a PowerPoint (.pptx) presentation from a generated sermon outline for live projection during preaching. Use when given a path to a sermon outline.md (the rich outline produced by the sermon-outliner agent, e.g. sermons/<date-title>/output/<slug>.md) and asked to make a slide deck, PowerPoint, or presentation. Produces a congregation/projection-view deck (title, scriptures verse-by-verse, point titles, sub-points, Branham quotes, closing) using a bundled sermon template.
---

# PWP — Sermon PowerPoint Creator

Turn a generated sermon **outline** into a projection-ready PowerPoint, styled with
the bundled sermon template (`scripts/template.pptx`, 16:9, layouts:
Title Slide / Quote / Scripture / Notes / Title and Content / Blank).

## Input

A path to a generated sermon outline — the rich outline written by the
sermon-outliner agent, e.g. `sermons/2026-06-16-serpent-seed/output/one-word-off-the-lie-that-beguiles-v1.md`.
**This is the outline, not the raw `notes.md`.** If the user hands you raw notes,
say so and point them to run the sermon-outliner agent first.

## Output

A `.pptx` written to the **same `output/` folder** as the outline, named from the
outline title (kebab-case), e.g. `output/one-word-off-the-lie-that-beguiles.pptx`.
If a file of that name exists, add `-v2`, `-v3`, … (don't overwrite).

## How it works

You read the outline, decide what belongs on the screen, and build a JSON **spec**.
A bundled Python script (`scripts/build_pptx.py`) turns that spec + the template
into the `.pptx`. The script auto-splits any over-long scripture, quote, or bullet
slide across multiple slides, so you never have to hand-paginate.

## Steps

1. **Read the outline file** in full.
2. **Build the slide spec** (a JSON object — schema below) following the
   *Content mapping* rules. Write it to the sermon's `output/` folder as
   `_pwp_spec.json`.
3. **Run the builder** from the project root:
   ```
   cd C:\Dev\code\message-search
   uv run python .claude/skills/pwp/scripts/build_pptx.py "sermons/<folder>/output/_pwp_spec.json"
   ```
4. **Report** the output path and slide count. You may delete `_pwp_spec.json`
   afterward, or leave it so the user can tweak and rebuild.

## Content mapping (congregation / projection view)

This deck is what the **congregation sees on the screen** — not the preacher's
manuscript. Keep text short and readable from the back of the room. **Put on slides:**

- **Title slide** (`type: title`)
  - `title` = the outline's main title (H1).
  - `subtitle` = the theme (one line) or the alternate title.
  - `footer` = `Guy Baseke / Grace Message Tabernacle, Mississauga, Ontario`
    (unless the outline says otherwise).
  - `date` = the "Prepared" date if present.

- **Opening Question** — a `section` divider titled "The Opening Question",
  then a `quote` slide holding the question text (leave `citation` empty).

- **Scriptures** (`type: scripture`) — every scripture in *Foundation Scriptures*
  and each point's *Key Scripture*. One reference per slide; put the reference in
  `reference` and the verse text in `text`. For multi-verse passages, keep the
  verse numbers in the text and separate verses with a blank line (`\n\n`) — the
  builder paginates long passages automatically.
  Keep `reference` to the bare citation only (e.g. `Genesis 3:13`). The reference
  renders at 50pt — do **not** append role labels like `(Setup)` or `(Fortress)`,
  they wrap and overflow the header.

- **Each main Point** — in order:
  1. a `section` divider with the point's title (e.g. "POINT 1 — He Does Not Break In; He Beguiles"),
  2. a `scripture` slide for the point's *Key Scripture*,
  3. a `point` slide whose `title` is the point name (or "Key Points") and whose
     `bullets` are the **Sub-points**, rewritten to ~8-word bullets,
  4. a `quote` slide for **each** Branham / Message quote under *From the Message*
     (`text` = the quote, `citation` = the date · title · ¶N line). Quote the
     Branham text **verbatim** — do not paraphrase or trim it; the builder splits
     long quotes across slides.

- **Note-card / anchor sections** that are already bulleted (e.g. "This Hour —
  Prophetic Anchor") → a `notes` slide (`header` + `bullets`).

- **Conclusion** —
  - the *Summary* points → a `point` slide ("Summary", bullets),
  - the *heart of this message* line → a `section` divider (its own slide),
  - the closing hymn → a `notes` slide titled "Closing Hymn" with the hymn name
    and the one-line reason.

**Leave OFF the slides** (these are preacher-only manuscript prose): the
*Human Scene / Human Need* paragraphs, the *Divine Revelation / type unfolds*
prose, the *THUS SAITH THE LORD — The Vision* paragraphs, the *Person Profile*,
and the *Preacher's Reserve*. They are for the preacher, not the screen.

Keep bullets short (aim ~8 words, like the outline's existing bullet style).
Never put a long prose paragraph on a `point`/`notes` bullet.

## Fitting the slides (the body font is 40pt)

The template's body text is **40pt**, so a body box holds only about **7 lines
(~245 characters)**. The builder measures the real box geometry and font size and
splits long `scripture` / `quote` / `notes` / `point` content across as many
slides as needed — you never hand-paginate. But help it produce a clean deck:

- **Quotes:** paste the full verbatim quote in one `quote` slide; let the builder
  split it. A long Branham quote will become 2–3 slides — that is expected.
- **`section` / `point` titles** render on one line (44pt). Keep them **short,
  ≤ ~36 characters** (e.g. `POINT 2 - The Weapon Was Flattery`). A `section`
  whose title is a long sentence (the *heart of the message*) is fine — the
  builder automatically renders it big on the Quote layout instead of clipping.
- **Bullets** wrap if long; ~8-word bullets keep ~6 per slide.

## Spec schema

```json
{
  "output": "C:/Dev/code/message-search/sermons/<folder>/output/<slug>.pptx",
  "slides": [
    {"type": "title",     "title": "...", "subtitle": "...", "footer": "...", "date": "..."},
    {"type": "section",   "title": "..."},
    {"type": "scripture", "reference": "Genesis 3:13", "text": "verse text..."},
    {"type": "quote",     "text": "verbatim quote...", "citation": "1958-09-28 - The Serpent's Seed - P71"},
    {"type": "point",     "title": "POINT 1 - ...", "bullets": ["short bullet", "short bullet"]},
    {"type": "notes",     "header": "...", "bullets": ["short bullet", "short bullet"]},
    {"type": "blank"}
  ]
}
```

- `output` is required and absolute. `template` is optional (defaults to the
  bundled `scripts/template.pptx`).
- Slide order in the array = slide order in the deck.
- **Any slide may carry an optional `"notes"` string** — preacher prose for the
  PowerPoint speaker-notes pane (Presenter View), which never shows on the screen.
  This is how the "clean screen" view still carries the preacher-only material:
  attach a point's Human Need / Divine Revelation / Vision prose as `notes` on
  that point's `section` divider, and the Introduction / Preacher's Reserve as
  `notes` on the title / conclusion slides. The notes pane has no size limit.
  If an entry produces several slides, the notes attach to the first one.
- The script preserves the template's fonts/colors — set **text only**, never
  hand-format.

## Windows notes

- Run with `uv run python ...` from the project root.
- The console is cp1252 — in the spec, prefer ASCII punctuation (use `-` and
  `P71` rather than `—` and `¶71`) to avoid encoding errors, **except** inside
  verbatim Branham quote `text`, which should stay faithful to the source.
