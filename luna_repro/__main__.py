"""CLI takes credentials only from the environment, never command arguments."""

import argparse
import json

from .client import PublishError, load_bundle, publish_bundle, sync


def main(argv=None):
    parser = argparse.ArgumentParser(description="Publish selected LUNA result bundles; never executes research code.")
    commands = parser.add_subparsers(dest="command", required=True)
    publish = commands.add_parser("publish", help="Publish one saved result JSON")
    publish.add_argument("bundle")
    publish.add_argument("--endpoint", help="HTTPS platform base URL; token comes from LUNA_REPRO_TOKEN")
    retry = commands.add_parser("sync", help="Retry local pending results explicitly")
    retry.add_argument("--outbox", default=".luna-repro/outbox")
    retry.add_argument("--endpoint")
    args = parser.parse_args(argv)
    try:
        if args.command == "publish":
            result = publish_bundle(load_bundle(args.bundle), endpoint=args.endpoint)
            code = 0
        else:
            result = sync(args.outbox, endpoint=args.endpoint)
            code = int(any(row["status"] != "published" for row in result))
        print(json.dumps(result, ensure_ascii=False))
        return code
    except (PublishError, ValueError, OSError):
        print("Result not published. Check the selected bundle, HTTPS endpoint and session token.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
