# ID Assist Demo Architecture

## Scope

This is a hackathon demonstration of an officer-activated identity workflow.
It is not a production law-enforcement system. All demo identities and
records must be synthetic, and the application must make mock mode obvious in
the UI.

## Components

| Component | Responsibility | Does not own |
| --- | --- | --- |
| `app/capture` | Start/stop the native camera helper, receive JPEG frames, maintain a short rolling buffer | Identity decisions |
| `app/detection` | Detect visible faces and maintain anonymous subject tracks | Facial recognition or records access |
| `app/workflow` | Validate the predicate, capture a burst, select frames, gate review, and coordinate state transitions | Provider-specific HTTP or database code |
| `app/providers` | Adapt a configured facial-search provider and normalize candidate responses | Human confirmation |
| `app/records` | Query synthetic records by confirmed identity and normalize the return | Candidate matching |
| `app/audit` | Persist append-only events with timestamps, actor, reason, subject, results, decisions, and disposition | UI presentation |
| `app/ui` | Show live feed, subject selection, review, records, logs, and threat notification state | Search or records policy |

## Suggested module contracts

```text
FrameSource.next() -> Frame
SubjectTracker.observe(Frame) -> list[AnonymousSubject]
FaceSearchProvider.search(images, request) -> list[Candidate]
RecordsProvider.lookup(confirmed_identity) -> RecordsResult
EventLog.append(event) -> event_id
```

`IdentificationSession` owns the ordered states:

```text
IDLE
  -> SUBJECT_SELECTED
  -> PREDICATE_RECORDED
  -> BURST_CAPTURED
  -> CANDIDATE_RETURNED
  -> HUMAN_CONFIRMED | HUMAN_REJECTED
  -> RECORDS_RETURNED
  -> NOTIFICATION_SENT
  -> CLOSED
```

Rejected, cancelled, timed-out, and provider-error paths must also close with
an audit event. No state may call `RecordsProvider` before
`HUMAN_CONFIRMED`.

## Evidence event minimum

Each search event should include:

- event ID, session ID, actor ID, UTC timestamp, and location label
- selected anonymous subject and source frame IDs
- documented search reason and predicate status
- selected image metadata and provider request ID
- normalized candidate, provider status, and provider error if any
- reviewer ID, review decision, and review timestamp
- records query ID, returned record categories, and final disposition
- notification status and delivery timestamp, when used

Store image bytes and sensitive payloads separately from the searchable event
index. For the hackathon, JSON Lines is enough for the audit stream; a
database can replace it behind the same `EventLog` contract later.

## Demo data

`data/mock_records/` should contain only fabricated people, image fixtures,
and records. `app/providers` should include a deterministic mock provider for
the judging path. A Clearview adapter, if approved and available, should be
disabled by default and must never silently fall back to real-person data.

## Implementation order

1. Extract the current feed client and detector behind `FrameSource` and
   `SubjectTracker` without changing the working camera launch path.
2. Add a rolling buffer, subject selection, reason form, and burst capture.
3. Implement mock provider, human review, synthetic records, and audit events
   as one end-to-end vertical slice.
4. Build the demo UI around the same session state and live event stream.
5. Add the optional Clearview adapter only after its API, data handling,
   authorization, retention, and network requirements are confirmed.
6. Add phone notification as a final adapter; it must never change the review
   or records gate.

## Open design questions

1. Is the intended demo allowed to send face images to Clearview, and do we
   have credentials, API documentation, and permission to use that service?
2. What exact search predicate and reviewer role should the demo require?
3. Should the operator interact with the Mac UI, the iPhone, or both? The
   current prototype has no iPhone control channel; it only streams camera
   frames to the Mac.
4. What should a mock record contain, and which result should trigger the
   phone noise or visual alert?
5. Should audit events be written to JSONL, SQLite, or Supabase during the
   hackathon? Who can view or export them?
6. What is the required retention behavior for captured frames and provider
   responses after a rejected or cancelled search?
7. Does the demo need multiple subjects in view, or can it enforce one
   selected face at a time as the current detector does?