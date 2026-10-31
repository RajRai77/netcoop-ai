# Evidence integrity (always applicable)

- Model immutable raw observations separately from normalized records, agent findings and diagnoses. Revisions supersede; never rewrite past findings silently.
- Every finding requires observation references; every diagnosis requires snapshot IDs, hypotheses and supporting evidence.
- Units are required; canonicalization only via documented registry. For `packet_loss = 0.02` do not assume whether ratio or percent unless source schema specifies it. Preserve original value/unit.
- Treat stale, unavailable and invalid measurements distinctly. Missing data cannot be evidence of normality.
- Two agents reading the same source counter do not create two independent observations.
- Treat a rule's score as **support** until calibrated against held-out data; do not display as a probability.
- Never tune ground-truth fixture labels to fit an incorrect implementation.
