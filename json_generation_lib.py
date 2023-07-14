import json
import os
import subprocess
import sys
import tempfile

from git.repo import Repo
from linaro_vault_lib import get_vault_secret

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
        pem = get_vault_secret("secret/misc/linaro-build-github.pem",
                               iam_role="arn:aws:iam::968685071553:role/vault_jira_project_updater")
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


def checkin_repo(repo, message):
    repo_dir = "%s/website" % os.getenv("GITHUB_WORKSPACE")
    os.chdir(repo_dir)
    # Only use run_git_command when we need the SSH key involved.
    run_command("git add --all")
    run_command(f"git commit -m \"{message}\"")
    run_git_command(
        "git push --set-upstream origin %s" % repo.active_branch.name)


def check_repo_status(repo, message):
    # Add any untracked files to the repository
    untracked_files = repo.untracked_files
    for f in untracked_files:
        repo.git.add(f)
    # See if we have changed anything
    if repo.is_dirty():
        print("Checking in git repository changes")
        checkin_repo(repo, message)
        return True

    print("No changes made to the git repository")
    return False


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
    return check_repo_status(repo, "Update project data")
