import hashlib
import json
import os
from dataclasses import dataclass
from urllib.parse import urlparse


DEFAULT_S3_REGION = "us-east-1"


class ArtifactStorageError(Exception):
    pass


@dataclass(frozen=True)
class StoredArtifact:
    uri: str
    sha256: str
    checksum_uri: str | None = None


def _sha256(content):
    return hashlib.sha256(content).hexdigest()


def _bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _join_key(*parts):
    return "/".join(str(part).strip("/") for part in parts if str(part).strip("/"))


class S3ArtifactStorage:
    def __init__(self, config):
        try:
            import boto3
            from botocore.config import Config
            from botocore.exceptions import ClientError
        except ImportError as exc:
            raise ArtifactStorageError("boto3 is required for S3 classifier storage") from exc

        self.bucket = config.get("SPAM_DETECTION_S3_BUCKET")
        if not self.bucket:
            raise ArtifactStorageError("SPAM_DETECTION_S3_BUCKET is required for S3 storage")
        self.prefix = (config.get("SPAM_DETECTION_S3_PREFIX") or "spam-detection").strip("/")
        self.promoted_key = config.get("SPAM_DETECTION_S3_PROMOTED_KEY") or "promoted/classifier.json"
        self.create_bucket = _bool(config.get("SPAM_DETECTION_S3_CREATE_BUCKET"))
        verify = config.get("SPAM_DETECTION_S3_VERIFY_TLS", True)
        if isinstance(verify, str) and verify.strip().lower() in {"false", "0", "no", "off"}:
            verify = False
        elif isinstance(verify, str) and verify.strip().lower() in {"true", "1", "yes", "on"}:
            verify = True

        self.region = config.get("SPAM_DETECTION_S3_REGION") or DEFAULT_S3_REGION
        self._client_error = ClientError
        addressing_style = config.get("SPAM_DETECTION_S3_ADDRESSING_STYLE") or "auto"
        self.client = boto3.client(
            "s3",
            endpoint_url=config.get("SPAM_DETECTION_S3_ENDPOINT_URL"),
            region_name=self.region,
            verify=verify,
            config=Config(
                s3={"addressing_style": addressing_style},
                retries={"max_attempts": 5, "mode": "standard"},
            ),
        )
        if self.create_bucket:
            self._ensure_bucket()

    def classifier_uri(self, version):
        key = _join_key(self.prefix, "classifiers", f"spam-classifier-{version}.json")
        return f"s3://{self.bucket}/{key}"

    def promoted_uri(self):
        key = _join_key(self.prefix, self.promoted_key)
        return f"s3://{self.bucket}/{key}"

    def put_classifier(self, version, content):
        uri = self.classifier_uri(version)
        return self._put(uri, content)

    def read(self, uri):
        bucket, key = self._location(uri)
        try:
            response = self.client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()
        except Exception as exc:
            raise ArtifactStorageError(f"unable to read classifier artifact: {uri}") from exc

    def exists(self, uri):
        if not uri:
            return False
        bucket, key = self._location(uri)
        try:
            self.client.head_object(Bucket=bucket, Key=key)
            return True
        except self._client_error as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status == 404:
                return False
            raise ArtifactStorageError(f"unable to inspect classifier artifact: {uri}") from exc

    def promote(self, content):
        destination = self.promoted_uri()
        promoted = self._put(destination, content, overwrite=True)
        checksum_uri = f"{destination}.sha256"
        checksum = f"{promoted.sha256}  {os.path.basename(destination)}\n".encode("utf-8")
        self._put(checksum_uri, checksum, overwrite=True, content_type="text/plain")
        return StoredArtifact(promoted.uri, promoted.sha256, checksum_uri)

    def healthcheck(self):
        self.client.head_bucket(Bucket=self.bucket)

    def _put(self, uri, content, overwrite=False, content_type="application/json"):
        bucket, key = self._location(uri)
        sha256 = _sha256(content)
        try:
            existing = self.client.head_object(Bucket=bucket, Key=key)
        except self._client_error as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status != 404:
                raise ArtifactStorageError(f"unable to inspect classifier artifact: {uri}") from exc
            existing = None

        if existing:
            existing_sha256 = (existing.get("Metadata") or {}).get("sha256")
            if existing_sha256 == sha256:
                return StoredArtifact(uri, sha256)
            if not overwrite:
                existing_content = self.read(uri)
                if existing_content == content:
                    return StoredArtifact(uri, sha256)
                try:
                    semantically_equal = json.loads(existing_content) == json.loads(content)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    semantically_equal = False
                if semantically_equal:
                    return StoredArtifact(uri, _sha256(existing_content))
                raise ArtifactStorageError("artifact object already exists with different content")

        try:
            self.client.put_object(
                Bucket=bucket,
                Key=key,
                Body=content,
                ContentType=content_type,
                Metadata={"sha256": sha256},
            )
        except Exception as exc:
            raise ArtifactStorageError(f"unable to write classifier artifact: {uri}") from exc
        return StoredArtifact(uri, sha256)

    def _ensure_bucket(self):
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return
        except self._client_error as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status not in {400, 403, 404}:
                raise
        kwargs = {"Bucket": self.bucket}
        if self.region != DEFAULT_S3_REGION:
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": self.region}
        self.client.create_bucket(**kwargs)

    @staticmethod
    def _location(uri):
        parsed = urlparse(uri)
        if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.strip("/"):
            raise ArtifactStorageError(f"invalid S3 classifier URI: {uri}")
        return parsed.netloc, parsed.path.lstrip("/")


def get_artifact_storage(config):
    return S3ArtifactStorage(config)


def artifact_storage_healthcheck(config):
    get_artifact_storage(config).healthcheck()
