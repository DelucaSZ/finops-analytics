from dataclasses import dataclass

import boto3
from botocore.config import Config

from app.core.config import settings
from app.models.account import AwsAccount

BOTO_CONFIG = Config(retries={"max_attempts": 6, "mode": "adaptive"})


@dataclass(frozen=True)
class CallerIdentity:
    account_id: str
    arn: str
    user_id: str


def base_session() -> boto3.Session:
    return boto3.Session(region_name=settings.aws_default_region)


def assume_account_session(account: AwsAccount) -> boto3.Session:
    client = base_session().client("sts", config=BOTO_CONFIG)
    request = {
        "RoleArn": account.role_arn,
        "RoleSessionName": settings.aws_role_session_name,
        "DurationSeconds": 3600,
    }
    if account.external_id:
        request["ExternalId"] = account.external_id
    response = client.assume_role(**request)
    credentials = response["Credentials"]
    return boto3.Session(
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
        region_name=account.regions[0] if account.regions else settings.aws_default_region,
    )


def get_caller_identity(session: boto3.Session) -> CallerIdentity:
    response = session.client("sts", config=BOTO_CONFIG).get_caller_identity()
    return CallerIdentity(
        account_id=response["Account"], arn=response["Arn"], user_id=response["UserId"]
    )
