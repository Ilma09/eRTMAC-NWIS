# eRTMAC-NWIS backend — known environment gotchas

Running notes on things that cost real debugging time, kept here instead of only in chat
history so they survive across sessions/AI assistants. See `src/config.py` for the specific
constants these relate to.

## Ollama's auto-updater can silently kill the running server mid-session

Observed directly during development: a batch of VLM extraction calls started failing with
a raw `httpx.ConnectError` / connection-refused, with no code change to explain it. The
cause was Ollama's own background auto-updater launching `OllamaSetup.exe` unprompted and
tearing down the running server process.

- Before any long-running batch operation (especially full document ingestion across many
  pages), run `ollama list` first to confirm the server is actually up.
- Consider disabling Ollama's auto-update setting for the duration of active development.
- All VLM calls in this codebase should go through `src/utils.py`'s `call_ollama_chat()`,
  which classifies a connection-refused failure explicitly ("Ollama isn't running") instead
  of letting a generic httpx traceback surface — that distinction matters most during a live
  demo, if it happens mid-upload.

## One database row is a manual test construction, not organic parser output

`npt_hazards.hazard_id = 16` (Lost Circulation, 1820m, well_id=13 / "GJ O-20.6/- B") was
**not** produced by a single parse_document() run. It combines two independently real VLM
extractions from two different source documents: the coordinates on well_id=13 came from
parsing the degraded sample, and the hazard depth/type came from parsing the clean sample
(where a hazard was correctly found but the well that produced it has no extractable
coordinates at all - that document genuinely has no location section). Neither document
alone produced both a located well and a valid hazard in one run, so this row was manually
inserted to let `hazard_monitor.py` be validated end-to-end against real (if recombined)
values rather than only synthetic test data.

Left in place deliberately (not cleaned up by oversight) as seed data for testing the
upcoming `risk` router - it's the only real hazard currently in the database with a well
that has verified coordinates. It's marked with a `[TEST-COMBINED]` prefix in its
`description` column. If a real second document is ever ingested and this row starts
causing confusion (e.g. it no longer matches what a re-run of the source PDFs produces),
delete it - `hazard_id = 16` specifically, not the well or document rows around it.

## Other setup gotchas already solved (don't re-debug these)

- `pypdfium2` does not auto-install `Pillow` — install it explicitly or `bitmap.to_pil()`
  fails with `ModuleNotFoundError`.
- A `numpy` version conflict caused `OverflowError: cannot convert longdouble infinity to
  integer` on Windows — fixed via a clean `pip uninstall numpy && pip install numpy` (let
  pip pick a compatible version, don't pin one).
- `venv\Scripts\activate` does not persist across terminal tabs — must be run in every new
  terminal.
- Ollama's CLI image-passing syntax: the file path goes **inside** the prompt string, not as
  a separate `--image` flag (that flag doesn't exist).
- The default Ollama context window (4096 tokens) is not enough to hold one 200 DPI page
  image — see `VLM_NUM_CTX_PASS1`/`VLM_NUM_CTX_PASS2` in `src/config.py`, which are measured
  from real calls, not assumed.
