from flask import Flask, render_template, jsonify, request
from src.helper import download_hugging_face_embeddings
from langchain_chroma import Chroma
from langchain_openai import ChatOpenAI
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from src.prompt import *
import os
import re


app = Flask(__name__)


load_dotenv()

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

PERSIST_DIR = "chroma_db"
COLLECTION_NAME = "medical-chatbot"

embeddings = download_hugging_face_embeddings()

docsearch = Chroma(
    collection_name=COLLECTION_NAME,
    embedding_function=embeddings,
    persist_directory=PERSIST_DIR,
)

# Plain similarity with k=5 starved comparison questions: whichever entity
# matched more strongly took every slot, so "aortic stenosis vs aortic
# dissection" reported no information on stenosis even though it answers that
# topic on its own. MMR scores a wider pool and then picks passages that are
# relevant *and* unlike each other, which is what a two-topic question needs.
retriever = docsearch.as_retriever(
    search_type="mmr",
    search_kwargs={"k": 8, "fetch_k": 40, "lambda_mult": 0.5},
)

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system_prompt),
        ("human", "{input}"),
    ]
)

# all-MiniLM-L6-v2 was trained on English, so a question in another language
# embeds far from every passage we indexed and retrieval comes back empty. The
# prompt cannot rescue that, because there is nothing in the context to
# translate. So the question is translated to English for the *search* only,
# while the original still goes to the answering model, which replies in the
# user's own language.
#
# The cleaner fix is a multilingual embedding model, but that means re-embedding
# all 18,388 chunks and replacing what is on disk.
ENGLISH_HINTS = re.compile(
    r"\b(what|which|who|how|why|when|where|is|are|was|were|do|does|did|can|"
    r"could|should|the|an|of|for|to|in|on|and|or|my|me|it|about)\b",
    re.IGNORECASE,
)

TRANSLATE_INSTRUCTION = (
    "Translate the following to English. If it is already English, repeat it "
    "unchanged. Reply with the text and nothing else.\n\n"
)

# The vector store and retriever are fully local. Only the answering model needs
# a key, so build the chain lazily and let /get report a clear error instead of
# failing at import time.
answer_chain = None
translator = None

if OPENAI_API_KEY:
    # temperature=0 because this assistant reports what the sources say. At the
    # 0.7 default the same question gave a grounded answer on one run and a
    # refusal on the next, which also makes the test suite meaningless.
    chatModel = ChatOpenAI(model="gpt-4o", temperature=0)
    answer_chain = create_stuff_documents_chain(chatModel, prompt)
    translator = ChatOpenAI(model="gpt-4o-mini", temperature=0)
else:
    print("WARNING: OPENAI_API_KEY is not set. Retrieval works, answering does not.")


def to_english(text):
    """Return an English version of the question, for retrieval only."""
    if translator is None:
        return text
    if text.isascii() and ENGLISH_HINTS.search(text):
        return text
    try:
        reply = translator.invoke(TRANSLATE_INSTRUCTION + text)
        return (reply.content or text).strip()
    except Exception as exc:
        print("Translation failed, searching with the original text:", exc)
        return text


@app.route("/")
def index():
    return render_template('chat.html')


@app.route("/get", methods=["GET", "POST"])
def chat():
    msg = request.form["msg"]
    print(msg)

    # Retrieval and answering are kept separate here, rather than using
    # create_retrieval_chain, because they need different text: the search runs
    # on the English translation, the answer is written from the original.
    search_text = to_english(msg)
    if search_text != msg:
        print("  searching instead for:", search_text)
    docs = retriever.invoke(search_text)

    if answer_chain is None:
        preview = docs[0].page_content[:300] if docs else "(no match)"
        return ("OPENAI_API_KEY is not set, so I cannot compose an answer. "
                "Retrieval is working; the top matching passage is:\n\n" + preview)

    answer = answer_chain.invoke({"input": msg, "context": docs})
    print("Response : ", answer)
    return str(answer)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port = 8080, debug=True)
