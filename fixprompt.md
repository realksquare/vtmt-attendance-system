# GEMINI_POST_IMPLEMENTATION_REVIEW_AND_FIX_PROMPT.md

Read this entire file before editing anything.

The previous anti-spoofing/classroom burst implementation has already been implemented. This task is a focused post-implementation audit and correction pass.

Do NOT rewrite the architecture from scratch.

Do NOT assume the previous implementation is correct simply because the requested features exist.

Inspect the actual current repository, verify behavior from source code, identify the issues below, fix only what is necessary, and run tests.

---

## 1. First: inspect the current implementation

Inspect at minimum:

- `burst_engine.py`
- `recognition.py`
- `attendance.py`
- `config.py`
- `liveness/quality.py`
- `liveness/tracker.py`
- `liveness/pad_engine.py`
- `liveness/challenge.py`
- `liveness/verification.py`
- existing tests
- relevant frontend/camera code

Trace the complete runtime path:

```text
camera
 -> frame acquisition
 -> quality
 -> tracking
 -> PAD
 -> recognition
 -> burst aggregation
 -> window result
 -> three-window voting
 -> attendance commit
```

Verify actual behavior rather than relying on comments or documentation.

Before changing anything, produce a concise list of:

1. current behavior
2. confirmed problems
3. files that need changes
4. tests required

Then implement.

---

# 2. Issue A: MultiFramePADAggregator consistency

The repository contains a `MultiFramePADAggregator`, but the current burst implementation appears to collect per-observation PAD scores in the tracker and calculate a median directly at finalization.

Inspect this carefully.

Determine whether:

```text
MultiFramePADAggregator
```

is actually part of the live burst-attendance path.

There must not be two competing PAD aggregation implementations with different semantics.

Choose ONE coherent design.

Preferred outcome:

- retain one authoritative multi-frame PAD aggregation mechanism
- remove/reduce dead duplicate logic where safe
- make the actual burst decision path explicit
- ensure the final PAD result is based on multiple observations
- ensure the same aggregation semantics are used consistently

Do not create another PAD aggregator.

If tracker-level median aggregation is the better implementation, it is acceptable to keep it and remove/deprecate the unused aggregator, provided this is safe and the final documentation reflects the real behavior.

If `MultiFramePADAggregator` already provides useful safeguards such as minimum sample count or confidence handling, reuse it instead.

Tests must verify the actual production path.

---

# 3. Issue B: small-but-trackable faces are still not recognized

The current three-tier quality system is useful, but inspect whether:

```text
TRACKABLE_BUT_SMALL
```

faces are only tracked and never produce recognition observations.

The desired behavior is NOT:

```text
small face -> lower recognition standards
```

The desired behavior is:

```text
small face
    |
    v
track across burst
    |
    v
collect best observations
    |
    v
when an observation becomes recognition-safe:
    run recognition
    |
    v
aggregate identity evidence
```

A track may begin as small and later contain a better frame.

Example:

```text
Frame 1 -> 24 px face -> TRACKABLE_BUT_SMALL
Frame 2 -> 27 px face -> TRACKABLE_BUT_SMALL
Frame 3 -> 43 px face -> RECOGNITION_SAFE
Frame 4 -> 39 px face -> small
Frame 5 -> 47 px face -> RECOGNITION_SAFE
```

Recognition should use Frames 3 and 5.

Do NOT force recognition on genuinely insufficient tiny crops.

Do NOT lower the recognition-safe threshold merely to make more tracks recognizable.

Do NOT use super-resolution as a substitute for missing biometric detail.

The objective is to accumulate the best real observations available during the burst.

---

# 4. Best-observation selection

Inspect the current track structure.

Ensure each track can retain the best useful observations during the burst.

At minimum consider:

- face size
- blur/sharpness
- brightness/exposure quality
- pose
- crop completeness
- PAD validity

Do not retain unlimited frames.

Use a bounded number of best observations.

For example:

```text
best_observations = top N quality-ranked observations
```

The exact N should be configurable or justified by the existing architecture.

Avoid storing raw frames permanently.

Temporary in-memory crops are acceptable when required for inference.

---

# 5. Recognition aggregation must remain identity-centric

Do NOT average face embeddings together blindly.

For each usable observation:

```text
probe embedding
    ->
compare against enrolled templates
    ->
candidate identity + similarity
```

Then aggregate candidate identities.

Use robust evidence such as:

- number of supporting observations
- support ratio
- median similarity
- top-k similarity
- consistency
- PAD support

Do not let one unusually high similarity score dominate a track if the other observations disagree.

Do not allow an identity to win purely because it appeared once.

---

# 6. Issue C: hard brightness rejection

Inspect `liveness/quality.py`.

The current implementation appears to use hard brightness limits that can classify an otherwise useful face as `UNUSABLE`.

This is too aggressive for real classrooms because lighting can vary due to:

- windows
- fluorescent lights
- projectors
- shadows
- backlighting
- classroom layout
- time of day

Do NOT remove brightness analysis.

Instead, distinguish between:

```text
catastrophic image failure
```

and:

```text
suboptimal lighting
```

A slightly dark or bright frame should generally become a lower-quality observation rather than automatically eliminating the person from the burst.

Hard rejection should be reserved for genuinely unusable conditions, such as severe clipping or near-black content.

Prefer:

```text
lighting quality score / penalty
```

over:

```text
simple brightness threshold = immediate rejection
```

where compatible with the existing quality architecture.

Do not weaken quality checks so much that poor frames enter recognition/PAD indiscriminately.

Calibrate using real classroom captures.

---

# 7. Issue D: PAD fallback must fail closed

This is a security-critical requirement.

Inspect all PAD paths, especially:

- `liveness/pad_engine.py`
- `recognition.py`
- any legacy recognition path
- any exception fallback

A failure such as:

```text
MiniFASNet unavailable
MiniFASNet inference exception
ONNX model missing
model initialization failure
invalid model output
```

must NOT silently become:

```text
live = True
```

or an equivalent successful authorization.

Do NOT return a synthetic high liveness score such as `0.85`, `100`, or equivalent merely because a heuristic fallback passed.

The system must distinguish:

```text
GENUINE
SPOOF
PAD_LOW_CONFIDENCE
PAD_ERROR
MODEL_UNAVAILABLE
```

Security rule:

```text
PAD_ERROR / MODEL_UNAVAILABLE
        ->
NO ATTENDANCE
```

If a fallback heuristic is intentionally retained, it must be explicitly classified as a separate lower-assurance mode and must not silently masquerade as equivalent to the dedicated PAD model.

For the automated attendance path, prefer fail-closed behavior.

---

# 8. Active liveness must match deployment reality

Inspect the existing active challenge system.

The physical deployment is:

```text
camera mounted in front of classroom
students remain seated
attendance is automated
```

Do not force every student to perform an interactive challenge unless the current product design explicitly supports that workflow.

Determine:

- whether active challenge is currently invoked
- whether it is bypassed
- whether it is intended only for manual verification

If active challenge is not practical for automated classroom attendance:

- preserve it for interactive/manual verification if useful
- do not pretend it is protecting the unattended burst path
- rely on passive multi-frame PAD and temporal evidence for the automated path
- document this limitation

If active challenge IS used, verify that its state machine is actually connected to the final security decision.

---

# 9. Three-window behavior

Preserve:

```text
Window A
Window B
Window C
```

and the existing 2-out-of-3 voting architecture.

Each window must produce one final aggregated result.

Do not allow individual frames to vote directly across windows.

The hierarchy must remain:

```text
frame observations
      ->
track result
      ->
window result
      ->
three-window result
      ->
attendance
```

---

# 10. PRESENT / ABSENT / UNRESOLVED

Ensure the implementation does not silently equate:

```text
not recognizable
```

with:

```text
absent
```

Use:

```text
PRESENT
ABSENT
UNRESOLVED
```

where appropriate.

Examples of `UNRESOLVED`:

- face detected but too small throughout burst
- insufficient valid observations
- persistent blur
- heavy occlusion
- conflicting identity evidence
- PAD uncertainty
- model/security component unavailable

Do not force an identity when evidence is insufficient.

Do not silently mark unresolved students absent unless the existing attendance policy explicitly requires that administrative behavior.

---

# 11. Camera-performance preservation

The previous implementation was changed to make the camera preview more responsive.

Verify that the current architecture actually preserves this.

The desired pattern is:

```text
camera acquisition
    |
    +--> responsive preview
    |
    +--> latest-frame inference sampling
             |
             +--> detection
             +--> PAD
             +--> recognition
             +--> tracking
```

Check that:

- heavy models are initialized once
- there is no model initialization inside the frame loop
- there is no unbounded frame queue
- stale frames are not processed unnecessarily
- expensive inference does not block every preview frame
- attendance/database writes are not performed for every frame

Do not introduce unnecessary threading complexity.

Profile first if performance has regressed.

---

# 12. 4K camera readiness

The final product may use a high-quality USB-UVC camera such as an IMX678-class 8MP/4K module.

Do not hard-code the architecture around:

```text
640x480
```

as the only possible camera resolution.

However, do NOT simply run every ML model on 4K frames.

Prefer:

```text
high-resolution camera input
       |
       v
efficient capture / preview
       |
       v
appropriate detection/inference resolution
       |
       v
native-quality face crops for recognition/PAD
```

Keep camera resolution configurable.

Preserve sufficient source detail for small classroom faces.

Do not regress the current performance architecture.

---

# 13. Configuration

Centralize any newly introduced parameters.

Potential configuration values include:

```text
minimum recognition-safe face size
trackable-small face range
maximum stored observations per track
minimum valid recognition observations
minimum identity support ratio
PAD threshold
minimum PAD observations
brightness severity threshold
burst duration
sampling interval
```

Do not scatter these constants throughout source files.

Do not choose arbitrary security thresholds without calibration.

---

# 14. Tests

Add/update deterministic tests for:

## PAD

- genuine multi-frame evidence passes
- spoof evidence fails
- PAD error fails closed
- model unavailable fails closed
- fallback cannot silently authorize attendance
- minimum PAD sample behavior is correct

## Small faces

- trackable-small face remains tracked
- later recognition-safe frame produces recognition
- all-small observations result in UNRESOLVED
- tiny/unusable face does not force recognition
- one poor frame does not invalidate a track

## Recognition aggregation

- one high score does not automatically win
- multiple consistent observations support an identity
- conflicting identities are handled safely
- median/support/top-k logic behaves deterministically

## Quality

- mildly poor lighting does not automatically eliminate a usable face
- severe clipping/black frames can still be rejected
- quality tiers behave as intended

## Attendance

- one window commits at most once per student
- attendance is not committed before final window aggregation
- unresolved is not silently converted to present
- unresolved is not silently converted to absent unless explicitly configured

## Three-window voting

Verify existing 2-out-of-3 behavior remains correct.

---

# 15. Real-world validation

After implementation, test with the actual camera environment where possible.

Minimum categories:

### Genuine

- front row
- middle row
- back row
- classroom lighting
- mild pose changes
- different distances

### Spoof

- phone photo
- printed photo
- screen photo
- replay video

### Edge cases

- small face
- partial occlusion
- motion blur
- multiple faces
- backlight
- projector light
- window light

Record actual results.

Do not claim a spoof type is blocked unless tested.

---

# 16. Do not overfit to tests

Do not implement special-case logic solely to satisfy a unit test.

Tests must reflect the intended architecture.

Do not:

- hard-code student IDs
- hard-code expected similarity values
- add artificial delays
- bypass security for test fixtures
- add fake PAD success values
- weaken thresholds solely to make fixtures pass

---

# 17. Final security model

The final automated attendance authorization must conceptually require:

```python
authorized = (
    identity_confident
    and sufficient_observations
    and quality_requirements_satisfied
    and pad_passed
    and security_components_available
)
```

Adapt this to the actual implementation.

The following must NEVER authorize attendance:

```text
PAD_ERROR
MODEL_UNAVAILABLE
insufficient biometric evidence
unknown identity
multiple-face ambiguity
unresolved track
```

Recognition confidence cannot override a failed security gate.

---

# 18. Implementation constraints

Do not:

- rewrite the entire project
- replace InsightFace without reason
- replace MiniFASNet without reason
- create a second tracker
- create a second PAD system
- remove security checks merely because they cause false rejects
- lower recognition thresholds blindly
- introduce cloud APIs
- introduce internet dependencies
- store raw classroom video permanently

Reuse the existing architecture.

---

# 19. Completion report

After implementation, provide:

## Changed files

Every modified/created file and why.

## Confirmed issues

Which of the requested issues were actually present.

## Fixes

Explain each fix.

## PAD

State:

- model
- preprocessing
- aggregation
- threshold
- failure behavior
- fallback behavior

## Small faces

State:

- recognition-safe range
- trackable-small behavior
- best-observation behavior
- unresolved behavior

## Quality

State:

- old lighting behavior
- new lighting behavior
- calibration/justification

## Performance

State:

- preview responsiveness
- inference latency
- burst duration
- any CPU/GPU measurements available

## Tests

List commands and results.

## Known limitations

Be explicit.

Do not claim a problem is solved unless the implementation and tests demonstrate it.

---

# 20. Final acceptance checklist

```text
[ ] Current implementation inspected
[ ] Production PAD path identified
[ ] Duplicate PAD aggregation resolved
[ ] Multi-frame PAD verified
[ ] PAD failures fail closed
[ ] Legacy PAD fallbacks cannot silently authorize attendance
[ ] Trackable-small faces can accumulate evidence
[ ] Later recognition-safe observations can recognize a track
[ ] Best observations are bounded and retained
[ ] Recognition remains identity-centric
[ ] One high similarity cannot dominate incorrectly
[ ] Lighting is not unnecessarily a hard rejection
[ ] Severe image failure is still rejected
[ ] PRESENT / ABSENT / UNRESOLVED behavior is correct
[ ] Three-window architecture preserved
[ ] 2-out-of-3 voting preserved
[ ] Attendance committed only after window aggregation
[ ] Attendance committed once per student/window
[ ] Camera preview remains responsive
[ ] Heavy models initialized once
[ ] No unbounded frame queue
[ ] Camera resolution remains configurable
[ ] 4K-capable camera path remains practical
[ ] Tests added/updated
[ ] Tests pass
[ ] Real-world validation performed where possible
[ ] Final diff reviewed
[ ] No unrelated code changed
```

# Core requirement

The system must never manufacture certainty.

It must distinguish:

```text
I know who this is.
I know this is live/genuine.
I have enough evidence to make that decision.
```

Only when all required security conditions are satisfied may automated attendance be recorded.
