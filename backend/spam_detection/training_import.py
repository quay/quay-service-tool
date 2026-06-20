import csv

from . import store


def import_csv(config, classifier_uuid, path, source="seed_import", operator=None):
    imported = 0
    skipped = 0
    with open(path, newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        if "text" not in reader.fieldnames or "label" not in reader.fieldnames:
            raise ValueError("CSV must include text and label columns")
        for row in reader:
            text = (row.get("text") or "").strip()
            label = (row.get("label") or "").strip().lower()
            if not text or label not in ("spam", "ham"):
                skipped += 1
                continue
            store.add_training_example(
                config,
                classifier_uuid,
                {
                    "text": text,
                    "label": label,
                    "source": source,
                    "source_ref": path,
                },
                operator=operator,
            )
            imported += 1
    return {"imported": imported, "skipped": skipped}
