import json
import boto3
import hashlib
import os
import zipfile
import uuid
import time
from urllib.parse import unquote_plus

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

TABLE_NAME = os.environ["DYNAMODB_FIRMWARE_TABLE_NAME"]

INCOMING_PREFIX = "incoming/"
PROCESSING_PREFIX = "processing/"
PROCESSED_PREFIX = "processed/"
ERROR_PREFIX = "errors/"
TMP_DIR = "/tmp"

firmware_table = dynamodb.Table(TABLE_NAME)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_manifest_schema(manifest):
    required_fields = [
        "class", "product_id", "application",
        "branch", "version", "commit",
        "created", "files"
    ]

    for field in required_fields:
        if field not in manifest:
            raise Exception(f"Manifest missing required field: {field}")

    if not isinstance(manifest["files"], list):
        raise Exception("Manifest 'files' must be an array")

    for entry in manifest["files"]:
        if "name" not in entry or "sha256" not in entry:
            raise Exception("Each file entry must contain 'name' and 'sha256'")
        if len(entry["sha256"]) != 64:
            raise Exception(f"Invalid SHA256 for {entry['name']}")


def put_error_item(uuid_name, error_message, original_name=None, manifest=None):
    product_id = "__UNKNOWN_PRODUCT__"
    version = f"ERROR#UNKNOWN#{uuid_name}"

    if isinstance(manifest, dict):
        if "product_id" in manifest:
            product_id = manifest["product_id"]
        if "version" in manifest:
            version = f"ERROR#{manifest['version']}#{uuid_name}"

    item = {
        "product_id": product_id,
        "version": version,
        "release_status": "ERROR",
        "error": error_message,
        "zip_name": uuid_name,
        "timestamp": int(time.time()),
        "deleted": False,
    }

    if original_name:
        item["original_name"] = original_name
    if manifest is not None:
        item["manifest"] = manifest

    firmware_table.put_item(Item=item)


def move_object(bucket, source_key, dest_key):
    s3.copy_object(
        Bucket=bucket,
        CopySource={"Bucket": bucket, "Key": source_key},
        Key=dest_key,
    )
    s3.delete_object(Bucket=bucket, Key=source_key)


def lambda_handler(event, context):
    record = event["Records"][0]
    bucket = record["s3"]["bucket"]["name"]
    key = unquote_plus(record["s3"]["object"]["key"])

    if not key.endswith(".zip"):
        return

    original_filename = os.path.basename(key)
    uuid_name = f"{uuid.uuid4()}.zip"

    incoming_key = key
    processing_key = f"{PROCESSING_PREFIX}{uuid_name}"
    processed_key = f"{PROCESSED_PREFIX}{uuid_name}"
    error_key = f"{ERROR_PREFIX}{uuid_name}"

    manifest = None

    try:
        move_object(bucket, incoming_key, processing_key)

        head = s3.head_object(Bucket=bucket, Key=processing_key)
        zip_size = head["ContentLength"]

        zip_path = os.path.join(TMP_DIR, uuid_name)
        s3.download_file(bucket, processing_key, zip_path)

        zip_sha256 = sha256_file(zip_path)

        extract_dir = os.path.join(TMP_DIR, "unzipped")
        os.makedirs(extract_dir, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(extract_dir)

        manifest_path = os.path.join(extract_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            raise Exception("manifest.json missing")

        with open(manifest_path) as f:
            manifest = json.load(f)

        validate_manifest_schema(manifest)

        product_id = manifest["product_id"]
        version = manifest["version"]

        for entry in manifest["files"]:
            file_path = os.path.join(extract_dir, entry["name"])
            if not os.path.exists(file_path):
                raise Exception(f"Missing file: {entry['name']}")

            actual_sha256 = sha256_file(file_path)
            if actual_sha256 != entry["sha256"]:
                raise Exception(f"SHA256 mismatch for {entry['name']}")

        item = {
            "product_id": product_id,
            "version": version,
            "class": manifest.get("class"),
            "application": manifest.get("application"),
            "branch": manifest.get("branch"),
            "commit": manifest.get("commit"),
            "created": manifest.get("created"),
            "files": manifest.get("files", []),
            "zip_name": uuid_name,
            "original_name": original_filename,
            "zip_sha256": zip_sha256,
            "zip_size": zip_size,
            "uploaded_at": int(time.time()),
            "deleted": False,
            "release_status": "PROCESSING",
        }

        firmware_table.put_item(Item=item)

        move_object(bucket, processing_key, processed_key)

    except Exception as e:
        put_error_item(
            uuid_name,
            str(e),
            original_name=original_filename,
            manifest=manifest,
        )

        try:
            move_object(bucket, processing_key, error_key)
        except Exception:
            pass

        raise
