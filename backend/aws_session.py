import os

import boto3
from botocore.exceptions import BotoCoreError, NoCredentialsError


def _load_dotenv_if_present() -> None:
    try:
        from dotenv import load_dotenv

        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env_path = os.path.join(repo_root, ".env")
        if os.path.exists(env_path):
            load_dotenv(dotenv_path=env_path)
    except Exception:
        pass


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def use_simulation_mode() -> bool:
    _load_dotenv_if_present()
    return _truthy(os.environ.get("USE_SIMULATION"))


def get_boto3_session() -> boto3.session.Session:
    """
    Prefer the standard AWS credential chain:
    - AWS_PROFILE / shared config (~/.aws)
    - environment variables
    - instance/role credentials (EC2/ECS/IRSA)
    """
    _load_dotenv_if_present()
    profile = os.environ.get("AWS_PROFILE")
    region = (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "us-east-1"
    )
    if profile:
        return boto3.session.Session(profile_name=profile, region_name=region)
    return boto3.session.Session(region_name=region)


def is_aws_configured() -> bool:
    _load_dotenv_if_present()
    if use_simulation_mode():
        return False
    try:
        session = get_boto3_session()
        creds = session.get_credentials()
        if creds is None:
            return False
        frozen = creds.get_frozen_credentials()
        return bool(frozen.access_key and frozen.secret_key)
    except (BotoCoreError, NoCredentialsError):
        return False
