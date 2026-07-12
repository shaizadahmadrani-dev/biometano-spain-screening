# Security

## Joblib model artifact

`models/benchmark_classifiers_mediterranean_proxy_v4.joblib` uses Python pickle-based
serialization. Loading a malicious or modified artifact can execute arbitrary code.

- Only load the file from this repository or another trusted source.
- Verify its SHA-256 before use.
- Do not accept replacement model files from untrusted users.

The expected SHA-256 is recorded in `MODEL_SHA256.txt`.

## Reporting

Report security issues privately to the repository owner through GitHub rather than
opening a public issue containing exploit details.

