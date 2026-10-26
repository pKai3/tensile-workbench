# External audit correspondence - 26 October 2026

The documents below preserve the audit exchange in chronological order. They are historical review records, not a statement that the proposed remediations have been implemented. Findings and verification claims apply to the revisions and environments stated in each document.

| Order | Document | Context |
| --- | --- | --- |
| 01 | [Original audit request (PDF)](01-audit-request.pdf) · [Markdown source](01-audit-request.md) | Original scope and instructions supplied for the external audit. The PDF preserves the source wording; historical terminology has not been updated. |
| 02 | [Claude's independent audit](02-claude-audit-report.pdf) | Findings C1-C10, additional concerns, verification results and a proposed remediation order. Audited commit `fdcb232`. |
| 03 | [Codex's response](03-codex-audit-response.pdf) | Accepted findings, proposed fixes, qualifications, rebuttals and independent checks against local commit `4bd8b8a`. |
| 04 | [Claude's follow-up reply](04-claude-audit-reply.pdf) | Further reported C3 experiments, clarification of evidence levels, withdrawal of the pointwise-SD concern, confirmation of the time-header issue, and responses to the qualified remedies. The reply states that `4bd8b8a` was not available in the public repository at the time. |

## Outstanding reproduction materials

The follow-up reply refers to `tensile_audit_repro.zip`, including generators, seeds and reference outputs. That archive was not supplied with these documents and is not included here. The expanded results reported in the reply have not been independently rerun as part of filing this correspondence.

## Preservation

- The received audit and reply, and the previously prepared response, are unchanged PDF copies with chronological filenames.
- The original request is retained as Markdown alongside its PDF rendering.
- The originals outside this repository were retained.
- Only these four documentation PDFs are exempted from the repository's PDF ignore rule. Research data, generated research outputs and personal settings remain ignored.
- Adding this correspondence changes no application code and does not implement any remediation.
