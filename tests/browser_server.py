"""Controlled browser fixture: disposable data and fake AI, never real provider calls."""
import json, os, time
from pathlib import Path
if not os.environ.get('DB_PATH') or not os.environ.get('DATA_DIR'):
    raise RuntimeError('Set DB_PATH and DATA_DIR to disposable test paths before starting this fixture.')
import fitz
import uvicorn
from src.database.db import init_db
from src.database.repository import DocumentRepository
from src.ai.embeddings import EmbeddingEngine
from src.ai.vector_math import serialize_embedding
from src.ingestion.ocr import retain_original
from src.ai import budget, notes
from src.quiz import generator
from src.api.routes import app
init_db()
repo=DocumentRepository(); engine=EmbeddingEngine()
for ident,title,text,kind in [('11111111-1111-1111-1111-111111111111','Rust notes.pdf','Rust focuses on memory safety and concurrency. Ownership prevents invalid memory access.','pdf'),('22222222-2222-2222-2222-222222222222','Python notes.txt','Python is a high-level programming language with dynamic typing and clear syntax.','txt')]:
    repo.delete_document(ident)
    repo.insert_document_with_chunks(doc_id=ident,title=title,filename=title,file_type=kind,file_size=100,doc_hash=ident,
        metadata={'embedding_backend':engine.profile},chunks=[{'id':ident+'-0','document_id':ident,'chunk_index':0,'content':text,'token_count':20,'page_number':1,'embedding':serialize_embedding(engine.embed_texts([text])[0])}])
    if kind=='pdf':
        path=Path(__import__('tempfile').gettempdir()) / 'study-fixture.pdf'
        with fitz.open() as pdf:
            page=pdf.new_page();page.insert_text((50,90),text,fontsize=10);pdf.save(path)
        retain_original(ident,kind,path)

def fake_stream(prompt):
    if 'data link layer provides framing' in prompt.lower():
        yield '**Data link layer**: The layer provides framing and node-to-node delivery. '
        yield '[Source 1]'
        return
    yield '**Memory safety**: Rust protects memory through ownership. '
    time.sleep(1.5 if 'stop test' in prompt.lower() else .2)
    yield '[Source 1]'
budget.stream=fake_stream
sample=[{'question':'Which language focuses on memory safety?','correct_answer':'Rust','topic':'Memory safety','source_page':1,'source_chunk_id':'0','source_quote':'Rust focuses on memory safety and concurrency.','difficulty':'easy','options':[{'label':label,'is_correct':label=='Rust'} for label in ['Rust','Ruby','R','Python']]}]
generator.call_llm=lambda *args,**kwargs:json.dumps(sample)
notes.call_llm=lambda *args,**kwargs:json.dumps({'heading':'Memory safety','explanation':'Ownership prevents invalid memory access.','bullets':['Rust uses ownership.','Borrowing controls references.'],'keyBox':{'title':'Ownership','items':['Memory safety']},'tip':'Trace who owns the value.'})
uvicorn.run(app,host='127.0.0.1',port=8000)
