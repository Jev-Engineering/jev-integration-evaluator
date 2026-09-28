"""Actual public entrypoint and independent baseline observation."""
import json
import sys

from host import EVENTS, public_entry


def main(argv):
    if len(argv) not in (3, 4):
        return 2
    if len(argv) == 4 and argv[3] not in ("permit", "deny"):
        return 2
    permitted = len(argv) == 3 or argv[3] == "permit"
    request = {"task_id": "corpus-" + argv[1], "item": argv[1], "intent": argv[2],
               "permit": permitted, "approved": argv[2] == "summarize"}
    result = public_entry(request)
    print(json.dumps({"result": result, "events": EVENTS}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
