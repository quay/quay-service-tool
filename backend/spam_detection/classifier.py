import hashlib
import json
import math
import os
import re
from collections import Counter
from datetime import datetime

from . import store


DEFAULT_TOKEN_PATTERN = r"[a-z0-9][a-z0-9_-]*"
HYPERLINK_PATTERN = re.compile(r"\bhttps?://[^\s<>()]+", re.IGNORECASE)
DEFAULT_FEATURE_CONFIG = {
    "token_pattern": DEFAULT_TOKEN_PATTERN,
    "include_repository_name": False,
}
MAX_ARTIFACT_VERSION_LENGTH = 128
DEFAULT_MIN_SPAM_EXAMPLES = 10
DEFAULT_MIN_HAM_EXAMPLES = 10


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
    return {
        "token_pattern": DEFAULT_TOKEN_PATTERN,
        "include_repository_name": bool(feature_config.get("include_repository_name", False)),
    }


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
    if not examples:
        raise ClassifierError("at least one training example is required")

    spam_counts = Counter()
    ham_counts = Counter()
    spam_examples = 0
    ham_examples = 0

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
    training_corpus_version = f"{len(examples)}-{hash_examples(examples)}"
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
            raise ClassifierError("artifact path already exists with different content")
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
    feature_config = artifact.get("feature_config") or DEFAULT_FEATURE_CONFIG
    text = repository_text(description, repository_name, feature_config)
    tokens = tokenize(text, feature_config)
    score = posterior_spam_probability(artifact, tokens)
    threshold = threshold_for_visibility(artifact, visibility)
    return {
        "allowed": score < threshold,
        "score": score,
        "threshold": threshold,
        "explanation": explain_tokens(artifact, tokens),
    }


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
