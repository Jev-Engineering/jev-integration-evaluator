"""Real caller entrypoint for the independent opaque host."""
import json
import sys

from service import Store, serve


def main(argv):
    if len(argv) != 3:
        return 2
    store = Store()
    observation = serve(argv[1], argv[2], store)
    print(json.dumps({"observation": observation, "events": store.events}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
