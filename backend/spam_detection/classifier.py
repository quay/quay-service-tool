import hashlib
import json
import math
import os
import re
from collections import Counter
from datetime import datetime

from . import store


DEFAULT_TOKEN_PATTERN = r"[a-z0-9][a-z0-9_-]*"
DEFAULT_FEATURE_CONFIG = {
    "token_pattern": DEFAULT_TOKEN_PATTERN,
    "include_repository_name": False,
}


class ClassifierError(Exception):
    pass


def artifact_dir(config):
    return config.get("SPAM_DETECTION_ARTIFACT_DIR") or "spam_detection_artifacts"


def tokenize(text, feature_config=None):
    feature_config = feature_config or DEFAULT_FEATURE_CONFIG
    pattern = feature_config.get("token_pattern", DEFAULT_TOKEN_PATTERN)
    return [match.group(0).lower() for match in re.finditer(pattern, text or "", re.IGNORECASE)]


def repository_text(description, repository_name=None, feature_config=None):
    feature_config = feature_config or DEFAULT_FEATURE_CONFIG
    parts = [description or ""]
    if feature_config.get("include_repository_name") and repository_name:
        parts.append(repository_name)
    return " ".join(parts)


def train_classifier(config, classifier_uuid, artifact_version=None):
    classifier = store.get_classifier(config, classifier_uuid)
    if not classifier:
        raise ClassifierError("classifier not found")

    feature_config = classifier.get("feature_config_json") or DEFAULT_FEATURE_CONFIG
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

    if spam_examples == 0 or ham_examples == 0:
        raise ClassifierError("training requires at least one spam and one ham example")

    vocabulary = set(spam_counts) | set(ham_counts)
    total_examples = spam_examples + ham_examples
    version = artifact_version or datetime.utcnow().strftime("%Y%m%d%H%M%S")
    training_corpus_version = f"{len(examples)}-{hash_examples(examples)}"

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
        "ingress_threshold": float(classifier["ingress_threshold"]),
        "ingress_thresholds": {
            "public": float(classifier["ingress_threshold"]),
            "private": max(float(classifier["ingress_threshold"]), 0.98),
        },
        "feature_config": feature_config,
        "training_corpus_version": training_corpus_version,
    }

    path, sha256 = write_artifact(config, artifact)
    return store.update_classifier_artifact(config, classifier["id"], artifact, path, sha256)


def export_artifact(config, classifier_uuid):
    classifier = store.get_classifier(config, classifier_uuid)
    if not classifier:
        raise ClassifierError("classifier not found")
    artifact = load_artifact_from_classifier(classifier)
    path, sha256 = write_artifact(config, artifact)
    return store.update_classifier_artifact(config, classifier["id"], artifact, path, sha256)


def hash_examples(examples):
    digest = hashlib.sha256()
    for example in examples:
        digest.update((example["label"] + "\0" + example["text"]).encode("utf-8"))
    return digest.hexdigest()[:12]


def artifact_bytes(artifact):
    return json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode("utf-8")


def write_artifact(config, artifact):
    output_dir = artifact_dir(config)
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"spam-classifier-{artifact['version']}.json")
    content = artifact_bytes(artifact)
    with open(path, "wb") as artifact_file:
        artifact_file.write(content)
    sha256 = hashlib.sha256(content).hexdigest()
    with open(f"{path}.sha256", "w", encoding="utf-8") as sha_file:
        sha_file.write(f"{sha256}  {os.path.basename(path)}\n")
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
