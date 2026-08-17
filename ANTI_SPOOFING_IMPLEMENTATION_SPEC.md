# ANTI_SPOOFING_IMPLEMENTATION_SPEC.md
## 1. Read before editing
Read this file completely before changing code.
First inspect the repository and map the real implementation:
- application entry point(s)
- runtime/language and dependency manager
- current three-window architecture
- camera capture/frame lifecycle
- face detector
- face-recognition pipeline
- embedding generation/storage
- attendance commit/write path
- existing landmark/liveness code
- model files and model-loading code
- configuration
- tests and run/build commands
- repository instructions such as `AGENTS.md`, `.github/*-instructions.md`, and project documentation
Then write a concise implementation plan based on the actual repository.
Do not invent existing files, APIs, classes, dependencies, or behavior.
Do not start by rewriting the application.
Do not modify unrelated code.
Implement incrementally, validate, then review the final diff.
---
## 2. Problem
The current face-recognition system can recognize a photograph of an enrolled student.
That is a presentation-attack problem.
Face recognition answers:
```text
Who does this face resemble?
```
It does not independently prove:
```text
Is a live physical person currently presenting the face?
```
The required solution is a hybrid offline verification pipeline:
```text
Camera
  -> Face Detection
  -> Face Quality
  -> Passive PAD
  -> Randomized Active Liveness
  -> Temporal Validation
  -> Face Recognition
  -> Final Security Gate
  -> Attendance Commit
```
The system must be designed to reject:
- printed photographs
- photographs displayed on smartphones
- photographs displayed on laptops/monitors
- static/manipulated image presentations
- common replay-video attacks where practical
- multiple-face sessions
- unknown identities
Do not claim 100% spoof-proof security.
---
## 3. Non-negotiable requirements
### Runtime
The attendance flow must work without internet access.
Do not use:
- cloud face recognition
- cloud liveness APIs
- remote inference
- frame uploads
- dynamic model downloads
All required inference runs locally.
### Security separation
Keep these concerns separate:
```text
face detection
face quality
PAD
active liveness
temporal validation
face recognition
final authorization
attendance persistence
```
A high face-recognition score must never compensate for failed PAD or failed liveness.
### Existing application
Preserve the current three-window design and working features.
Reuse adequate existing:
- camera capture
- face detector
- landmark engine
- recognition
- configuration
- logging
- testing infrastructure
Do not create duplicate pipelines without a concrete reason.
---
## 4. Coding-agent workflow
### Phase A — inspect
Before edits:
1. map the repository
2. locate the recognition call
3. locate the attendance commit
4. identify the camera owner
5. inspect dependency versions
6. inspect model loading
7. inspect tests
8. inspect repository agent instructions
### Phase B — plan
Produce a short plan with:
- files to create
- files to modify
- files intentionally untouched
- dependencies
- model artifacts
- interfaces
- state transitions
- tests
- validation commands
### Phase C — implement
Use focused phases:
1. PAD abstraction
2. PAD model integration
3. multi-frame PAD aggregation
4. active challenge controller
5. landmark/pose/blink validation
6. temporal validation
7. final decision gate
8. UI states
9. tests
10. performance cleanup
### Phase D — validate
After each meaningful phase:
- run targeted tests
- run the existing test suite
- start the application when practical
- verify camera behavior
- verify recognition behavior
At completion:
- run all available checks
- inspect the final diff
- verify dependency changes
- verify no unrelated files changed
This research → plan → implement → validate workflow is consistent with current guidance for coding agents. See the references at the end.
---
## 5. Coding standards
### Minimal focused changes
Do not:
- rewrite the whole application
- migrate frameworks
- rename unrelated files
- refactor unrelated modules
- introduce duplicate camera loops
Make the smallest coherent change that solves the problem.
### Minimal comments
Prefer clear names and small functions.
Comments should explain only:
- non-obvious security rules
- mathematical reasoning
- model quirks
- compatibility workarounds
Do not add comments that simply restate the code.
### No API guessing
When library behavior is uncertain, verify the installed version and authoritative documentation before coding.
Do not invent package names or method signatures.
### Error handling
Do not silently swallow errors:
```python
try:
    ...
except Exception:
    pass
```
Handle expected failures explicitly.
### Fail closed
If a critical security component is unavailable or cannot produce a trustworthy result:
```text
DO NOT MARK ATTENDANCE
```
Do not silently fall back to recognition-only attendance.
---
## 6. Passive PAD model
Use a dedicated face anti-spoofing model.
Preferred candidate:
```text
MiniFASNet V2
```
Prefer local ONNX Runtime inference when compatible with the current repository.
MiniFASNet is specifically designed for face anti-spoofing, and public implementations provide lightweight ONNX inference. One current reference implementation exposes MiniFASNetV1SE/V2 and reports roughly 0.43M parameters for those variants.
This is a preferred candidate, not a mandatory dependency.
Before integration verify:
- exact model artifact
- source URL
- license
- model input size
- preprocessing
- output/class ordering
- score semantics
- runtime compatibility
- CPU inference latency
If another local PAD model is selected, document the exact model and why.
Never assume all MiniFASNet checkpoints have identical preprocessing or outputs.
---
## 7. PAD abstraction
Hide model-specific details behind a small engine.
Example shape:
```python
class AntiSpoofEngine:
    def __init__(self, model_path, config):
        ...
    def predict(self, face_crop):
        ...
    def is_live(self, score):
        ...
```
Adapt names to repository conventions.
The rest of the application should not need to know:
- tensor layout
- normalization constants
- class index
- ONNX session details
- model-specific crop scale
unless genuinely required by the existing architecture.
---
## 8. PAD preprocessing
Follow the exact preprocessing required by the selected model:
```text
detected face
 -> expanded face crop
 -> clamp to image bounds
 -> required aspect-ratio handling
 -> resize to model input
 -> channel conversion if required
 -> normalization if required
 -> inference
```
Do not guess:
- RGB vs BGR
- NCHW vs NHWC
- normalization range
- crop scale
- input dimensions
Verify these values from the exact model implementation.
---
## 9. Multi-frame PAD
Never authorize liveness from one PAD inference.
During one verification session:
- collect several valid PAD samples
- use at least 5 valid samples initially
- use a short configurable sampling window
- aggregate robustly, e.g. median
- retain sample statistics for debugging
Example result:
```python
{
    "samples": [...],
    "median_score": ...,
    "min_score": ...,
    "max_score": ...,
    "passed": ...
}
```
Do not use an arbitrary:
```python
score > 0.5
```
rule unless the exact model semantics and local calibration justify it.
---
## 10. PAD calibration
Create a local calibration set using the actual target camera.
Include:
- genuine captures
- printed photos
- phone-screen photos
- laptop/monitor photos
- replay videos
- varied lighting where practical
Record:
- score
- attack/genuine class
- camera/environment
- decision
Choose the operating threshold from the observed score distributions.
Store it in configuration.
Do not tune thresholds separately per user.
---
## 11. Active liveness
Passive PAD is not sufficient by itself.
Add randomized challenge-response.
V1 challenge set:
```text
TURN_LEFT
TURN_RIGHT
BLINK
```
Initial policy:
- 2 actions per session
- random selection
- random order
- runtime generation
- configurable per-action timeout
- configurable total timeout
Do not use a fixed sequence such as:
```text
BLINK -> TURN_LEFT -> TURN_RIGHT
```
for every session.
Generate the challenge after the session starts.
Randomization is a replay-mitigation layer, not a cryptographic guarantee.
---
## 12. Challenge controller
Create a controller similar to:
```python
class LivenessChallengeController:
    def start_session(self):
        ...
    def process_frame(self, landmarks, face_state):
        ...
    def is_complete(self):
        ...
    def is_failed(self):
        ...
    def get_result(self):
        ...
```
Adapt to the actual project.
Responsibilities:
- generate challenge sequence
- track current action
- track deadlines
- consume temporal evidence
- advance on success
- fail on timeout
- reset cleanly
- never write attendance
---
## 13. Challenge state machine
Use explicit state.
```text
IDLE
 -> STARTED
 -> WAITING_FOR_ACTION
 -> ACTION_DETECTED
 -> ACTION_CONFIRMED
 -> next action OR COMPLETE
deadline exceeded -> FAILED
```
Keep state transitions deterministic and testable.
Do not scatter challenge logic across UI callbacks.
---
## 14. Landmark engine
Reuse an existing adequate landmark engine.
If none exists, MediaPipe Face Landmarker is a strong local candidate because its API supports:
- facial landmarks
- blendshapes
- tracking
- facial transformation information
Do not add another landmark stack if the current repository already has a suitable one.
Expose stable measurements to the challenge controller instead of spreading model-specific details throughout the codebase.
---
## 15. Blink detection
Blink must be temporal.
Do not accept a single closed-eye frame.
Require a sequence equivalent to:
```text
OPEN -> CLOSED -> OPEN
```
Use the actual blendshape/landmark representation available in the chosen stack.
Require persistence across multiple frames.
Blink alone must never determine liveness.
---
## 16. Head-turn detection
Use normalized facial geometry or head pose.
Preferred logic:
```text
capture neutral baseline
 -> estimate current pose
 -> calculate relative yaw/pitch
 -> cross calibrated threshold
 -> remain valid for several frames
 -> challenge succeeds
```
Do not use raw whole-frame pixel displacement as proof of head turning.
OpenCV `solvePnP` may be used when appropriate, but reuse existing pose information first.
Calibrate pose thresholds on the actual camera.
---
## 17. Temporal validation
Maintain a short history of:
- timestamps
- face box
- normalized landmarks
- head pose
- challenge observations
- PAD scores
Use this to confirm that the requested action happened coherently.
Do not use:
```text
motion detected == live
```
Replay media also contains motion.
The goal is coherent execution of a newly generated challenge.
---
## 18. Replay attacks
Replay video can contain:
- blinking
- expressions
- head motion
Therefore do not rely on one gesture.
Use:
```text
passive PAD
+
randomized challenge
+
temporal validation
+
face recognition
```
Test replay attacks explicitly.
Describe replay resistance as mitigation against tested attacks, not complete elimination.
---
## 19. Camera-motion normalization
Normalize landmark coordinates relative to the face.
Example:
```python
normalized_x = (x - face_left) / face_width
normalized_y = (y - face_top) / face_height
```
Reuse an equivalent existing implementation if present.
This reduces sensitivity to the face moving around inside the frame.
---
## 20. Optional optical flow
OpenCV optical flow can be used as supporting evidence:
```text
cv2.calcOpticalFlowPyrLK
cv2.calcOpticalFlowFarneback
```
Do not make optical flow the primary liveness classifier.
Add it only if measurement shows that it improves robustness.
Do not add complexity merely because the technique sounds advanced.
---
## 21. Face-quality gate
Before expensive PAD/recognition:
- reject absent face
- reject multiple faces
- check minimum face size
- check blur
- check exposure
- check completeness
- check excessive pose
- check landmark stability where available
A Laplacian-variance blur metric may be used as a rough quality signal.
Blur is not PAD.
A sharp photograph can still be a spoof.
A slightly blurred genuine user can still be live.
Calibrate quality thresholds on the target camera.
---
## 22. Multiple-face rule
If more than one face is visible:
```text
REJECT / ASK USER TO LEAVE ONE FACE IN FRAME
```
Never choose an arbitrary face for attendance.
---
## 23. Recognition separation
Keep the existing recognition pipeline independent.
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
    "challenge_type": ...,
    "temporal_consistency": ...
}
```
Combine them in a final decision engine.
The PAD layer must not write to the attendance database.
The recognition layer must not write attendance before the final security gate.
---
## 24. Final authorization
Use an explicit final security decision.
Conceptually:
```python
authorized = (
    face_present
    and quality_passed
    and pad_passed
    and challenge_passed
    and temporal_validation_passed
    and recognition_passed
)
```
Do not make V1 one weighted score.
Do not allow:
```text
high recognition similarity
```
to override:
```text
PAD failure
liveness failure
quality failure
multiple faces
missing security component
```
---
## 25. Verification session
Use a central verification session/controller if the existing architecture lacks one.
Track:
- session ID
- start time
- state
- face count
- quality
- PAD results
- challenge state
- temporal history
- recognition result
- final result
- failure reason
Do not persist full video.
Do not persist raw frames by default.
---
## 26. Timeouts
Use configurable bounds.
Initial values:
```text
total verification: 5–10 seconds
per challenge: about 3 seconds
```
Calibrate for usability.
On timeout:
- fail the session
- clear temporary state
- show retry state
- do not mark attendance
No state should remain indefinitely in a waiting state.
---
## 27. Failure reasons
Use explicit internal reasons. Suggested values:
```text
NO_FACE
MULTIPLE_FACES
LOW_FACE_QUALITY
LOW_LIGHT
EXCESSIVE_BLUR
PAD_SPOOF
PAD_LOW_CONFIDENCE
CHALLENGE_TIMEOUT
CHALLENGE_FAILED
TEMPORAL_INCONSISTENCY
UNKNOWN_PERSON
LOW_RECOGNITION_SCORE
MODEL_UNAVAILABLE
LANDMARK_ENGINE_UNAVAILABLE
CAMERA_ERROR
SYSTEM_ERROR
```
Adapt names to the repository.
---
## 28. UI behavior
Normal users should not see raw ML scores.
Prefer:
```text
Live face could not be verified.
Please use the camera directly and try again.
```
Challenge:
```text
Please turn your head left.
```
Success:
```text
Liveness verified.
Identity verified.
Attendance recorded.
```
Expose technical scores only in an explicit developer/debug view.
---
## 29. Performance
Initialize models once where practical.
Never do:
```python
for frame in camera:
    model = load_model()
```
Use:
```python
model = load_model()
for frame in camera:
    result = model(frame)
```
Apply this to:
- detector
- PAD
- landmarks
- recognition
Do not build a huge backlog of stale camera frames.
If inference is expensive, sample it appropriately.
Prefer the newest usable frame.
---
## 30. Concurrency
If inference blocks the current UI:
- keep camera acquisition responsive
- use a bounded latest-frame buffer when useful
- avoid unbounded queues
- preserve clean startup/shutdown
Do not introduce complicated threading until actual profiling shows the need.
---
## 31. Configuration
Use the existing configuration mechanism.
If none exists, centralize parameters such as:
```yaml
liveness:
  enabled: true
  pad:
    enabled: true
    threshold: null
    minimum_valid_samples: 5
  challenge:
    enabled: true
    count: 2
    per_action_timeout_seconds: 3
    total_timeout_seconds: 10
  quality:
    min_face_size: null
    blur_threshold: null
```
Do not scatter thresholds across source files.
Do not invent calibration-sensitive defaults without evidence.
---
## 32. Dependency/model governance
Before adding packages:
1. inspect installed versions
2. check runtime compatibility
3. add only required packages
4. avoid unrelated upgrades
5. update dependency files correctly
6. run the application afterward
For external models record:
- exact artifact
- source
- license
- preprocessing
- input size
- output semantics
- redistribution status
Preserve required attribution/license files.
---
## 33. Test strategy
Use the existing test framework.
### Challenge controller tests
Cover:
- generation
- valid action
- invalid action
- timeout
- completion
- reset
- invalid state
### Decision engine tests
Cover:
- all gates pass -> ACCEPT
- PAD fail -> REJECT
- challenge fail -> REJECT
- recognition fail -> REJECT
- quality fail -> REJECT
- multiple faces -> REJECT
- security model unavailable -> REJECT/ERROR
### PAD wrapper tests
Cover:
- initialization
- preprocessing shape
- output interpretation
- threshold behavior
- multi-frame aggregation
### Integration tests
Cover:
- genuine flow
- static photo flow
- failed challenge
- unknown identity
Do not invent ML accuracy tests without suitable fixtures.
---
## 34. Attack evaluation
Use the real target camera.
### Genuine
- normal lighting
- lower lighting
- different distances
- moderate pose
- glasses if relevant
### Static photo
- printed A4 photo
- smaller printed photo
- smartphone photo
- laptop photo
- monitor photo
### Replay
- recorded head movement
- recorded blink
- recorded expression
- smartphone replay
- laptop/monitor replay
- replay containing a different challenge sequence
### Edge cases
- multiple faces
- partial occlusion
- backlight
- motion blur
- poor framing
---
## 35. Metrics
Report measured results:
- false accepts
- false rejects
- genuine acceptance rate
- attack acceptance rate
- challenge completion rate
- average verification time
- PAD latency
- recognition latency
- total verification latency
If formal biometric metrics are used, define exactly how they were calculated.
Do not present model-repository benchmark accuracy as if it were performance of this attendance system.
---
## 36. Evaluation methodology
Use a local dataset from the actual deployment hardware.
Include multiple people and multiple attack types.
Keep calibration and final evaluation samples separate when practical.
Document:
- number of subjects
- genuine samples
- spoof samples
- attack classes
- camera
- environment
- selected thresholds
Do not tune a threshold on the same samples used for final reporting.
---
## 37. Security and privacy constraints
Do not claim:
- 100% spoof-proof
- impossible to bypass
- guaranteed replay protection
- guaranteed deepfake/mask detection
- certification unless actually certified
Do not permanently store camera frames.
Prefer storing only operational metadata such as:
```text
timestamp
student ID
recognition result
PAD result
challenge result
failure reason
```
Treat biometric data as sensitive.
---
## 38. Suggested module boundaries
Adapt names to the repository, but keep responsibilities similar:
```text
face/
  detector
  recognizer
  landmarks
liveness/
  pad_engine
  challenge_controller
  temporal_analyzer
  quality_analyzer
verification/
  verification_session
  decision_engine
attendance/
  attendance_manager
```
Dependency direction:
```text
UI
 |
 v
Verification controller
 |
 +--> Face detection
 +--> Quality
 +--> PAD
 +--> Liveness
 +--> Recognition
 |
 v
Decision engine
 |
 v
Attendance manager
 |
 v
Database
```
Avoid circular dependencies.
---
## 39. V1 boundaries
V1 is complete with:
1. local PAD model
2. multi-frame PAD aggregation
3. randomized active challenge
4. temporal landmark validation
5. independent recognition
6. fail-closed final decision
7. UI feedback
8. deterministic tests
9. real attack evaluation
Do not add rPPG, depth cameras, IR, second PAD models, or custom training unless the first implementation is stable and measured.
The architecture may leave extension points for these later.
---
## 40. Acceptance criteria
The implementation is complete only when:
- genuine enrolled users can authenticate
- unknown users are rejected
- multiple faces are rejected
- static phone photos do not receive attendance
- printed photos do not receive attendance
- screen photos do not receive attendance
- tested replay attacks fail the randomized challenge where expected
- runtime works without internet
- attendance is written only after all required security gates pass
- the current three-window application still works
- face recognition still works
- models are not loaded per frame
- critical security failure cannot silently bypass verification
- tests/checks pass
- final diff contains no unrelated changes
---
## 41. Completion report
After implementation, report exactly:
### Changed
Every created/modified file and why.
### Not changed
Important existing modules intentionally untouched.
### Dependencies
Every dependency change and reason.
### Model
State:
- exact model
- exact artifact
- source
- format
- license
- preprocessing
- input size
- output semantics
### Verification flow
Actual implemented sequence.
### Tests
Commands run and results.
### Attack evaluation
Results for:
- genuine
- printed photo
- phone photo
- screen photo
- replay
- multiple faces
### Limitations
Known unresolved issues.
Do not claim an attack class is blocked unless it was actually tested.
---
## 42. Final agent checklist
```text
[ ] Repository inspected
[ ] Three-window architecture mapped
[ ] Recognition pipeline mapped
[ ] Attendance commit path mapped
[ ] Repository instructions checked
[ ] Dependency versions checked
[ ] PAD model provenance verified
[ ] PAD preprocessing verified
[ ] PAD integrated locally
[ ] Multi-frame PAD implemented
[ ] PAD threshold configurable
[ ] Random challenge implemented
[ ] Challenge generated per session
[ ] Blink is temporal
[ ] Head turn uses normalized landmarks/pose
[ ] Temporal state machine implemented
[ ] Multiple-face rejection implemented
[ ] Session timeout implemented
[ ] Fail-closed behavior implemented
[ ] Final security gate implemented
[ ] Attendance cannot bypass verification
[ ] UI feedback implemented
[ ] Unit tests added/updated
[ ] Integration tests added/updated
[ ] Attack matrix prepared
[ ] Performance measured
[ ] Full checks run
[ ] Final diff reviewed
[ ] No unrelated files modified
```
---
## 43. Core rule
The system must independently establish:
```text
WHO is this?
```
and:
```text
IS this a live physical presentation?
```
Only when both are satisfactory may attendance be recorded.
---
## Sources / references
Agent workflow:
- GitHub Docs — Research, plan, implement, iterate:
  https://docs.github.com/en/copilot/tutorials/optimize-ai-usage
- GitHub Docs — focused custom instructions:
  https://docs.github.com/en/copilot/tutorials/customize-code-review
- GitHub Docs — repository-specific instructions:
  https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-copilot-overview
- OpenAI — repository-scoped instructions and required checks:
  https://openai.com/index/introducing-codex/
PAD / biometrics:
- MiniFASNet ONNX reference:
  https://github.com/yakhyo/face-anti-spoofing
- Silent-Face-Anti-Spoofing ONNX:
  https://github.com/QingHeYang/Silent-Face-Anti-Spoofing-onnx
- NIST SP 800-63B:
  https://pages.nist.gov/800-63-4/sp800-63b/authenticators/
- NIST SP 800-63A:
  https://pages.nist.gov/800-63-4/sp800-63a.html
- MediaPipe Face Landmarker:
  https://ai.google.dev/edge/api/mediapipe/python/mp/tasks/vision/FaceLandmarkerOptions
