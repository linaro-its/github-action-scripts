import json
import os
import shutil
import subprocess
import sys
import tempfile

import requests
import vault_auth
from git import Repo
from requests.auth import HTTPBasicAuth
from google.oauth2 import service_account
from googleapiclient.discovery import build
import json

nesting_level = 0
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly"
]
SPREADSHEET_ID = "1b6O-YbZhj1t94zUS1sTRFQ9S4uqNTzTGCiDaGhdpugI"

def create_json_object(delegated_creds):
    # Create our new dict
    json_blob = {
        "maintainers_by_company": [],
        "maintainers_by_project": [],
    }
    # Create new google sheets service with delegated_creds
    with build('sheets', 'v4', credentials=delegated_creds) as service:
        sheet = service.spreadsheets()
        # Get data from projects sheet
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID,
                                    range="maintainers  by project!A1:B").execute()
        values = result.get('values', [])
        if not values:
            print("Failed to retreive projects data from areas by project!A1:B for spreadsheet with Id - {}".format(SPREADSHEET_ID))
            return False
        else:
            for row in values[1:]:
                # Print columns A and E, which correspond to indices 0 and 4.
                print(row)
                json_blob["maintainers_by_project"].append({"name": row[0], "num": row[1] })
        # Get data from maintainers sheet
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID,
                                    range="pivot: area by company!A1:B").execute()
        values = result.get('values', [])
        if not values:
            print("Failed to retreive projects data from 'pivot: area by company!A1:B' for spreadsheet with Id - {}".format(SPREADSHEET_ID))
            return False
        else:
            for row in values[1:]:
                # Print columns A and E, which correspond to indices 0 and 4.
                print(row)
                json_blob["maintainers_by_company"].append({"name": row[0], "num": row[1] })
    return json_blob

def get_vault_secret(user_id):
    secret = vault_auth.get_secret(
        user_id,
        iam_role="vault_update_maintainers",
        url="https://login.linaro.org:8200"
    )
    return secret["data"]["pw"]

def initialise_auth():
    # Username (email) of user to run scripts as.
    username = "kyle.kirkby@linaro.org"
    # Get the Google Service Account JSON blob
    google_service_account_json = json.loads(get_vault_secret("secret/misc/google-gitmaintainerssync.json"))
    # Instantiate a new service account auth object
    service_account_auth = service_account.Credentials.from_service_account_info(
            google_service_account_json, scopes=SCOPES)
    delegated_creds = service_account_auth.with_subject(username)
    return delegated_creds

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
    run_command("git commit -m \"Update maintainers data\"")
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

def do_the_git_bits(data):
    repo = get_repo()
    working_dir = os.getenv("GITHUB_WORKSPACE")
    with open(
            "%s/website/_data/maintainers.json" % working_dir,
            "w"
            ) as json_file:
        json.dump(
            data,
            json_file,
            indent=4,
            sort_keys=True
        )
    check_repo_status(repo)

def main():
    # Initialize Google Auth
    delegated_creds = initialise_auth()
    # Create the JSON files with the returned credentials
    json_data = create_json_object(delegated_creds)
    # Check if files have been created successfully.
    if not json_data:
        print("Failed to created the maintainers/projects JSON files")
        sys.exit(1)
    else:
        print("Maintainers data fetched. Checking in the changes.")
        # Check for changes
        do_the_git_bits(json_data)

if __name__ == '__main__':
    main()


