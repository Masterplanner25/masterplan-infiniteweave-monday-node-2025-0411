# Implementation Docs — Utility Parity Audit

---

## 1. Scope

Source folder: `AINDY/Implementation docs`

Documents audited:
- `Authorship_Holythosis_Idea_Scoring_System.docx`
- `dedicated word count function.docx`

This is a **utility audit**, not a system layer.

---

## 2. Doc → Code Parity Table

| Documented Capability | Implementation Reality | Status | Primary Files |
| --- | --- | --- | --- |
| Epistemic scoring (1–100) | Not implemented | Missing | N/A |
| YAML insight encoding | Not implemented | Missing | N/A |
| Scribalicious refinement pipeline | Not implemented | Missing | N/A |
| Center-of-gravity tagging | Not implemented | Missing | N/A |
| Authorship watermarking | Implemented | Implemented | `apps/authorship/services/authorship.py`, `apps/authorship/services/authorship_services.py`, `routes/authorship_router.py` |
| Dedicated word-limit generator | Not implemented | Missing | N/A |
| Word count utility (basic) | Implemented only in SEO routes | Partial | `routes/seo_routes.py`, `apps/search/services/seo_services.py` |

---

## 3. Gap → File Mapping

| Gap | Impact | Files to Update |
| --- | --- | --- |
| No epistemic scoring or insight encoding | Doc-only utility; no runtime integration | N/A |
| No word-limit enforcement utility | Doc-only utility; no runtime integration | N/A |
| Authorship vs scoring conflation | Conceptual mismatch | `Authorship_Holythosis_Idea_Scoring_System.docx` |

---

## 4. Risk Register

| Risk | Type | Failure Mode | Impact | Likely? |
| --- | --- | --- | --- | --- |
| Scoring system assumed to exist | Docs drift | Users assume epistemic scoring is live | High expectation gap | High |
| Word-limit generator assumed to exist | Docs drift | No utility in runtime | Medium | Medium |
| Authorship watermarking mistaken for scoring | Conceptual | Wrong system boundary | Medium | Medium |

---

## 5. Summary (Operational Truth)

Only **authorship watermarking** is implemented.  
Epistemic scoring, YAML insight encoding, and a dedicated word-limit generator
exist only in documentation and are not wired into the runtime.
