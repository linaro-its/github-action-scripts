""" Simple library to retrieve a secret from Linaro Vault using the BambooBitbucketRole role (ghactions server) """

import requests
import hvac


SECRETS_CACHE = None

def get_vault_secret(secret_path: str, key: str = "pw") -> str:
    global SECRETS_CACHE # pylint: disable=global-statement
    if SECRETS_CACHE is None:
        SECRETS_CACHE = {}
    if secret_path not in SECRETS_CACHE or key not in SECRETS_CACHE[secret_path]:
        url = f"http://169.254.169.254/latest/meta-data/iam/security-credentials/BambooBitbucketRole"
        response = requests.get(url=url)
        response.raise_for_status()
        credentials = response.json()
        client = hvac.Client(url="https://login.linaro.org:8200")
        token = client.auth.aws.iam_login(credentials['AccessKeyId'], credentials['SecretAccessKey'], credentials['Token'], role="vault_jira_project_updater")
        header = {
            "X-Vault-Token": token
        }
        response = requests.get(
            f"https://login.linaro.org:8200/v1/{secret_path}",
            headers=header)
        # Revoke the Vault token now that we're done with it.
        requests.post(
            "https://login.linaro.org:8200/v1/auth/token/revoke-self",
            headers=header)
        response.raise_for_status
        secret = response.json()
        if secret_path not in SECRETS_CACHE:
            SECRETS_CACHE[secret_path] = {}
        SECRETS_CACHE[secret_path][key] = secret["data"][key]
    return SECRETS_CACHE[secret_path][key]
