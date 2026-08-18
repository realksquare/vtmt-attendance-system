# GEMINI_CLASSROOM_ATTENDANCE_IMPLEMENTATION_PROMPT.md

Read `ANTI_SPOOFING_IMPLEMENTATION_SPEC.md` completely before modifying anything.

Also inspect the screenshot attached to this prompt. It shows the current Admin Panel while triggering a burst capture. The camera/capture window opens, but the capture process is noticeably laggy.

Do not start coding immediately.

First inspect the actual repository and understand the existing implementation. Then produce a concise implementation plan based on the real codebase. Only after that should you implement the changes.

## 1. Current project context

This is an offline smart attendance system using a three-window/burst-based classroom attendance architecture.

The camera will eventually be physically mounted at the front of a classroom and must capture students across the entire room.

The current system already contains components related to:

- three-window attendance
- burst capture
- OpenCV
- InsightFace / `buffalo_l`
- face recognition
- PAD / anti-spoofing
- MiniFASNet ONNX models
- multi-frame PAD aggregation
- active liveness/challenge logic
- 2-out-of-3 window voting
- encrypted biometric storage
- SQLite/database attendance persistence

Do not create duplicate implementations if suitable existing infrastructure already exists.

Inspect the actual repository to determine the exact current behavior.

## 2. First task: repository inspection

Before modifying code, inspect at minimum:

- `burst_engine.py`
- `recognition.py`
- `attendance.py`
- `config.py`
- `app.py`
- `staff_app.py`
- `test_system.py`
- `liveness/`
- `models/`
- relevant frontend files
- dependency files
- database/storage modules
- existing camera/capture utilities
- existing three-window scheduler/voting logic

Also inspect repository-level instructions such as `AGENTS.md`, `.github/*-instructions.md`, README/project documentation, and test/build/run configuration.

Determine:

1. Where the camera is initialized.
2. Where camera frames are captured.
3. Where the capture preview is rendered.
4. Where InsightFace is initialized.
5. Where PAD is initialized.
6. Where liveness/challenge logic is initialized.
7. Where individual frames are currently recognized.
8. Where `record_window_attendance()` or its equivalent is called.
9. Whether attendance can currently be committed from a single frame.
10. How Window A, Window B and Window C communicate their results.
11. How the existing 2-out-of-3 voting works.
12. Why the current capture window becomes laggy.
13. Why the existing quality thresholds reject classroom faces too aggressively.
14. Why the existing multi-frame PAD infrastructure is or is not controlling the final attendance decision.

Do not assume the README is completely accurate. Verify behavior from source code.

## 3. Required implementation philosophy

Do not rewrite the project.

Do not replace working components without a technical reason.

Do not create a second face-recognition pipeline.

Do not create a second PAD pipeline if the existing one can be improved/reused.

Do not modify unrelated modules.

Prefer the smallest coherent architectural change that solves the problems below.

Before changing a threshold, algorithm or security behavior, understand how the existing implementation currently works.

## 4. Problem A: capture window is too laggy

The screenshot shows that the capture window opens, but the camera/preview becomes noticeably laggy.

Investigate the actual bottleneck.

Determine whether the current camera loop is doing expensive operations such as InsightFace inference, PAD inference, face detection, image preprocessing, database access, UI rendering, or other blocking synchronous work inside the same loop responsible for camera display.

Do not simply lower resolution/FPS as the primary solution.

Prefer an architecture similar to:

```text
Camera acquisition
       |
       v
Latest-frame buffer
       |
       +----> responsive preview
       |
       v
Controlled inference sampling
       |
       +----> face detection
       +----> PAD
       +----> landmarks/liveness
       +----> recognition
       |
       v
Burst-level aggregation
```

The preview should remain responsive while expensive inference happens at a controlled rate.

Avoid unbounded frame queues.

Prefer processing the newest useful frame rather than building up stale frames.

Do not initialize models inside the frame loop.

InsightFace, PAD and landmark models should be initialized once and reused.

Measure inference/capture latency before and after the change.

Report the actual bottleneck discovered.

## 5. Problem B: quality constraints are too restrictive

The current system has quality checks involving face size, blur, brightness, face boundaries, pose, and exposure.

These checks are useful, but they must not be treated as:

```text
bad individual frame = student absent
```

For classroom burst capture, quality checks should primarily determine whether an individual observation is usable for biometric processing.

Example:

```text
Frame 1 -> poor lighting -> discard observation
Frame 2 -> valid -> process
Frame 3 -> motion blur -> discard observation
Frame 4 -> valid -> process
Frame 5 -> valid -> process
```

The burst should continue.

Do not reject the student simply because one frame is poor.

Do not remove quality checks entirely.

Instead, classify observations into useful quality levels.

## 6. Classroom-wide face-size problem

The camera will be mounted at the front of the classroom and must cover every student.

Therefore, students in the back rows may occupy significantly fewer pixels than students in the front rows.

A student can be physically present while their face is too small for reliable recognition in a particular frame.

Do NOT treat:

```text
face too small in one frame
```

as:

```text
student absent
```

The system needs three conceptual quality levels:

```text
RECOGNITION_SAFE
TRACKABLE_BUT_SMALL
UNUSABLE
```

### RECOGNITION_SAFE

The face is sufficiently large/clear for reliable biometric processing.

Perform PAD, recognition, and liveness/temporal processing as appropriate.

### TRACKABLE_BUT_SMALL

The face is detectable and trackable but individual-frame recognition may be unreliable.

Do not immediately discard this person.

Maintain a temporary track across the entire burst.

Collect:

- bounding boxes
- timestamps
- quality scores
- best available face crops
- PAD observations when valid
- recognition observations when valid
- candidate identity evidence

Use the best valid observations from the entire burst.

### UNUSABLE

There is insufficient information for reliable tracking or biometric processing.

Do not force recognition.

Do not classify the student as absent merely because the face is unusable.

## 7. Track-level burst processing

The burst must operate at the level of a tracked face/person, not merely independent frames.

Conceptually:

```text
Track 01
  frame 1 -> small
  frame 2 -> small
  frame 3 -> usable
  frame 4 -> blurry
  frame 5 -> usable
  frame 6 -> usable
  ...
  final -> aggregate evidence
```

A temporary track structure should contain information similar to:

```text
track_id
timestamps
bounding_boxes
quality_scores
best_crops
PAD observations
recognition observations
candidate identities
final status
```

Use an existing tracking mechanism if the project already has one.

Do not add a complex tracker unnecessarily if a lightweight tracking approach is sufficient.

The purpose is to accumulate evidence from the same person across the burst.

## 8. MOST IMPORTANT: no single-frame attendance

Inspect the current `burst_engine.py` and the exact attendance commit path.

If the current implementation can do something equivalent to:

```text
frame
 -> recognize
 -> authorized
 -> record attendance
```

inside the per-frame loop, change this.

A burst/window is a temporal observation period.

The system must:

```text
capture/sample frames
      |
      v
validate observations
      |
      v
extract embeddings from valid observations
      |
      v
compare each probe embedding independently
against enrolled templates
      |
      v
store per-observation identity/similarity evidence
      |
      v
aggregate evidence by candidate identity
      |
      v
make ONE final decision for the window
      |
      v
commit attendance ONCE
```

Never call the attendance commit function simply because one frame passed.

## 9. Recognition aggregation

Do NOT interpret "average the face embeddings" literally.

Do not average an enrolled template with probe embeddings.

Instead:

1. Generate an embedding independently for each valid probe observation.
2. Compare each probe embedding against the enrolled templates.
3. Store the resulting candidate identity and similarity.
4. Aggregate the observations by candidate identity.

Example:

```text
Frame 1 -> Student A -> 0.71
Frame 2 -> Student A -> 0.78
Frame 3 -> unusable
Frame 4 -> Student A -> 0.81
Frame 5 -> Student A -> 0.76
Frame 6 -> Student B -> 0.51
Frame 7 -> Student A -> 0.79
```

Final result should strongly favor Student A.

Use robust evidence such as:

- number of valid observations
- identity support ratio
- median similarity
- top-k similarity
- consistency across observations
- PAD/liveness support

Do not simply average every similarity from every identity.

Do not allow one unusually high similarity score to dominate the entire burst.

## 10. Example final aggregation

For example:

```text
Student A:
4 strong observations
support = 4/5 useful identity observations
median similarity = 0.775
top-k similarity = strong
PAD support = sufficient

Student B:
1 weak observation
similarity = 0.51
```

Final result:

```text
Student A -> PRESENT
```

The exact thresholds must be calibrated against the actual system.

Do not invent arbitrary thresholds merely to make the test pass.

## 11. Insufficient evidence

If a track has too few usable observations, consistently tiny faces, insufficient recognition quality, insufficient PAD evidence, conflicting identities, or excessive uncertainty, do not force a recognition result.

Use:

```text
UNRESOLVED
```

rather than automatically treating the student as absent.

## 12. ABSENT vs UNRESOLVED

The system should distinguish:

```text
PRESENT
ABSENT
UNRESOLVED
```

### PRESENT

The student was reliably identified.

### ABSENT

The system has sufficient evidence that the student was not observed/identified during the attendance process, according to the existing attendance policy.

### UNRESOLVED

The system observed evidence of a person/student position but did not obtain sufficient biometric evidence to identify them reliably.

Examples:

```text
face too small throughout burst
heavy occlusion
insufficient valid observations
persistent motion blur
conflicting identity evidence
PAD uncertainty
```

Do not silently convert:

```text
UNRESOLVED -> ABSENT
```

unless the existing project explicitly requires a final administrative policy for unresolved cases.

## 13. Use the three-window architecture

The project already uses Window A, Window B and Window C with 2-out-of-3 voting.

Preserve this.

Each window should produce ONE aggregated result.

Example:

```text
Window A
  -> multi-frame observations
  -> aggregation
  -> Student 17 = UNRESOLVED

Window B
  -> multi-frame observations
  -> aggregation
  -> Student 17 = UNRESOLVED

Window C
  -> multi-frame observations
  -> aggregation
  -> Student 17 = PRESENT

Final 2-out-of-3 result
  -> PRESENT
```

Another example:

```text
A -> PRESENT
B -> PRESENT
C -> UNRESOLVED

Final -> PRESENT
```

Do not let one frame inside Window A directly override Window B/C.

The unit of voting must remain the completed window result.

## 14. Small-face threshold calibration

Do NOT immediately remove the current minimum face-size threshold.

First measure the real deployment conditions.

Determine the distribution of face sizes for:

- front row
- middle row
- back row
- left edge of classroom
- right edge of classroom
- worst-case seating positions

Then test recognition/PAD performance at different face sizes.

Measure:

- recognition similarity
- recognition accuracy
- false accepts
- false rejects
- PAD reliability
- tracking stability

Use these measurements to define:

```text
RECOGNITION_SAFE
TRACKABLE_BUT_SMALL
UNUSABLE
```

Do not choose thresholds simply because values such as `40x40` look reasonable.

## 15. Important physical limitation

Do not attempt to solve insufficient source resolution purely in software.

If a student's face is only around 12–25 pixels wide throughout the entire burst, do not assume that:

```text
upscale -> face recognition
```

creates reliable biometric information.

Do not use AI super-resolution as a substitute for missing biometric pixels.

If the camera physically cannot provide enough pixels per face at the back of the classroom, report that as a camera/FOV limitation.

Potential hardware solutions include:

- higher-resolution camera
- appropriate lens/FOV
- better mounting position
- camera zoning
- multiple cameras

Do not implement multi-camera support unless currently required, but keep the architecture extensible.

## 16. Capture-window performance

The screenshot shows the capture window opening but becoming laggy.

The desired behavior is:

```text
smooth camera preview
+
controlled biometric sampling
+
burst-level aggregation
```

The preview must not wait for every expensive inference.

Do not blindly increase threading complexity.

Profile first.

Then implement the simplest architecture that removes the measured bottleneck.

## 17. Existing PAD infrastructure

Inspect the repository's existing:

```text
liveness/pad_engine.py
liveness/
models/
```

The repository already contains MiniFASNet-related ONNX models and multi-frame PAD infrastructure.

Do NOT create another independent PAD system.

Determine:

- how the current PAD model is loaded
- how its score is interpreted
- how preprocessing works
- how `MultiFramePADAggregator` works
- where it is currently called
- whether its result actually influences the final burst decision

Integrate/fix the existing infrastructure.

Only replace it if inspection demonstrates that it is technically unsuitable.

## 18. PAD failure must fail closed

Inspect all PAD paths, including legacy `recognition.py`.

A PAD/model exception must NEVER become:

```text
live = True
```

or an equivalent successful authorization.

Distinguish:

```text
GENUINE
SPOOF
PAD_LOW_CONFIDENCE
PAD_ERROR
MODEL_UNAVAILABLE
```

A security-model failure must not silently authorize attendance.

If a fallback PAD method exists, document exactly what it does and whether it provides equivalent security.

Do not silently downgrade from dedicated PAD to a permissive heuristic.

## 19. Active liveness

Inspect the existing:

```text
liveness/challenge.py
liveness/verification.py
```

The repository already contains active challenge infrastructure.

Determine whether automated burst attendance currently bypasses it.

If active challenge is appropriate for the attendance mode, integrate it into the verification flow.

However, this is an unattended classroom system.

Do NOT blindly force a student to interact with the camera if that would make the classroom attendance workflow impractical.

If active interaction is unsuitable for automated classroom capture:

- document the limitation
- rely on stronger passive multi-frame PAD/temporal evidence
- preserve active challenge support for a manual/interactive verification mode if useful

Do not pretend that blink/head-turn challenges are available when the physical deployment does not allow them.

## 20. Face recognition and PAD must remain separate

Recognition should answer:

```text
Who is this?
```

PAD/liveness should answer:

```text
Is this a genuine/live presentation?
```

Keep their outputs separate.

Conceptual recognition result:

```python
{
    "identity": ...,
    "similarity": ...,
    "matched": ...
}
```

Conceptual liveness result:

```python
{
    "pad_passed": ...,
    "pad_score": ...,
    "challenge_passed": ...,
    "temporal_consistency": ...
}
```

Then use a final decision engine.

## 21. Final security gate

Attendance should only be authorized when all required gates pass:

```python
authorized = (
    identity_confident
    and sufficient_observations
    and quality_requirements_satisfied
    and pad_requirements_satisfied
    and liveness_requirements_satisfied
)
```

Adapt the exact condition to the existing implementation.

Do not make V1 a single weighted score.

Do not allow high recognition similarity to override:

```text
PAD failure
liveness failure
insufficient evidence
multiple faces
security model failure
```

## 22. Attendance commit

Attendance persistence must occur exactly once per:

```text
student + attendance window
```

Do not commit attendance repeatedly from multiple frames.

Make the attendance commit happen only after the burst/window aggregation is complete.

If the same student appears in multiple frames, that must not create multiple attendance records.

Preserve existing idempotency/duplicate protections.

## 23. Performance and model lifecycle

Ensure the following are initialized once and reused:

- InsightFace
- PAD model/session
- landmark model
- other heavy ML components

Never do:

```python
for frame in frames:
    model = load_model()
```

Prefer:

```python
model = load_model()

for frame in frames:
    result = model(frame)
```

Sample expensive inference at an appropriate rate rather than running every model on every camera frame.

## 24. Configuration

Use the existing configuration system.

If necessary, centralize:

```text
PAD threshold
minimum valid PAD samples
minimum usable observations
challenge count
challenge timeout
burst duration
recognition threshold
face-size quality tiers
blur threshold
brightness threshold
```

Do not scatter calibration values across source files.

Do not invent thresholds without testing.

## 25. Testing requirements

Update/add tests for:

### Burst aggregation

- one high-confidence frame cannot immediately mark attendance
- multiple consistent observations can mark attendance
- one bad frame does not invalidate an otherwise valid burst
- insufficient valid observations produce UNRESOLVED/retry
- conflicting identities are handled safely
- attendance is committed exactly once per window

### PAD

- PAD is aggregated over observations
- spoof observations are rejected
- PAD model failure cannot authorize attendance
- existing MiniFASNet/multi-frame PAD infrastructure remains functional

### Quality

- small face in one frame does not automatically mean absent
- small-but-trackable face can accumulate evidence
- genuinely unusable face produces unresolved/retry
- normal classroom lighting does not cause unnecessary rejection

### Three-window voting

- A PRESENT + B PRESENT + C UNRESOLVED -> PRESENT
- A UNRESOLVED + B UNRESOLVED + C PRESENT -> according to existing voting policy, PRESENT
- all unresolved -> UNRESOLVED/review state
- existing 2-out-of-3 voting remains intact

### Performance

Measure:

- camera preview responsiveness
- inference latency
- burst processing time
- CPU usage if practical

## 26. Real-world attack evaluation

Use the actual target camera.

Test:

### Genuine

- front-row students
- middle-row students
- back-row students
- different lighting
- moderate pose
- different distances

### Static photos

- printed A4
- smaller printed photo
- smartphone photo
- laptop photo
- monitor photo

### Replay

- recorded blink
- recorded head movement
- recorded expression
- replay on smartphone
- replay on monitor/laptop

### Edge cases

- multiple faces
- partial occlusion
- backlighting
- motion blur
- tiny faces
- students at frame edges

Report actual measured results.

Do not claim an attack class is blocked unless it was tested.

## 27. Privacy

Keep runtime offline.

Do not permanently store camera frames.

Prefer storing operational metadata such as:

```text
timestamp
student ID
window
recognition result
PAD result
final result
failure reason
```

Do not log raw embeddings or images unnecessarily.

## 28. Do not overclaim

Do not claim:

- 100% spoof prevention
- zero false rejects
- impossible-to-bypass liveness
- guaranteed replay protection
- guaranteed deepfake/mask detection

The system must be evaluated against the actual deployment environment.

## 29. Implementation process

Before editing:

1. inspect the repository
2. identify the actual bottleneck
3. identify the current single-frame attendance commit
4. identify current quality thresholds
5. identify existing PAD aggregation
6. identify active challenge behavior
7. identify current three-window aggregation
8. identify the smallest set of files that must change

Then produce the implementation plan.

After each major change:

- run targeted tests
- run the existing test suite
- run the application
- verify camera preview
- verify recognition
- verify attendance persistence

Do not make a large uncontrolled rewrite.

## 30. Final acceptance criteria

The implementation is successful only when:

- camera preview is measurably more responsive
- expensive inference does not block every preview frame
- attendance is never committed from a single successful frame
- each burst produces one aggregated window result
- multiple observations contribute to identity decisions
- one poor frame does not reject a genuine student
- small faces are not automatically treated as absent
- small-but-trackable faces can accumulate evidence
- insufficient evidence produces UNRESOLVED rather than forced absence
- three-window voting remains functional
- PAD is actually part of the final decision
- PAD/model failure cannot authorize attendance
- printed photos are rejected
- phone-screen photos are rejected
- screen-displayed photos are rejected
- tested replay attacks are mitigated
- multiple faces are rejected
- unknown identities are rejected
- attendance is committed once per student/window
- runtime remains offline
- existing application functionality is preserved
- tests pass
- final diff contains no unrelated changes

## 31. Required completion report

After implementation, report:

### Changed files

Every created/modified file and why.

### Unchanged files

Important existing files intentionally untouched.

### Architecture

Explain the actual final burst flow.

### Aggregation

Explain exactly how per-frame observations become one window-level identity decision.

Include:

- observation count
- identity support
- similarity aggregation
- PAD aggregation
- handling of conflicts
- handling of insufficient evidence

### Quality

Report:

- old thresholds
- new thresholds
- why they changed
- how they were calibrated

### Small-face handling

Explain:

- recognition-safe range
- trackable-but-small behavior
- unusable behavior
- unresolved behavior

### PAD

Report:

- exact model
- model artifact
- preprocessing
- threshold
- aggregation method
- failure behavior

### Liveness

Report:

- whether active challenge is used for automated attendance
- why
- how it interacts with passive PAD

### Performance

Report actual measurements before/after where available:

- preview FPS/responsiveness
- inference latency
- burst processing time
- CPU usage

### Tests

List commands run and results.

### Attack evaluation

Report results for:

- genuine
- printed photo
- phone photo
- screen photo
- replay
- multiple faces
- small faces

### Limitations

List known limitations honestly.

Do not claim an attack or edge case is solved unless it was actually tested.

## 32. Final checklist

```text
[ ] Existing repository inspected
[ ] Three-window architecture understood
[ ] Camera pipeline understood
[ ] Attendance commit path identified
[ ] Single-frame attendance removed
[ ] Burst-level aggregation implemented
[ ] Per-observation recognition implemented
[ ] Candidate identity aggregation implemented
[ ] Attendance committed once per window
[ ] Existing 2-out-of-3 voting preserved
[ ] Quality checks converted to observation eligibility where appropriate
[ ] Small-face handling implemented
[ ] Track-level evidence implemented or existing tracking reused
[ ] UNRESOLVED state implemented
[ ] Face-size thresholds calibrated
[ ] Existing PAD infrastructure inspected and reused
[ ] Multi-frame PAD actually controls final verification
[ ] PAD failure cannot authorize attendance
[ ] Active challenge behavior evaluated for classroom deployment
[ ] Camera preview performance improved
[ ] Heavy models initialized once
[ ] No unbounded frame backlog
[ ] Tests updated
[ ] Attack evaluation performed
[ ] Performance measured
[ ] Full checks passed
[ ] Final diff reviewed
[ ] No unrelated code modified
```

## 33. Core rule

The final system must answer two separate questions:

```text
WHO is this?
```

and:

```text
IS there sufficient evidence that this is a genuine/live presentation?
```

For classroom-wide attendance, it must also answer:

```text
DID WE OBTAIN ENOUGH EVIDENCE TO MAKE THAT DECISION?
```

If the answer to the third question is no, do not invent certainty.

Use:

```text
UNRESOLVED
```

and allow subsequent attendance windows or an administrative review path to resolve it.
