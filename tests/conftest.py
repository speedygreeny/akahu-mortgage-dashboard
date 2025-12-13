import os
import sys

# Ensure the repository root is on sys.path so test modules can import the package
repo_root = os.path.dirname(os.path.dirname(__file__))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
