#!/usr/bin/env python3
"""
Phase 0: Minimal PyTorch + CUDA test for packaging validation.

This script tests:
1. PyTorch CUDA availability
2. Basic tensor operations on GPU
3. Model loading from transformers (SigLIP)

Run directly: python scripts/test_cuda_packaging.py
Package test: pyinstaller --onefile scripts/test_cuda_packaging.py
"""

import sys


def test_pytorch_cuda():
    """Test basic PyTorch CUDA functionality."""
    print("=" * 60)
    print("Phase 0: PyTorch + CUDA Packaging Test")
    print("=" * 60)

    # Test 1: Import PyTorch
    print("\n[1/5] Importing PyTorch...")
    try:
        import torch
        print(f"  ✓ PyTorch version: {torch.__version__}")
    except ImportError as e:
        print(f"  ✗ Failed to import PyTorch: {e}")
        return False

    # Test 2: CUDA availability
    print("\n[2/5] Checking CUDA availability...")
    if torch.cuda.is_available():
        print(f"  ✓ CUDA available: {torch.cuda.get_device_name(0)}")
        print(f"  ✓ CUDA version: {torch.version.cuda}")
    else:
        print("  ✗ CUDA not available - will use CPU")
        print("  Note: GPU acceleration won't work, but app can still run")

    # Test 3: Basic tensor operation
    print("\n[3/5] Testing tensor operations...")
    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        x = torch.randn(100, 100, device=device)
        y = torch.matmul(x, x.T)
        print(f"  ✓ Tensor ops on {device}: shape {y.shape}")
    except Exception as e:
        print(f"  ✗ Tensor operation failed: {e}")
        return False

    # Test 4: Import transformers
    print("\n[4/5] Importing transformers...")
    try:
        import transformers
        print(f"  ✓ Transformers version: {transformers.__version__}")
    except ImportError as e:
        print(f"  ✗ Failed to import transformers: {e}")
        return False

    # Test 5: Test SigLIP model loading (without downloading if not cached)
    print("\n[5/5] Testing model availability...")
    try:
        from transformers import AutoProcessor, AutoModel
        model_name = "google/siglip-so400m-patch14-384"

        # Just check if we can create the config (doesn't download weights)
        from transformers import AutoConfig
        try:
            config = AutoConfig.from_pretrained(model_name)
            print(f"  ✓ SigLIP config accessible: {config.hidden_size} hidden size")
        except Exception:
            print(f"  ! SigLIP not cached - will download on first use (~1.5GB)")

    except Exception as e:
        print(f"  ✗ Model check failed: {e}")
        return False

    print("\n" + "=" * 60)
    print("✓ All packaging tests passed!")
    print("=" * 60)

    # Print summary for packaging
    print("\nPackaging info:")
    print(f"  Python: {sys.version}")
    print(f"  Platform: {sys.platform}")
    if torch.cuda.is_available():
        print(f"  GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")

    return True


if __name__ == "__main__":
    success = test_pytorch_cuda()
    sys.exit(0 if success else 1)
