# Gate options: the four items between here and `/api/diagnose`

**Date:** 2026-10-30
**Status:** decision document. Nothing here is implemented until you pick.
**Why this file exists:** `scripts/definition_of_done.sh` reports four
unsatisfied gates, and `/api/diagnose` returns **503** because of them. Rather
than leave that as a permanent wall, this document lays out, for each gate, the
options you actually have, what each costs, and what each unblocks.

**The rule that does not change under any option:** no performance or fairness
number is published that is not backed by a frozen `model_manifest.json` and an
evaluation report. "Not yet measured" stays "not yet measured". The
research/educational-only, not-a-medical-device disclaimer stays on every
artefact.

---

## Gate 1 -- S1-1: a verifiable, frozen model artefact

`model_manifest.json` says `status: placeholder`; no checkpoint exists in the
repository, so the serving path refuses to diagnose rather than invent output.

| Option | What it means | Cost | Unblocks | Risk |
| --- | --- | --- | --- | --- |
| **A. Train + freeze in-house** (recommended) | Train the 3-class head on HAM10000 (public, CC BY-NC 4.0), freeze with `scripts/freeze_model.py`, record SHA-256 in the manifest, write the model card from the real run | **Compute:** a few GPU-hours, or ~6-12 h CPU at reduced epochs. **Effort:** 1-2 days including hygiene + evaluation | `/api/diagnose` with a real model; every metric can finally be measured; poster/paper numbers become legitimate | Longest path; HAM10000 alone is light-skinned, so fairness claims still need DDI/SCIN |
| **B. Adopt a published third-party checkpoint** | Take an existing HAM10000-trained public checkpoint, verify licence + provenance, hash it, re-run evaluation yourself | **Effort:** ~1 day (licence check, hash, eval). **Compute:** 1-2 h | Same as A, faster | Provenance of the weights may be unverifiable; licence may forbid redistribution; you inherit someone else's split, so you must re-evaluate on your own hold-out before quoting anything |
| **C. Ship no weights, keep 503** | Status quo | 0 | Nothing -- but the API stays honest | The demo cannot demonstrate diagnosis; every result stays "not yet measured" |

**Rejected, do not propose:** loading an ImageNet backbone with an untrained head
behind `/api/diagnose`. It would produce plausible-looking output with no
validity, which is exactly the failure the gate exists to prevent.

**Recommendation:** A. It is the only option that makes *your* numbers yours.

---

## Gate 2 -- S2-4: the go-live runbook signature

The runbook itself is written and passes its tests
(`tests/test_s2_4_operations_runbook.py`); the checklist line at the end is
unsigned.

| Option | What it means | Cost | Unblocks | Risk |
| --- | --- | --- | --- | --- |
| **A. Self-sign with an explicit scope statement** (recommended) | You sign and date, and the signature reads "single-engineer review; no independent audit" | 10 minutes | Gate closes as a document; the limitation is on the record | Nobody independent has looked at it -- but that is stated, not hidden |
| **B. Independent review + signature** | A supervisor, clinician or colleague reads the runbook and signs | 1-2 weeks calendar, ~1 h of their time | Stronger artefact; useful for a report appendix | Depends on someone else's availability -- the same dependency that stalled PASSION |
| **C. Leave unsigned** | Status quo | 0 | Nothing | `definition_of_done.sh` keeps reporting it as "met (document), unsigned" |

**Recommendation:** A now, B if this document will be examined externally.

---

## Gate 3 -- Written retention and backup policy

`SECURITY.md` §4 carries the policy as **"Draft -- not yet in force"**. The
mechanisms behind it are already tested: `scripts/purge_records.py`,
`scripts/backup_db.py`, and a verified backup/restore drill in the gate script.

| Option | What it means | Cost | Unblocks | Risk |
| --- | --- | --- | --- | --- |
| **A. Adopt it as project owner, with a review date** (recommended) | Change "Draft" to "In force from <date>, reviewed every 90 days"; you are the data controller for this prototype | 30 minutes | Retention becomes enforceable and auditable; the storage limitation stops being aspirational | You are accountable for it -- acceptable while data is synthetic/de-identified |
| **B. Institutional approval** | Data-protection officer or supervisor approves | 2-6 weeks | Stronger for real data; required before real patient data anyway | Blocks progress on an item that does not need to block public-data work |
| **C. Keep the draft** | Status quo | 0 | Nothing | The purge job has no policy to justify it |

**Recommendation:** A now; B is subsumed into Gate 4 if you ever handle real
patient data.

---

## Gate 4 -- IRB / ethics sign-off

This is the only gate that is genuinely outside the code, and the only one where
the right answer depends on a fact you already know: **what data will you use?**

| Option | What it means | Cost | Unblocks | Risk |
| --- | --- | --- | --- | --- |
| **A. Exemption / "not human-subjects research" determination** (recommended for the current scope) | Written determination from your institutional review board that work on public, de-identified datasets is exempt | 1-3 weeks, usually no fee | Public-data training, evaluation and publication; the gate becomes "exemption on file" instead of "not met" | It does **not** cover real patient images, prospective collection, or deployment |
| **B. Full ethics approval** | Standard application to the institutional REC / national council | 4-12 weeks, possible fee, protocol + consent forms | Real patient images, Ugandan cohorts, clinical partnership | Slowest; also drags in data-protection registration |
| **C. Partner under an existing approval** | Join a collaborator's approved protocol as a named investigator | 2-6 weeks, involves negotiation | Real data without running your own application | Depends entirely on a partner -- the exact risk that stalled PASSION |
| **D. Defer; declare the scope limitation** | Status quo, stated loudly in README + model card | 0 | Nothing new, but nothing is misrepresented | Any hint of clinical use must stay forbidden |

**Recommendation:** **A**, with **B** started only if/when real patient data
becomes the plan. Doing A costs little and turns an open-ended "not met" into a
bounded answer.

---

## What the combinations buy

| Combination | Can do | Cannot do |
| --- | --- | --- |
| 1C + 2C + 3C + 4D (today) | Public-data research write-up, honest 503 API, dashboard demo with no diagnosis | Serve a diagnosis; state any accuracy; touch patient data |
| **1A + 2A + 3A + 4A** (recommended minimum) | Serve `/api/diagnose` from a frozen, hash-verified checkpoint; publish measured numbers with a stated scope; demonstrate the full pipeline | Accept real patient images; claim clinical validity |
| 1A + 2B + 3B + 4B (full) | Above, plus real de-identified patient images under an approved protocol | Still not a medical device -- regulatory clearance is a separate track that this project does not pursue |

Estimated total effort for the recommended minimum: **2-4 days of work plus
1-3 weeks of waiting** (the waiting is Gate 4, and it overlaps with Gate 1
compute).

---

## Decision needed from you

1. Gate 1: **A / B / C**? (A is recommended; B needs a checkpoint you trust.)
2. Gate 2: **A / B / C**?
3. Gate 3: **A / B / C**?
4. Gate 4: **A / B / C / D**?

Reply with any combination (e.g. `1A 2A 3A 4A`) and the work will be done
test-first, with `scripts/definition_of_done.sh` re-run afterwards. Until then,
the four items stay listed as unmet in `REMEDIATION_STATUS.md` -- which is the
correct state, not an oversight.
