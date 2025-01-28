""" Update Members on the Linaro Website from LDAP data """
#!/usr/bin/python3
#
# This script is run by a GitHub Action to:
#
# * Create a new branch on the repo already put there by the GHA
# * Update the MD and JSON files pertaining to members
# * Update the logos stored in static.linaro.org pertaining to members
# * If any changes have been made to the repo, commit them and create a
#   pull request
#
# The script uses direct git commands for the pull/clone/commit actions and
# GitPython for the operations that result in manipulating the repo.

import glob
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

import boto3
import requests
from git.repo import Repo
from ldap3 import SUBTREE, Connection
# from linaro_vault_lib import get_vault_secret
import ssmparameterstorelib

IMAGE_URL = "https://static.linaro.org/common/member-logos"
GOT_ERROR = False
INVALIDATE_CACHE = False


# def initialise_ldap():
#     """ Return a LDAP Connection """
#     username = "cn=update-members,ou=binders,dc=linaro,dc=org"
#     password = get_vault_secret(
#         "secret/ldap/{}".format(username),
#         iam_role="arn:aws:iam::968685071553:role/vault_update_members")
#     return Connection(
#             'ldaps://login.linaro.org',
#             user=username,
#             password=password,
#             auto_bind="DEFAULT"
#         )


def initialise_ldap():
    """ Return a LDAP Connection """
    username = "cn=update-members,ou=binders,dc=linaro,dc=org"
    password = ssmparameterstorelib.get_secret_from_ssm_parameter_store(
        "/secret/ldap/update-members"
    )
    return Connection(
            'ldaps://login.linaro.org',
            user=username,
            password=password,
            auto_bind="DEFAULT"
        )


def run_command(command):
    """ Run the command """
    global GOT_ERROR # pylint: disable=global-statement
    print("Running command: %s" % command)
    result = subprocess.run(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    print("Command output:")
    print(result.stdout.decode("utf-8"))
    if result.returncode != 0:
        GOT_ERROR = True
        print("Error output:")
        print(result.stderr.decode("utf-8"))


def logo_directory():
    """ Where are the logos on the Actions server? """
    return "%s/logos" % os.getenv("GITHUB_WORKSPACE")

def repo_directory():
    """ Where is the repo on the Actions server? """
    return "%s/website" % os.getenv("GITHUB_WORKSPACE")


def create_branch(repo):
    """ Create a new branch """
    # Name the branch after the date and time
    now = datetime.now()
    branch_name = "member-update-%s" % now.strftime("%y%m%d-%H%M")
    # Make sure we base the new branch off master
    repo.heads.master.checkout()
    branch = repo.create_head(branch_name)
    branch.checkout()
    print("Checked out %s" % branch_name)


def get_members(ldap_conn):
    """ Get all Members from LDAP """
    global GOT_ERROR # pylint: disable=global-statement
    results = []
    results_with_images = []
    with ldap_conn:
        if ldap_conn.search(
                "ou=accounts,dc=linaro,dc=org",
                search_filter=(
                    "(&(objectClass=organizationalUnit)(displayName=*))"
                    ),
                search_scope=SUBTREE,
                attributes=[
                    "ou",
                    "businessCategory",
                    "description",
                    "displayName",
                    "jpegPhoto",
                    "organizationalStatus",
                    "labeledURI",
                    "modifyTimestamp"
                ]
                ):
            results = ldap_conn.entries
        else:
            print("ERROR: LDAP search for OUs failed")
            GOT_ERROR = True
    # Remove any entries that do not have images
    for item in results:
        if item.jpegPhoto.value is not None:
            results_with_images.append(item)
        else:
            print(f"Dropping {item.ou.value} as a member as they don't have an image")
    return results_with_images


# def delete_member_file(ldap_rec):
#     """ Delete Member pages per Ebba's request """
#     file = "%s/_company/%s.md" % (repo_directory(), ldap_rec.ou.value)
#     if os.path.isfile(file):
#         os.remove(file)


# def write_member_file(ldap_rec):
#     """ Write out the Member's file for this LDAP record """
#     with open(
#         "%s/_company/%s.md" % (repo_directory(), ldap_rec.ou.value),
#         "w"
#     ) as handle:
#         handle.write("---\n")
#         handle.write("title: %s\n" % ldap_rec.displayName.value)
#         if ldap_rec.description.value is not None:
#             handle.write("description: >\n    %s\n" % ldap_rec.description.value)
#         handle.write("company_image: %s/%s.jpg\n" % (IMAGE_URL, ldap_rec.ou.value))
#         handle.write("---\n")
#         if ldap_rec.businessCategory.value is not None:
#             handle.write(
#                 "%s\n" % ldap_rec.businessCategory.value.replace('\r', '')
#             )


def save_member_logo(ldap_rec):
    """ Save the Member's logo for this LDAP record """
    global INVALIDATE_CACHE # pylint: disable=global-statement
    # Exit this quickly if we don't have a logo in the record!
    if ldap_rec.jpegPhoto.value is None:
        print("No logo for %s" % ldap_rec.ou.value)
        return
    # Do we have a logos directory? If not, create it
    logo_dir = logo_directory()
    if not os.path.isdir(logo_dir):
        os.mkdir(logo_dir)
    # Does the logo already exist? If it does, get the modification time
    # to compare it against LDAP.
    os.chdir(logo_dir)
    logo_file = "%s.jpg" % ldap_rec.ou.value
    save_logo = False
    if not os.path.isfile(logo_file):
        save_logo = True
    else:
        file_modtime = datetime.fromtimestamp(
            os.path.getmtime(logo_file),
            tz=timezone.utc
        )
        ldap_modtime = ldap_rec.modifyTimestamp.value
        if ldap_modtime > file_modtime:
            save_logo = True
    if save_logo:
        print("Saving logo")
        with open(logo_file, "wb") as handle:
            handle.write(ldap_rec.jpegPhoto.value)
        INVALIDATE_CACHE = True


def update_member(company, ldap_rec):
    """ Update a Member, but not Linaro! """
    if company == "Linaro" and ldap_rec.displayName.value != "Linaro":
        print("Processing %s" % ldap_rec.displayName.value)
        # write_member_file(ldap_rec)
        # delete_member_file(ldap_rec)
        save_member_logo(ldap_rec)


def is_member(members, filename, extension):
    """ Does 'filename' belong to a Member? """
    for memb in members:
        m_file = "%s.%s" % (memb.ou.value, extension)
        if m_file == filename and memb.displayName.value != "Linaro":
            return True
    return False


def remove_nonmatches(members, directory, extension):
    """ Remove any files not belonging to Members """
    removed = False
    os.chdir(directory)
    for filepath in glob.iglob('*.%s' % extension):
        if not is_member(members, filepath, extension):
            print("Removing %s" % filepath)
            os.remove(filepath)
            removed = True
    return removed


# Only called when running on the Linaro repo.
def remove_spurious_members(members):
    """ Remove files belonging to ex-Members """
    global INVALIDATE_CACHE # pylint: disable=global-statement
    # Iterate through _company removing any markdown files that don't match
    # active members.
    # company_dir = "%s/_company" % repo_directory()
    # remove_nonmatches(members, company_dir, "md")
    logo_dir = logo_directory()
    result = remove_nonmatches(members, logo_dir, "jpg")
    if result:
        INVALIDATE_CACHE = True


def add_to_group(data, group_name, level_name, member, company):
    """ Add this company to the group block in the data """
    global GOT_ERROR # pylint: disable=global-statement
    print("Processing group %s" % group_name)
    # Find the group specified
    for entry in data:
        if entry["id"] == group_name:
            if level_name not in entry:
                entry[level_name] = []
            block = {
                "name": member.displayName.value,
                "image": "%s/%s.jpg" % (IMAGE_URL, member.ou.value)
                # "url": "/membership/%s/" % (member.ou.value)
            }
            if member.labeledURI.value is not None:
                block["uri"] = member.labeledURI.value
            else:
                print("No outbound linking URL for %s" % member.displayName.value)
            entry[level_name].append(block)
            return
    if company == "Linaro":
        # Use that to show we are managing the master site, in which case
        # not all membership options will be matched.
        print("WARNING: Failed to find %s in members.json when adding %s" % (
            group_name, member.ou.value))


def process_groups(data, member, company):
    """ Iterate through the membership data for this Member """
    # We use .values instead of .value to ensure that we always get a list
    # back, even if there is only one value.
    groups = member.organizationalStatus.values
    for grp in groups:
        if "|" in grp:
            parts = grp.split('|')
            add_to_group(data, parts[0], parts[1], member, company)
        else:
            add_to_group(data, grp, "members", member, company)


def write_members_json(company, members):
    """ Write the membership data file out """
    # To maintain maximum flexibility around how the group data is managed,
    # this script works through the structure of the members.json file in
    # the repo, removing all existing members and adding back the ones that
    # are listed as being in each group.
    with open(
            "%s/_data/members.json" % repo_directory()
            ) as json_file:
        data = json.load(json_file)
    for group in data:
        if "members" in group:
            del group["members"]
        if "advisory_board" in group:
            del group["advisory_board"]
    for memb in members:
        process_groups(data, memb, company)
    with open(
            "%s/_data/members.json" % repo_directory(),
            "w"
            ) as json_file:
        json.dump(
            data,
            json_file,
            indent=2,
            sort_keys=True
        )


def sync_member_logos():
    """ Sync the logos from the Actions server to AWS S3 """
    logo_dir = logo_directory()
    os.chdir(logo_dir)
    run_command(
        'aws --profile update-member-logos s3 sync --cache-control'
        ' "public, max-age=86400" ./'
        ' "s3://static-linaro-org/common/member-logos" --delete'
    )


def update(company):
    """ Update all of the Members """
    global GOT_ERROR # pylint: disable=global-statement
    # Fetch all of the Member data from LDAP. Iterate through the Members,
    # outputting the individual Member markdown files and saving the logos
    # to a spare directory ready for syncing to S3. Finally, output the
    # members.json file.
    #
    # The LDAP OU structure under accounts contains OUs that we don't want
    # to include, and we filter based off the displayName attribute, since
    # that is critical to the markdown file. No attribute means ignore for
    # this.
    #
    # Change as of 19th Jan: if a Member company doesn't have a logo, it
    # does NOT get included in the member data.
    # See https://linaro-servicedesk.atlassian.net/browse/ITS-17890 for
    # the reason why.
    connection = initialise_ldap()
    members = get_members(connection)
    connection.unbind()
    for member in members:
        update_member(company, member)
    if not GOT_ERROR:
        write_members_json(company, members)
    # write_members_json can set got_error hence the need to check it again
    if not GOT_ERROR and company == "Linaro":
        remove_spurious_members(members)
        sync_member_logos()


def create_github_pull_request(company, repo):
    """ Create a pull request """
    global GOT_ERROR # pylint: disable=global-statement
    now = datetime.now()
    data = {
        "title": "Member update for %s" % now.strftime("%d-%m-%y"),
        "body": "Automated pull request",
        "head": repo.active_branch.name,
        "base": "master"
    }
    token = os.getenv("TOKEN")
    headers = {'Authorization': 'token %s' % token}
    url = "https://api.github.com/repos/%s/website/pulls" % company
    result = requests.post(url, json=data, headers=headers)
    if result.status_code != 201:
        print("ERROR: Failed to create pull request")
        print(result.text)
        GOT_ERROR = True
    else:
        json_result = result.json()
        print("Pull request created: %s" % json_result["html_url"])
        # Request that Kyle reviews this PR
        data = {
            "reviewers": [
                "pcolmer",
                "DelaraGi",
                "prasanthcambridge",
                "louismorgan-linaro"
            ]
        }
        url = (
            "https://api.github.com/repos/%s/website/pulls/"
            "%s/requested_reviewers"
        ) % (company, json_result["number"])
        result = requests.post(url, json=data, headers=headers)
        if result.status_code != 201:
            print("ERROR: Failed to add review to the pull request")
            print(result.text)
            GOT_ERROR = True


def checkin_repo(company, repo):
    """ Commit the changes made """
    os.chdir(repo_directory())
    run_command("git add --all")
    run_command("git commit -m %s" % repo.active_branch.name)
    # Only use run_git_command when we need the SSH key involved.
    run_command(
        "git push --set-upstream origin %s" % repo.active_branch.name)
    create_github_pull_request(company, repo)


def check_logo_status():
    """ Invalidate the CloudFront cache if we've changed any logos """
    global INVALIDATE_CACHE # pylint: disable=global-statement

    if INVALIDATE_CACHE:
        objects = [
            "/common/member-logos/*"
        ]
        # Use STS to assume the role
        sts_client = boto3.client('sts')
        assumed_role = sts_client.assume_role(
            RoleArn=(
                "arn:aws:iam::691071635361:"
                "role/static-linaro-org-update_members"
            ),
            RoleSessionName="AssumeRoleUpdateMembers"
        )
        client = boto3.client(
            'cloudfront',
            aws_access_key_id=assumed_role['Credentials']['AccessKeyId'],
            aws_secret_access_key=assumed_role[
                'Credentials']['SecretAccessKey'],
            aws_session_token=assumed_role['Credentials']['SessionToken']
        )
        # Create invalidation request
        print("Creating CloudFront invalidation")
        response = client.create_invalidation(
            DistributionId="E374OER1SABFCK",
            InvalidationBatch={
                "Paths": {
                    "Quantity": len(objects),
                    "Items": objects
                },
                "CallerReference": str(time.time())
            }
        )
        waiter = client.get_waiter('invalidation_completed')
        print("Waiting for invalidation to complete")
        waiter.wait(
            DistributionId="E374OER1SABFCK",
            Id=response["Invalidation"]["Id"],
            WaiterConfig={
                "Delay": 30,
                "MaxAttempts": 60
            }
        )
    else:
        print("No changes made to the Member logos")


def check_repo_status(company, repo):
    """ Have we modified the repo? """
    # Add any untracked files to the repository
    untracked_files = repo.untracked_files
    for file in untracked_files:
        repo.git.add(file)
    # See if we have changed anything
    if repo.is_dirty():
        checkin_repo(company, repo)
    else:
        print("No changes made to the git repository")


def clean_up_repo(repo):
    """ Clean up the local copy of the repo """
    global GOT_ERROR # pylint: disable=global-statement
    # If we got an error, delete any untracked files that we might have
    # created and do a git reset to reset any tracked modifications.
    if GOT_ERROR:
        untracked_files = repo.untracked_files
        # The files are relative to the repo directory so change there first
        os.chdir(repo_directory())
        # and delete them
        for file in untracked_files:
            os.remove(file)
        # Now reset the branch back to its original state. It doesn't need the
        # SSH key so no need for git_run_command.
        run_command("git reset --hard")
    # Switch back to the master branch and delete the working branch
    branch = repo.active_branch
    master = repo.heads.master.checkout()
    master.delete(repo, branch)


def process_repo(company):
    """ Work on the repo for this company website """
    repo = Repo(repo_directory())
    create_branch(repo)
    update(company)
    if not GOT_ERROR:
        check_logo_status()
        check_repo_status(company, repo)
    clean_up_repo(repo)


def main(company):
    """ Process the specified company """
    process_repo(company)
    if GOT_ERROR:
        sys.exit(1)


if __name__ == '__main__':
    if len(sys.argv) == 1:
        sys.exit("The company must be specified")
    main(sys.argv[1])
