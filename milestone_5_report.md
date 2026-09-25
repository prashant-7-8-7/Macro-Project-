# MACRO PROJECT – MILESTONE 5
**Working Prototype, Hybrid Retrieval and Automated Study Notes Engine**

**Project:** AI Powered Document Retrieval & Assessment System
**Student:** Prashant Sharma, Sankalp Singh
**Technology:** Python, FastAPI, SQLite, Embeddings, Gemini API / LLMs

## 1. Milestone Objective
The main goal for this milestone was to transition our project from a conceptual architecture into a fully working prototype. The current system successfully handles document ingestion, chunking, and embedding storage. It performs hybrid retrieval to answer document-specific questions and can summarize documents. 

Instead of the originally planned quiz maker, this milestone introduces a new major feature: the **Automated Study Notes Engine**. This module takes the retrieved document context and structures it into visually engaging, comprehensive study notes. 

## 2. Previous Evaluation Feedback and Response
In the previous evaluation, our project scored 7/8. The faculty pointed out that while our architecture was well-planned, we needed to show concrete evidence of the implementation, database design, and actual prototype behavior rather than just folder links.

| Previous Feedback | Implemented Response |
| :--- | :--- |
| **Show actual implementation** | Working FastAPI backend, ingestion pipeline, retrieval engine, and the new Notes Maker module. |
| **Provide vector-generation evidence** | Document chunks are actively embedded and semantic similarity is utilized during search. |
| **Show SQL/database design** | Implemented SQLite schema with repository layer for storing documents, chunks, embeddings, and FTS5 data. |
| **Demonstrate the prototype** | Web interface now fully supports document upload, viewing, and AI-generated structured study notes. |
| **Provide a direct report file** | This document serves as the direct implementation report. |

## 3. Implemented System Architecture
The current prototype operates on a pipeline where uploaded documents are parsed and divided into chunks. Each chunk is saved in SQLite and assigned a vector embedding. Retrieval uses both lexical (keyword) and semantic methods. The retrieved context is then sent to the language model to generate grounded responses and notes.

* **Document Upload** → Parsing → Chunking
* **Chunk Storage** → SQLite + FTS5 + Embeddings
* **Query** → Keyword Retrieval + Semantic Retrieval
* **Hybrid Results** → Reciprocal Rank Fusion (RRF)
* **Document Context** → AI Study Notes Generation
* **Generated Notes** → JSON Parsing → Visual Notebook UI Rendering

## 4. Core Implementation

### 4.1 Document Ingestion and Database Design
The pipeline processes text and splits it into manageable chunks, retaining page numbers and chunk indexes for source traceability. We use SQLite as our main database, utilizing two primary tables: `documents` and `document_chunks`. We also implemented an FTS5 virtual table synchronized via database triggers to allow for incredibly fast keyword searching alongside our vector embeddings.

### 4.2 Hybrid Retrieval
We implemented keyword, semantic, and hybrid search modes. Keyword search relies on SQLite FTS5, while semantic search embeds the query and calculates cosine similarity against stored chunk embeddings. For the hybrid approach, we merge the two result sets using Reciprocal Rank Fusion (RRF) so that exact keyword matches and semantic meaning both influence the final ranking.

### 4.3 Automated Study Notes Engine
A major addition in this milestone is the Study Notes Engine. Instead of just returning plain text, the system takes the document context and prompts the AI to generate a highly structured JSON object representing study notes. 

The application enforces specific layout rules (like split layouts, comparisons, bullet points, and key takeaways). Once the AI returns the JSON, the frontend parses it and dynamically renders a "Handwritten Notebook" interface using custom CSS. This makes the generated content much easier for students to digest and study from.

## 5. API Integration Challenges & Diagnostics
During development, we ran into a significant issue where the system was throwing connection errors and failing to generate content. We weren't sure if the problem was a bad API key, rate limiting, or if the specific AI model versions we were calling had been deprecated.

To solve this perfectly without constantly breaking our main server, we wrote a standalone diagnostic script (`find_working_model.py`). This script:
1. Securely loaded our `GEMINI_API_KEY` directly from the `.env` file to verify the environment variables were being read correctly.
2. Iterated through a predefined list of candidate models (e.g., `gemini-3.6-flash`, `gemini-flash-latest`, `gemini-pro-latest`).
3. Sent a minimal test prompt ("Say yes") to each model endpoint.

By running this script, we were able to instantly pinpoint which specific model version was currently active and accepting requests with our API key. This allowed us to update our main application configuration confidently and restored the generation features.

## 6. Web Interface Integration
The entire application is served through FastAPI. We built a unified document workspace that includes:
* A document library for uploaded files.
* A document viewer that displays page and chunk information.
* A "Make Notes" action button that triggers the AI generation pipeline.
* A modal overlay that renders the structured JSON into a visual notebook format, complete with different section colors, key takeaway boxes, and print support.

## 7. Next Steps
* Refine the JSON parsing logic to better handle edge cases where the language model might return slightly malformed syntax.
* Implement pagination or streaming for larger note generations.
* Add user accounts so students can save their generated notes for future sessions.
