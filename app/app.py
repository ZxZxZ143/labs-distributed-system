import redis
import os
import socket
import uuid
from datetime import datetime

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from flask import Flask, jsonify, request

app = Flask(__name__)

# Maximum text file size: 1 MiB
MAX_FILE_BYTES = 1024 * 1024
app.config["MAX_CONTENT_LENGTH"] = 2 * MAX_FILE_BYTES

BUCKET = os.environ.get("BUCKET", "lab4-files")
ENDPOINT = os.environ.get("S3_ENDPOINT")

s3_config = Config(
    s3={"addressing_style": "path"} if ENDPOINT else {},
    connect_timeout=2,
    read_timeout=3,
    retries={"max_attempts": 1},
)

s3 = boto3.client(
    "s3",
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
    endpoint_url=ENDPOINT,
    config=s3_config,
)


def ensure_bucket():
    try:
        s3.head_bucket(Bucket=BUCKET)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]

        if code in ("404", "NoSuchBucket", "NotFound"):
            s3.create_bucket(Bucket=BUCKET)
        else:
            raise


@app.errorhandler(413)
def request_too_large(error):
    return jsonify({"error": "request too large"}), 400


# Existing Lab 3 endpoints

@app.get("/time")
def get_time():
    return jsonify({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "served_by": socket.gethostname(),
    }), 200


@app.post("/echo")
def echo():
    data = request.get_json(silent=True)

    if not data or "message" not in data:
        return jsonify({
            "error": "field 'message' is required"
        }), 400

    return jsonify({"message": data["message"]}), 200


# Lab 4: Object Storage

@app.post("/files")
def save_file():
    data = request.get_json(silent=True)

    if not isinstance(data, dict) or not isinstance(
        data.get("content"), str
    ):
        return jsonify({
            "error": "field 'content' must be a string"
        }), 400

    content = data["content"].encode("utf-8")

    if len(content) > MAX_FILE_BYTES:
        return jsonify({
            "error": "file exceeds 1 MiB limit"
        }), 400

    file_id = str(uuid.uuid4())
    key = f"files/{file_id}.txt"

    try:
        ensure_bucket()
        s3.put_object(
            Bucket=BUCKET,
            Key=key,
            Body=content,
            ContentType="text/plain; charset=utf-8",
        )
    except (BotoCoreError, ClientError):
        app.logger.exception("S3 write failed")
        return jsonify({
            "error": "storage unavailable"
        }), 503

    return jsonify({
        "file_id": file_id,
        "size_bytes": len(content),
    }), 201


@app.get("/files/<file_id>")
def read_file(file_id):
    try:
        # Reject invalid identifiers
        if str(uuid.UUID(file_id)) != file_id:
            raise ValueError()
    except ValueError:
        return jsonify({
            "error": "invalid file identifier"
        }), 400

    key = f"files/{file_id}.txt"

    try:
        obj = s3.get_object(Bucket=BUCKET, Key=key)
        content = obj["Body"].read().decode("utf-8")

    except ClientError as exc:
        code = exc.response["Error"]["Code"]

        if code in ("NoSuchKey", "404", "NotFound"):
            return jsonify({
                "error": "file not found"
            }), 404

        app.logger.exception("S3 read failed")
        return jsonify({
            "error": "storage unavailable"
        }), 503

    except (BotoCoreError, UnicodeError):
        app.logger.exception("S3 read failed")
        return jsonify({
            "error": "storage unavailable"
        }), 503

    return jsonify({
        "file_id": file_id,
        "content": content,
    }), 200



# Lab 4 — Redis Replication

REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")

primary = redis.Redis(
    host=REDIS_HOST,
    port=int(os.environ.get("REDIS_PRIMARY_PORT", "6379")),
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)

replica = redis.Redis(
    host=REDIS_HOST,
    port=int(os.environ.get("REDIS_REPLICA_PORT", "6380")),
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)


@app.post("/counter/increment")
def increment_counter():
    try:
        value = primary.incr("counter")
    except redis.exceptions.RedisError:
        app.logger.exception("Redis primary unavailable")
        return jsonify({
            "error": "storage unavailable"
        }), 503

    return jsonify({
        "value": value,
        "source": "primary"
    }), 200


@app.get("/counter")
def get_counter():
    source = request.args.get("from", "primary")

    if source not in ("primary", "replica"):
        return jsonify({
            "error": "invalid source"
        }), 400

    client = primary if source == "primary" else replica

    try:
        value = client.get("counter")
    except redis.exceptions.RedisError:
        app.logger.exception("Redis %s unavailable", source)
        return jsonify({
            "error": "storage unavailable"
        }), 503

    return jsonify({
        "value": int(value or 0),
        "source": source
    }), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
