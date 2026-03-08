"""SigLIP embedding generation for images and text.

Handles GPU inference with dynamic batching and OOM fallback.
Model is kept loaded in VRAM for fast queries.
"""

import threading
from typing import Any, Sequence

import numpy as np
import torch
from PIL import Image
from transformers import AutoModel, AutoProcessor

from fastlrsearch.config import settings


class Embedder:
    """SigLIP embedder for images and text.

    Manages model lifecycle and provides batched inference.
    """

    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
    ):
        """Initialize embedder.

        Args:
            model_name: HuggingFace model ID (defaults to settings)
            device: Compute device (defaults to settings)
        """
        self.model_name = model_name or settings.embedding_model
        self.device = device or settings.get_device()

        # Lazy loading - initialized on first use
        self._model: Any = None
        self._processor: Any = None

        # Dynamic batch size for OOM handling
        self._current_batch_size = settings.batch_size

        # Thread safety lock for model inference
        self._lock = threading.Lock()

    @property
    def model(self) -> Any:
        """Lazy load model."""
        if self._model is None:
            self._load_model()
        return self._model

    @property
    def processor(self) -> Any:
        """Lazy load processor."""
        if self._processor is None:
            self._load_model()
        return self._processor

    def _load_model(self):
        """Load model and processor into memory."""
        print(f"Loading {self.model_name} on {self.device}...")

        self._processor = AutoProcessor.from_pretrained(self.model_name, use_fast=True)
        # Load directly to device to avoid CPU/GPU tensor mismatch
        if self.device == "cuda":
            self._model = AutoModel.from_pretrained(
                self.model_name,
                device_map="cuda",
                torch_dtype="auto",
            )
        elif self.device == "mps":
            # MPS: check if enough GPU memory for this model (~4GB in float16)
            # Metal's MPS abort on too-large buffers is a C++ SIGABRT that
            # cannot be caught by Python try/except, so we must check upfront.
            recommended = torch.mps.recommended_max_memory()
            model_size_estimate = 4 * 1024 * 1024 * 1024  # ~4GB for this model in fp16
            if recommended >= model_size_estimate * 1.5:
                # Enough memory: use device_map to load directly to MPS
                # (avoids 2x memory spike from CPU load + .to("mps") copy)
                print(f"MPS recommended max memory: {recommended / 1024**3:.1f} GiB, loading to GPU...")
                self._model = AutoModel.from_pretrained(
                    self.model_name,
                    torch_dtype=torch.float16,
                    device_map="mps",
                    low_cpu_mem_usage=True,
                )
            else:
                # Not enough MPS memory (e.g. 8GB Mac): use CPU
                print(f"MPS recommended max memory: {recommended / 1024**3:.1f} GiB (too small for model), using CPU")
                self.device = "cpu"
                self._model = AutoModel.from_pretrained(
                    self.model_name,
                    torch_dtype=torch.float32,
                    low_cpu_mem_usage=True,
                )
        else:
            # CPU: load with auto dtype
            self._model = AutoModel.from_pretrained(
                self.model_name,
                torch_dtype="auto",
            )
            self._model = self._model.to(self.device)
        self._model.train(False)

        # On CPU, set batch size to core count (no GPU parallelism to exploit)
        if self.device == "cpu":
            import os
            cpu_batch = os.cpu_count() or 8
            self._current_batch_size = cpu_batch
            print(f"CPU mode: batch size set to {cpu_batch} (core count)")

        print(f"Model loaded on {self.device}. Embedding dim: {settings.embedding_dim}")

    def unload(self):
        """Unload model from memory."""
        if self._model is not None:
            del self._model
            del self._processor
            self._model = None
            self._processor = None
            if self.device == "cuda" and torch.cuda.is_available():
                torch.cuda.empty_cache()

    def embed_image(self, image: Image.Image) -> np.ndarray:
        """Embed a single image.

        Args:
            image: PIL Image

        Returns:
            Embedding vector as numpy array (float32)
        """
        return self.embed_images([image])[0]

    def embed_images(
        self,
        images: Sequence[Image.Image],
        batch_size: int | None = None,
    ) -> list[np.ndarray]:
        """Embed multiple images with batching.

        Args:
            images: List of PIL Images
            batch_size: Override batch size (uses dynamic sizing by default)

        Returns:
            List of embedding vectors as numpy arrays
        """
        if not images:
            return []

        with self._lock:  # Thread safety
            batch_size = batch_size or self._current_batch_size
            embeddings = []

            for i in range(0, len(images), batch_size):
                batch = images[i : i + batch_size]
                try:
                    batch_embeddings = self._embed_batch(batch)
                    embeddings.extend(batch_embeddings)
                except torch.cuda.OutOfMemoryError:
                    # OOM: reduce batch size and retry
                    self._handle_oom()
                    # Retry with smaller batch size
                    batch_embeddings = self._embed_batch_safe(batch)
                    embeddings.extend(batch_embeddings)

            return embeddings

    def _embed_batch(self, images: Sequence[Image.Image]) -> list[np.ndarray]:
        """Embed a batch of images.

        Args:
            images: Batch of PIL Images

        Returns:
            List of embedding vectors
        """
        inputs = self.processor(images=list(images), return_tensors="pt", padding=True)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model.get_image_features(**inputs)

        # Some transformers versions return a model output object instead of a tensor
        if not isinstance(outputs, torch.Tensor):
            outputs = outputs.pooler_output if hasattr(outputs, "pooler_output") else outputs.last_hidden_state[:, 0]

        # Normalize embeddings
        embeddings = outputs / outputs.norm(dim=-1, keepdim=True)
        return [emb.cpu().numpy().astype(np.float32) for emb in embeddings]

    def _embed_batch_safe(self, images: Sequence[Image.Image]) -> list[np.ndarray]:
        """Embed batch with automatic retry on OOM.

        Falls back to single-image processing if needed.
        """
        batch_size = self._current_batch_size
        embeddings = []

        for i in range(0, len(images), batch_size):
            batch = images[i : i + batch_size]
            try:
                batch_embeddings = self._embed_batch(batch)
                embeddings.extend(batch_embeddings)
            except torch.cuda.OutOfMemoryError:
                # Process one at a time as last resort
                torch.cuda.empty_cache()
                for img in batch:
                    try:
                        emb = self._embed_batch([img])
                        embeddings.extend(emb)
                    except torch.cuda.OutOfMemoryError:
                        print(f"Warning: OOM even with single image, skipping")
                        # Return zero vector as placeholder
                        embeddings.append(np.zeros(settings.embedding_dim, dtype=np.float32))

        return embeddings

    def _handle_oom(self):
        """Handle OOM by reducing batch size."""
        torch.cuda.empty_cache()

        old_size = self._current_batch_size
        self._current_batch_size = max(settings.batch_size_min, old_size // 2)

        print(f"OOM: Reducing batch size {old_size} -> {self._current_batch_size}")

    def try_increase_batch_size(self):
        """Try to increase batch size (call periodically)."""
        if self._current_batch_size < settings.batch_size_max:
            self._current_batch_size = min(
                settings.batch_size_max,
                self._current_batch_size + 4,
            )

    def embed_text(self, text: str) -> np.ndarray:
        """Embed a text query.

        Args:
            text: Query string

        Returns:
            Embedding vector as numpy array (float32)
        """
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: Sequence[str]) -> list[np.ndarray]:
        """Embed multiple text queries.

        Args:
            texts: List of query strings

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        with self._lock:  # Thread safety
            # SigLIP 2 requires padding="max_length" and max_length=64
            inputs = self.processor(
                text=list(texts),
                return_tensors="pt",
                padding="max_length",
                max_length=64,
                truncation=True,
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self.model.get_text_features(**inputs)

            # Some transformers versions return a model output object instead of a tensor
            if not isinstance(outputs, torch.Tensor):
                outputs = outputs.pooler_output if hasattr(outputs, "pooler_output") else outputs.last_hidden_state[:, 0]

            # Normalize embeddings
            embeddings = outputs / outputs.norm(dim=-1, keepdim=True)
            return [emb.cpu().numpy().astype(np.float32) for emb in embeddings]


# Global singleton for convenience (optional - can instantiate directly)
_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    """Get global embedder instance."""
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder


def unload_embedder():
    """Unload global embedder to free memory."""
    global _embedder
    if _embedder is not None:
        _embedder.unload()
        _embedder = None
