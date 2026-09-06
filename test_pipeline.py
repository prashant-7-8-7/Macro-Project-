import os
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO)
load_dotenv()

from src.ingestion.pipeline import IngestionPipeline

# Create a dummy text file
with open("test_upload.txt", "w") as f:
    f.write("This is a test document for the upload pipeline.")

pipeline = IngestionPipeline()
print("Processing file...")
result = pipeline.process_file("test_upload.txt")
print(result)
