# v0.27 reports

Files in this directory record implementation evidence. They are not the
current requirements for v0.27.0.

- [`260829-high-payload-routed-multi-inbox-webhooks.md`](./260829-high-payload-routed-multi-inbox-webhooks.md)
  is the PRD that drove the first payload-routing candidate.
- [`260829-implementation-report-payload-routed-multi-inbox-webhooks.md`](./260829-implementation-report-payload-routed-multi-inbox-webhooks.md)
  describes that candidate and the checks run at the time.

The candidate established useful routing and isolation behavior, but the later
grilling session replaced several contracts. Use [`../plan.md`](../plan.md) and
the PRDs under [`../wappa/`](../wappa/) and [`../symphonai/`](../symphonai/) for
current requirements.

- [`260830-release-report-v0.27.0-multi-inbox-hardening.md`](./260830-release-report-v0.27.0-multi-inbox-hardening.md)
  records the finished PRD series: verification results, artifact hashes, the
  test groups, known limits, and the operator-gated actions still pending
  (tag, PyPI publication, callback cutover).

Add the Symphonai adoption evidence and the PyPI verification result here
before the feature series is deleted. Git history becomes the archive after
deletion.
