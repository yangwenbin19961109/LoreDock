# Long procedure context fixture

## Safe reindex procedure

Step alpha creates a sidecar index named rebuild-alpha and leaves the active index readable while source identifiers and raw files remain unchanged.

Step beta validates the sidecar manifest, embedding dimensions, normalization rule, chunking contract, and citation ranges before any visible switch occurs.

Step gamma records marker gamma-archive and keeps the former active index available when validation reports a missing raw source copy.

Step delta obtains a consistent SQLite backup through the backup API, rather than copying a live database main file without its WAL state.

Step epsilon checks every source hash against trusted raw bytes and records marker epsilon-hash when the hash is unchanged.

Step zeta rebuilds Parent and Child records in one temporary index and verifies that each Child range belongs to its original source text.

Step eta waits for all vector writes to finish before publishing the temporary index, so readers never observe mixed dimensions.

Step theta publishes only after the new index returns stable citations for marker theta-citation and its surrounding source context.

Step iota preserves the previous index when disk space is insufficient and reports the exact remaining capacity required for a retry.

Step kappa removes sidecar files only after the atomic replacement completes, preserving the old index if replacement cannot finish.

Step lambda confirms that BM25-only search remains available when the embedding provider is missing or its verification fails.

Step mu writes marker mu-audit after the completed rebuild, but does not log complete document text or unredacted user queries.

Step nu verifies the database with PRAGMA integrity_check before declaring marker nu-integrity successful.

Step xi restarts interrupted jobs from their durable state and never creates an empty index merely because the trusted raw copy is absent.

Step omicron holds the index writer lock through manifest publication, which prevents a concurrent reader from treating a partially initialized index as incompatible.

Step pi exposes the successful result only after the new source version and all citation metadata are committed together.
