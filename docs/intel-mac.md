# Intel macOS app review (Issue #1)

Build and test on x86_64 Python 3.13. The DMG embeds Python 3.13.16 for the host architecture; it does not need Terminal or an installed Python at runtime. Intel builds produce `Orchard-mac-x86_64.dmg`; Apple Silicon builds retain `Orchard-mac-arm64.dmg`. Release CI builds both and runs the real visual-search smoke test.

## Dependencies and model compatibility

Keep ONNX Runtime 1.23.2 for Intel macOS wheel compatibility. Importing it alone does not prove model compatibility. Test both pinned SigLIP 2 encoders using `scripts/smoke-test --visual`, including text-to-image ranking. This does not establish compatibility with arbitrary ONNX models or later model revisions. Do not clear indexes or models to troubleshoot a runtime incompatibility.

The local validation environment on 2026-10-24 was x86_64 Python 3.13.2, ONNX Runtime 1.23.2, NumPy 2.5.3, Pillow 12.3.0, tokenizers 0.23.3, pywebview 6.2.1 and PyObjC 12.2.2. Both pinned encoders ran on CPU and returned `(1, 768)` vectors. `pip check` passed. The isolated Intel DMG also built successfully (67 MB), its ad hoc signature verified, and its embedded x86_64 Python 3.13.16 loaded the native toolkit. The packaged visual smoke test scanned four images in five files, loaded the page/script, and ranked the blue image first for a blue-square text query. The 171-test Python suite, Ruff, shell syntax and C compilation passed. The native launcher also passed the isolated SIGTERM/relaunch/persistence test. Finder/Dock and permission checks below remain manual.

## Safe review build

```sh
.venv/bin/python scripts/build-app --out build/intel-review
.venv/bin/python scripts/smoke-test --launcher build/intel-review/dmg/Orchard.app/Contents/MacOS/Orchard --port 4499 --visual --data-dir build/intel-review-data
.venv/bin/python -m unittest discover -s tests
```

Use an unused port. Smoke tests generate their own images. `tests/test_lifecycle.py` starts real processes on a temporary port and data directory, checks handoff to the existing instance, sends SIGTERM, verifies that HTTP stops, relaunches without a folder argument, and checks restored library identity/counts and unchanged originals. Unit tests cover window close, window failure, and toolkit failure cleanup. Neither command installs the app.

For a clone-backed app, run `scripts/install-app build/clone-review` into an empty destination. It refuses to overwrite an existing bundle. This app depends on the clone and its `.venv`; the DMG app is self-contained. Do not run `./orchard` against a working clone environment merely to test a requirements change: it rebuilds `.venv` when requirements change.

## Intel Mac manual acceptance checklist

These checks require a logged-in macOS desktop and user review; automated HTTP tests do not establish them. Quit the working app yourself before testing default port 4400. Keep its bundle and data backup available. For isolated tests, launch the review executable with `--port 4499 --data-dir /absolute/path/to/review-data`.

- [ ] Record Intel model, macOS version, Python/runtime versions from Copy diagnostics, and the review commit.
- [ ] Mount the DMG; copy the app to a separate review folder, never over the working installation. Verify its signature with `codesign --verify --verbose /path/to/Orchard.app`.
- [ ] Double-click the review app with no Terminal open. Confirm one Orchard Dock icon, native window, menus, and responsive folder picker. Test a clone-backed app too if using it.
- [ ] Open a generated image folder. Wait for scanning and visual indexing. Record image count and run a text and image search.
- [ ] Launch again while open (including two rapid executable launches). Confirm the existing window comes forward and only one server owns the port.
- [ ] Close the window, then separately test Cmd+Q and Dock Quit. Confirm no app-owned server remains (`lsof -nP -iTCP:4400 -sTCP:LISTEN`). Never kill another process simply because it holds that port.
- [ ] Relaunch. Confirm last folder, counts, previews, search index, theme, and window frame survive. Confirm no unnecessary model download. Repeat after sleep/wake and with the last folder disconnected.
- [ ] Test a path with spaces/non-ASCII characters, a read-only image folder, and denied folder permissions. Check the actionable alert. Test an occupied port without stopping its owner.
- [ ] Review Photos permission prompts and Show in Photos using a test library. Confirm original files and metadata are unchanged. Orchard has no photo-delete or modification flow.
- [ ] Copy diagnostics: confirm no photo names or folder paths. Native startup alerts point to the private local log without displaying raw tracebacks. Logs can contain paths; inspect/redact before sharing. The log is owner-readable/writable and appended so a second launch cannot truncate the first launch's failure.

## Rollback and data

No migration or cache-key change is introduced. Libraries, SQLite indexes, vectors, previews and models remain in `~/Library/Application Support/orchard`; recent.json remembers the last library. The app bundle and clone are separate from that data. Quitting closes the library and releases its server; browser-only sessions also close on SIGTERM. Watch loops are signalled to stop. A native app whose toolkit fails exits with an explanation rather than silently leaving a browser server behind.

To roll back, quit the review app and reopen the untouched working app. Remove only the review bundle/DMG and temporary review data when no longer needed. Do not delete Application Support, photo folders, model caches or indexes. If testing with real data, back up Application Support before review and restore that backup only with both apps quit. There is no automatic installation, replacement, merge or data deletion in this workflow.
