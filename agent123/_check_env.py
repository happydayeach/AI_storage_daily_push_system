import sys
print("executable:", sys.executable)
print("prefix:", sys.prefix)
print("path entries:")
for p in sys.path:
    print(" ", p)
import pytest
print("pytest version:", pytest.__version__)
