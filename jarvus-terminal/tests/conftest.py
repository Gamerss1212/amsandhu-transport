import os
import sys
import tempfile

# tests never touch the owner's real credential vault or data folder
os.environ.setdefault("MAB_SECRETS_DIR", tempfile.mkdtemp(prefix="jarvus-vault-"))
os.environ["MAB_SECRETS_NO_KEYRING"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), "market_analysis_bots"))
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), "market_analysis_bots", "tests"))
