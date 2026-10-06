# Sample reports

`json-reporter-run.json` is a real `--reporter=json` output, captured from a
small Playwright suite. It is kept as a format fixture: if the parser ever stops
handling it, the shape assumption has drifted.

The generated demo data lives in `samples/generated/` and is not committed —
run `python scripts/generate_demo_data.py` to recreate it.
