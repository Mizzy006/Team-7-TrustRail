import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(r"c:\Users\USER\Desktop\Team-7-TrustRail\services\gateway")))
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.seed import ensure_schema_and_seed
try:
    ensure_schema_and_seed()
    print("Success!")
except Exception as e:
    import traceback
    traceback.print_exc()
