import os
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO)
load_dotenv()

from src.ingestion.pipeline import IngestionPipeline
from src.database.repository import DocumentRepository

repo = DocumentRepository()
repo.delete_document('fcfb42be-e314-4b91-a14c-ef5b108079a3') # delete OOPS notes

pipeline = IngestionPipeline()
print("Processing OOPS notes.PDF...")
result = pipeline.process_file(r"data\uploads\OOPS notes.PDF")
print(result)
