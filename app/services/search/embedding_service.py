"""
Embedding service for semantic search.

Uses sentence-transformers on CPU - no GPU required, free and efficient.
"""
import os
from typing import List, Optional
import numpy as np
from numpy.linalg import norm

# Lazy import to avoid loading model if not needed
_sentence_transformer = None


def get_embedding_model():
    """
    Get or load sentence transformer model.
    Uses lazy loading - model is loaded only when first needed.
    
    Model: all-MiniLM-L6-v2
    - Lightweight (80MB)
    - Fast on CPU
    - Good quality for semantic search
    - No GPU required
    """
    global _sentence_transformer
    
    if _sentence_transformer is None:
        try:
            from sentence_transformers import SentenceTransformer
            
            # Use lightweight model that works well on CPU
            model_name = "all-MiniLM-L6-v2"
            print(f"Loading embedding model: {model_name} (this may take a moment on first use)...")
            _sentence_transformer = SentenceTransformer(model_name)
            print("Embedding model loaded successfully!")
        except ImportError:
            raise ImportError(
                "sentence-transformers not installed. "
                "Install it with: pip install sentence-transformers"
            )
    
    return _sentence_transformer


def get_embeddings(texts: List[str]) -> np.ndarray:
    """
    Generate embeddings for a list of texts.
    
    Args:
        texts: List of text strings to embed
        
    Returns:
        numpy array of shape (len(texts), embedding_dim)
    """
    model = get_embedding_model()
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    return embeddings


def get_embedding(text: str) -> np.ndarray:
    """
    Generate embedding for a single text.
    
    Args:
        text: Text string to embed
        
    Returns:
        numpy array of shape (embedding_dim,)
    """
    return get_embeddings([text])[0]


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """
    Calculate cosine similarity between two vectors.
    
    Args:
        vec1: First vector
        vec2: Second vector
        
    Returns:
        Similarity score between -1 and 1 (usually 0 to 1 for normalized embeddings)
    """
    return np.dot(vec1, vec2) / (norm(vec1) * norm(vec2))


def find_most_similar(
    query_embedding: np.ndarray,
    document_embeddings: np.ndarray,
    top_k: int = 5
) -> List[tuple[int, float]]:
    """
    Find most similar documents to query using cosine similarity.
    
    Args:
        query_embedding: Embedding of the query
        document_embeddings: Array of document embeddings (shape: n_docs x embedding_dim)
        top_k: Number of top results to return
        
    Returns:
        List of tuples (index, similarity_score) sorted by similarity (highest first)
    """
    # Calculate cosine similarities
    similarities = np.dot(document_embeddings, query_embedding) / (
        norm(document_embeddings, axis=1) * norm(query_embedding)
    )
    
    # Get top k indices
    top_indices = np.argsort(similarities)[::-1][:top_k]
    
    # Return list of (index, similarity) tuples
    return [(int(idx), float(similarities[idx])) for idx in top_indices]


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """
    Split text into chunks for better semantic search.
    
    Args:
        text: Text to chunk
        chunk_size: Maximum characters per chunk
        overlap: Number of characters to overlap between chunks
        
    Returns:
        List of text chunks
    """
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        
        # Try to break at sentence boundary
        if end < len(text):
            # Look for sentence endings
            for punct in ['. ', '! ', '? ', '\n']:
                last_punct = chunk.rfind(punct)
                if last_punct > chunk_size * 0.5:  # Only break if we're past halfway
                    chunk = chunk[:last_punct + len(punct)]
                    end = start + len(chunk)
                    break
        
        chunks.append(chunk.strip())
        start = end - overlap  # Overlap for context
    
    return chunks
