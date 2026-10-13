"""Shared publisher checks for the desktop updater and release build."""
import base64
import binascii
import re


def validate_publisher(publisher, expected_repository=None):
    if not isinstance(publisher, dict):
        raise ValueError("publisher.json must contain a JSON object.")
    repo = publisher.get("repository", "")
    if not isinstance(repo, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Update publishing is not configured. The project owner must set the GitHub owner/repository in publisher.json; see docs/PUBLISHING.md. Installing a newer NextUp EXE keeps your saved settings.")
    key = publisher.get("public_key", "")
    try:
        if not isinstance(key, str) or len(base64.b64decode(key, validate=True)) != 32:
            raise ValueError()
    except (ValueError, binascii.Error):
        raise ValueError("The publisher's Ed25519 public key is missing or invalid. The project owner must complete docs/PUBLISHING.md before distributing in-app updates.") from None
    if publisher.get("channel") not in ("beta", "stable"):
        raise ValueError("Set publisher.json channel to beta or stable.")
    if expected_repository and repo.lower() != expected_repository.lower():
        raise ValueError("publisher.json repository does not match the GitHub repository running this release. Configure the publisher before building.")
