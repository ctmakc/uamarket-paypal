import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ALLOW_INSECURE_DEV", "true")
# Speed, not safety: test databases skip fsync, and PIN hashing uses the lowest work factor
# the locker module accepts. Production reads neither default (see app/db.py, locker.py).
os.environ.setdefault("SQLITE_FAST_UNSAFE", "true")
os.environ.setdefault("LOCKER_PIN_KDF_ITERATIONS", "1000")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Locker pickup is offered only once the owner has said where the locker is, so a suite
# that exercises pickup orders needs an address of its own. This is a test fixture and
# nothing else: the shop's real address is the owner's to give (docs/OWNER-ACTIONS.md).
# setdefault, so a run that sets its own value keeps it, and tests that check the
# unconfigured state delete the variable themselves.
os.environ.setdefault("PICKUP_ADDRESS", "12 Test Lane, Ottawa ON K1A 0B1")

# Seeding the demo catalogue writes the generated demonstration pictures to MEDIA_ROOT.
# A run gets a throwaway directory so it never leaves WebP files in the checkout; a test
# that sets its own MEDIA_ROOT keeps it.
os.environ.setdefault("MEDIA_ROOT", tempfile.mkdtemp(prefix="uamarket-test-media-"))
