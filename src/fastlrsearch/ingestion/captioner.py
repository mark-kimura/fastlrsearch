"""Florence-2 caption and tag generation.

Runs as a background task after embedding completes.
Generates captions and tags for BM25 text search.
"""

import re
from typing import Any, Sequence

import torch
from PIL import Image
from transformers import AutoModelForCausalLM, AutoProcessor

from fastlrsearch.config import settings


class Captioner:
    """Florence-2 captioner for generating image descriptions and tags.

    Generates both a short caption and a set of tags for each image.
    """

    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
    ):
        """Initialize captioner.

        Args:
            model_name: HuggingFace model ID (defaults to settings)
            device: Compute device (defaults to settings)
        """
        self.model_name = model_name or settings.caption_model
        self.device = device or settings.get_device()

        # Lazy loading
        self._model: Any = None
        self._processor: Any = None

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
        """Load model and processor."""
        print(f"Loading {self.model_name} on {self.device}...")

        self._processor = AutoProcessor.from_pretrained(
            self.model_name, trust_remote_code=True
        )
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_name, trust_remote_code=True
        )
        self._model = self._model.to(self.device)
        self._model.eval()

        print("Captioner loaded.")

    def unload(self):
        """Unload model from memory."""
        if self._model is not None:
            del self._model
            del self._processor
            self._model = None
            self._processor = None
            if self.device == "cuda":
                torch.cuda.empty_cache()

    def caption_image(self, image: Image.Image) -> tuple[str, list[str]]:
        """Generate caption and tags for a single image.

        Args:
            image: PIL Image

        Returns:
            Tuple of (caption, list of tags)
        """
        results = self.caption_images([image])
        return results[0] if results else ("", [])

    def caption_images(
        self,
        images: Sequence[Image.Image],
        batch_size: int | None = None,
    ) -> list[tuple[str, list[str]]]:
        """Generate captions and tags for multiple images.

        Args:
            images: List of PIL Images
            batch_size: Override batch size

        Returns:
            List of (caption, tags) tuples
        """
        if not images:
            return []

        batch_size = batch_size or settings.caption_batch_size
        results = []

        for i in range(0, len(images), batch_size):
            batch = list(images[i : i + batch_size])

            # Get short captions
            captions = self._generate_batch(batch, "<CAPTION>")

            # Get detailed descriptions for tag extraction
            details = self._generate_batch(batch, "<MORE_DETAILED_CAPTION>")

            for caption, detail in zip(captions, details):
                tags = self._extract_tags(detail)
                results.append((caption, tags))

        return results

    def _generate_batch(
        self,
        images: list[Image.Image],
        task_prompt: str,
    ) -> list[str]:
        """Generate text for a batch using a specific task prompt.

        Args:
            images: List of PIL Images
            task_prompt: Florence-2 task prompt

        Returns:
            List of generated texts
        """
        results = []

        # Florence-2 doesn't support true batching well, process one at a time
        for image in images:
            try:
                inputs = self.processor(
                    text=task_prompt,
                    images=image,
                    return_tensors="pt",
                )
                inputs = {k: v.to(self.device) for k, v in inputs.items()}

                with torch.no_grad():
                    generated_ids = self.model.generate(
                        **inputs,
                        max_new_tokens=256,
                        num_beams=3,
                        do_sample=False,
                    )

                generated_text = self.processor.batch_decode(
                    generated_ids, skip_special_tokens=True
                )[0]

                # Parse Florence-2 output format
                parsed = self._parse_output(generated_text, task_prompt)
                results.append(parsed)

            except Exception as e:
                print(f"Warning: Caption generation failed: {e}")
                results.append("")

        return results

    def _parse_output(self, text: str, task_prompt: str) -> str:
        """Parse Florence-2 output format.

        Florence-2 outputs in format: "<task>text</task>"
        """
        # Remove task tags if present
        task_name = task_prompt.strip("<>")

        # Try to find tagged content
        pattern = f"<{task_name}>(.*?)</{task_name}>"
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()

        # Fallback: return as-is after removing any tags
        return re.sub(r"<[^>]+>", "", text).strip()

    def _extract_tags(self, description: str) -> list[str]:
        """Extract meaningful tags from a detailed description.

        Uses simple NLP heuristics to extract nouns and adjectives.

        Args:
            description: Detailed image description

        Returns:
            List of tags (lowercased, deduplicated)
        """
        # Simple extraction: split on common delimiters and filter
        # More sophisticated NLP could be added later

        # Common stop words to exclude
        stop_words = {
            "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "must", "shall", "can", "need", "dare",
            "and", "or", "but", "if", "then", "else", "when", "where", "why",
            "how", "what", "which", "who", "whom", "this", "that", "these",
            "those", "i", "you", "he", "she", "it", "we", "they", "them",
            "my", "your", "his", "her", "its", "our", "their", "mine", "yours",
            "in", "on", "at", "to", "for", "of", "with", "by", "from", "up",
            "about", "into", "through", "during", "before", "after", "above",
            "below", "between", "under", "again", "further", "once", "here",
            "there", "all", "each", "few", "more", "most", "other", "some",
            "such", "no", "nor", "not", "only", "own", "same", "so", "than",
            "too", "very", "just", "also", "now", "image", "photo", "picture",
            "shows", "showing", "depicted", "scene", "visible", "appears",
        }

        # Tokenize and filter
        words = re.findall(r"\b[a-zA-Z]{3,}\b", description.lower())
        tags = [w for w in words if w not in stop_words]

        # Deduplicate while preserving order
        seen = set()
        unique_tags = []
        for tag in tags:
            if tag not in seen:
                seen.add(tag)
                unique_tags.append(tag)

        # Limit to reasonable number of tags
        return unique_tags[:20]


# Global singleton
_captioner: Captioner | None = None


def get_captioner() -> Captioner:
    """Get global captioner instance."""
    global _captioner
    if _captioner is None:
        _captioner = Captioner()
    return _captioner


def unload_captioner():
    """Unload global captioner to free memory."""
    global _captioner
    if _captioner is not None:
        _captioner.unload()
        _captioner = None
