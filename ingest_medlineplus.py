"""Add MedlinePlus health topics to the local Chroma index.

MedlinePlus is produced by the U.S. National Library of Medicine and is in
the public domain. Refresh the source file from https://medlineplus.gov/xml.html
(the bulk files are date-stamped and rebuilt daily).
"""
import glob
import html
import re
import xml.etree.ElementTree as ET

from langchain.schema import Document
from langchain_chroma import Chroma

from src.helper import text_split, download_hugging_face_embeddings

PERSIST_DIR = "chroma_db"
COLLECTION_NAME = "medical-chatbot"

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def clean(raw):
    return WS_RE.sub(" ", html.unescape(TAG_RE.sub(" ", raw or ""))).strip()


def load_medlineplus(path):
    root = ET.parse(path).getroot()
    docs = []
    for topic in root.iter("health-topic"):
        if topic.get("language") != "English":
            continue
        title = topic.get("title")
        summary = clean("".join(topic.find("full-summary").itertext())
                        if topic.find("full-summary") is not None else "")
        if not summary:
            continue
        aka = [clean(a.text) for a in topic.findall("also-called")]
        header = title if not aka else f"{title} (also called: {', '.join(aka)})"
        docs.append(Document(
            page_content=f"{header}\n\n{summary}",
            metadata={"source": topic.get("url") or "MedlinePlus", "title": title},
        ))
    return docs


if __name__ == "__main__":
    path = sorted(glob.glob("Data/sources/mplus_topics_*.xml"))[-1]
    print(f"Reading {path}")
    docs = load_medlineplus(path)
    print(f"Parsed {len(docs)} English topics")

    chunks = text_split(docs)
    print(f"Split into {len(chunks)} chunks; embedding now ...")

    store = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=download_hugging_face_embeddings(),
        persist_directory=PERSIST_DIR,
    )
    before = store._collection.count()
    for i in range(0, len(chunks), 500):
        store.add_documents(chunks[i:i + 500])
        print(f"  {min(i + 500, len(chunks))}/{len(chunks)}", flush=True)
    print(f"Done. Collection grew from {before} to {store._collection.count()} vectors.")
