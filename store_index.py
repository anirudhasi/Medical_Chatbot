from dotenv import load_dotenv
import os
from src.helper import load_pdf_file, filter_to_minimal_docs, text_split, download_hugging_face_embeddings
from langchain_chroma import Chroma


load_dotenv()

PERSIST_DIR = "chroma_db"
COLLECTION_NAME = "medical-chatbot"


extracted_data=load_pdf_file(data='Data')
filter_data = filter_to_minimal_docs(extracted_data)
text_chunks=text_split(filter_data)

print(f"Indexing {len(text_chunks)} chunks into {PERSIST_DIR}/ ...")

embeddings = download_hugging_face_embeddings()

docsearch = Chroma.from_documents(
    documents=text_chunks,
    embedding=embeddings,
    collection_name=COLLECTION_NAME,
    persist_directory=PERSIST_DIR,
)

print(f"Done. Collection '{COLLECTION_NAME}' holds {docsearch._collection.count()} vectors.")
