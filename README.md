# Medical Chatbot

A retrieval-augmented chatbot that answers medical questions **only** from a
local corpus of reference material, and says so plainly when the corpus does not
cover the question.

The model never answers from its own knowledge. Every question is used to search
a local vector database first; the passages that come back are pasted into the
prompt, and the model is instructed to stay inside them. Swap the documents and
you have a different chatbot, with no retraining.

## What is in the index

Three public-domain sources, in one Chroma collection of 18,388 passages:

| Source | What it is | Passages |
| --- | --- | ---: |
| Gale Encyclopedia of Medicine | Reference book. This copy is Volume 1 only, so entries A to B. | 7,299 |
| MedlinePlus health topics | Plain-language topic pages from the US National Library of Medicine. 2,033 topics. | 6,936 |
| openFDA drug labels | Official labels for about 130 common generic medicines. | 4,153 |

Coverage is wide but uneven, which is deliberate and visible in the tests: the
encyclopedia is deep and stops at B, MedlinePlus is shallow and covers the whole
alphabet.

## How it works

**Build time**, run once. Each source is loaded, cleaned, and cut into chunks of
about 400 characters with 20 characters of overlap. Every chunk is turned into
384 numbers by `sentence-transformers/all-MiniLM-L6-v2`, running locally, and
stored in Chroma with an HNSW index.

**Ask time**, on every question. The question is embedded by the same model, the
retriever returns the passages worth reading, they are pasted into the prompt
alongside six safety rules, and GPT-4o writes at most three sentences.

Everything except the final call to GPT-4o runs on your own machine.

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows;  source .venv/bin/activate on Linux/macOS
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
OPENAI_API_KEY=sk-...
```

`.env` is gitignored. Do not commit it.

## Building the index

Run these once, in any order. The first run also downloads the embedding model,
about 90 MB. Expect roughly 20 minutes in total on CPU.

```bash
python store_index.py           # the encyclopedia PDF
python ingest_medlineplus.py    # the MedlinePlus bulk XML
python fetch_openfda.py         # downloads drug labels, then indexes them
```

This creates `chroma_db/`, about 116 MB. It is gitignored, and generated rather
than written by hand.

Re-running `store_index.py` or `ingest_medlineplus.py` **adds** to the collection
rather than replacing it, so running one twice will duplicate its passages. Only
`fetch_openfda.py` clears its own previous entries first. Delete `chroma_db/` and
rebuild if you need a clean slate.

To refresh the MedlinePlus data, download a newer dated bulk file from
<https://medlineplus.gov/xml.html> into `Data/sources/`. The ingest script picks
the newest file matching `mplus_topics_*.xml`.

## Running it

```bash
python app.py
```

Then open <http://localhost:8080>.

Without an API key the app still starts and still retrieves. It says it cannot
compose an answer and shows the best matching passage instead.

## Testing

`tests/questions.md` holds 50 questions in six groups, each checking a different
behaviour: answering from the encyclopedia, answering from MedlinePlus, staying
quiet when a topic is absent, staying quiet when a topic is present but too
shallow, refusing questions that are not medical, handling safety-sensitive
questions, and retrieval edge cases such as bare keywords and non-English input.

```bash
python app.py &                 # in one shell
bash tests/run.sh               # in another
```

`tests/results.md` records the answers from the last full run, in which all 50
behave as specified.

The most valuable groups are the ones that expect silence. Anything else measures
whether the bot can talk. Only those measure whether it can stay quiet, which is
the point of building it this way.

## Notes on the design

- **Chroma, not a hosted vector database.** No account, no key, no network. It
  will not scale to many users, which is fine for this.
- **Local embeddings.** Free and unlimited. Embedding 18,388 chunks through an
  API would cost money and time.
- **MMR retrieval, not plain similarity.** With plain top-k, a question naming
  two conditions gave every slot to whichever matched more strongly, and the bot
  denied knowing the other one. MMR picks passages that are relevant *and*
  unlike each other.
- **temperature = 0.** This assistant reports what the sources say, so the same
  question should give the same answer. At the default of 0.7 it answered on one
  run and refused on the next, which also makes the test suite meaningless.
- **The rule order in `src/prompt.py` is load-bearing.** Emergencies are rule 1.
  With scope first, "I have chest pain radiating down my left arm" came back as
  "I can only answer medical questions from my reference sources".
- **Non-English questions are translated for the search only.** The embedding
  model is English-only, so a Spanish question retrieved nothing at all. The
  translation feeds the search; the answer is written from the original, in the
  user's language.

## Known limitations

- No conversation memory. Every request is independent, so follow-up questions
  do not work.
- The encyclopedia covers only A to B.
- MedlinePlus summaries are shallow, so some reasonable questions are correctly
  refused. "What are the stages of syphilis?" is the example in the test set.
- Retrieval quality sets the ceiling. If the right passage never comes back, no
  model can save the answer.

## Layout

```
app.py                     Flask server: loads the DB, builds the chain, serves /get
store_index.py             build step, encyclopedia PDF into Chroma
ingest_medlineplus.py      build step, MedlinePlus XML into Chroma
fetch_openfda.py           build step, downloads drug labels then indexes them
src/helper.py              shared: load PDF, split text, load the embedder
src/prompt.py              the six safety rules
templates/chat.html        the chat page
static/style.css           chat styling
Data/                      source documents
tests/                     50 questions, the runner, and the last results
```

## Disclaimer

This is a teaching project. It is not a medical device, it has not been
clinically validated, and nobody should make a health decision from it. The
`Data/Medical_book.pdf` file is included for coursework use; check the rights on
any reference work before redistributing it.
