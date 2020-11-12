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

import sys
import os
import subprocess
from datetime import datetime, timezone
from git import Repo
from ldap3 import Connection, SUBTREE
import vault_auth
import glob
import json
import requests
import boto3
import time


IMAGE_URL = "https://static.linaro.org/common/member-logos"
pkf = None
got_error = False
invalidate_cache = False


def get_vault_secret(user_id):
    secret = vault_auth.get_secret(
        user_id,
        iam_role="vault_update_members",
        url="https://login.linaro.org:8200"
    )
    return secret["data"]["pw"]


def initialise_ldap():
    username = "cn=update-members,ou=binders,dc=linaro,dc=org"
    password = get_vault_secret("secret/ldap/{}".format(username))
    return Connection(
            'ldaps://login.linaro.org',
            user=username,
            password=password,
            auto_bind=True
        )


def run_command(command):
    global got_error
    print("Running command: %s" % command)
    result = subprocess.run(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print("Command output:")
    print(result.stdout.decode("utf-8"))
    if result.returncode != 0:
        got_error = True
        print("Error output:")
        print(result.stderr.decode("utf-8"))


# def run_git_command(command):
#     # We do some funky stuff around the git command processing because we want
#     # to keep the SSH key under tight control.
#     # See https://stackoverflow.com/a/4565746/1233830
#     git_cmd = 'ssh-add "%s"; %s' % (pkf, command)
#     full_cmd = "ssh-agent bash -c '%s'" % git_cmd
#     run_command(full_cmd)


# def init_pkf():
#     global pkf

#     # Work out where the GitHub key is located.
#     pkf = os.path.dirname(
#         os.path.abspath(__file__)) + "/linaro-build-github.pem"


def logo_directory(working_dir):
    return "%s/logos" % working_dir


# def clone_repo(company):
#     # The environment variable bamboo_build_working_directory says where we
#     # can put stuff ... :)
#     working_dir = os.getenv("bamboo_build_working_directory")
#     repo_dir = "%s/%s" % (working_dir, company)
#     # If the repo is there already, go into it and pull, otherwise clone it.
#     if os.path.isdir(repo_dir):
#         print("Pulling website repository for %s" % company)
#         os.chdir(repo_dir)
#         run_git_command("git pull")
#     else:
#         print("Cloning website repository for %s" % company)
#         os.chdir(working_dir)
#         run_git_command("git clone git@github.com:%s/website.git %s" % (company, company))
#     # Make sure the master branch is present
#     os.chdir(repo_dir)
#     run_git_command("git checkout master")
#     return Repo(repo_dir)


def create_branch(repo):
    # Name the branch after the date and time
    now = datetime.now()
    branch_name = "member-update-%s" % now.strftime("%y%m%d-%H%M")
    # Make sure we base the new branch off master
    repo.heads.master.checkout()
    branch = repo.create_head(branch_name)
    branch.checkout()
    print("Checked out %s" % branch_name)


def get_members(ldap_conn):
    global got_error
    results = []
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
                    "modifyTimestamp"
                ]
                ):
            results = ldap_conn.entries
        else:
            print("ERROR: LDAP search for OUs failed")
            got_error = True
    return results


def write_member_file(ldap_rec):
    repo_dir = "%s/website" % os.getenv("GITHUB_WORKSPACE")
    with open(
        "%s/_company/%s.md" % (repo_dir, ldap_rec.ou.value),
        "w"
    ) as fp:
        fp.write("---\n")
        fp.write("title: %s\n" % ldap_rec.displayName.value)
        if ldap_rec.description.value is not None:
            fp.write("description: >\n    %s\n" % ldap_rec.description.value)
        fp.write("company_image: %s/%s.jpg\n" % (IMAGE_URL, ldap_rec.ou.value))
        fp.write("---\n")
        if ldap_rec.businessCategory.value is not None:
            fp.write(
                "%s\n" % ldap_rec.businessCategory.value.replace('\r', '')
            )


def save_member_logo(ldap_rec):
    global invalidate_cache
    # Exit this quickly if we don't have a logo in the record!
    if ldap_rec.jpegPhoto.value is None:
        print("No logo for %s" % ldap_rec.ou.value)
        return
    # Do we have a logos directory? If not, create it
    logo_dir = logo_directory("%s/website" % os.getenv("GITHUB_WORKSPACE"))
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
        with open(logo_file, "wb") as fp:
            fp.write(ldap_rec.jpegPhoto.value)
        invalidate_cache = True


def update_member(company, ldap_rec):
    print("Processing %s" % ldap_rec.displayName.value)
    if company == "Linaro":
        write_member_file(ldap_rec)
    save_member_logo(ldap_rec)


def is_member(members, filename, extension):
    for m in members:
        m_file = "%s.%s" % (m.ou.value, extension)
        if m_file == filename:
            return True
    return False


def remove_nonmatches(members, dir, extension):
    removed = False
    os.chdir(dir)
    for filepath in glob.iglob('*.%s' % extension):
        if not is_member(members, filepath, extension):
            print("Removing %s" % filepath)
            os.remove(filepath)
            removed = True
    return removed


def remove_spurious_members(members):
    global invalidate_cache
    # Iterate through _company removing any markdown files that don't match
    # active members.
    company_dir = "%s/website/_company" % os.getenv("GITHUB_WORKSPACE")
    remove_nonmatches(members, company_dir, "md")
    logo_dir = logo_directory("%s/website" % os.getenv("GITHUB_WORKSPACE"))
    result = remove_nonmatches(members, logo_dir, "jpg")
    if result:
        invalidate_cache = True


def add_to_group(data, group_name, level_name, member, company):
    global got_error
    # Find the group specified
    for d in data:
        if d["id"] == group_name:
            if level_name not in d:
                d[level_name] = []
            block = {
                "name": member.displayName.value,
                "image": "%s/%s.jpg" % (IMAGE_URL, member.ou.value),
                "url": "/membership/%s/" % (member.ou.value)
            }
            d[level_name].append(block)
            return
    if company == "Linaro":
        # Use that to show we are managing the master site, in which case
        # not all membership options will be matched.
        print("ERROR: Failed to find %s in members.json when adding %s" % (
            group_name, member.ou.value))
        got_error = True


def process_groups(data, member, company):
    # We use .values instead of .value to ensure that we always get a list
    # back, even if there is only one value.
    groups = member.organizationalStatus.values
    for g in groups:
        if "|" in g:
            parts = g.split('|')
            add_to_group(data, parts[0], parts[1], member, company)
        else:
            add_to_group(data, g, "members", member, company)


def write_members_json(company, members):
    # To maintain maximum flexibility around how the group data is managed,
    # this script works through the structure of the members.json file in
    # the repo, removing all existing members and adding back the ones that
    # are listed as being in each group.
    repo_dir = "%s/website" % os.getenv("GITHUB_WORKSPACE")
    with open(
            "%s/_data/members.json" % repo_dir
            ) as json_file:
        data = json.load(json_file)
    for group in data:
        if "members" in group:
            del group["members"]
        if "advisory_board" in group:
            del group["advisory_board"]
    for m in members:
        process_groups(data, m, company)
    with open(
            "%s/_data/members.json" % repo_dir,
            "w"
            ) as json_file:
        json.dump(
            data,
            json_file,
            indent=4,
            sort_keys=True
        )


def sync_member_logos():
    logo_dir = logo_directory("%s/website" % os.getenv("GITHUB_WORKSPACE"))
    os.chdir(logo_dir)
    run_command(
        'aws --profile update-member-logos s3 sync --cache-control'
        ' "public, max-age=86400" ./'
        ' "s3://static-linaro-org/common/member-logos" --delete'
    )


def update(company, repo):
    global got_error
    # Fetch all of the Member data from LDAP. Iterate through the Members,
    # outputting the individual Member markdown files and saving the logos
    # to a spare directory ready for syncing to S3. Finally, output the
    # members.json file.
    #
    # The LDAP OU structure under accounts contains OUs that we don't want
    # to include, and we filter based off the displayName attribute, since
    # that is critical to the markdown file. No attribute means ignore for
    # this.
    connection = initialise_ldap()
    members = get_members(connection)
    connection.unbind()
    for member in members:
        update_member(company, member)
    if not got_error:
        write_members_json(company, members)
    # write_members_json can set got_error hence the need to check it again
    if not got_error:
        if company == "Linaro":
            remove_spurious_members(members)
        sync_member_logos()


def create_github_pull_request(company, repo):
    global got_error
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
        got_error = True
    else:
        json = result.json()
        print("Pull request created: %s" % json["html_url"])
        # Request that Kyle reviews this PR
        data = {
            "reviewers": [
                "kylekirkby"
            ]
        }
        url = (
            "https://api.github.com/repos/%s/website/pulls/"
            "%s/requested_reviewers"
        ) % (company, json["number"])
        result = requests.post(url, json=data, headers=headers)
        if result.status_code != 201:
            print("ERROR: Failed to add review to the pull request")
            print(result.text)
            got_error = True


def checkin_repo(company, repo):
    repo_dir = "%s/website" % os.getenv("GITHUB_WORKSPACE")
    os.chdir(repo_dir)
    run_command("git add --all")
    run_command("git commit -m %s" % repo.active_branch.name)
    # Only use run_git_command when we need the SSH key involved.
    run_command(
        "git push --set-upstream origin %s" % repo.active_branch.name)
    create_github_pull_request(company, repo)


def check_logo_status():
    global invalidate_cache

    if invalidate_cache:
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
    # Add any untracked files to the repository
    untracked_files = repo.untracked_files
    for f in untracked_files:
        repo.git.add(f)
    # See if we have changed anything
    if repo.is_dirty():
        checkin_repo(company, repo)
    else:
        print("No changes made to the git repository")


def clean_up_repo(company, repo):
    global got_error
    # If we got an error, delete any untracked files that we might have
    # created and do a git reset to reset any tracked modifications.
    if got_error:
        untracked_files = repo.untracked_files
        # The files are relative to the repo directory so change there first
        repo_dir = "%s/website" % os.getenv("GITHUB_WORKSPACE")
        os.chdir(repo_dir)
        # and delete them
        for f in untracked_files:
            os.remove(f)
        # Now reset the branch back to its original state. It doesn't need the
        # SSH key so no need for git_run_command.
        run_command("git reset --hard")
    # Switch back to the master branch and delete the working branch
    branch = repo.active_branch
    master = repo.heads.master.checkout()
    master.delete(repo, branch)


def process_repo(company):
    repo = Repo("%s/website" % os.getenv("GITHUB_WORKSPACE"))
    create_branch(repo)
    update(company, repo)
    if not got_error:
        check_logo_status()
        check_repo_status(company, repo)
    clean_up_repo(company, repo)


def main(company):
    # init_pkf()
    process_repo(company)
    if got_error:
        sys.exit(1)


if __name__ == '__main__':
    if len(sys.argv) == 1:
        sys.exit("The company must be specified")
    main(sys.argv[1])
