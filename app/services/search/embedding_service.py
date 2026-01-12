"""
Embedding service for semantic search. Uses sentence-transformers on CPU 
"""
from typing import List, Optional

import numpy as np
from numpy.linalg import norm

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    try:
        from langchain.text_splitter import RecursiveCharacterTextSplitter
    except ImportError:
        RecursiveCharacterTextSplitter = None  


_sentence_transformer = None


def get_embedding_model():
    """
    Load sentence transformer model.
    
    Model: all-MiniLM-L6-v2
    """
    global _sentence_transformer
    
    if _sentence_transformer is None:
        try:
            from sentence_transformers import SentenceTransformer
            model_name = "all-MiniLM-L6-v2"
            print(f"Loading embedding model: {model_name}...")
            _sentence_transformer = SentenceTransformer(model_name)
            print("Embedding model loaded!")
        except ImportError:
            raise ImportError(
                "sentence-transformers not installed. "
            )
    
    return _sentence_transformer


def get_embeddings(texts: List[str], batch_size: int = 100) -> np.ndarray:
    """
    Generate embeddings for a list of texts.    
    Args:
        texts: List of text strings to embed
        batch_size: num of texts to process at once 
        
    Returns:
        np.array of shape (len(texts), embedding_dim)
    """
    if not texts:
        return np.array([])
    
    model = get_embedding_model()
    
    if len(texts) <= batch_size:
        embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return embeddings
    
    all_embeddings = []
    num_batches = (len(texts) + batch_size - 1) // batch_size
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        batch_embeddings = model.encode(batch, convert_to_numpy=True, show_progress_bar=False)
        all_embeddings.append(batch_embeddings)
        
        batch_num = i // batch_size + 1
        if num_batches > 1:
            print(f"Processed embedding batch {batch_num}/{num_batches} ({len(batch)} texts)")
    
    return np.vstack(all_embeddings)


def get_embedding(text: str) -> np.ndarray:
    return get_embeddings([text])[0]


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    return np.dot(vec1, vec2) / (norm(vec1) * norm(vec2))


def find_most_similar(query_embedding: np.ndarray, document_embeddings: np.ndarray,
    top_k: int = 5) -> List[tuple[int, float]]:
    """
    Find most similar documents to query using cosine similarity.
    
    Args:
        query_embedding: embedding of the query
        document_embeddings: arr of doc embeddings (n_docs x embedding_dim)
        top_k: num of top results
    Returns:
        List of tuples (index, similarity_score) sorted by similarity
    """
    # cosine similarities
    similarities = np.dot(document_embeddings, query_embedding) / (
        norm(document_embeddings, axis=1) * norm(query_embedding)
    )
    
    #  top k indices
    top_indices = np.argsort(similarities)[::-1][:top_k]    
    return [(int(idx), float(similarities[idx])) for idx in top_indices]


_text_splitter: Optional["RecursiveCharacterTextSplitter"] = None


def _get_text_splitter(chunk_size: int = 500, chunk_overlap: int = 50) -> "RecursiveCharacterTextSplitter":
    if RecursiveCharacterTextSplitter is None:
        raise ImportError(
            "langchain-text-splitters not installed. "
            "Install it with: pip install langchain-text-splitters"
        )
    
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", "! ", "? ", " ", ""] 
    )

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50, max_chunks: Optional[int] = None) -> List[str]:
    """
    Split text into chunks for better semantic search.
    
    Args:
        text: text to chunk
        chunk_size:  chars per chunk
        overlap: num of characters to overlap between chunks
        max_chunks: Optional maximum number of chunks to return
        
    Returns:
        List of text chunks
    """
    if not text or len(text.strip()) == 0:
        return []
    
    if len(text) <= chunk_size:
        return [text.strip()]
    
    try:
        splitter = _get_text_splitter(chunk_size=chunk_size, chunk_overlap=overlap)
        chunks = splitter.split_text(text)
        
        chunks = [chunk.strip() for chunk in chunks if chunk.strip()]
        
        if max_chunks is not None and len(chunks) > max_chunks:
            print(f"Warning: Transcription has {len(chunks)} chunks, limiting to {max_chunks}.")
            chunks = chunks[:max_chunks]
        return chunks
    except (ImportError, AttributeError) as e:
        raise ImportError("langchain-text-splitters not installed") from e
