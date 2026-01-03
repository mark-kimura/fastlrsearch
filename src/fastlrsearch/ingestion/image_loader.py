"""Image loading with RAW support and EXIF orientation handling.

Handles JPEG, PNG, WebP, and RAW files (CR2, DNG, NEF, ARW, RAF).
Uses embedded previews from RAW files when available for speed.
"""

from io import BytesIO
from pathlib import Path

import exifread
import numpy as np
from PIL import Image

from fastlrsearch.config import settings

# RAW extensions that need special handling
RAW_EXTENSIONS = {".cr2", ".dng", ".nef", ".arw", ".raf"}

# EXIF orientation to PIL transpose operation
ORIENTATION_TRANSFORMS = {
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}


def get_exif_orientation(filepath: Path) -> int:
    """Extract EXIF orientation from image file.

    Returns:
        Orientation value (1-8), or 1 if not found
    """
    try:
        with open(filepath, "rb") as f:
            tags = exifread.process_file(f, stop_tag="Orientation", details=False)
            if "Image Orientation" in tags:
                return int(tags["Image Orientation"].values[0])
    except Exception:
        pass
    return 1


def apply_orientation(img: Image.Image, orientation: int) -> Image.Image:
    """Apply EXIF orientation to PIL Image.

    Args:
        img: PIL Image
        orientation: EXIF orientation value (1-8)

    Returns:
        Correctly oriented PIL Image
    """
    if orientation in ORIENTATION_TRANSFORMS:
        return img.transpose(ORIENTATION_TRANSFORMS[orientation])
    return img


def load_raw_preview(filepath: Path) -> Image.Image | None:
    """Extract embedded preview from RAW file.

    Uses rawpy to extract the embedded JPEG thumbnail/preview.
    Falls back to full demosaic if no preview available.

    Args:
        filepath: Path to RAW file

    Returns:
        PIL Image or None if extraction fails
    """
    import rawpy

    try:
        with rawpy.imread(str(filepath)) as raw:
            # Try to extract embedded thumbnail first (fastest)
            try:
                thumb = raw.extract_thumb()
                if thumb.format == rawpy.ThumbFormat.JPEG:  # type: ignore[attr-defined]
                    return Image.open(BytesIO(thumb.data))
                elif thumb.format == rawpy.ThumbFormat.BITMAP:  # type: ignore[attr-defined]
                    return Image.fromarray(thumb.data)
            except rawpy.LibRawNoThumbnailError:  # type: ignore[attr-defined]
                pass

            # Fallback: full demosaic (slower but guaranteed)
            rgb = raw.postprocess(
                use_camera_wb=True,
                output_bps=8,
                no_auto_bright=False,
            )
            return Image.fromarray(rgb)

    except Exception as e:
        print(f"Warning: Failed to load RAW {filepath}: {e}")
        return None


def load_image(filepath: Path, target_size: int | None = None) -> Image.Image | None:
    """Load image from file, handling RAW and EXIF orientation.

    Args:
        filepath: Path to image file
        target_size: Optional long-side resize target

    Returns:
        PIL Image in RGB mode, or None if loading fails
    """
    filepath = Path(filepath)
    ext = filepath.suffix.lower()

    try:
        # Load image based on type
        if ext in RAW_EXTENSIONS:
            img = load_raw_preview(filepath)
            if img is None:
                return None
            # RAW files also have EXIF orientation - read and apply it
            orientation = get_exif_orientation(filepath)
        else:
            img = Image.open(filepath)
            orientation = get_exif_orientation(filepath)

        # Convert to RGB (handles RGBA, L, etc.)
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Apply EXIF orientation
        img = apply_orientation(img, orientation)

        # Resize if target specified
        if target_size is not None:
            img = resize_long_side(img, target_size)

        return img

    except Exception as e:
        print(f"Warning: Failed to load {filepath}: {e}")
        return None


def resize_long_side(img: Image.Image, target: int) -> Image.Image:
    """Resize image so longest side equals target.

    Args:
        img: PIL Image
        target: Target size for longest side

    Returns:
        Resized PIL Image
    """
    w, h = img.size

    if max(w, h) <= target:
        return img

    if w >= h:
        new_w = target
        new_h = int(h * target / w)
    else:
        new_h = target
        new_w = int(w * target / h)

    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)


def image_to_numpy(img: Image.Image) -> np.ndarray:
    """Convert PIL Image to numpy array.

    Args:
        img: PIL Image in RGB mode

    Returns:
        numpy array with shape (H, W, 3), dtype uint8
    """
    return np.array(img, dtype=np.uint8)


def load_for_embedding(filepath: Path) -> Image.Image | None:
    """Load image ready for embedding model.

    Loads, orients, and resizes to model's native input size.

    Args:
        filepath: Path to image file

    Returns:
        PIL Image resized for embedding, or None if loading fails
    """
    return load_image(filepath, target_size=settings.embedding_resize)


def load_for_thumbnail(filepath: Path) -> Image.Image | None:
    """Load image ready for thumbnail generation.

    Args:
        filepath: Path to image file

    Returns:
        PIL Image resized for thumbnail, or None if loading fails
    """
    return load_image(filepath, target_size=settings.thumbnail_size)
