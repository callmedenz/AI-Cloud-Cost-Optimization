from __future__ import annotations

import re
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError


ROLE_ARN_PATTERN = re.compile(
    r"^arn:aws:iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_-]+$"
)


def validate_role_arn(role_arn: str) -> None:
    if not ROLE_ARN_PATTERN.fullmatch(role_arn):
        raise ValueError("role_arn must be an IAM role ARN in the same AWS partition")


def validate_aws_role(role_arn: str, external_id: str) -> dict[str, Any]:
    validate_role_arn(role_arn)
    if not external_id.strip():
        raise ValueError("external_id is required")

    sts = boto3.client("sts")
    try:
        assumed = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName="cloud-cost-copilot-validation",
            ExternalId=external_id,
            DurationSeconds=900,
        )
        credentials = assumed["Credentials"]
        session = boto3.Session(
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
        )
        identity = session.client("sts").get_caller_identity()
        return {
            "connected": True,
            "account_id": identity.get("Account"),
            "assumed_role": identity.get("Arn"),
        }
    except (BotoCoreError, ClientError) as exc:
        error = getattr(exc, "response", {}).get("Error", {})
        code = error.get("Code", "AWS_ERROR")
        message = error.get("Message", "AWS role validation failed")
        raise RuntimeError(f"{code}: {message}") from exc
