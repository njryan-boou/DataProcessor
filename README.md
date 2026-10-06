# DataFlow

DataFlow is a full-stack CSV workspace for inspecting, cleaning, visualizing, and exporting datasets. React, TypeScript, Vite, Tailwind CSS, and Recharts power the dashboard; FastAPI and pandas provide parsing, statistics, transformations, and temporary dataset storage.

Upload a CSV or load the included example, review its quality and column statistics, apply transformations, undo individual steps, create charts, and download the processed CSV. The original upload is preserved throughout its active transformation pipeline.

## Quick start

Prerequisites: Python **3.11 or newer**, Node.js **20.19 or newer**, npm, and [uv](https://docs.astral.sh/uv/getting-started/installation/). Use the existing repository checkout; a separate Git worktree is unnecessary.

From the repository root, optionally copy the environment template:

```bash
cp .env.example .env
```

Start the backend in one terminal:

```bash
cd backend
uv sync --locked --group dev
source .venv/bin/activate
uvicorn app.main:app --reload
```

Start the frontend in another terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open **http://localhost:5173**. The development server proxies `/api` requests to **http://127.0.0.1:8000**, so no separate CORS configuration is needed. Interactive API documentation is available at **http://127.0.0.1:8000/docs**.

Choose the example dataset on the upload screen or upload [backend/sample.csv](backend/sample.csv) to try the complete workflow immediately. No database or AI API key is required.

## Docker

The [Dockerfile](Dockerfile) builds the frontend with the npm lockfile and installs backend dependencies with the uv lockfile. The runtime serves the compiled frontend and `/api` from the same origin using one Uvicorn worker under a non-root user. No separate frontend service or database is needed.

From the repository root:

```bash
docker build -t dataflow .
docker run --rm --name dataflow -p 8000:8000 dataflow
```

Open **http://localhost:8000**. The container exposes port 8000 by default; `PORT` controls its listening port when supplied by a hosting platform. Match the published container port if overriding `PORT` locally. To supply application settings, add `--env-file .env` before the image name. Local `.env` files and development dependencies are excluded from the image.

The image sets `DATAFLOW_FRONTEND_DIST=/app/frontend/dist`. For a same-origin production build outside Docker, run `npm run build` in `frontend` and set `DATAFLOW_FRONTEND_DIST` to the resulting `dist` directory before starting the backend. The directory must contain `index.html`. Leave this setting unset for the two-server Vite development workflow.

## Render deployment

[render.yaml](render.yaml) defines a single Docker web service named `dataflow` on Render's free plan in Oregon. Connect the repository to your Render account, then [create a Blueprint from this repository](https://dashboard.render.com/blueprint/new?repo=https://github.com/njryan-boou/DataProcessor) and review the service configuration. Render builds the image from `main`, supplies `PORT`, checks `/api/health`, and automatically deploys subsequent commits. Use the service URL shown in your Render dashboard after deployment succeeds.

The Blueprint uses smaller limits to leave memory headroom on a free instance: 10 MB uploads, 100,000 rows, 100 columns, four active datasets, and a 128 MB dataframe-snapshot budget. Other defaults, including the 20-step history limit and one-hour inactivity expiration, remain unchanged. Adjust settings in Render's environment configuration if your service plan and workload require it.

Free instances can sleep when idle. Sleep, restarts, and deployments discard in-memory datasets; the next request may also have a startup delay. Export results before leaving the application. This deployment provides the temporary-data MVP described below; it does not add accounts or persistent storage.

For automated deployment through Render's API, supply `RENDER_API_KEY` securely in the cloud environment and allow `api.render.com` if outbound networking is restricted. This is a deployment credential, not a DataFlow runtime requirement; it should not be included in the image or application environment template. Manual Blueprint creation uses your signed-in Render account instead. The optional AI provider is configured separately using the `DATAFLOW_AI_*` settings.

## Features and data behavior

- Upload and drag-and-drop CSV files, with configurable size, row, and column limits. The upload screen reads the actual server upload limit.
- Inspect sanitized filename, original file size, current row/column counts, inferred types, missing values, duplicates, and a paginated preview. The table has sticky headers and scrolls horizontally and vertically rather than rendering the entire dataset.
- View numeric count, mean, median, sample standard deviation, minimum, maximum, quartiles, unique values, missing values, and potential outliers. Text, boolean, and datetime columns show distinct counts and the ten most common values with frequencies.
- Review recommendations for duplicate rows, columns with more than 30% missing values, constant columns, and numeric outliers. Recommendations do not modify data.
- Clean and transform with validated operations, inspect history, undo the most recent operation, and export the current result as UTF-8 CSV.
- Create histograms, bar charts, line charts, scatter plots, and box plots with column-type validation on both the frontend and backend.
- Propose natural-language transformations, review their structured plan, and apply them through the same transformation engine as the regular tools.

CSV input must be UTF-8 (a UTF-8 BOM is accepted), comma-separated, and have unique, nonempty column names and at least one data row. Quoted fields and embedded newlines are supported. Malformed rows, binary content, unsupported formats, infinite numeric values, and oversized files are rejected. Empty cells and pandas' standard missing-value tokens, such as `NA`, `N/A`, and `null`, are interpreted as missing values. Numeric-looking text, including leading-zero identifiers, may be inferred as numeric; review types after uploading. Dates remain text until explicitly converted.

## Architecture

```text
frontend/
  src/
    components/         Dashboard, table, tools, charts, and assistant
    services/           Typed API client
    types/              Shared frontend API types
backend/
  app/
    main.py             FastAPI wiring, safe errors, and health checks
    api/datasets.py     Dataset REST routes
    models/schemas.py   Pydantic request and response models
    services/
      parsing.py        Filename validation and format parser registry
      storage.py        DatasetStore interface and bounded in-memory implementation
      statistics.py     Column summaries and recommendations
      transformations.py  Validated transformation registry and reusable functions
      charts.py         Type-safe, bounded chart data
      assistant.py      Replaceable provider interface and validated plans
      frontend.py       Optional same-origin production frontend serving
    utils/              Application error types and request-size middleware
  tests/                Backend unit and API tests
  sample.csv            Included example dataset
```

Each dataset receives a UUID and retains its original dataframe plus transformation snapshots. Transformations operate on copies. A batch is applied atomically: if any operation fails validation or exceeds storage limits, none of the batch is committed. Undo removes the latest individual transformation, including one step from a batch. Upload itself cannot be undone.

`DatasetStore` defines the boundary for future persistent storage. `DatasetParser` and the parser registry provide an extension point for XLSX and JSON; this version accepts **CSV only**. Adding a format requires implementing and registering a parser rather than changing the transformation engine or API routes.

## Transformations

Send an operation name and parameters to the generic transformation endpoint. Column names, parameter types, values, and resulting data limits are validated server-side; unknown operations and parameters are rejected.

| Operation | Parameters | Behavior |
| --- | --- | --- |
| `remove_duplicates` | optional `subset: string[]` | Keep the first occurrence of each duplicate row. |
| `drop_missing` | optional `columns: string[]` | Remove rows missing any selected value; defaults to all columns. |
| `fill_missing` | `column`, `method`, optional `value` | Numeric methods: `mean`, `median`, `zero`, `custom`. Text and boolean columns accept a matching custom value. |
| `rename_column` | `column`, `new_name` | Rename without creating blank or duplicate column names. |
| `delete_columns` | `columns: string[]` | Delete selected columns while retaining at least one. |
| `filter` | `column`, `operator`, optional `value` | Filter using a typed comparison or missing-value check. |
| `sort` | `column`, optional `ascending: boolean` | Stable sort; missing values are placed last. |
| `convert_type` | `column`, `type` | Convert to `numeric`, `text`, `boolean`, or `datetime`; reject unconvertible nonmissing values. |
| `trim_whitespace` | optional `columns: string[]` | Trim selected text columns; defaults to all text columns. |
| `change_case` | `column`, `case` | Convert text to `upper` or `lower`. |
| `detect_outliers` | `column`, optional `method: "iqr"` | Add `<column>_outlier` boolean flags using the 1.5 × IQR rule; retain all rows. |
| `select_columns` | `columns: string[]` | Keep selected columns in the requested order. |

Filter operators: `>`, `>=`, `<`, `<=`, `==`, `!=`, `contains`, `not_contains`, `is_missing`, and `not_missing`. Containment is literal text matching, not a regular expression. Missing-value operators omit `value`; other operators require it. Ordinary comparisons exclude missing values. Boolean comparisons accept only equality/inequality and boolean values. Datetime comparisons use date or timestamp strings.

`fill_missing` requires `value` only for `custom`; numeric custom values must be numbers rather than numeric strings. Boolean conversion recognizes true/false, yes/no, y/n, t/f, and 1/0. Datetime conversion normalizes valid values to UTC. Failed conversions leave the dataset unchanged.

## Charts

| Chart | Valid columns | Aggregation or display |
| --- | --- | --- |
| Histogram | Numeric X; no Y | Frequency distribution with 1–100 bins. |
| Bar | Non-datetime X; optional numeric Y | Category counts, or mean Y by category. Shows the 30 most frequent categories. |
| Line | Numeric or datetime X, numeric Y | Sorted by X; at most 2,000 evenly spaced observations. |
| Scatter | Numeric X and numeric Y | At most 2,000 evenly spaced observations. |
| Box | Numeric X; no Y | Quartiles, median, 1.5 × IQR whiskers, and outliers. |

Rows with missing chart values are omitted; the chart response reports omitted rows and whether points/categories were bounded. Chart sampling affects the display only. Statistics, transformations, and CSV exports use the complete dataset.

## Natural-language assistant

Without a key, a limited local parser supports explicit requests such as:

```text
Remove duplicates, fill missing age values with the median, and only keep rows where salary is greater than 50000.
```

It also supports dropping missing rows, sorting, trimming whitespace, and changing case. Unsupported or partially understood requests are rejected rather than partially applied; the regular tools remain available.

For a model-backed assistant, set `DATAFLOW_AI_API_KEY`, optionally `DATAFLOW_AI_BASE_URL`, and `DATAFLOW_AI_MODEL`. The default provider uses the OpenAI-compatible `/chat/completions` API with JSON responses and requires an HTTPS base URL. `AssistantProvider` is the interface for replacing it.

In a cloud environment with restricted outbound networking, add the configured provider hostname (default: `api.openai.com`) to the environment's network allowlist when enabling this integration. No provider access or API key is needed for the rest of DataFlow or the local parser.

The provider receives your prompt and column names/types, not dataset rows. It returns predefined operation objects, never executable Python. Every proposed operation is validated sequentially against a copy of the dataset before the UI offers the plan for review. Applying the reviewed plan uses the ordinary atomic batch endpoint. Provider errors do not affect other application features.

## Environment variables

All settings use the `DATAFLOW_` prefix. Copy [.env.example](.env.example) to the repository-root `.env`; when starting from `backend`, `backend/.env` takes precedence over the root file. Process environment variables take precedence over both. Restart the backend after changing settings. Never commit actual API keys.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATAFLOW_MAX_UPLOAD_MB` | `20` | Maximum uploaded file size; allowed range 1–200 MB. |
| `DATAFLOW_MAX_ROWS` | `200000` | Maximum input/result row count. |
| `DATAFLOW_MAX_COLUMNS` | `200` | Maximum input/result column count. |
| `DATAFLOW_MAX_DATASETS` | `8` | Maximum active datasets. |
| `DATAFLOW_HISTORY_LIMIT` | `20` | Maximum retained transformation steps per dataset; allowed range 1–100. |
| `DATAFLOW_MAX_MEMORY_MB` | `512` | Storage budget for dataframe snapshots. |
| `DATAFLOW_DATASET_TTL_SECONDS` | `3600` | Dataset expiration after inactivity. |
| `DATAFLOW_AI_API_KEY` | empty | Optional model-provider key; empty enables the limited local parser. |
| `DATAFLOW_AI_BASE_URL` | `https://api.openai.com/v1` | HTTPS OpenAI-compatible API base URL. |
| `DATAFLOW_AI_MODEL` | `gpt-4o-mini` | Model name accepted by your provider. |
| `DATAFLOW_FRONTEND_DIST` | unset | Optional path to a built frontend directory containing `index.html`; set automatically in Docker. |

Leave `DATAFLOW_FRONTEND_DIST` absent when unused; an empty value is interpreted as a filesystem path, not as disabled frontend serving.

## Testing

Backend, from `backend` after installation:

```bash
.venv/bin/pytest
```

Frontend, from `frontend`:

```bash
npm test -- --run
npm run build
```

Backend tests cover parsing, statistics, duplicate removal, missing values, filtering, sorting, conversions, transformation history/undo, invalid requests, charts, and the assistant. Frontend tests cover uploads, pagination, statistics, operation forms, undo controls, assistant plan review/application, chart selectors, and chart-type validation. The frontend production build includes TypeScript checking.

For a running-backend smoke check:

```bash
curl http://127.0.0.1:8000/api/health
curl -F 'file=@backend/sample.csv' http://127.0.0.1:8000/api/datasets/upload
```

The upload command above is run from the repository root. Use its returned `id` for the dataset endpoints below.

## API overview

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Backend readiness. |
| GET | `/api/config` | Active upload, row, column, and history limits; no secrets. |
| GET | `/api/assistant/status` | Current assistant provider and availability. |
| POST | `/api/datasets/upload` | Multipart CSV upload using field `file`. |
| POST | `/api/datasets/demo` | Create a dataset from the included example. |
| GET | `/api/datasets/{id}` | Metadata, column information, and operation history. |
| GET | `/api/datasets/{id}/preview?page=1&page_size=50` | Paginated rows; page size 1–100. |
| GET | `/api/datasets/{id}/statistics` | Column statistics and recommendations. |
| POST | `/api/datasets/{id}/transform` | Apply one validated operation. |
| POST | `/api/datasets/{id}/transform-batch` | Atomically apply 1–20 operations. |
| POST | `/api/datasets/{id}/undo` | Undo the last transformation. |
| GET | `/api/datasets/{id}/chart?kind=scatter&x=age&y=salary` | Prepare validated chart data. |
| POST | `/api/datasets/{id}/assistant/plan` | Validate and propose a plan for `{ "prompt": "..." }`; does not change data. |
| GET | `/api/datasets/{id}/export` | Stream the current dataset as a downloadable CSV. |
| DELETE | `/api/datasets/{id}` | Remove a temporary dataset and its history. |

Example transformation body:

```json
{
  "operation": "fill_missing",
  "parameters": { "column": "age", "method": "median" }
}
```

Example batch body:

```json
{
  "operations": [
    { "operation": "remove_duplicates", "parameters": {} },
    { "operation": "fill_missing", "parameters": { "column": "age", "method": "median" } },
    { "operation": "filter", "parameters": { "column": "salary", "operator": ">", "value": 50000 } }
  ]
}
```

Errors return a consistent `{ "error": { "code": "...", "message": "..." } }` response without Python stack traces. Typical status codes include 400 for invalid CSV/transformations, 404 for missing or expired datasets, 409 for unavailable undo/history capacity, 413 for size/storage limits, 415 for unsupported formats, and 422 for malformed API requests.

Request-size middleware rejects oversized uploads before multipart parsing, including requests without a `Content-Length` header. The multipart body allowance is the configured upload limit plus 1 MB for form overhead; the file itself still has the exact configured limit. Other mutation request bodies are limited to 1 MB.

## MVP limits

Datasets live in server memory and expire after inactivity. Restarting or reloading the backend removes uploads. The dashboard manages one active dataset: after a new upload or sample loads successfully, it discards the previously active dataset and its history to release storage. Export your current result before replacing it. A failed upload leaves the current dataset available.

Run **one Uvicorn worker**; multiple workers would have separate dataset stores. The memory setting bounds retained dataframe snapshots, not total process memory or temporary pandas allocations. Export before restarting, expiration, or reaching the history limit; exporting and re-uploading starts a new pipeline.

This MVP has no accounts, authentication, database, or cross-device persistence. Dataset UUIDs identify temporary data but are not an access-control system. The Docker and Render configurations serve the frontend and API together for MVP evaluation. Private-user production use requires an authenticated storage boundary and persistent storage. Uploaded content is treated only as data, filenames are sanitized, and all transformations are allowlisted and validated on the server.
