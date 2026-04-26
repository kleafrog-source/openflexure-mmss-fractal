# Ideas

## Near-term API ideas

- Add a small JSON endpoint such as `/api/latest-analysis` that returns the newest session metadata, key metrics, formula, and URLs. That would make it easier to integrate the report into other UIs without scraping HTML.
- Add `/api/capture-and-analyze` as one internal workflow entrypoint so the microscope UI or external tools can trigger the whole chain with one request.
- Add `/api/sessions` with pagination and filters by date, detected fractal type, status, and metric ranges.
- Add `/api/session/{id}` to fetch image path, report JSON, and derived summary fields for a single run.

## Microscope UI ideas

- Embed `result_streamer` inside the microscope browser UI as an iframe panel or secondary tab called `Live Analysis`.
- Show a compact overlay mode for the microscope screen: preview image, detected type, V, D_f, final formula, and recommended light/focus settings.
- Add a kiosk mode URL for the microscope display with extra-large typography and auto-hiding raw JSON details.
- Add a comparison mode that shows current capture vs previous capture for focus tuning or growth tracking.

## Capture workflow ideas

- Add a `watch folder` mode so any new file dropped into a configured directory is analyzed and published automatically.
- Add scheduled capture jobs using the OpenFlexure API so the system can collect and analyze time series without manual clicks.
- Add burst capture support: capture N images, analyze all of them, and create one batch gallery page.
- Add automatic naming presets based on sample id, operator, plate id, or experiment id.

## Analysis ideas

- Persist a normalized summary per session in CSV or SQLite so runs can be searched and charted quickly.
- Add trend plots for `V`, `D_f`, `entropy`, and `contrast` across a session series.
- Add confidence scoring and model agreement indicators when multiple detectors produce close matches.
- Save derived preview assets such as thresholded image, skeleton, ROI crop, and edge map next to each report.

## Automation ideas

- Use the OpenFlexure stage API to build scan patterns: grid scans, autofocus sweeps, and revisit coordinates after classification.
- Apply detector-driven feedback automatically: if the classifier suggests different light or focus, queue a safe follow-up capture.
- Add Telegram, email, or webhook notifications when a run finishes or when a target fractal type is detected.
- Send completed results to Google Sheets, a lab notebook, or a database for experiment logging.

## Product ideas for your app

- Turn the app into a lightweight lab dashboard with three views: `Live Capture`, `Latest Result`, and `Session History`.
- Add user annotations per session: sample name, notes, tags, experiment conditions, and approval status.
- Add export bundles for collaborators: zipped image + JSON + HTML viewer for one session or a whole experiment.
- Add role-based views: operator mode on the microscope, researcher mode on desktop, and gallery mode on wall display.

## Reliability ideas

- Add a health page that checks microscope connectivity, Mistral API availability, report server status, and free disk space.
- Add retry and timeout handling around capture, download, and analysis so the UI can show clean failure states.
- Add retention rules or archival jobs so old sessions can be moved or compressed automatically.
- Add structured logs per session to make debugging easier when a run partially succeeds.
