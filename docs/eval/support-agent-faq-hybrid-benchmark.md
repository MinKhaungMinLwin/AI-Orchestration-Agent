# Support Agent FAQ Hybrid Search Benchmark

## Summary

This benchmark compares the legacy FAQ retrieval flow against the new hybrid FAQ search flow for the T-Station support agent.

The support-only benchmark shows that hybrid search preserves answer quality while reducing both latency and token usage.

## Quality Result

| Metric | Value |
| --- | ---: |
| Total queries | 17 |
| Match | 17 |
| Mismatch | 0 |
| Error | 0 |
| Match rate | 100.00% |

The LLM-as-judge evaluation found no meaningful answer-quality regression. All hybrid answers were judged semantically equivalent to the legacy answers.

## Latency Result

| Metric | Legacy | Hybrid | Delta | Delta % |
| --- | ---: | ---: | ---: | ---: |
| Average | 14,061 ms | 9,312 ms | -4,749 ms | -33.77% |
| P50 | 9,417 ms | 9,209 ms | -208 ms | -2.21% |
| P95 | 25,775 ms | 15,923 ms | -9,852 ms | -38.22% |
| P99 | 27,892 ms | 20,389 ms | -7,503 ms | -26.90% |
| Min | 4,787 ms | 4,905 ms | +118 ms | +2.47% |
| Max | 28,421 ms | 21,505 ms | -6,916 ms | -24.33% |

Hybrid search improves average latency by about 34%. 

## Token Usage: Support Agent Only

These numbers include only LLM generations under `agent:support`.

| Metric | Legacy | Hybrid | Delta | Delta % |
| --- | ---: | ---: | ---: | ---: |
| Input tokens | 220,078 | 156,269 | -63,809 | -28.99% |
| Output tokens | 1,101 | 932 | -170 | -15.40% |
| Total tokens | 221,179 | 157,200 | -63,978 | -28.93% |

Hybrid search reduces support-agent total token usage by about 29%. Most of the reduction comes from input tokens, which indicates that the hybrid retrieval context is more compact.

## Token Usage: Full Trace

These numbers include the full trace, including router, classifier, and support-agent LLM calls.

| Metric | Legacy | Hybrid | Delta | Delta % |
| --- | ---: | ---: | ---: | ---: |
| Input tokens | 226,024 | 162,215 | -63,809 | -28.23% |
| Output tokens | 1,209 | 1,032 | -177 | -14.64% |
| Total tokens | 227,233 | 163,247 | -63,986 | -28.16% |

Full-trace token usage follows the same trend as support-agent-only usage because every benchmark query routed through the support agent.

## Conclusion

On the support-agent-only benchmark, hybrid FAQ search is better than the legacy FAQ retrieval flow:

- Answer quality remained equivalent: `100% MATCH`.
- Average latency improved by `33.77%`.
- Tail latency improved: `P95 -38.22%`, `P99 -26.90%`.
- Support-agent total token usage decreased by `28.93%`.
- Full-trace total token usage decreased by `28.16%`.

The result supports adopting hybrid FAQ search for support-agent FAQ handling. It keeps answer behavior stable while making the flow faster and less token-heavy.