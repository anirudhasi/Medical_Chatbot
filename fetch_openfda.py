"""Download FDA drug labels for common medicines and index them locally.

openFDA data is produced by the U.S. Food and Drug Administration and is in
the public domain.

Each label section becomes its own set of chunks, and every chunk is prefixed
with the drug name and section heading. Without that prefix the splitter
produces fragments like "Ibuprofen (FDA drug label)" that match a drug name
strongly but carry no information, crowding the real content out of the
retriever's top results.
"""
import json
import time
import urllib.parse
import urllib.request

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain_chroma import Chroma

from src.helper import download_hugging_face_embeddings

PERSIST_DIR = "chroma_db"
COLLECTION_NAME = "medical-chatbot"
SOURCE_TAG = "openFDA drug label"
API = "https://api.fda.gov/drug/label.json"
MAX_SECTION_CHARS = 6000

SECTIONS = [
    ("indications_and_usage", "what it is used for"),
    ("dosage_and_administration", "dosage and administration"),
    ("warnings", "warnings"),
    ("warnings_and_cautions", "warnings and cautions"),
    ("contraindications", "contraindications"),
    ("adverse_reactions", "side effects"),
    ("drug_interactions", "drug interactions"),
    ("pregnancy", "use in pregnancy"),
]

DRUGS = """
ibuprofen aspirin acetaminophen naproxen diclofenac celecoxib tramadol
morphine oxycodone codeine gabapentin pregabalin amitriptyline duloxetine
sertraline fluoxetine escitalopram citalopram paroxetine venlafaxine
bupropion mirtazapine trazodone alprazolam lorazepam diazepam clonazepam
zolpidem quetiapine risperidone olanzapine aripiprazole haloperidol lithium
lamotrigine valproate carbamazepine phenytoin levetiracetam topiramate
metformin insulin glipizide glimepiride sitagliptin empagliflozin
atorvastatin simvastatin rosuvastatin lisinopril enalapril ramipril losartan
valsartan amlodipine nifedipine metoprolol atenolol propranolol carvedilol
furosemide hydrochlorothiazide spironolactone warfarin apixaban rivaroxaban
clopidogrel heparin digoxin amiodarone
amoxicillin penicillin azithromycin clarithromycin ciprofloxacin
levofloxacin doxycycline cephalexin ceftriaxone clindamycin metronidazole
nitrofurantoin trimethoprim vancomycin acyclovir oseltamivir fluconazole
albuterol salmeterol budesonide fluticasone montelukast prednisone
prednisolone dexamethasone hydrocortisone methotrexate azathioprine
omeprazole pantoprazole ranitidine famotidine ondansetron loperamide
cetirizine loratadine diphenhydramine fexofenadine pseudoephedrine
levothyroxine methimazole allopurinol colchicine alendronate tamsulosin
finasteride sildenafil oxybutynin
"""


def fetch_label(drug):
    q = urllib.parse.quote(f'openfda.generic_name:"{drug}"')
    url = f"{API}?search={q}&limit=1"
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            results = json.load(r).get("results", [])
    except Exception:
        return None
    return results[0] if results else None


def build_docs(drug, rec, splitter):
    docs = []
    for field, heading in SECTIONS:
        val = rec.get(field)
        if not val:
            continue
        body = " ".join(val)[:MAX_SECTION_CHARS].strip()
        if not body:
            continue
        header = f"{drug.capitalize()} - {heading} (FDA drug label)"
        for piece in splitter.split_text(body):
            docs.append(Document(
                page_content=f"{header}\n\n{piece}",
                metadata={"source": SOURCE_TAG, "title": drug, "section": heading},
            ))
    return docs


if __name__ == "__main__":
    drugs = sorted(set(DRUGS.split()))
    splitter = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=80)

    store = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=download_hugging_face_embeddings(),
        persist_directory=PERSIST_DIR,
    )

    print(f"Removing previously indexed '{SOURCE_TAG}' vectors ...")
    store.delete(where={"source": SOURCE_TAG})
    print(f"Collection now holds {store._collection.count()} vectors")

    all_docs, missing = [], []
    for i, drug in enumerate(drugs, 1):
        rec = fetch_label(drug)
        if rec is None:
            missing.append(drug)
        else:
            all_docs.extend(build_docs(drug, rec, splitter))
        if i % 20 == 0:
            print(f"  {i}/{len(drugs)} drugs, {len(all_docs)} chunks so far", flush=True)
        time.sleep(0.3)

    print(f"Fetched {len(drugs) - len(missing)} of {len(drugs)} drugs "
          f"-> {len(all_docs)} chunks")
    if missing:
        print(f"No label found for: {', '.join(missing)}")

    for i in range(0, len(all_docs), 500):
        store.add_documents(all_docs[i:i + 500])
        print(f"  embedded {min(i + 500, len(all_docs))}/{len(all_docs)}", flush=True)

    print(f"Done. Collection holds {store._collection.count()} vectors.")
