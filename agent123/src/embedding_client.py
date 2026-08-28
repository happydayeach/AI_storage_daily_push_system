# src/embedding_client.py
from sentence_transformers import SentenceTransformer
from typing import List, Union
import numpy as np

class EmbeddingClient:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)

    def encode(self, texts: Union[str, List[str]]) -> List[List[float]]:
        if isinstance(texts, str):
            texts = [texts]
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()
