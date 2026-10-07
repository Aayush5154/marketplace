import os
from dotenv import load_dotenv

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX = os.getenv("PINECONE_INDEX")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

CHUNK_SIZE = 700
CHUNK_OVERLAP = 150

TOP_K = 5