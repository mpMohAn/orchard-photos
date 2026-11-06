# Intel performance and indexing controls

This is the Phase 2 implementation and measurement record for [ROADMAP.md](../ROADMAP.md). It preserves the working installation and ONNX Runtime 1.23.2 compatibility pin.

## Controls

Info → Indexing controls provides **Pause indexing / Resume indexing** and a **CPU threads** setting.

- Pause stops visual indexing between batches; a batch already running may finish and commit. Completed embeddings remain searchable and are not discarded.
- Pause is saved in the app's data directory as `indexing.json`. Quitting and reopening preserves both the setting and completed vectors. Resuming indexes only the remaining images.
- Paused work still responds to closing a library or quitting the application.
- CPU threads defaults to **Automatic**, preserving existing ONNX scheduling. A chosen thread limit applies to the CPU image/text inference sessions on the next app launch. The UI explains when a restart is needed.
- This is an inference thread limit, not a hard percentage cap on total process CPU. It does not throttle photo scanning, model downloads, or a GPU provider. Downloads/model initialization already in flight may finish before indexing pauses.
- These controls do not delete originals, change model revisions, clear caches, or replace the installed application.

The loopback-only, same-origin API exposes `GET /api/indexing` and `POST /api/indexing`. A POST accepts `paused` (boolean) and/or `threads` (integer 0–64, where 0 means automatic). Responses include `active_threads` separately from the saved setting. Other values/keys are rejected. Writes are atomic and settings take effect only after the save succeeds.

## Reproducible benchmark

Run with the existing Python environment on macOS or Linux. The benchmark uses generated 1024×768 PNGs, a temporary data directory, an unused loopback port, and no native window. It checks original hashes and shuts down its server before cleaning up. It never runs the installation launcher or touches personal photo libraries.

```sh
.venv/bin/python scripts/benchmark --images 2000 --out build/benchmarks/gallery-new.json

# Optional real inference; requires a complete existing test-model cache.
.venv/bin/python scripts/benchmark --images 12 --visual --threads 2 \
  --models build/intel-review-data/models --out build/benchmarks/visual-new.json
```

Output reports are never overwritten. For visual runs, the complete existing cache is copied into temporary data before starting the server. Hugging Face offline mode is enabled; there are no model downloads and the source cache stays unchanged. Peak RSS is sampled every 250 ms. CPU seconds include the server and the small `ps` sampler subprocesses. Reported gallery/search/thumbnail latency is HTTP response time, not rendered UI frame time. OS caches are not flushed.

## Recorded Intel results

Machine: macOS 14.4.1, x86_64, 12 logical CPUs, Python 3.13.2, ONNX Runtime 1.23.2. These are synthetic workload measurements, not acceptance results for an 11,500-photo personal library.

The archived 2026-10-28 run on 2,000 generated images recorded:

| Measurement | Result |
| --- | --- |
| First catalog image, including server startup | 0.900 s |
| Scan complete, including startup | 14.352 s |
| Scan throughput, including startup | 139.354 images/s |
| Gallery API median / p95 | 1.335 / 1.510 ms |
| Cached-thumbnail API median / p95 | 0.742 / 1.128 ms |
| Filename-search API median / p95 | 1.305 / 33.788 ms |
| Sampled peak RSS | 129.53 MiB |

Fresh real-model runs were repeated three times per profile on 2026-11-05, indexing the same 12 generated images and performing five description queries. The following table gives medians across the three runs; per-run raw reports are committed under [benchmarks/2026-11-05](benchmarks/2026-11-05).

| Measurement | Automatic threads | Two threads |
| --- | --- | --- |
| Visual search ready from process launch | 7.435 s | 9.119 s |
| Total CPU seconds, including sampler | 24.805 | 15.964 |
| Sampled peak RSS | 1,095.16 MiB | 1,100.22 MiB |

The limited-thread profile traded longer elapsed time for less CPU work. It did not reduce model memory meaningfully. This small experiment is not a statistically controlled hardware benchmark or a general speedup claim. No thumbnail/cache optimization was added merely to satisfy a checklist: cached-thumbnail API responses were already fast in this workload. Larger real-image and rendered-gallery profiling remains necessary before changing cache behavior.

## Validation and remaining acceptance

- 184 Python tests passed locally, including controls persistence/validation, CPU options on both CPU model sessions, DirectML GPU compatibility with a CPU text-session limit, and preserving partial indexing progress. The CPU-only test explicitly selects CPU providers so its expectations are independent of the runner's installed GPU providers.
- A real-process test paused mid-index, verified stable progress, quit while paused, restarted, resumed, and checked that completed batches were not repeated and generated originals were unchanged. It uses deterministic offline vectors to isolate lifecycle behavior; the benchmark separately exercises real ONNX inference.
- The Playwright smoke scenario verifies pause/resume, saved CPU settings across page reload, the restart explanation, and existing browsing/filtering/map/search interactions. Its server and data are isolated, and downloads are disabled.
- Ruff, ESLint, TypeScript checks, and the frontend build passed. Rebuilt `dist/` is included with the UI changes.
- Representative large-library acceptance, scanner resource throttling, and rendered UI responsiveness under a large indexing workload remain unverified/not implemented. The scope of this PR is the repeatable baseline plus visual-indexing controls; it does not mark every Phase 2 outcome complete.

No merge, installed-app replacement, personal-photo access, or release publication is part of this validation.

## Generated 10,000-image checks, 2026-11-06

The 1024×768 scanner workload completed in 80.164 seconds, with its first image at 1.540 seconds and sampled peak RSS of 145.76 MiB. All 10,000 original hashes remained unchanged. Gallery API median was 1.295 ms. Filename-search p95 was 296.651 ms, including a cold query.

A separate opt-in browser workload used 10,000 tiny 48×48 generated PNGs. The first tile appeared 1.436 seconds after opening the folder. Across 120 animation frames while scrolling, the median interval was 16.5 ms, p95 18.7 ms, and maximum 27.7 ms. There were 80 mounted tiles after scrolling, and the full-size viewer opened successfully. These headless browser intervals do not establish physical display frame rates. Neither workload performs model inference. Both ran on the same machine during this validation session, so the measurements are observational rather than controlled comparisons.

Raw reports are in [benchmarks/2026-11-06](benchmarks/2026-11-06). Reproduce the browser check with `ORCHARD_UI_LARGE=1 npm run test:ui -- --grep 'large library'`. The normal smoke fixture remains unchanged. Representative-library acceptance and responsiveness during large-scale real-model indexing remain pending.

All seven jobs passed in [GitHub Actions run 42053895128](https://github.com/mpMohAn/orchard-photos/actions/runs/42053895128), including the retried Apple Silicon job.
