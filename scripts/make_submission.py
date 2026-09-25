"""Build a Kaggle submission from a generation.

    python scripts/make_submission.py              # from avlod/best
    python scripts/make_submission.py --gen 7      # from avlod/avlod_007

Creates submission/main.py and submission/submission.tar.gz (main.py at the root).
Then:  kaggle competitions submit kaggriculture -f submission/main.py -m "avlod 7"
"""
import argparse
import os
import shutil
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", type=int, default=None)
    args = ap.parse_args()
    src = os.path.join(ROOT, "avlod", "best" if args.gen is None else f"avlod_{args.gen:03d}", "main.py")
    if not os.path.exists(src):
        raise SystemExit(f"{src} not found - train first: python -m trainer.evolve")
    out = os.path.join(ROOT, "submission")
    os.makedirs(out, exist_ok=True)
    shutil.copy(src, os.path.join(out, "main.py"))
    with tarfile.open(os.path.join(out, "submission.tar.gz"), "w:gz") as t:
        t.add(os.path.join(out, "main.py"), arcname="main.py")
    print(f"submission/main.py <- {os.path.relpath(src, ROOT)}")
    print("kaggle competitions submit kaggriculture -f submission/main.py -m \"...\"")


if __name__ == "__main__":
    main()
