# LoreDock API contract conventions

## Versioning

- HTTP endpoints start with `/api/v1`.
- Core and desktop exchange `/api/v1/version` before enabling application features.
- Additive response fields are compatible within v1.
- Removing or changing a field's meaning requires a new API version or an explicit migration window.
- Database schema, index schema, and build contracts use independent integer versions.

## Naming and serialization

- JSON keys use `snake_case` to match Core boundary models.
- Identifiers are opaque UUID strings and must not encode local paths.
- Timestamps use UTC RFC 3339 values.
- Pagination is cursor-based and bounded to 200 items per page.
- Public contracts reject unknown input fields.

## Success envelope

Single resources are returned directly. Collections use:

```json
{
  "items": [],
  "page": {
    "limit": 50,
    "next_cursor": null
  }
}
```

## Error envelope

All expected API failures use:

```json
{
  "error": {
    "code": "library_not_found",
    "message": "The requested knowledge library does not exist.",
    "request_id": "optional-correlation-id",
    "fields": {
      "name": ["A library name is required."]
    }
  }
}
```

Error codes are stable machine-readable contract values. User-facing clients localize messages and
must not branch on free-form text.

## Local transport

- Development default: `http://127.0.0.1:49321`.
- Packaged desktop: a dynamically allocated loopback port with a per-process authentication secret.
- Local Core must reject non-loopback binding unless a future explicit server profile is active.

## Phase 2 resources

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/libraries` | Create a knowledge library |
| `GET` | `/api/v1/libraries` | List libraries |
| `GET` | `/api/v1/libraries/{library_id}` | Read library metadata |
| `PATCH` | `/api/v1/libraries/{library_id}` | Rename a library |
| `DELETE` | `/api/v1/libraries/{library_id}` | Delete the library and owned data |
| `POST` | `/api/v1/libraries/{library_id}/sources` | Upload and synchronously index a supported file |
| `GET` | `/api/v1/libraries/{library_id}/sources` | List sources |
| `GET` | `/api/v1/sources/{source_id}` | Read source metadata and state |
| `GET` | `/api/v1/sources/{source_id}/content` | Read a bounded character range |
| `DELETE` | `/api/v1/sources/{source_id}` | Delete raw copy, artifact, FTS rows and vectors |
| `POST` | `/api/v1/libraries/{library_id}/search` | Hybrid or BM25-only search |
| `GET` | `/api/v1/jobs/{job_id}` | Read persistent indexing job state |
| `POST` | `/api/v1/jobs/{job_id}/retry` | Retry a failed indexing job, up to three attempts |
| `POST` | `/api/v1/libraries/{library_id}/import-batches` | Create a persistent import batch before uploading its items |
| `GET` | `/api/v1/libraries/{library_id}/import-batches` | List the 1–100 most recent import batches |
| `GET` | `/api/v1/import-batches/{batch_id}` | Read aggregate batch progress and outcome counts |
| `POST` | `/api/v1/import-batches/{batch_id}/seal` | Mark item submission complete |
| `POST` | `/api/v1/import-batches/{batch_id}/pause` | Pause leasing new jobs and cooperatively pause the running item |
| `POST` | `/api/v1/import-batches/{batch_id}/resume` | Resume a paused batch |
| `POST` | `/api/v1/import-batches/{batch_id}/cancel` | Cooperatively cancel unfinished batch items |
| `POST` | `/api/v1/import-batches/{batch_id}/retry` | Retry failed or canceled items below the attempt limit |
| `GET` | `/api/v1/settings` | Read non-sensitive application preferences |
| `PUT` | `/api/v1/settings` | Replace non-sensitive application preferences |
| `POST` | `/api/v1/backups` | Create and verify a managed consistent backup |
| `GET` | `/api/v1/backups` | List managed backups and validity state |
| `POST` | `/api/v1/backups/{backup_id}/verify` | Re-run manifest, checksum and SQLite integrity checks |
| `POST` | `/api/v1/backups/{backup_id}/restore` | Schedule verified restoration for the next Core restart |
| `GET` | `/api/v1/models/default` | Read the pinned local embedding model state |
| `POST` | `/api/v1/models/default/install` | Start or reuse the pinned model install job |
| `GET` | `/api/v1/models/jobs/latest` | Read the latest model install job, if any |
| `GET` | `/api/v1/models/jobs/{job_id}` | Poll exact byte progress and state |
| `POST` | `/api/v1/models/jobs/{job_id}/cancel` | Pause an active model download |
| `POST` | `/api/v1/models/jobs/{job_id}/retry` | Resume a failed or canceled download |

### Application settings

Settings use a singleton resource persisted in `app.sqlite`. The v1 payload contains
`onboarding_completed`, `theme` (`system`, `light`, or `dark`), and `default_search_mode`
(`hybrid` or `lexical`). `PUT` replaces the complete resource so clients cannot accidentally retain
unknown future values. Credentials and model-provider secrets are never part of this contract.

### Managed backups

Managed backups are versioned archives under the LoreDock data directory. `app.sqlite` and every
knowledge-library `index.sqlite` are copied with the SQLite Backup API while writers are excluded;
raw sources, parsed artifacts and build manifests are included. Each file is bound to the archive
manifest by its relative path, byte size and SHA-256. Verification also runs SQLite `quick_check`
and foreign-key checks.

Restore never replaces a live database. A successful restore request first creates a recovery point
for the current state, verifies the selected archive and writes a pending marker. The desktop then
restarts Core, which performs the replacement before opening any database connection and rolls back
the original files if switching fails. The response contains `restart_required: true`. Backups do
not contain OS credential-store secrets, Agent connection metadata or downloaded model assets.

### Managed default model

The model status reports `missing`, `ready`, or `corrupt`, whether the current Core process is using
it, download and disk-space requirements, and whether a restart is required. Installation uses a
pinned repository revision and SHA-256 checksums. Model jobs report actual downloaded and total
bytes; clients derive display percentages from those values. Failed, canceled, or interrupted
downloads retain `.part` files and resume with an HTTP Range request. A server that ignores Range
starts that asset again safely. Search continues through its fallback path until the verified model
is activated on Core restart.

### Source list pagination

`GET /api/v1/libraries/{library_id}/sources` accepts these optional query parameters:

| Parameter | Contract |
|---|---|
| `limit` | Page size from 1 to 200; defaults to 50 |
| `cursor` | Opaque continuation token returned by the preceding response |
| `filter` | Case-insensitive literal match against name, media type, or processing status; maximum 200 characters |
| `sort` | `updated-desc` (default), `name-asc`, or `size-desc` |

Pagination uses stable keyset ordering with the source ID as a tie-breaker. A cursor is bound to the
filter and sort values that created it; reusing it with different values returns
`invalid_cursor`. Clients must treat cursor contents as opaque and restart from the first page when
the filter or sort changes.

The Phase 2 upload endpoint completes indexing before returning. Job state is persisted throughout
the operation, interrupted jobs are recovered as failed at startup, and the same use case can move
to a background worker without changing its HTTP result contracts.

Supported uploads are Markdown, TXT, PDF, DOCX, PPTX, XLSX and HTML, with a 100 MiB per-file limit. PPTX text is extracted in slide order from text boxes and tables, with slide-number citation metadata. XLSX text is extracted in workbook order with sheet names and cell coordinates; formulas are never executed. HTML is
converted to inert UTF-8 text; script, style, template and embedded-frame content is excluded. A
repeated content hash within the same library returns the existing source and job with
`duplicate: true`.

`POST /api/v1/libraries/{library_id}/url-sources` accepts `{ "url": "https://..." }` and creates a bounded, one-time HTML or plain-text snapshot. The Core permits only public HTTP/HTTPS destinations on standard ports, pins the connection to a validated public DNS result, revalidates up to three redirects, rejects HTTPS downgrade, compressed or unsupported responses, and limits the decoded snapshot input to 10 MiB. URL sources expose additive `source_kind` and `origin_url` fields; file sources use `source_kind: "file"` and `origin_url: null`.

File and URL import responses now represent durable acceptance, not completed indexing. A new source normally returns `source.status: "pending"` and `job.status: "pending"`; clients poll `GET /api/v1/jobs/{job_id}` until `succeeded`, `failed`, or `canceled`. `POST /api/v1/jobs/{job_id}/cancel` cooperatively cancels a pending or running source job. `POST /api/v1/jobs/{job_id}/retry` requeues a failed or canceled job while its trusted source copy exists and the three-attempt limit has not been reached. Duplicate imports may return an already terminal existing job.

Multi-item clients create an import batch, pass its ID as the optional `batch_id` query parameter for file imports or `batch_id` JSON field for URL imports, then seal the batch after all submissions have completed. Batch history persists queued and duplicate items separately. Pausing prevents new leases and returns a running job to `pending` at its next stage boundary; resuming reuses the same job and trusted source copy. Batch list responses are bounded and newest-first. Clients that omit `batch_id` remain compatible with the single-job API.

## Phase 2.5 search context fields

Search keeps the Phase 2 `chunk_id`, `text`, `char_start`, and `char_end` fields as the precise
ranked Child match. It adds the following compatible fields:

- `matched_chunk_id`: explicit identifier of the Child used for ranking.
- `parent_id`: structural Parent Section identifier when one exists.
- `context_id`: stable Parent ID or bounded range handle used to deduplicate returned context.
- `context_text`: bounded Parent or neighboring context; clients must still cite the matched range.
- `matched_range`: page and character range for the ranked Child.
- `context_range`: page and character range represented by `context_text`.

Clients may ignore these additive fields. MCP and UI adapters should display or cite
`matched_range`, use `context_text` for answer context, and request source content by range when
more text is required. A search response never returns an entire large document by default.
