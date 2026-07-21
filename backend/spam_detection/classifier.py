import hashlib
import json
import math
import os
import re
from collections import Counter
from datetime import datetime

from . import store


DEFAULT_TOKEN_PATTERN = r"[a-z0-9][a-z0-9_-]*"
DEFAULT_CLASSIFICATION_WINDOW_TOKENS = 128
DEFAULT_CLASSIFICATION_WINDOW_STRIDE = 64
MAX_CLASSIFICATION_WINDOW_TOKENS = 4096
HYPERLINK_PATTERN = re.compile(r"\bhttps?://[^\s<>()]+", re.IGNORECASE)
DEFAULT_FEATURE_CONFIG = {
    "token_pattern": DEFAULT_TOKEN_PATTERN,
    "include_repository_name": False,
    "classification_window_tokens": DEFAULT_CLASSIFICATION_WINDOW_TOKENS,
    "classification_window_stride": DEFAULT_CLASSIFICATION_WINDOW_STRIDE,
}
MAX_ARTIFACT_VERSION_LENGTH = 128
DEFAULT_MIN_SPAM_EXAMPLES = 10
DEFAULT_MIN_HAM_EXAMPLES = 10
DEFAULT_MAX_ARTIFACT_BYTES = 25 * 1024 * 1024
REQUIRED_ARTIFACT_FIELDS = {
    "version": str,
    "training_corpus_version": str,
    "spam_prior": (int, float),
    "ham_prior": (int, float),
    "token_spam_counts": dict,
    "token_ham_counts": dict,
    "spam_token_total": int,
    "ham_token_total": int,
    "vocabulary_size": int,
    "smoothing": (int, float),
    "ingress_threshold": (int, float),
    "ingress_thresholds": dict,
    "feature_config": dict,
    "training_metrics": dict,
}


class ClassifierError(Exception):
    pass


def artifact_dir(config):
    return config.get("SPAM_DETECTION_ARTIFACT_DIR") or "spam_detection_artifacts"


def min_spam_examples(config):
    return int(config.get("SPAM_DETECTION_MIN_SPAM_EXAMPLES", DEFAULT_MIN_SPAM_EXAMPLES))


def min_ham_examples(config):
    return int(config.get("SPAM_DETECTION_MIN_HAM_EXAMPLES", DEFAULT_MIN_HAM_EXAMPLES))


def generated_artifact_version():
    return datetime.utcnow().strftime("%Y%m%d%H%M%S%f")


def validate_artifact_version(version):
    if not version or not isinstance(version, str):
        raise ClassifierError("artifact version is required")
    if len(version) > MAX_ARTIFACT_VERSION_LENGTH:
        raise ClassifierError("artifact version is too long")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", version):
        raise ClassifierError("artifact version may only contain letters, numbers, dots, underscores, and dashes")
    return version


def validate_feature_config(feature_config):
    feature_config = feature_config or DEFAULT_FEATURE_CONFIG
    token_pattern = feature_config.get("token_pattern", DEFAULT_TOKEN_PATTERN)
    if token_pattern != DEFAULT_TOKEN_PATTERN:
        raise ClassifierError("custom token_pattern is not supported in the initial spam detector")
    window_tokens = _feature_config_int(
        feature_config,
        "classification_window_tokens",
        DEFAULT_CLASSIFICATION_WINDOW_TOKENS,
    )
    window_stride = _feature_config_int(
        feature_config,
        "classification_window_stride",
        DEFAULT_CLASSIFICATION_WINDOW_STRIDE,
    )
    if window_tokens > MAX_CLASSIFICATION_WINDOW_TOKENS:
        raise ClassifierError(
            f"classification_window_tokens must be {MAX_CLASSIFICATION_WINDOW_TOKENS} or fewer"
        )
    if window_stride > window_tokens:
        raise ClassifierError(
            "classification_window_stride must not exceed classification_window_tokens"
        )
    return {
        "token_pattern": DEFAULT_TOKEN_PATTERN,
        "include_repository_name": bool(feature_config.get("include_repository_name", False)),
        "classification_window_tokens": window_tokens,
        "classification_window_stride": window_stride,
    }


def _feature_config_int(feature_config, field, default):
    value = feature_config.get(field, default)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ClassifierError(f"{field} must be a positive integer")
    return value


def tokenize(text, feature_config=None):
    feature_config = validate_feature_config(feature_config)
    pattern = feature_config.get("token_pattern", DEFAULT_TOKEN_PATTERN)
    return [match.group(0).lower() for match in re.finditer(pattern, text or "", re.IGNORECASE)]


def contains_hyperlink(text):
    return HYPERLINK_PATTERN.search(text or "") is not None


def repository_text(description, repository_name=None, feature_config=None):
    feature_config = feature_config or DEFAULT_FEATURE_CONFIG
    parts = [description or ""]
    if feature_config.get("include_repository_name") and repository_name:
        parts.append(repository_name)
    return " ".join(parts)


def effective_ingress_threshold(config, classifier):
    policy = store.get_policy(config)
    if policy and policy.get("active_classifier_id") == classifier["id"]:
        return float(policy.get("ingress_threshold"))
    return float(classifier["ingress_threshold"])


def ingress_thresholds(threshold):
    return {
        "public": float(threshold),
        "private": max(float(threshold), 0.98),
    }


def training_metrics(config, total_examples, spam_examples, ham_examples):
    return {
        "example_count": total_examples,
        "spam_examples": spam_examples,
        "ham_examples": ham_examples,
        "spam_ratio": spam_examples / total_examples if total_examples else 0,
        "ham_ratio": ham_examples / total_examples if total_examples else 0,
        "min_spam_examples": min_spam_examples(config),
        "min_ham_examples": min_ham_examples(config),
        "precision": None,
        "recall": None,
        "validation_status": "not_available",
    }


def validate_training_corpus(config, spam_examples, ham_examples):
    min_spam = min_spam_examples(config)
    min_ham = min_ham_examples(config)
    if spam_examples < min_spam:
        raise ClassifierError(f"training requires at least {min_spam} spam examples")
    if ham_examples < min_ham:
        raise ClassifierError(f"training requires at least {min_ham} ham examples")


def validate_artifact_training_metrics(config, artifact):
    metrics = artifact.get("training_metrics") or {}
    spam_examples = metrics.get("spam_examples")
    ham_examples = metrics.get("ham_examples")
    if spam_examples is None or ham_examples is None:
        raise ClassifierError("artifact is missing training metrics")
    validate_training_corpus(config, int(spam_examples), int(ham_examples))


def validate_artifact(config, artifact):
    if not isinstance(artifact, dict):
        raise ClassifierError("artifact must be a JSON object")
    for field, expected_type in REQUIRED_ARTIFACT_FIELDS.items():
        if field not in artifact:
            raise ClassifierError(f"artifact is missing required field: {field}")
        if not isinstance(artifact[field], expected_type):
            raise ClassifierError(f"artifact field has invalid type: {field}")

    validate_artifact_version(artifact["version"])
    validate_feature_config(artifact["feature_config"])
    validate_artifact_training_metrics(config, artifact)
    if artifact["spam_prior"] <= 0 or artifact["ham_prior"] <= 0:
        raise ClassifierError("artifact priors must be greater than zero")
    if artifact["spam_token_total"] < 0 or artifact["ham_token_total"] < 0:
        raise ClassifierError("artifact token totals must be non-negative")
    if artifact["vocabulary_size"] <= 0:
        raise ClassifierError("artifact vocabulary size must be greater than zero")
    if artifact["smoothing"] <= 0:
        raise ClassifierError("artifact smoothing must be greater than zero")
    if not 0 <= float(artifact["ingress_threshold"]) <= 1:
        raise ClassifierError("artifact ingress threshold must be between 0 and 1")
    for counts_field in ("token_spam_counts", "token_ham_counts"):
        for token, count in artifact[counts_field].items():
            if not isinstance(token, str) or not isinstance(count, int) or count < 0:
                raise ClassifierError(f"artifact field has invalid token counts: {counts_field}")
    return artifact


def import_classifier_artifact(config, name, artifact_content, enabled=False, operator=None):
    if not name or not name.strip():
        raise ClassifierError("name is required")
    max_bytes = int(config.get("SPAM_DETECTION_MAX_ARTIFACT_BYTES", DEFAULT_MAX_ARTIFACT_BYTES))
    if not artifact_content:
        raise ClassifierError("artifact file is required")
    if len(artifact_content) > max_bytes:
        raise ClassifierError(f"artifact must be {max_bytes} bytes or fewer")
    try:
        artifact = json.loads(artifact_content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClassifierError("artifact must contain valid UTF-8 JSON") from exc
    validate_artifact(config, artifact)

    artifact_sha256 = hashlib.sha256(artifact_content).hexdigest()
    existing = store.get_classifier_by_artifact_version(config, artifact["version"])
    if existing:
        if (
            not existing.get("base_artifact_sha256")
            and existing.get("base_model_snapshot_json") == artifact
        ):
            existing = store.update_classifier_base_identity(
                config,
                existing["id"],
                artifact["version"],
                artifact_sha256,
            )
        existing_sha256 = existing.get("base_artifact_sha256") or existing.get(
            "artifact_sha256"
        )
        if existing_sha256 != artifact_sha256:
            raise ClassifierError("artifact version already exists with different content")
        if enabled and not existing.get("enabled"):
            existing = store.update_classifier(
                config,
                existing["uuid"],
                {"enabled": True},
                operator=operator,
            )
        return existing, False

    path = os.path.join(artifact_dir(config), f"spam-classifier-{artifact['version']}.json")
    write_artifact_bytes_to_path(artifact_content, path)
    created = store.create_imported_classifier(
        config,
        {"name": name.strip(), "enabled": enabled},
        artifact,
        path,
        artifact_sha256,
        operator=operator,
    )
    return created, True


def apply_ingress_policy(config, classifier, artifact, artifact_version=None):
    artifact = dict(artifact)
    threshold = effective_ingress_threshold(config, classifier)
    previous_threshold = float(artifact.get("ingress_threshold", threshold))

    if artifact_version:
        artifact["version"] = validate_artifact_version(artifact_version)
    elif previous_threshold != threshold:
        artifact["version"] = generated_artifact_version()

    artifact["ingress_threshold"] = threshold
    artifact["ingress_thresholds"] = ingress_thresholds(threshold)
    return artifact


def train_classifier(config, classifier_uuid, artifact_version=None):
    classifier = store.get_classifier(config, classifier_uuid)
    if not classifier:
        raise ClassifierError("classifier not found")

    feature_config = validate_feature_config(classifier.get("feature_config_json") or DEFAULT_FEATURE_CONFIG)
    examples = store.list_training_examples(config, classifier["id"])
    base_artifact = classifier.get("base_model_snapshot_json") or {}
    if not examples and not base_artifact:
        raise ClassifierError("at least one training example is required")

    if base_artifact:
        validate_artifact(config, base_artifact)
    base_metrics = base_artifact.get("training_metrics") or {}
    spam_counts = Counter(base_artifact.get("token_spam_counts") or {})
    ham_counts = Counter(base_artifact.get("token_ham_counts") or {})
    spam_examples = int(base_metrics.get("spam_examples") or 0)
    ham_examples = int(base_metrics.get("ham_examples") or 0)

    for example in examples:
        text = repository_text(
            example["text"],
            example.get("repository_name"),
            feature_config,
        )
        tokens = tokenize(text, feature_config)
        if example["label"] == "spam":
            spam_examples += 1
            spam_counts.update(tokens)
        elif example["label"] == "ham":
            ham_examples += 1
            ham_counts.update(tokens)

    validate_training_corpus(config, spam_examples, ham_examples)

    vocabulary = set(spam_counts) | set(ham_counts)
    total_examples = spam_examples + ham_examples
    version = validate_artifact_version(artifact_version or generated_artifact_version())
    if store.artifact_version_exists(config, version, classifier["id"]):
        raise ClassifierError("artifact version is already used by another classifier")
    example_version = f"{len(examples)}-{hash_examples(examples)}"
    base_version = base_artifact.get("training_corpus_version")
    training_corpus_version = (
        f"{base_version}+{example_version}" if base_version else example_version
    )
    threshold = effective_ingress_threshold(config, classifier)

    artifact = {
        "version": version,
        "spam_prior": spam_examples / total_examples,
        "ham_prior": ham_examples / total_examples,
        "token_spam_counts": dict(sorted(spam_counts.items())),
        "token_ham_counts": dict(sorted(ham_counts.items())),
        "spam_token_total": sum(spam_counts.values()),
        "ham_token_total": sum(ham_counts.values()),
        "vocabulary_size": max(len(vocabulary), 1),
        "smoothing": 1.0,
        "ingress_threshold": threshold,
        "ingress_thresholds": ingress_thresholds(threshold),
        "feature_config": feature_config,
        "training_corpus_version": training_corpus_version,
        "training_metrics": training_metrics(config, total_examples, spam_examples, ham_examples),
    }

    path, sha256 = write_artifact(config, artifact)
    return store.update_classifier_artifact(config, classifier["id"], artifact, path, sha256)


def export_artifact(config, classifier_uuid, artifact_version=None, output_path=None):
    classifier = store.get_classifier(config, classifier_uuid)
    if not classifier:
        raise ClassifierError("classifier not found")
    artifact = load_artifact_from_classifier(classifier)
    artifact = apply_ingress_policy(config, classifier, artifact, artifact_version)
    validate_artifact_training_metrics(config, artifact)
    if store.artifact_version_exists(config, artifact["version"], classifier["id"]):
        raise ClassifierError("artifact version is already used by another classifier")
    path, sha256 = write_artifact(config, artifact)
    updated = store.update_classifier_artifact(config, classifier["id"], artifact, path, sha256)
    if output_path:
        export_path, export_sha256 = write_artifact_to_path(artifact, output_path)
        updated["export_path"] = export_path
        updated["export_sha256"] = export_sha256
    return updated


def promote_artifact(config, classifier_uuid):
    destination = config.get("SPAM_DETECTION_PROMOTED_ARTIFACT_PATH")
    if not destination:
        raise ClassifierError("SPAM_DETECTION_PROMOTED_ARTIFACT_PATH is not configured")
    configured = store.get_classifier(config, classifier_uuid)
    if not configured:
        raise ClassifierError("classifier not found")
    artifact_path = configured.get("artifact_path")
    if not artifact_path or not os.path.isfile(artifact_path):
        raise ClassifierError("classifier has no generated artifact")
    with open(artifact_path, "rb") as artifact_file:
        content = artifact_file.read()
    try:
        artifact = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClassifierError("classifier artifact is not valid UTF-8 JSON") from exc
    validate_artifact(config, artifact)
    actual_sha256 = hashlib.sha256(content).hexdigest()
    if configured.get("artifact_sha256") != actual_sha256:
        raise ClassifierError("classifier artifact checksum does not match stored metadata")
    promoted_path, promoted_sha256 = write_artifact_bytes_to_path(
        content,
        destination,
        overwrite=True,
    )
    return {
        "classifier": configured,
        "promoted_path": promoted_path,
        "promoted_sha256": promoted_sha256,
    }


def hash_examples(examples):
    digest = hashlib.sha256()
    for example in examples:
        digest.update((example["label"] + "\0" + example["text"]).encode("utf-8"))
    return digest.hexdigest()[:12]


def artifact_bytes(artifact):
    return json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode("utf-8")


def write_artifact(config, artifact):
    validate_artifact_version(artifact["version"])
    output_dir = artifact_dir(config)
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"spam-classifier-{artifact['version']}.json")
    return write_artifact_to_path(artifact, path)


def write_artifact_to_path(artifact, path):
    validate_artifact_version(artifact["version"])
    output_dir = os.path.dirname(os.path.abspath(path))
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    content = artifact_bytes(artifact)
    if os.path.exists(path):
        with open(path, "rb") as existing_file:
            existing_content = existing_file.read()
        if existing_content != content:
            try:
                existing_artifact = json.loads(existing_content.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ClassifierError("artifact path already exists with different content") from exc
            if existing_artifact != artifact:
                raise ClassifierError("artifact path already exists with different content")
            content = existing_content
    else:
        tmp_path = f"{path}.tmp.{os.getpid()}"
        with open(tmp_path, "wb") as artifact_file:
            artifact_file.write(content)
            artifact_file.flush()
            os.fsync(artifact_file.fileno())
        os.replace(tmp_path, path)
    sha256 = hashlib.sha256(content).hexdigest()
    sha_path = f"{path}.sha256"
    tmp_sha_path = f"{sha_path}.tmp.{os.getpid()}"
    with open(tmp_sha_path, "w", encoding="utf-8") as sha_file:
        sha_file.write(f"{sha256}  {os.path.basename(path)}\n")
        sha_file.flush()
        os.fsync(sha_file.fileno())
    os.replace(tmp_sha_path, sha_path)
    return path, sha256


def write_artifact_bytes_to_path(content, path, overwrite=False):
    output_dir = os.path.dirname(os.path.abspath(path))
    os.makedirs(output_dir, exist_ok=True)
    write_content = not os.path.exists(path)
    if os.path.exists(path):
        with open(path, "rb") as existing_file:
            existing_content = existing_file.read()
            if existing_content != content and not overwrite:
                raise ClassifierError("artifact path already exists with different content")
            write_content = existing_content != content
    if write_content:
        tmp_path = f"{path}.tmp.{os.getpid()}"
        with open(tmp_path, "wb") as artifact_file:
            artifact_file.write(content)
            artifact_file.flush()
            os.fsync(artifact_file.fileno())
        os.replace(tmp_path, path)
    sha256 = hashlib.sha256(content).hexdigest()
    sha_path = f"{path}.sha256"
    tmp_sha_path = f"{sha_path}.tmp.{os.getpid()}"
    with open(tmp_sha_path, "w", encoding="utf-8") as sha_file:
        sha_file.write(f"{sha256}  {os.path.basename(path)}\n")
        sha_file.flush()
        os.fsync(sha_file.fileno())
    os.replace(tmp_sha_path, sha_path)
    return path, sha256


def load_artifact_from_classifier(classifier):
    artifact = classifier.get("model_snapshot_json")
    if artifact:
        return artifact
    artifact_path = classifier.get("artifact_path")
    if artifact_path:
        with open(artifact_path, "r", encoding="utf-8") as artifact_file:
            return json.load(artifact_file)
    raise ClassifierError("classifier has no trained artifact")


def classify_text(artifact, description, repository_name=None, visibility=None):
    feature_config = validate_feature_config(artifact.get("feature_config"))
    text = repository_text(description, repository_name, feature_config)
    tokens = tokenize(text, feature_config)
    windows = classification_windows(tokens, feature_config)
    scored_windows = [
        (start, window, posterior_spam_probability(artifact, window))
        for start, window in windows
    ]
    window_start, winning_window, score = max(scored_windows, key=lambda item: item[2])
    threshold = threshold_for_visibility(artifact, visibility)
    explanation = explain_tokens(artifact, winning_window)
    explanation.update(
        {
            "token_count": len(tokens),
            "window_count": len(windows),
            "window_start": window_start,
            "window_end": window_start + len(winning_window),
            "window_token_count": len(winning_window),
        }
    )
    return {
        "allowed": score < threshold,
        "score": score,
        "threshold": threshold,
        "explanation": explanation,
    }


def classification_windows(tokens, feature_config):
    window_tokens = feature_config["classification_window_tokens"]
    window_stride = feature_config["classification_window_stride"]
    if len(tokens) <= window_tokens:
        return [(0, tokens)]

    last_start = len(tokens) - window_tokens
    starts = list(range(0, last_start + 1, window_stride))
    if starts[-1] != last_start:
        starts.append(last_start)
    return [(start, tokens[start : start + window_tokens]) for start in starts]


def posterior_spam_probability(artifact, tokens):
    spam_counts = artifact.get("token_spam_counts") or {}
    ham_counts = artifact.get("token_ham_counts") or {}
    spam_total = artifact.get("spam_token_total")
    ham_total = artifact.get("ham_token_total")
    vocabulary_size = artifact.get("vocabulary_size")
    smoothing = float(artifact.get("smoothing", 1.0))
    spam_prior = float(artifact.get("spam_prior", 0.5))
    ham_prior = float(artifact.get("ham_prior", 0.5))

    if spam_total is None:
        spam_total = sum(spam_counts.values())
    if ham_total is None:
        ham_total = sum(ham_counts.values())
    if vocabulary_size is None:
        vocabulary_size = len(set(spam_counts) | set(ham_counts)) or 1

    log_spam = math.log(spam_prior)
    log_ham = math.log(ham_prior)
    spam_denominator = spam_total + smoothing * vocabulary_size
    ham_denominator = ham_total + smoothing * vocabulary_size

    for token in tokens:
        spam_count = spam_counts.get(token, 0)
        ham_count = ham_counts.get(token, 0)
        log_spam += math.log((spam_count + smoothing) / spam_denominator)
        log_ham += math.log((ham_count + smoothing) / ham_denominator)

    if log_spam >= log_ham:
        return 1 / (1 + math.exp(log_ham - log_spam))
    return math.exp(log_spam - log_ham) / (1 + math.exp(log_spam - log_ham))


def threshold_for_visibility(artifact, visibility):
    thresholds = artifact.get("ingress_thresholds") or {}
    if visibility and visibility in thresholds:
        return float(thresholds[visibility])
    return float(artifact.get("ingress_threshold", 0.9))


def explain_tokens(artifact, tokens, limit=8):
    spam_counts = artifact.get("token_spam_counts") or {}
    ham_counts = artifact.get("token_ham_counts") or {}
    spam_total = artifact.get("spam_token_total") or sum(spam_counts.values())
    ham_total = artifact.get("ham_token_total") or sum(ham_counts.values())
    vocabulary_size = artifact.get("vocabulary_size") or len(set(spam_counts) | set(ham_counts)) or 1
    smoothing = float(artifact.get("smoothing", 1.0))
    spam_denominator = spam_total + smoothing * vocabulary_size
    ham_denominator = ham_total + smoothing * vocabulary_size

    seen = sorted(set(tokens))
    weights = []
    for token in seen:
        spam_probability = (spam_counts.get(token, 0) + smoothing) / spam_denominator
        ham_probability = (ham_counts.get(token, 0) + smoothing) / ham_denominator
        weights.append(
            {
                "token": token,
                "spam_count": spam_counts.get(token, 0),
                "ham_count": ham_counts.get(token, 0),
                "weight": math.log(spam_probability / ham_probability),
            }
        )
    weights.sort(key=lambda item: abs(item["weight"]), reverse=True)
    return {"tokens": weights[:limit], "token_count": len(tokens)}
