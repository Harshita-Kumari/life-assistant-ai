from openai import OpenAI
import numpy as np
import faiss

client = OpenAI()

# Convert text into chunks
def chunk_text(text, chunk_size=1000):
    chunks = []
    for i in range(0, len(text), chunk_size):
        chunks.append(text[i:i+chunk_size])
    return chunks

# Get embeddings
def get_embeddings(chunks):
    embeddings = []
    for chunk in chunks:
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=chunk
        )
        embeddings.append(response.data[0].embedding)
    return np.array(embeddings).astype('float32')

# Store in FAISS
def create_faiss_index(embeddings):
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(embeddings)
    return index

# Search relevant chunks
def search(index, query_embedding, chunks, k=3):
    D, I = index.search(np.array([query_embedding]).astype('float32'), k)
    return [chunks[i] for i in I[0]]