# Studio terminal design

Studio is a built-in skin for the classic `freeide` CLI. Activate it with
`/skin studio`, or set `display.skin: studio` in the active profile's config.
The shared skin engine also supplies its palette to the Ink TUI and desktop;
the compact launch card and activity row described here belong to the classic CLI.

## UX findings and changes

| Gap | Studio behavior |
| --- | --- |
| Large wordmark and repeated borders push the composer down | One compact card, capped at 88 columns |
| Setup details compete with the next action | Model and workspace first; capabilities and commands below |
| Empty input offers no starting point | Task/question placeholder with slash-command discovery |
| Busy hint assumes interrupt mode | Enter guidance follows interrupt, queue, or steer configuration |
| Several competing decorative animations | A single 120 ms braille activity marker; plain thinking labels |
| Long tool paths wrap and move the input | Cell-aware ellipsis keeps activity in one row, preserving the timer when space permits |
| Dark and light themes look unrelated | Paired slate/blue palettes with semantic success, warning, and error colors |
| Interpolated markup can consume brackets in paths | Model, path, and session values render literally |

## Visual and motion rules

Blue marks actions and active work. Slate separates surfaces. Body text is bright
on dark backgrounds and dark on light backgrounds. Color is paired with text;
status must never rely on color alone. The theme needs no Nerd Font.

The launch card uses whitespace and a single rounded border. At narrow widths,
the CLI uses its compact startup path. The card renderer itself also handles
narrow previews, hiding secondary session details before sacrificing primary facts.

Only active work animates. The existing idle behavior remains still. Set
`display.reduce_motion: true` to freeze Studio's activity marker and the CLI's
command marker; elapsed time still refreshes. This setting does not control
animations in the separate Ink or desktop applications.

## Verification and preview

`python scripts/preview_studio.py --output studio.svg` renders the actual
components with clearly labeled example data and no API requests. Add `--light`
or `--width 40` to inspect the paired palette and narrow layout.

Regression coverage checks terminal cell widths (including CJK), literal markup,
the reduced-motion contract, busy-mode guidance, and loading Studio through a
real temporary profile. The existing palette audit checks role completeness
and contrast.

Future UX work should separately exercise the full model picker, approvals,
screen-reader behavior, and live resizing across Windows Terminal and SSH.
This change does not claim those flows have all been redesigned or validated.
