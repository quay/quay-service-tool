import argparse
import json
import os

import yaml

from spam_detection import (
    DEFAULT_QUARANTINE_DESCRIPTION,
    classifier,
    scanner,
    store,
    training_import,
)
from spam_detection.database import migrate_state_db
from spam_detection.quay_db import check_connection


def load_config():
    config_path = os.environ.get("CONFIG_PATH", "config")
    with open(os.path.join(config_path, "config.yaml"), encoding="utf-8") as config_file:
        config = yaml.load(config_file, Loader=yaml.FullLoader)
    config.setdefault("SPAM_DETECTION_STATE_DB_URI", "sqlite:///spam_detection_state.db")
    config.setdefault("SPAM_DETECTION_BATCH_SIZE", 200)
    config.setdefault("SPAM_DETECTION_SLEEP_BETWEEN_BATCHES", 0.5)
    config.setdefault("SPAM_DETECTION_SCAN_DRY_RUN", True)
    config.setdefault("SPAM_DETECTION_MAX_REPOS", 0)
    config.setdefault("SPAM_DETECTION_API_SCAN_LIMIT", 10000)
    config.setdefault("SPAM_DETECTION_MAX_TRAINING_TEXT_LENGTH", 10000)
    config.setdefault("SPAM_DETECTION_MIN_SPAM_EXAMPLES", classifier.DEFAULT_MIN_SPAM_EXAMPLES)
    config.setdefault("SPAM_DETECTION_MIN_HAM_EXAMPLES", classifier.DEFAULT_MIN_HAM_EXAMPLES)
    config.setdefault("SPAM_DETECTION_INCLUDE_PRIVATE", False)
    config.setdefault(
        "SPAM_DETECTION_QUARANTINE_DESCRIPTION",
        DEFAULT_QUARANTINE_DESCRIPTION,
    )
    return config


def print_json(payload):
    print(json.dumps(payload, indent=2, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description="Quay spam detection service-tool CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("migrate")
    subparsers.add_parser("healthcheck")

    create_classifier = subparsers.add_parser("create-classifier")
    create_classifier.add_argument("--name", required=True)
    create_classifier.add_argument("--enabled", action="store_true")

    import_csv = subparsers.add_parser("import-csv")
    import_csv.add_argument("--classifier", required=True)
    import_csv.add_argument("--path", required=True)
    import_csv.add_argument("--source", default="seed_import")

    train = subparsers.add_parser("train")
    train.add_argument("--classifier", required=True)
    train.add_argument("--artifact-version")

    export_artifact = subparsers.add_parser("export-artifact")
    export_artifact.add_argument("--classifier", required=True)
    export_artifact.add_argument("--artifact-version")
    export_artifact.add_argument(
        "--output-path",
        help="Optional exact artifact file path for build jobs that copy the classifier into the Quay image.",
    )

    scan = subparsers.add_parser("scan")
    scan.add_argument("--source", default="cli")
    scan.add_argument("--dry-run", action="store_true")
    scan.add_argument("--enforce", action="store_true")
    scan.add_argument("--max-repos", type=int)

    args = parser.parse_args()
    config = load_config()

    if args.command == "migrate":
        migrate_state_db(config)
        print_json({"status": "ok"})
        return

    if args.command == "healthcheck":
        migrate_state_db(config)
        check_connection(config.get("SPAM_DETECTION_READONLY_DB_URI"), read_only=True)
        check_connection(config.get("SPAM_DETECTION_WRITE_DB_URI"))
        print_json({"status": "ok"})
        return

    if args.command == "create-classifier":
        created = store.create_classifier(
            config,
            {"name": args.name, "enabled": args.enabled},
            operator="cli",
        )
        print_json({"classifier": created})
        return

    if args.command == "import-csv":
        result = training_import.import_csv(
            config,
            args.classifier,
            args.path,
            source=args.source,
            operator="cli",
        )
        print_json(result)
        return

    if args.command == "train":
        updated = classifier.train_classifier(
            config,
            args.classifier,
            artifact_version=args.artifact_version,
        )
        print_json({"classifier": updated})
        return

    if args.command == "export-artifact":
        updated = classifier.export_artifact(
            config,
            args.classifier,
            artifact_version=args.artifact_version,
            output_path=args.output_path,
        )
        print_json({"classifier": updated})
        return

    if args.command == "scan":
        dry_run = True if args.dry_run else None
        if args.enforce:
            dry_run = False
        run = scanner.run_scan(
            config,
            source=args.source,
            dry_run=dry_run,
            max_repos=args.max_repos,
            operator="cli",
        )
        print_json({"run": run})


if __name__ == "__main__":
    main()
