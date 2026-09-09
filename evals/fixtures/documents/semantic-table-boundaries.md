# Retention matrix for bounded table retrieval

This fixture checks that a table heading, its column names, and a distant row remain available as one bounded Parent context. The values are synthetic and contain no user data.

## Service retention matrix

| Service | Record class | Retention | Deletion action | Audit marker |
|---|---|---:|---|---|
| ledger-01 | invoice event | 31 days | purge source and index | audit-01 |
| ledger-02 | invoice event | 32 days | purge source and index | audit-02 |
| ledger-03 | invoice event | 33 days | purge source and index | audit-03 |
| ledger-04 | invoice event | 34 days | purge source and index | audit-04 |
| ledger-05 | invoice event | 35 days | purge source and index | audit-05 |
| ledger-06 | invoice event | 36 days | purge source and index | audit-06 |
| ledger-07 | invoice event | 37 days | purge source and index | audit-07 |
| ledger-08 | invoice event | 38 days | purge source and index | audit-08 |
| ledger-09 | invoice event | 39 days | purge source and index | audit-09 |
| ledger-10 | invoice event | 40 days | purge source and index | audit-10 |
| ledger-11 | invoice event | 41 days | purge source and index | audit-11 |
| ledger-12 | invoice event | 42 days | purge source and index | audit-12 |
| ledger-13 | invoice event | 43 days | purge source and index | audit-13 |
| ledger-14 | invoice event | 44 days | purge source and index | audit-14 |
| ledger-15 | invoice event | 45 days | purge source and index | audit-15 |
| ledger-16 | invoice event | 46 days | purge source and index | audit-16 |
| ledger-17 | invoice event | 47 days | purge source and index | audit-17 |
| ledger-18 | invoice event | 48 days | purge source and index | audit-18 |
| ledger-19 | invoice event | 49 days | purge source and index | audit-19 |
| ledger-20 | invoice event | 50 days | purge source and index | audit-20 |
| ledger-21 | invoice event | 51 days | purge source and index | audit-21 |
| ledger-22 | invoice event | 52 days | purge source and index | audit-22 |
| ledger-23 | invoice event | 53 days | purge source and index | audit-23 |
| ledger-24 | invoice event | 54 days | purge source and index | audit-24 |
| ledger-25 | invoice event | 55 days | purge source and index | audit-25 |
| ledger-26 | invoice event | 56 days | purge source and index | audit-26 |
| ledger-27 | invoice event | 57 days | purge source and index | audit-27 |
| ledger-28 | invoice event | 58 days | purge source and index | audit-28 |
| ledger-29 | invoice event | 59 days | purge source and index | audit-29 |
| ledger-30 | invoice event | 60 days | purge source and index | audit-30 |
| ledger-31 | invoice event | 61 days | purge source and index | audit-31 |
| ledger-32 | invoice event | 62 days | purge source and index | audit-32 |
| ledger-33 | invoice event | 63 days | purge source and index | audit-33 |
| ledger-34 | invoice event | 64 days | purge source and index | audit-34 |
| ledger-35 | invoice event | 65 days | purge source and index | audit-35 |
| ledger-36 | invoice event | 66 days | purge source and index | audit-36 |
| ledger-37 | invoice event | 67 days | purge source and index | audit-37 |
| ledger-38 | invoice event | 68 days | purge source and index | audit-38 |
| ledger-39 | invoice event | 69 days | purge source and index | audit-39 |
| ledger-40 | invoice event | 70 days | purge source and index | audit-40 |

The retention column is measured in calendar days. Every deletion action removes the trusted source copy and derived index rows together.
