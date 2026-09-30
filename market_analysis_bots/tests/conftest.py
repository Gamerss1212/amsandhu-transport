import os
import tempfile

# tests never touch the owner's real credential vault
os.environ.setdefault("MAB_SECRETS_DIR", tempfile.mkdtemp(prefix="mab-vault-"))
os.environ["MAB_SECRETS_NO_KEYRING"] = "1"
