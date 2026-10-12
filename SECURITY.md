# Security / 보안

This SDK only serializes explicitly selected values/files and transmits them after an explicit publish/sync call. It does not crawl directories or run research code. Source snapshots are opt-in; review selected code for secrets before publication. The platform evaluates current project access separately.

SDK 0.3.0 candidate discovery stays local and uses a bounded plain namespace and recognized object types. It never sends the whole namespace. Review contents even when names pass the sensitive-name filter. Notebook Send requires a frozen preview; explicit publish calls and doubly opted-in saved rules may send directly. Automatic rules authorize one send per invocation, not retries or unbounded scheduling. Capture only wraps matplotlib show/close inside an explicit scope and restores hooks; raw warning messages and exception bodies are excluded.

Browser connection sends a random challenge, displays an approval code and keeps the resulting scoped key in memory. Approve only the expected project/code; clear local state with `repro.clear()` and revoke server access in platform settings. No local listener or persistent credential file is created. Ordinary notebook execution is not proof of a saved provider cell identity; explicit source helpers remain necessary for exact source navigation.

연결 키는 환경 변수 또는 숨김 입력으로 전달하고 소스·노트북 출력·CLI 인수·URL·공개 이슈에 넣지 마세요. outbox와 JSON에는 선택한 연구 원문이 포함될 수 있습니다. 로컬 결과는 비공개로 보호하고 Git에 추가하지 마세요. 토큰 폐기는 플랫폼에서 수행합니다.

Use HTTPS endpoints; only explicit loopback development endpoints may use HTTP. Redirects are rejected. Keep project tokens out of logs and URLs. A successful receipt confirms storage, not independent reproduction or scientific correctness. Private results do not become public because this SDK is public.

Do not post exploitable details, credentials, private bundles or research source in public issues. Use GitHub's private vulnerability reporting only when enabled for this repository, or an already verified private maintainer contact. If neither exists, open a non-sensitive request for a private reporting channel without disclosing the vulnerability. No reporting channel is assumed to be configured by this file.

Release reviewers must run the explicit public-file audit, clean notebook checks, SDK tests, deterministic rebuild and clean artifact installs. Never publish `.build`, outbox, real project identifiers, credentials, original research data or platform history. Referenced external datasets/notebooks/models retain their own licenses.
