# De Bono Creative Workflow

An interactive, reusable workflow for applying the creative problem-solving tools from
Edward de Bono's *Serious Creativity* — a dynamic, on-screen version of the process,
instead of working through it on paper.

## Why this exists

De Bono's tools (Six Thinking Hats, PO / Random Entry, Concept Fan, Sequencing, and
others) all sit downstream of a **generic pre-tool sequence**: defining what kind of
focus you're working with, phrasing it a few different ways, and generating alternatives
from a fixed point. That sequence doesn't change based on which tool you use afterward —
so this project builds it once, as its own module, and tool-specific modules will plug
into its output.

## Architecture

```
debono-creative-workflow/
  index.html          entry point
  css/styles.css       styling
  js/stages.js         DATA: the stage definitions (edit this to change the flow)
  js/app.js             ENGINE: renders whatever stages.js defines (shouldn't need edits
                        to add/reorder/remove stages)
```

The engine is config-driven: `stages.js` is a plain array of stage objects (title,
instructions, input type, options, optional conditional `showIf` branching). `app.js`
reads that array and renders a step-by-step wizard, validates each step, and persists
progress to `localStorage` so a refresh doesn't lose your answers. Adding a stage, or a
whole new tool module later, means adding data — not rewriting the engine.

## Current status: Focus & Alternatives pipeline

The universal pre-tool sequence is implemented as **Stage 1 → 5b**:

1. **Focus Type** — General Focus vs. Purpose Type Focus
   1b. *(if Purpose)* Purpose subtype — Opportunity / Improvement / Task / Problem Solving
2. **Alternative Phrasing & Definition of Focus** — 2–3 alternative phrasings
3. **Sub-Focuses** *(optional)* — break the focus into sub-focuses for later
4. **State Existing Known Alternatives**
5. **Fixed Point Type** — Purpose / Group Characteristics / Resemblance / Concept
   5b. Define the specific fixed point

This is a working draft transcribed from notes — **not a comprehensive rendering of the
book's method**. It will be extended as more of the sequence is drafted.

## Tool modules (planned)

Each De Bono tool will be its own module downstream of the Focus & Alternatives output,
and will get its own section here documenting:
- the tool's specific step sequence
- what it consumes from the Focus & Alternatives output
- what it produces

No tool modules are built yet. Candidates: Random Entry / PO, Six Thinking Hats, Concept
Fan, Sequencing.

## Running it

No build step. Open `index.html` directly in a browser, or serve the folder locally:

```
python3 -m http.server 8000
```

then visit `http://localhost:8000/debono-creative-workflow/`.

## Source

Stage definitions are drawn from the user's own notes taken while reading *Serious
Creativity* (Edward de Bono), not reproduced from the book's text.
