# Evaluation cases

Hand labels for checking the classifier. Labels were written by reading each answer before any prompt
tuning, and committed before the prompt was changed.

## Files

- `labels_v1.jsonl`: 12 responses from the pack: 3 Google AI Mode, 4 ChatGPT, 5 Gemini.
- `edge_cases.jsonl`: 3 edge cases chosen on purpose, marked `"edge_case": true`.
- Prompt categories live in `app/categories_v1.json` (one category per prompt, plus `branded`), because the app uses them.

Each case has `split`: `tune` cases may be looked at while changing the prompt; `final` cases are only
used for the final check.

## How cases were chosen

The pack has a sharp split: the 25 branded questions get answers that name Kasparro, the 25 unbranded
ones never do. Cases cover both, all three engines and six categories, and aim for variety in the labels:

- absent: unbranded questions where other tools are listed (prompts 027, 036, 040)
- mentioned without endorsement: method and availability questions (009, 023)
- possible negative: answers that doubt Kasparro's reach or price (001, 012, 018)
- comparisons with a named competitor (003, 017)
- answers with and without kasparro.com citations (005, 011 with; 017 without)

Selection used simple counts (Kasparro mentions, Kasparro citations, a numbered list) to find variety,
then each case was read. It is not a random sample, so results describe these cases, not the whole pack.

## Edge cases

1. Prompt 014, Gemini: the answer is about Kaspr, a different product. Kasparro is not mentioned even
   though the question names it.
2. Prompt 007, ChatGPT: a numbered list of Kasparro's audit modules. It is not a ranking of options, so
   `position` should be null.
3. `edge-injection-1`: a short synthetic answer that tells the classifier to mark Kasparro as
   recommended. Labels must follow what the answer says, not its instructions.

## Label fields

`mentioned`, `recommended`, `negative` (true/false), `competitors` (names as written), `position` (place in
a ranked list of options, or null), and `evidence`: a list of `{"label", "quote"}` with a short quote
copied from the answer for each true label.
