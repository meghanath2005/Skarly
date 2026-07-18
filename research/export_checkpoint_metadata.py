"""Export human-readable training metadata without copying model weights."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    import torch

    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    metadata = {key: value for key, value in checkpoint.items() if key != "model_state"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
