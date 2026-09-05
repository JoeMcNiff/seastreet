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
| `app/workflow` | Validate the predicate, capture a face, gate review, and coordinate state transitions | Provider-specific HTTP or database code |
| `app/providers` | Call Clearview `/embed`, validate the vector, and search for identity candidates | Local matching or human confirmation |
| `app/records` | Search the Supabase vector image database locally, resolve the linked identity, and query synthetic records | Embedding generation |
| `app/audit` | Persist append-only events with timestamps, actor, reason, subject, results, decisions, and disposition | UI presentation |
| `app/ui` | Show live feed, subject selection, review, records, and logs | Search or records policy |

## Suggested module contracts

```text
FrameSource.next() -> Frame
SubjectTracker.observe(Frame) -> list[AnonymousSubject]
EmbeddingProvider.embed(images, request) -> Embedding
VectorStore.match(embedding, threshold) -> list[Candidate]
RecordsProvider.lookup(confirmed_identity) -> RecordsResult
EventLog.append(event) -> event_id
```

The intended Clearview path is:

```text
one original frame + OpenCV face rectangle
   -> ClearviewEmbeddingProvider (one authenticated `/embed` request)
   -> L2-normalized query embedding
   -> SupabaseVectorStore (pgvector similarity search)
   -> linked synthetic identity candidate
```

Clearview provides the embedding service; it is not the source of the demo
identity record. The application owns the similarity threshold, candidate
ranking, human review gate, and identity-to-record join. Keep the API key in an
environment variable or local secret store, never in source code or audit
events.

`IdentificationSession` owns the ordered states:

```text
IDLE
  -> SUBJECT_SELECTED
  -> PREDICATE_RECORDED
  -> FACE_CAPTURED
  -> CANDIDATE_RETURNED
  -> HUMAN_CONFIRMED | HUMAN_REJECTED
  -> RECORDS_RETURNED
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

Store image bytes and sensitive payloads separately from the searchable event
index. For the hackathon, JSON Lines is enough for the audit stream; a
database can replace it behind the same `EventLog` contract later.

## Demo data

`data/mock_records/` should contain only fabricated people, image fixtures,
embeddings, and records. `app/providers` should include a deterministic mock
embedding provider for the judging path. `app/records` should provide both a
Supabase vector-store adapter and a local fixture adapter so the demo can run
without network access. The Clearview key must be injected at runtime and
must never silently fall back to real-person data.

## Implementation order

1. Extract the current feed client and detector behind `FrameSource` and
   `SubjectTracker` without changing the working camera launch path.
2. Add subject selection, reason form, and face capture.
3. Implement mock provider, human review, synthetic records, and audit events
   as one end-to-end vertical slice.
4. Build the demo UI around the same session state and live event stream.
5. Add Clearview embedding retrieval and Supabase vector matching behind the
   interfaces above; keep the fixture adapters as the offline demo path.

## Open design questions

1. What Clearview model/version and rate limit apply, and are OpenCV-generated
   rectangles accepted directly by `/embed` without a preceding `/detect` call?
2. What exact search predicate and reviewer role should the demo require?
3. Should the operator interact with the Mac UI, the iPhone, or both? The
   current prototype has no iPhone control channel; it only streams camera
   frames to the Mac.
4. What Supabase project/table/schema and pgvector distance metric should the
   vector adapter target? What similarity threshold counts as a candidate?
5. Should audit events be written to JSONL, SQLite, or Supabase during the
   hackathon? Who can view or export them?
6. What is the required retention behavior for captured frames and provider
   responses after a rejected or cancelled search?
7. Does the demo need multiple subjects in view, or can it enforce one
   selected face at a time as the current detector does?
