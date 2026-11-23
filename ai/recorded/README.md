# Recorded answers

Each file of this folder is one real exchange with the model, recorded once by `scripts/record_ai.py`: what Doors
asked, turn by turn, and what the model answered. Outside the live mode, Doors plays these answers again instead of
calling the model. Nothing here was written by hand, and nothing is made up for a route or a sentence that has no
file: the screen then says that no answer is recorded, and shows only what the engine finds on its own.

The live mode takes two things in the environment of the server, `DOORS_AI=live` and a key (`ANTHROPIC_API_KEY`).
A key alone is not enough: the page never spends on its own.

What is recorded, for the demo route with unchanged assumptions, in English and in French:

- `stress.*.json`: one "Find what breaks my plan", the whole search and the explanations;
- `ask.*.json`: six sentences of "Ask in your own words", one of which Doors cannot set.

A file holds the route, the assumptions, the language and, for "Ask", the sentence it answers; the model, the date
and the version of the SDK; the tokens the API counted and what they cost; and the turns. A turn is the request as
Doors built it and the answer: the texts and the tool calls of the model. The thinking of the model is not kept, and
no file holds a key.

A recording is never shown as it is. It is played again by the loop that made it:

- the tools run on the engine of today, and the checker reads the texts again;
- each request Doors builds today must be, to the letter, the request that was answered then. If the engine, a prompt
  or a form has changed since, the recording is refused, and a test fails until it is recorded again.

`tests/test_live.py` plays every file of this folder again.
