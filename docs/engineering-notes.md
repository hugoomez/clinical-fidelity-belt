# Engineering notes

Problems that were hit during development and how they were resolved. These are
recorded because several of them are findings in their own right, and because
two of them changed the design.

## 1. Two APIs, two incompatible authentication schemes

Neither service offers a standard login endpoint, and they authenticate in
entirely different ways.

**Recog** takes a plain API key in an `X-API-Key` header — no token exchange.

**Idonia** requires a self-signed JWT: the client signs an HS256 token with the
API secret and puts the API key in a claim. The secret needs preprocessing that
is not documented anywhere — strip the `S2` prefix, then base64url-decode the
remainder — which had to be recovered by reading the staging Swagger and
reproducing the signature scheme by hand.

Both are encapsulated in their respective live clients, so the rest of the
pipeline never sees a transport detail. `_signing_key` and `_generate_jwt` are
kept as separate one-purpose functions specifically because the exact expected
shape of the key claim was never confirmed: adapting to a different scheme means
changing one function.

## 2. Recog's output quality depends on receiving the whole report

Validating against production surfaced a hard constraint. Sending Recog an
excerpt or a pre-summarised fragment of the report **directly degrades its
output**: with an excerpt centred on the ACL, Recog omitted the other five
findings entirely. With the complete report (3,541 characters) it preserved all
six principal findings.

This was encoded as a pipeline constraint rather than left as folklore:
`HumanizeReport` receives the original text untruncated, and any preprocessing
that would shorten the report before the Recog call is prohibited by design. The
constraint is documented on the `RecogClient` protocol itself, where anyone
implementing a new backend will see it.

## 3. The validator penalised correct reports

The most methodologically valuable finding of the project: the lexical belt
flagged a humanised report that was clinically faithful. Distinguishing the two
causes was what made it actionable rather than merely frustrating.

**Miscalibrated patterns — real bugs.** The MCL attenuation pattern fired on
*"...without complete tear"*, a faithful negation rather than an attenuation. A
negative lookbehind fixed it, so the pattern only triggers when the lesion is
actually described as milder than it is.

**Inherent limits of lexical matching — not bugs.** Comparing strings will never
recognise that *"injury from a blow to the bones"* is equivalent to *"bone
marrow oedema in a pivot-shift pattern"*. More regex does not fix this. It has to
be delegated to a semantic backend.

The dual-backend architecture had been designed in anticipation of exactly this
ceiling. Hitting it is empirical justification for the design rather than a
defect in it. Full numbers in [results.md](results.md) §3.

## 4. NER is not concept normalisation

Switching layer 2 to a transformer NER was expected to solve the synonym
problem. Recall **fell from 56 % to 8.6 %**.

The cause: a NER model extracts literal spans from the document, and those spans
rarely coincide with how a humanised report words the same concept. The model was
doing its job correctly; the job was the wrong one. What the layer actually needs
is **normalisation to canonical concepts**, which is entity linking (SNOMED-CT,
UMLS), not recognition.

Given the time available, the pragmatic answer was a hand-curated
technical↔lay dictionary, which raised recall from 56 % to 64 % at zero
implementation cost. The humble solution beat the sophisticated one because it
was solving the right problem. Proper entity linking with ClinLinker-ES is listed
as future work.

This is the clearest negative result in the project and it is kept prominent for
that reason.

## 5. Silent truncation of the LLM judge by reasoning tokens

On integrating the judge (Gemini 2.5 Flash), responses came back truncated after
the first finding. The model was spending its output token budget on internal
reasoning before emitting the JSON, leaving roughly 68 tokens for the actual
answer.

The fix has three parts: disable reasoning with `thinking_budget=0`, raise
`max_output_tokens` to 8192, and force `response_mime_type=application/json`,
plus robust delimiter-based extraction of the array. The failure mode is worth
recording because it is silent — the response is valid JSON, just incomplete, so
nothing raises.

## 6. Console output portability

The belt summary uses status glyphs (`✓`, `△`, `✗`) to make a verdict readable at
a glance. On consoles whose default code page is not UTF-8 — Windows cp1252, for
instance — this aborted the demo outright.

`sys.stdout.reconfigure(encoding="utf-8")` at the entry point fixes it, guarded
by a `hasattr` check for interpreters that do not expose it. Applied in the demo
and in every evaluation script.

## 7. Response shape instability on Idonia uploads

Idonia's `/files` upload endpoints were observed returning three different shapes
for the same operation: a bare UUID string, a single-element list (containing
either strings or objects), and a full object.

Rather than guess at one, `IdoniaLiveClient._normalize_file_response` accepts all
three and logs which one it received, so an unexpected shape shows up in the
trace instead of surfacing later as a `KeyError`. The normalisation is shared by
`upload_study` and `upload_report`.

A related known limitation: the API host and the patient-facing viewer host are
separate deployments and Idonia exposes no mapping between them, so the viewer
URL is derived by string substitution on the hostname. Correct for the staging
host this was built against, and fragile for any other.

## 8. Optional dependencies must stay lazily imported

`PyJWT` (Idonia live) and `PyMuPDF` (Recog live) ship in the optional `live`
extra. Both are imported inside the functions that use them rather than at module
scope. This is deliberate and easy to "clean up" by mistake: hoisting `import
jwt` to the top of `clients/idonia.py` would make the entire `clients` package
unimportable for anyone who installed only the base dependencies, which would
break the offline test suite and the demo for every user who followed the
standard install instructions.

`PyMuPDF` goes further and degrades gracefully: `_extract_text_from_pdf` catches
`ImportError`, warns, and returns empty text.
