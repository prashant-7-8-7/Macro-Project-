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
    
    # Get port from environment variable (default to 8000 for local)
    import os
    port = int(os.environ.get("PORT", 8000))
    
    # Run the FastAPI server
    uvicorn.run("src.api.routes:app", host="0.0.0.0", port=port, reload=False)
