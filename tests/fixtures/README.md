# Recorded responses

These are real responses from `POST /api/decide`, recorded through `jevtester serve`.

- `decide-exploring-ditch.json`: `decision-1@foundry` answering the request `build_request` makes today for the ditch message. A test checks that it still matches the current request, so re-record it when the request changes.
- `decide-target-failed.json`: a target that failed. It was recorded against `clef-flash@ollama`, which isn't downloaded, with an earlier version of the request. Only its error result matters to the tests.
