# Decision note

**Scoring.** `scoring_v1` gives each answer 0 to 100 from four parts: included (25), recommended (40),
position in a ranked list (20, as 1/position) and a Kasparro URL among the supplied citations (15), minus
30 if Kasparro is framed negatively. When a part cannot be observed (no ranked list), its weight is
spread over the others, and the result records which parts were used. Failed answers get no score;
they are counted, never treated as zero. A mention is not a recommendation, and a citation only shows
that a link was returned, not that it supports anything.

**Backend.** FastAPI, one SQLite file with hand-written SQL, and one worker thread that works through
a job table of `pending` rows. Each result is saved as soon as it finishes, so a restart simply carries
on. Re-running the same configuration (dataset, mode, prompt, model, scoring and category versions)
returns the existing run. The database ensures one stored result per answer. It cannot ensure one model
call: if the process dies after the model replies but before the save, the answer is classified again.
Attempts are capped at three and every call is logged.

**Review.** A report has numbered versions. Submitting freezes a version. Approving or rejecting
needs a comment and is a guarded update, so a repeated or concurrent decision gets 409. Edits use an
ETag (`If-Match`); a stale copy gets 412 and a missing header gets 428. Editing a submitted, approved or
rejected version creates a new draft. Reviews expire after 48 hours and approvals after 168 hours,
checked at the moment of action. Export returns only an approved, unexpired, named version.

**Alternatives considered.** A hosted model was not available, so the classifier runs on a local model
(Ollama, qwen2.5:3b) and saves every output for keyless replay. A live mode is not built. Diagnostics are
templated from the counts rather than written by a model, so every claim traces to response IDs. A
broker or multiple workers were rejected as unnecessary for 150 answers.

**Top remedy.** Investigate which sources the unbranded answers draw on and whether Kasparro appears in
them, because Kasparro shows up mainly when the question names it. This is an investigation, not a
promise of better ranking.

**Failure, fix and regression.** On the 15 hand-labelled cases, 11 first failed. Diagnosis: the model
reads the markdown view but quotes it without `*` and `#`, and one bad quote failed the whole answer.
Fix: quotes are matched with markdown marks removed, and unverifiable quotes are dropped. A true
label left with no verified quote still fails, so no answer is labelled without evidence. Failures
fell to 6, and `test_unverified_quote_is_dropped_when_label_keeps_one` guards the change. A second fix
removes Kasparro from its own competitor list (`clean_competitors`, with its own test).

**Main risk.** Labels come from a 3-billion-parameter model on a CPU. On the graded cases, the simple
keyword baseline agrees with the hand labels more often than the model does, especially on
"recommended" and "negative". The model's labels should not be trusted without review. Replay only
repeats that one run.

**Omissions.** No live mode. Repeat runs to measure variation were not done (60 to 140 seconds per call
on this machine). The full 150-answer run was incomplete at submission time; `output/findings.json`
reports successful, failed and pending counts rather than hiding them. Active time was about 251 minutes; see
`docs/time-log.md`.

**Questions.** Which engines and prompt types matter most to Kasparro commercially? Is there an
approved list of Kasparro facts the report may state?

**AI assistance.** I used an AI coding assistant (Claude Code) to draft code, tests and documents. I
set the design rules, hand-labelled the evaluation cases, reviewed each change and ran the tests and
linters myself before each merge.
