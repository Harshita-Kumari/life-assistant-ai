import pdfplumber
from openai import OpenAI
import os


from .rag_utils import chunk_text, get_embeddings, create_faiss_index, search

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def extract_text(pdf_path):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            if page.extract_text():
                text += page.extract_text()
    return text

def generate_notes_with_rag(text):
    chunks = chunk_text(text)

    embeddings = get_embeddings(chunks)
    index = create_faiss_index(embeddings)

    # Better query
    query = "Give full detailed summary of entire document"
    query_embedding = get_embeddings([query])[0]

    # 🔥 Increase number of chunks
    relevant_chunks = search(index, query_embedding, chunks, k=8)

    combined_text = " ".join(relevant_chunks)

    prompt = f"""
    Create a COMPLETE and DETAILED summary of the document.

    Include:
    - All important topics
    - Key points
    - Explanation in simple language

    Do NOT skip parts.

    Text:
    {combined_text}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content


from .rag_utils import chunk_text, get_embeddings, create_faiss_index, search
from openai import OpenAI

client = OpenAI()

def chat_with_pdf(text, user_query):
    # Step 1: Chunk text
    chunks = chunk_text(text)

    # Step 2: Create embeddings
    embeddings = get_embeddings(chunks)
    index = create_faiss_index(embeddings)

    # Step 3: Query embedding
    query_embedding = get_embeddings([user_query])[0]

    # Step 4: Get relevant chunks
    relevant_chunks = search(index, query_embedding, chunks)

    context = " ".join(relevant_chunks)

    # Step 5: Ask AI
    prompt = f"""
    Answer the question based only on the context below.

    Context:
    {context}

    Question:
    {user_query}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content