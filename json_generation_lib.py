import json
import os
import subprocess
import sys
import tempfile

import vault_auth
from git import Repo

SECRETS_CACHE = None

def get_vault_secret(secret_path, key="pw"):
    global SECRETS_CACHE # pylint: disable=global-statement
    if SECRETS_CACHE is None:
        SECRETS_CACHE = {}
    if secret_path not in SECRETS_CACHE or key not in SECRETS_CACHE[secret_path]:
        secret = vault_auth.get_secret(
            secret_path,
            iam_role="vault_jira_project_updater",
            url="https://login.linaro.org:8200"
        )
        if secret_path not in SECRETS_CACHE:
            SECRETS_CACHE[secret_path] = {}
        SECRETS_CACHE[secret_path][key] = secret["data"][key]
    return SECRETS_CACHE[secret_path][key]


def run_command(command):
    result = subprocess.run(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        print("ERROR: '%s'" % command)
        print(result.stdout.decode("utf-8"))
        print(result.stderr.decode("utf-8"))
        sys.exit(1)


def run_git_command(command):
    # We do some funky stuff around the git command processing because we want
    # to keep the SSH key under tight control.
    # See https://stackoverflow.com/a/4565746/1233830

    # Fetch the SSH key from Vault and store it in a temporary file
    with tempfile.NamedTemporaryFile(mode='w+', delete=False) as pem_file:
        pem = get_vault_secret("secret/misc/linaro-build-github.pem")
        pem_file.write(pem)
        pkf = pem_file.name

    git_cmd = 'ssh-add "%s"; %s' % (pkf, command)
    full_cmd = "ssh-agent bash -c '%s'" % git_cmd
    run_command(full_cmd)
    os.remove(pkf)


def get_repo():
    repo_dir = "%s/website" % os.getenv("GITHUB_WORKSPACE")
    os.chdir(repo_dir)
    run_git_command("git checkout master")
    return Repo(repo_dir)


def checkin_repo(repo):
    repo_dir = "%s/website" % os.getenv("GITHUB_WORKSPACE")
    os.chdir(repo_dir)
    # Only use run_git_command when we need the SSH key involved.
    run_command("git add --all")
    run_command("git commit -m \"Update project data\"")
    run_git_command(
        "git push --set-upstream origin %s" % repo.active_branch.name)


def check_repo_status(repo):
    # Add any untracked files to the repository
    untracked_files = repo.untracked_files
    for f in untracked_files:
        repo.git.add(f)
    # See if we have changed anything
    if repo.is_dirty():
        print("Checking in git repository changes")
        checkin_repo(repo)
    else:
        print("No changes made to the git repository")


def working_dir():
    return os.getenv("GITHUB_WORKSPACE")


def do_the_git_bits(data, filename):
    repo = get_repo()
    with open(filename, "w") as json_file:
        json.dump(
            data,
            json_file,
            indent=4,
            sort_keys=True
        )
    check_repo_status(repo)
