"""Actual package entrypoint for subprocess baseline checks."""
import json
import sys

from app.pipeline import entry


if __name__ == "__main__":
    item, action, permit = sys.argv[1:4]
    print(json.dumps(entry({"item": item, "action": action,
                            "permit": permit == "yes"}), sort_keys=True))
