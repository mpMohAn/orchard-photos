# Orchard — Original Product Roadmap

This is the agreed scope for improving both the native Intel macOS application and Orchard itself. Follow these six phases. Do not substitute a launcher-only project, count existing features as new work, or change the scope or sequence without the user's explicit approval.

Source: [Original planning conversation](https://chatgpt.com/share/6ae210f5-0158-83e8-bef2-a447f7b37c65), including the original-plan screenshot supplied by the user.

Status updated on 2026-11-09. Implementation, automated validation, manual acceptance, and release are tracked separately below.

## Approved review update — 2026-11-09

The user asked for a Google Photos-inspired layout, clearer visual search, useful selection/Trash and Finder actions, and a fix for the slow similarity view. The similarity view is retained and renamed **Visual Explore**. It is not a geographic map. Existing architecture, local processing, and compatibility pins are retained.

The review implementation adds prominent sidebar search/explore navigation and search-by-image access, saved-search naming, compact indexing controls, tighter photo spacing, and selection/folder Trash review. Folder-wide review lists all indexed originals in the folder/subfolders, independently of loaded thumbnails, up to 5,000 files per explicit confirmation. The native journaled Trash workflow is extended; no automatic or permanent deletion is added. Personal-photo moves and installation changes were not performed.

The renderer no longer continuously redraws while thumbnails are loading. Retina canvas resolution is capped at 1.5×, atlas sheets decode at most two at a time, and aborted view loads release their bitmaps. A 3,000-point synthetic browser regression records zero idle draw calls over 300 ms with held thumbnail requests. This does not establish real-library frame-rate or first-layout performance. First layout still computes in the background.

Validation passed 100 focused Python tests (API, duplicates, library, searches, layout), frontend lint/type checks and build, and serial browser smoke including light/dark views and 320/375/414/768 px layouts. Ruff is not installed in this environment. Native Trash/Put Back and representative-library performance acceptance remain pending.

## Product goal

Build a polished, dependable Intel Mac photo application by extending Orchard's existing architecture, improving large-library performance, modernizing photo-management interactions, adding safe duplicate review and cleanup, and improving local search.

Preserve the working foundation rather than rewriting it. Folder/Photos-library selection, thumbnail browsing, full-size previews, filename and semantic/image search, timeline/map browsing, filters, and similar-image grouping already exist. These are baseline capabilities to preserve, not new milestones to claim as delivered.

## Phase 1 — Native Intel Mac application

Extend `scripts/install-app`, `scripts/build-app`, and `server/window.py`.

- Provide a proper Intel `.app` bundle, custom icon, and Dock integration.
- Launch without an open Terminal.
- Start the app-owned server on launch and stop it cleanly on quit.
- Prevent duplicate app-owned servers and bring the existing window forward.
- Remember the selected photo folder/library and preserve indexes and caches.
- Show actionable startup/permission errors and privacy-preserving diagnostics.
- Include launch-at-login as an optional setting, as described in the original plan.
- Validate launch, shutdown, relaunch, permissions, and index persistence.

**Deliverable:** A reliable Dock-launchable Intel `Orchard.app`.

**Current status:** Substantially implemented in PR #2. Intel packaging, lifecycle safeguards, diagnostics, and CI were added. CI passed on Intel Mac, Apple Silicon, Windows, and Linux, alongside lint, web, and UI checks. Isolated desktop tests covered Finder launch, the folder picker, Cmd+Q, window close, user-performed Dock Quit and sleep/wake, restored library identity/counts, and unchanged generated originals.

**Review follow-up:** Optional launch-at-login is implemented in Info, off by default. It writes a per-bundle/per-data-directory user LaunchAgent only when enabled, for the next graphical login. Disabling removes that agent. Temporary mounted/translocated bundles cannot enable it. Tests use temporary homes and simulated browser responses; the user's login settings were not changed. Real logout/login acceptance remains pending.

**Remaining limitations:** Fresh macOS privacy-prompt denial and Photos permission/integration were not verified. Dock cold launch/icon count was not verified. Desktop testing used a configuration-isolated review bundle, not an untouched release DMG. Merge, installation, and release are separate approval steps.

## Phase 2 — Intel performance

- Benchmark scanning and AI indexing throughput on the Intel Mac.
- Measure CPU and memory use, first-gallery response, thumbnail loading, and search latency.
- Add configurable indexing/resource limits and adjustable CPU usage.
- Add indexing pause/resume and predictable background operation for large libraries.
- Improve thumbnail/cache responsiveness where measurements identify a bottleneck.
- Preserve completed indexing work across pauses and restarts.

**Deliverable:** Measurable, predictable performance with large photo libraries.

**Current status:** Baseline and visual-indexing controls implemented on `feature/intel-performance`, ready for review. Added a repeatable generated-image benchmark, persisted pause/resume, and configurable inference CPU threads (applied on app restart), with controls in Info. Local validation passed 184 Python tests, the Playwright smoke scenario, lint/type checks, and the frontend build. Three real-model benchmark runs per CPU profile are recorded in [docs/performance.md](docs/performance.md). These changes are not yet merged or installed, and do not establish representative large-library acceptance.

**Remaining acceptance:** Review PR #5 and validate representative-library behavior during real-model indexing. Generated 10,000-image scanner and browser checks are complete and recorded in [docs/performance.md](docs/performance.md). The CPU setting limits inference threads. Scanner resource controls and further cache changes require measured justification. Personal-photo access requires explicit authorization.

## Phase 3 — Modern photo-management UI

- Introduce a folder/library sidebar and better gallery navigation/layout.
- Improve image-preview interactions, sorting, and keyboard navigation.
- Add selection tools.
- Add a visible indexing activity panel with progress and the Phase 2 controls.
- Support the original plan's unified multi-folder browsing direction, including the necessary indexing, database-query, and UI-state changes. A cosmetic folder selector alone does not complete unified browsing.

**Deliverable:** A more polished and capable photo-browsing experience.

**Current status:** Implemented for review on `feature/library-workspace` in PR #6. The responsive sidebar provides folder navigation and combined workspaces. Sorting supports newest/oldest, filename, and file size, with saved preferences. Selection includes select-loaded/clear and keyboard shortcuts. The viewer adds a thumbnail strip, a details toggle, Z to switch zoom, and Home/End to navigate to the first/last loaded image. Real indexing activity and persisted pause/CPU settings remain visible.

**Combined-folder behavior:** Add a folder through the sidebar's plus button. Up to 16 separate, non-overlapping image folders share a catalog, filters, filename/description/image search, date timeline, and map infrastructure. Root names namespace file paths, including roots with the same basename. Exact copies share an image record while retaining their original locations. Removing a source changes the workspace. Each distinct folder set has its own cache and initial indexing pass. Existing single-folder cache identities are retained. Workspace paths are saved atomically and restored on app startup. An unavailable root stops rescanning and retains the previous catalog until it reconnects. Apple Photos opens separately.

**Validation:** Phase 3 passed 193 Python tests and [GitHub CI](https://github.com/mpMohAn/orchard-photos/actions/runs/42191815565). Generated-data browser tests cover sorting persistence, cross-folder navigation/search, original preview paths, source addition/removal, preview controls, light/dark themes, and responsive layouts. Python tests cover duplicate identity, stable paging/sorts, overlapping-root rejection, failed saves, unavailable drives, platform-safe paths, and real-process workspace restoration. A six-image, two-folder offline smoke test indexed every image using the existing real model cache and passed description/image queries. These checks use isolated generated data.

**Remaining acceptance:** Representative personal-library testing and native desktop review of this UI remain pending. Phase 3 is implemented for review and has not been merged or installed.

## Phase 4 — Duplicate management

- Distinguish exact duplicates from visually similar photos.
- Provide side-by-side comparison and explicit selection of copies to keep or remove.
- Show storage/recoverable-space estimates.
- Add reviewed, confirmed moves to macOS Trash and a documented recovery workflow.
- Never delete automatically or permanently purge originals.

**Deliverable:** Safe duplicate review and cleanup, with user control and recoverability.

**Current status:** Implemented for review on `feature/duplicate-review`. The sidebar opens exact-copy and similar-photo categories with group navigation, side-by-side previews, dimensions, original paths, and logical extra-file size estimates. Files default to keep. Cleanup requires a selected subset, a server-generated review, a verified keeper, a confirmation checkbox, and an explicit final move action.

**Cleanup behavior:** macOS folder libraries use native Trash. Apple Photos and other platforms provide read-only review. Each review permits up to 50 files and expires after ten minutes. Content hashes and file identity are checked again before moves. Symlinked and hard-linked files are read-only. A durable per-catalog journal records progress and resulting Trash locations. Repeated confirmations return saved outcomes. Partial and interrupted operations stop for review and manual recovery. [Recovery instructions](docs/using-orchard.md#duplicate-review) describe Put Back, recorded locations, and rescanning.

**Validation and remaining acceptance:** All 208 Python tests, browser smoke, lint/type checks, and the frontend build passed locally. Automated tests cover exact/similar classification, unchanged-file and keeper checks, explicit confirmation, partial failures, journal failures, interruption, repeated requests, and combined-folder source identity. Browser tests cover comparison, keep selection, cancellation, confirmation, results, and mobile layout. Automated filesystem moves use generated files and a simulated Trash location. Browser move requests are intercepted. Native macOS Trash/Put Back acceptance and representative-library review remain pending.

## Phase 5 — Smarter local search

- Combine semantic similarity with filenames, dates, and other available metadata.
- Improve result ranking and search usability for objects, scenes, colors, and descriptions.
- Add search suggestions and saved searches.
- Treat face grouping/person identification as a separate exploration requiring explicit privacy decisions; do not imply that semantic search already identifies people.
- Keep photo processing local and avoid cloud-service dependencies.

**Deliverable:** Better photo discovery without uploading personal photos.

**Current status:** Implemented for review on `feature/search-distribution`. Combined search merges the existing thresholded semantic candidates with filename/camera matches and bounded metadata bonuses. Explicit date, year, camera, file type, filename/path, and folder operators narrow the current filters. Search tools provides catalog-derived suggestions and up to 100 named searches per workspace, retaining mode, filters, and order. No cloud dependency was added. Face/person identification remains a separate privacy decision.

**Validation and remaining acceptance:** The 218-test regression suite, frontend build, static checks, and browser smoke passed locally. Generated-data tests cover parsing, literal filenames, stable combined ranking, saved-search persistence, and UI restore/remove flows. A six-image, two-folder offline real-model check passed combined description search, metadata filters, and image matching. The ranking bonuses are heuristic. Representative-library relevance evaluation remains pending.

**2026-11-09 review fix:** Combined search now ranks all matching members before collapsing similar-photo groups. A regression test covers a matching non-cover image, competing semantic matches, and filename fallback. The follow-up passed 77 focused Python tests (search, login, API, duplicates, indexing, workspace), browser smoke, frontend lint/type checks, and the production build. Ruff is unavailable in the current environment; a fresh full-suite result is not claimed. The earlier Intel DMG predates these fixes and must be rebuilt before artifact acceptance.

## Phase 6 — Distribution

- Produce a distributable Intel DMG.
- Automate x86_64 builds and packaged smoke tests.
- Test installation on a fresh environment.
- Document and rehearse upgrades and rollback while preserving libraries, indexes, and caches.
- Complete release acceptance before proposing replacement of the working installation.

**Deliverable:** A tested, distributable Intel Mac application with a safe upgrade path.

**Current status:** Distribution implementation is ready for review on `feature/search-distribution`. The Intel builder produces an ad hoc signed, self-contained DMG, a SHA-256 sidecar, and a source/runtime manifest. Release automation retains native x86_64 coverage and adds a temporary fresh-setup/upgrade/rollback rehearsal with archived reports. A local cached-package build validates requirement pins and native architectures before reuse.

**Validation and remaining acceptance:** The final 66 MB Intel DMG passed signature, checksum, source-manifest, bundled Python 3.13.16, ONNX Runtime 1.23.2, and toolkit checks. Packaged combined-text and uploaded-image queries passed with real offline models. Fresh-home setup and upgrade/rollback against the older review bundle preserved catalog identities, two embeddings, saved searches, indexing settings, and generated originals. [Artifact evidence](docs/benchmarks/2026-11-06/phase6-artifact.json) and [distribution rehearsal](docs/benchmarks/2026-11-06/phase6-distribution.json) record the results. This tests isolated HOME/data and temporary installation paths on this Mac. Fresh physical-Mac, Gatekeeper, native privacy, published-release, and user-approved replacement acceptance remain pending.

## Execution and safety rules

1. Continue from this roadmap. Phases 5 and 6 now have reviewable implementations. Prepare the combined review and finish the listed acceptance work before release. Keep earlier gaps, including real login-launch and native Trash/permission acceptance, visible.
2. Preserve the existing architecture and functionality. Make targeted changes rather than an unsolicited rewrite or broad code reorganization.
3. Keep the Intel ONNX Runtime 1.23.2 compatibility change until a replacement is explicitly justified and validated with both pinned image and text models. Verify other platforms when dependency changes affect them.
4. Work on development branches with isolated test builds/data. Do not replace or modify the user's working Orchard installation automatically.
5. Originals remain read-only by default. The explicit, confirmed duplicate/selection/folder Trash workflow is the approved exception; it does not authorize background deletion or permanent deletion.
6. Merge, installation/replacement, release publication, personal-photo access, and consequential file actions require the relevant explicit user authorization. Saving this roadmap does not authorize those actions.
7. Keep development automation separate from the photo app. Use the existing local Codex/ChatGPT setup within plan limits; do not introduce paid APIs, paid runners, or extra-cost services without approval. Batch routine implementation, checks, and reporting to minimize manual handoffs.
8. Maintain progress against concrete requirements and evidence. Separate implemented, tested, shipped, and unverified work. Do not invent an overall completion percentage or count existing features as newly delivered.
9. Keep remaining limitations documented and distinguish generated-data tests from representative-library and real-desktop acceptance.

## Current execution order

1. Review the Phase 5 search implementation and Phase 6 Intel DMG, manifests, checksums, and test reports.
2. Complete remaining representative-library and native desktop acceptance, including Trash recovery and permission prompts, with the applicable authorization.
3. Validate the optional launch-at-login setting with a real logout/login before calling the original plan fully complete.
4. Approve merge, installation/replacement, and release publication separately.

## Progress summary

| Phase | Status |
| --- | --- |
| 1. Native Intel Mac application | Substantially implemented and tested; remaining items listed above |
| 2. Intel performance | Baseline, controls, and generated 10,000-image scanner/browser checks verified; representative-library acceptance remains |
| 3. Modern photo-management UI | Sorting, previews and combined-folder browsing implemented for review; representative-library/native acceptance remains |
| 4. Duplicate management | Review/confirmation/journal implemented; native Trash and representative-library acceptance pending |
| 5. Smarter local search | Combined ranking, metadata filters, suggestions and saved searches implemented for review; representative relevance evaluation pending |
| 6. Distribution | Final Intel review DMG and isolated setup/upgrade/rollback validated; fresh physical-Mac/Gatekeeper and release acceptance remain |

Update this file as evidence changes. Scope changes must be explicitly approved by the user and recorded here; do not silently replace this plan with a different one.

## Review checkpoint — 2026-11-10

The user approved a closer Google Photos browsing/selection flow and opt-in local People grouping. The selection pass adds thumbnail checkmarks, Shift-click ranges among loaded photos, a top selected-count toolbar, and visible folder-wide selection before Trash review. The previous “Review all photos in this folder for Trash” command has been replaced. Existing native Trash verification/journaling is retained.

People grouping was approved at this checkpoint and implemented in the 2026-11-11 follow-up below. It requires detection, alignment, local face embeddings, editable groups/names, opt-in/pause/clear controls, licensing and Intel validation. Pet grouping, cloud backup/sharing, advanced AI edits, and Locked Folder are not implemented. No installed app or personal-photo data has been modified.

## Preview follow-up — 2026-11-11

Small originals keep their native display dimensions in the gallery, and rows containing only small images stay compact. Tiny tile selection controls leave the photo centre available for opening. The viewer starts with details collapsed, uses a dark photo stage, animates from the thumbnail where available, fades between images, and fades on close. Reduced-motion preference bypasses transitions. Build, ESLint and TypeScript checks pass. Browser regression covers 48-pixel originals, selection, preview navigation and details controls. The People implementation and Intel validation are recorded below. The earlier DMG predates these changes.


## People implementation — 2026-11-11

The approved local People feature is implemented. The sidebar opens a dedicated People page with circular face portraits, names and photo counts, a person gallery, editable names, group merging, individual-face separation and false-detection dismissal. Named people can be found using `person:"Name"` in the main search. The layout follows the supplied Google Photos reference and adapts to narrow windows.

Processing is opt-in per library. Setup downloads approximately 39 MB of hash-verified YuNet and SFace models. Detection, alignment and embeddings run locally through the existing Intel ONNX Runtime 1.23.2 dependency, with two CPU threads and one image processed at a time. Work yields to scanning and visual indexing. Pause/resume and per-image checkpoints preserve progress across restarts. Explicit confirmed clearing removes this library's face crops, embeddings, names and groups and turns processing off. An incompatible model version preserves existing data and requires explicit clearing before re-enabling.

Validation includes 112 focused Python tests, frontend lint/type/build checks, responsive People browser coverage, real inference and named-search checks using two public OpenCV sample images, and a 50-image public-sample-variant Intel workload. The workload completed in 7.46 seconds including pause and restart, with gallery API median 4.44 ms, p95 5.72 ms and sampled peak server memory 169.76 MB. [Inference report](docs/benchmarks/2026-11-11/people-inference.json) and [performance report](docs/benchmarks/2026-11-11/people-performance.json) record the scope and limitations.

Representative-library accuracy, large People collections and native user acceptance remain open. Automatic grouping is conservative and can miss or split matches. Correction controls are part of the delivered workflow. Pet grouping and the other previously excluded features remain outside this implementation.


The final performance follow-up keeps model sessions unloaded when naming or correcting completed groups and skips model loading on scans with no pending photos. A dedicated regression test verifies that naming does not restart processing. Eight People tests pass. GitHub CI also validates the complete platform suites, lint, web build and browser flow. Native Trash simulation runs on supported POSIX test platforms, while Windows retains coverage for the other features and the browser checks its available folder-reveal action.


## Review fixes — 2026-11-11

The user requested direct face naming/matching, prompt updates for new downloads, and the right-hand preview details/duplicate information. Each detected face now has **Name or match person**, opening a portrait-and-name picker for existing groups or a new name. Group-level **Same person? Merge groups** uses the same visual picker. Assignment updates the existing face record and invalidates person-photo caches.

Regular-folder monitoring now probes directory metadata between periodic full reconciliations, debounces changes, discovers newly created subfolders, and retries incomplete downloads after their file metadata changes. Continuous additions have a bounded debounce, and the index directory is excluded from probes. Probe frequency adapts to the cost of checking large/slow folder trees. The generated-file normal-entry test observed 0.951 seconds for a new image, 2.067 seconds after a partial download completed, and 1.995 seconds for a new subfolder. These measurements cover a small local generated library. Apple Photos retains periodic reconciliation.

Preview details now open by default. File metadata and exact-duplicate locations are visible without expanding another disclosure, alongside the existing near-duplicate previews. The animated dark viewer and native-size small-image rendering remain available. Browser tests cover default details, exact duplicate locations, individual face assignment/new-name submission, group matching, and responsive layouts. Focused Python regression and lint/build checks pass. A new Intel review artifact is required for these changes.


The follow-up catches downloads that finish before the next metadata probe by comparing their current metadata with the failed scan's recorded size and modification time. A regression test covers this timing window. The final generated-library check observed a live gallery refresh in 3.107 seconds without reloading the browser. Its API checks measured 3.309 seconds for a new image, 6.93 seconds after download completion, and 2.792 seconds for a new subfolder during concurrent validation. The updated folder-update report records these results.
