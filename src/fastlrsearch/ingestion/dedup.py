"""Duplicate detection using perceptual hashing (pHash).

Computes perceptual hashes for images to detect near-duplicates.
"""

import imagehash
from PIL import Image


def compute_phash(image: Image.Image, hash_size: int = 16) -> str:
    """Compute perceptual hash for an image.

    Args:
        image: PIL Image
        hash_size: Hash size (default 16 = 256 bits)

    Returns:
        Hex string representation of pHash
    """
    h = imagehash.phash(image, hash_size=hash_size)
    return str(h)


def hamming_distance(hash1: str, hash2: str) -> int:
    """Compute Hamming distance between two pHashes.

    Args:
        hash1: First pHash as hex string
        hash2: Second pHash as hex string

    Returns:
        Hamming distance (number of differing bits)
    """
    h1 = imagehash.hex_to_hash(hash1)
    h2 = imagehash.hex_to_hash(hash2)
    return h1 - h2


def are_similar(hash1: str, hash2: str, threshold: int = 10) -> bool:
    """Check if two images are perceptually similar.

    Args:
        hash1: First pHash as hex string
        hash2: Second pHash as hex string
        threshold: Maximum Hamming distance for similarity (default 10)

    Returns:
        True if images are similar
    """
    return hamming_distance(hash1, hash2) <= threshold


def find_duplicates(
    hashes: dict[str, str],
    threshold: int = 10,
) -> list[set[str]]:
    """Find groups of duplicate images.

    Args:
        hashes: Dict mapping photo_id to pHash
        threshold: Maximum Hamming distance for duplicates

    Returns:
        List of sets, each containing photo_ids of duplicates
    """
    # Simple O(n^2) comparison - could be optimized with LSH for large sets
    items = list(hashes.items())
    n = len(items)

    # Union-find for grouping
    parent = {pid: pid for pid, _ in items}

    def find(x):
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    # Compare all pairs
    for i in range(n):
        pid1, hash1 = items[i]
        for j in range(i + 1, n):
            pid2, hash2 = items[j]
            if are_similar(hash1, hash2, threshold):
                union(pid1, pid2)

    # Group by root
    groups: dict[str, set[str]] = {}
    for pid, _ in items:
        root = find(pid)
        if root not in groups:
            groups[root] = set()
        groups[root].add(pid)

    # Return only groups with more than one member
    return [g for g in groups.values() if len(g) > 1]
