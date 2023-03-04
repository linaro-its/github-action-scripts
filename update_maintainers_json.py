import json
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build

import json_generation_lib
from linaro_vault_lib import get_vault_secret

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

def initialise_auth():
    # Username (email) of user to run scripts as.
    username = "kyle.kirkby@linaro.org"
    # Get the Google Service Account JSON blob
    google_service_account_json = json.loads(get_vault_secret(
        "secret/misc/google-gitmaintainerssync.json",
        iam_role="arn:aws:iam::968685071553:role/vault_jira_project_updater"))
    # Instantiate a new service account auth object
    service_account_auth = service_account.Credentials.from_service_account_info(
            google_service_account_json, scopes=SCOPES)
    delegated_creds = service_account_auth.with_subject(username)
    return delegated_creds

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
        working_dir = json_generation_lib.working_dir()
        json_generation_lib.do_the_git_bits(json_data, "%s/website/_data/maintainers.json" % working_dir)

if __name__ == '__main__':
    main()
