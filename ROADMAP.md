# Orchard — Original Product Roadmap

This is the agreed scope for improving both the native Intel macOS application and Orchard itself. Follow these six phases. Do not substitute a launcher-only project, count existing features as new work, or change the scope or sequence without the user's explicit approval.

Source: [Original planning conversation](https://chatgpt.com/share/6ae210f5-0158-83e8-bef2-a447f7b37c65), including the original-plan screenshot supplied by the user.

Status recorded: 2026-11-05. Status describes work evidenced in this conversation; it is not a claim that every requirement has shipped.

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

**Remaining limitations:** Fresh macOS privacy-prompt denial and Photos permission/integration were not verified. Dock cold launch/icon count was not verified. Optional launch-at-login has not been delivered. Desktop testing used a configuration-isolated review bundle, not an untouched release DMG. Merge, installation, and release are separate approval steps.

## Phase 2 — Intel performance

- Benchmark scanning and AI indexing throughput on the Intel Mac.
- Measure CPU and memory use, first-gallery response, thumbnail loading, and search latency.
- Add configurable indexing/resource limits and adjustable CPU usage.
- Add indexing pause/resume and predictable background operation for large libraries.
- Improve thumbnail/cache responsiveness where measurements identify a bottleneck.
- Preserve completed indexing work across pauses and restarts.

**Deliverable:** Measurable, predictable performance with large photo libraries.

**Current status:** Baseline and visual-indexing controls implemented on `feature/intel-performance`, ready for review. Added a repeatable generated-image benchmark, persisted pause/resume, and configurable inference CPU threads (applied on app restart), with controls in Info. Local validation passed 184 Python tests, the Playwright smoke scenario, lint/type checks, and the frontend build. Three real-model benchmark runs per CPU profile are recorded in [docs/performance.md](docs/performance.md). These changes are not yet merged or installed, and do not establish representative large-library acceptance.

**Remaining work:** Review the baseline and indexing-controls PR, validate larger/representative workloads and rendered UI responsiveness, and add further scanner/cache/resource changes only where measurements justify them. The current CPU setting limits inference threads, not photo scanning or a hard percentage of total CPU. Personal-photo access still requires explicit authorization; generated-data results must not be presented as full large-library acceptance.

## Phase 3 — Modern photo-management UI

- Introduce a folder/library sidebar and better gallery navigation/layout.
- Improve image-preview interactions, sorting, and keyboard navigation.
- Add selection tools.
- Add a visible indexing activity panel with progress and the Phase 2 controls.
- Support the original plan's unified multi-folder browsing direction, including the necessary indexing, database-query, and UI-state changes. A cosmetic folder selector alone does not complete unified browsing.

**Deliverable:** A more polished and capable photo-browsing experience.

**Current status:** Not delivered. The existing grid, map, filters, search bar, and viewer are not evidence of a new UI implementation.

## Phase 4 — Duplicate management

- Distinguish exact duplicates from visually similar photos.
- Provide side-by-side comparison and explicit selection of copies to keep or remove.
- Show storage/recoverable-space estimates.
- Add reviewed, confirmed moves to macOS Trash and a documented recovery workflow.
- Never delete automatically or permanently purge originals.

**Deliverable:** Safe duplicate review and cleanup, with user control and recoverability.

**Current status:** Not delivered. Existing similar-image grouping is the foundation, not the completed cleanup workflow.

## Phase 5 — Smarter local search

- Combine semantic similarity with filenames, dates, and other available metadata.
- Improve result ranking and search usability for objects, scenes, colors, and descriptions.
- Add search suggestions and saved searches.
- Treat face grouping/person identification as a separate exploration requiring explicit privacy decisions; do not imply that semantic search already identifies people.
- Keep photo processing local and avoid cloud-service dependencies.

**Deliverable:** Better photo discovery without uploading personal photos.

**Current status:** Not delivered. Existing SigLIP semantic search and image-to-image matching are baseline functionality.

## Phase 6 — Distribution

- Produce a distributable Intel DMG.
- Automate x86_64 builds and packaged smoke tests.
- Test installation on a fresh environment.
- Document and rehearse upgrades and rollback while preserving libraries, indexes, and caches.
- Complete release acceptance before proposing replacement of the working installation.

**Deliverable:** A tested, distributable Intel Mac application with a safe upgrade path.

**Current status:** Partly implemented. An isolated Intel DMG was built and its runtime, signature, toolkit, and visual-search smoke behavior were checked locally. Intel release-workflow coverage exists. These checks do not establish fresh-install, published-release, or upgrade/rollback acceptance.

## Execution and safety rules

1. Continue from this roadmap. The next product-development phase is Phase 2; keep unfinished Phase 1 items visible instead of repeatedly redefining the overall project around them.
2. Preserve the existing architecture and functionality. Make targeted changes rather than an unsolicited rewrite or broad code reorganization.
3. Keep the Intel ONNX Runtime 1.23.2 compatibility change until a replacement is explicitly justified and validated with both pinned image and text models. Verify other platforms when dependency changes affect them.
4. Work on development branches with isolated test builds/data. Do not replace or modify the user's working Orchard installation automatically.
5. Originals remain read-only by default. Phase 4's explicit, confirmed Trash workflow is the planned exception; it does not authorize background deletion or permanent deletion.
6. Merge, installation/replacement, release publication, personal-photo access, and consequential file actions require the relevant explicit user authorization. Saving this roadmap does not authorize those actions.
7. Keep development automation separate from the photo app. Use the existing local Codex/ChatGPT setup within plan limits; do not introduce paid APIs, paid runners, or extra-cost services without approval. Batch routine implementation, checks, and reporting to minimize manual handoffs.
8. Maintain progress against concrete requirements and evidence. Separate implemented, tested, shipped, and unverified work. Do not invent an overall completion percentage or count existing features as newly delivered.
9. Keep remaining limitations documented and distinguish generated-data tests from representative-library and real-desktop acceptance.

## Progress summary

| Phase | Status |
| --- | --- |
| 1. Native Intel Mac application | Substantially implemented and tested; remaining items listed above |
| 2. Intel performance | Baseline, controls, and generated 10,000-image scanner/browser checks verified; representative-library acceptance remains |
| 3. Modern photo-management UI | Not delivered |
| 4. Duplicate management | Not delivered |
| 5. Smarter local search | Not delivered |
| 6. Distribution | Packaging groundwork completed; release acceptance remains |

Update this file as evidence changes. Scope changes must be explicitly approved by the user and recorded here; do not silently replace this plan with a different one.
