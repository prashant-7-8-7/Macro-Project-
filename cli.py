import argparse
import sys
import logging
from src.database.db import init_db
from src.ingestion.pipeline import IngestionPipeline
from src.retrieval.engine import HybridSearchEngine
from src.ai.rag import synthesize_answer

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

def main():
    parser = argparse.ArgumentParser(description="AI Document Retrieval CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Ingest command
    parser_ingest = subparsers.add_parser("ingest", help="Ingest a document")
    parser_ingest.add_argument("file", help="Path to the document file (pdf, txt, docx, etc.)")
    
    # Search command
    parser_search = subparsers.add_parser("search", help="Search the knowledge base")
    parser_search.add_argument("query", help="Search query")
    parser_search.add_argument("--mode", choices=["hybrid", "semantic", "keyword"], default="hybrid", help="Search mode")
    parser_search.add_argument("--top-k", type=int, default=5, help="Number of results")
    
    # Ask command
    parser_ask = subparsers.add_parser("ask", help="Ask a question to the AI")
    parser_ask.add_argument("query", help="Question to ask")
    
    # Init DB command
    subparsers.add_parser("init", help="Initialize the database")

    args = parser.parse_args()

    if args.command == "init":
        init_db()
        print("Database initialized.")
        
    elif args.command == "ingest":
        init_db()
        pipeline = IngestionPipeline()
        result = pipeline.process_file(args.file)
        print(f"Ingestion result: {result}")
        
    elif args.command == "search":
        init_db()
        engine = HybridSearchEngine()
        results = engine.search(args.query, mode=args.mode, top_k=args.top_k)
        print(f"\n--- Top {len(results)} Results for '{args.query}' [{args.mode}] ---\n")
        for i, res in enumerate(results):
            score = res.get('rank_score', res.get('similarity', 0))
            print(f"[{i+1}] {res['filename']} (Page {res['page_number']}) | Score: {score:.4f}")
            print(f"{res['content'][:200]}...\n")
            
    elif args.command == "ask":
        init_db()
        engine = HybridSearchEngine()
        contexts = engine.search(args.query, mode="hybrid", top_k=5)
        print("\nSynthesizing answer...\n")
        response = synthesize_answer(args.query, contexts)
        print(f"--- AI Answer ---\n{response['answer']}\n")
        if response['citations']:
            print("--- Citations ---")
            for cit in response['citations']:
                print(f"[{cit['id']}] {cit['filename']} (Page {cit['page_number']})")
                
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
