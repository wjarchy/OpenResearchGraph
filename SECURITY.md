# Security Policy

Do not include secrets in a public issue. Report a suspected vulnerability privately to the repository owner through GitHub's security advisory feature.

Before deployment:

- use a read-only database identity for analytical queries;
- keep the API behind authentication and rate limiting;
- set explicit CORS origins;
- isolate model and search credentials in a secret manager;
- treat model output and retrieved documents as untrusted input.
- place Python execution in a network-disabled container or microVM for untrusted tenants;
- keep PostgreSQL and Milvus credentials in a secret manager, never in checkpoints.
