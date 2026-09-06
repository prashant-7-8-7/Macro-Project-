import argparse
import uvicorn
import logging
from dotenv import load_dotenv

# Load environment variables from .env file FIRST
load_dotenv()

from src.database.db import init_db
from src.api.routes import app

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

if __name__ == "__main__":
    # Ensure database is initialized before starting server
    init_db()
    
    # Run the FastAPI server
    uvicorn.run("src.api.routes:app", host="127.0.0.1", port=8000, reload=True)
