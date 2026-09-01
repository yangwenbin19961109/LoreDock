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

The Phase 2 upload endpoint completes indexing before returning. Job state is persisted throughout
the operation, interrupted jobs are recovered as failed at startup, and the same use case can move
to a background worker without changing its HTTP result contracts.

Supported uploads are Markdown, TXT, PDF and DOCX, with a 100 MiB per-file limit. A repeated content
hash within the same library returns the existing source and job with `duplicate: true`.
