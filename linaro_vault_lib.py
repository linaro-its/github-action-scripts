""" Simple library to retrieve a secret from Linaro Vault using the BambooBitbucketRole role (ghactions server) """

import requests
import hvac
import boto3


SECRETS_CACHE = None

def get_vault_secret(secret_path: str, iam_role: str, key: str = "pw") -> str:
    global SECRETS_CACHE # pylint: disable=global-statement
    if SECRETS_CACHE is None:
        SECRETS_CACHE = {}
    if secret_path not in SECRETS_CACHE or key not in SECRETS_CACHE[secret_path]:
        # Get the credentials from the EC2 instance role
        url = f"http://169.254.169.254/latest/meta-data/iam/security-credentials/BambooBitbucketRole"
        response = requests.get(url=url)
        response.raise_for_status()
        credentials = response.json()
        # Assume the desired IAM role
        sts_client = boto3.client(
            'sts',
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['Token']
        )
        assumed_role_object = sts_client.assume_role(
            RoleArn=iam_role,
            RoleSessionName="AssumeRoleSession1"
        )
        assumed_credentials = assumed_role_object['Credentials']
        # Authenticate to Vault and get a Vault token back
        client = hvac.Client(url="https://login.linaro.org:8200")
        token = client.auth.aws.iam_login(
            assumed_credentials['AccessKeyId'],
            assumed_credentials['SecretAccessKey'],
            assumed_credentials['SessionToken'])
        # Now request the secret with that token
        header = {
            "X-Vault-Token": token["auth"]["client_token"]
        }
        response = requests.get(
            f"https://login.linaro.org:8200/v1/{secret_path}",
            headers=header)
        # Revoke the Vault token now that we're done with it.
        requests.post(
            "https://login.linaro.org:8200/v1/auth/token/revoke-self",
            headers=header)
        response.raise_for_status
        # Retrieve the secret and cache it
        secret = response.json()
        if secret_path not in SECRETS_CACHE:
            SECRETS_CACHE[secret_path] = {}
        SECRETS_CACHE[secret_path][key] = secret["data"][key]
    return SECRETS_CACHE[secret_path][key]
