import json
import os
import shutil
import subprocess
import sys
import tempfile

import requests
import vault_auth
from git import Repo
from ldap3 import SUBTREE, Connection
from requests.auth import HTTPBasicAuth

PI_SLUG = "Project Information"
nesting_level = 0


def get_vault_secret(user_id):
    secret = vault_auth.get_secret(
        user_id,
        iam_role="vault_jira_project_updater",
        url="https://login.linaro.org:8200"
    )
    return secret["data"]["pw"]


def initialise_ldap():
    username = "cn=bamboo-bind,ou=binders,dc=linaro,dc=org"
    password = get_vault_secret("secret/ldap/{}".format(username))
    return Connection(
            'ldaps://login.linaro.org',
            user=username,
            password=password,
            auto_bind=True
        )


def initialise_auth():
    username = "it.support.bot"
    password = get_vault_secret("secret/ldap/{}".format(username))
    return HTTPBasicAuth(username, password)


def jira_get(url, jira_auth):
    headers = {'content-type': 'application/json'}
    try:
        response = requests.get(
            "https://projects.linaro.org/%s" % url,
            headers=headers, auth=jira_auth)
        if response.status_code != 200:
            print("Getting %s failed with code %s" % (url, response.status_code))
            sys.exit(1)
        return response.json()
    except Exception as e:
        print("While fetching %s, got exception: %s" % (url, str(e)))
        sys.exit(1)


def get_all_projects(jira_auth):
    return jira_get("rest/api/2/project", jira_auth)


def meta_value(meta_data, key, group="Project Visibility"):
    for m in meta_data:
        if m["key"] == key and m["group"] == group:
            return m["value"]
    return ""


def get_metadata(jira_projects, jira_auth):
    # Iterate through the projects, looking for projects
    # that have got metadata defined.
    meta_results = {}
    for p in jira_projects:
        meta = jira_get(
            "rest/metadata/latest/project/%s?includeHidden=true" % p["key"], jira_auth)
        # Only include projects thare are active, open and published
        if meta != []:
            pv_open = meta_value(meta, "Open")
            pv_active = meta_value(meta, "Active")
            pv_published = meta_value(meta, "Published")
            pv_visibility = meta_value(meta, "property_visibility", "system")
            if pv_open == "Yes" and pv_active == "Yes" and pv_published == "Yes" and pv_visibility != "":
                meta_results[p["key"]] = meta
            else:
                print("Ignoring %s - open='%s', active='%s', published='%s', visibility='%s'" % (
                    p["key"], pv_open, pv_active, pv_published, pv_visibility))
        else:
            print("Ignoring %s - no metadata" % p["key"])
    return meta_results


def get_specific_projects(metadata, jira_auth):
    results = []
    for key in metadata.keys():
        project = jira_get(
            "rest/api/2/project/%s" % key, jira_auth)
        results.append(project)
    return results


def lookup_email(email):
    # Try to get a display name back for the given email address.
    with initialise_ldap() as ldap_conn:
        if ldap_conn.search(
            "dc=linaro,dc=org",
            search_filter="(mail=%s)" % email,
            search_scope=SUBTREE,
            attributes=["displayName"]):
            return ldap_conn.entries[0].displayName.value
    return None


def htmlise_email(email):
    # If the email address ends with a full-stop, remove it
    # before wrapping tags around and then add it back
    # afterwards.
    if email[-1] == ".":
        got_fullstop = True
        email = email[:-1]
    else:
        got_fullstop = False
    name = lookup_email(email)
    if name is None:
        result = "<a href=\"mailto:%s\">%s</a>" % (email, email)
    else:
        result = "%s <a class=\"email-icon\" href=\"mailto:%s\"><span class=\"icon-mail\"></span></a>" % (name, email)
    if got_fullstop:
        result += "."
    return result


def htmlise_markdown(url):
    # Split on the |
    parts = url.split("|")
    if len(parts) != 2:
        sys.exit("'%s' looks like markdown but isn't." % url)
    part1 = parts[0][1:]
    part2 = parts[1][:-1]
    return "<a href=\"%s\">%s</a>" % (part2, part1)
    

def htmlise_url(url):
    # Does the URL look like markdown?
    if url[0] == "[":
        return htmlise_markdown(url)
    # If the url ends with a full-stop, remove it
    # before wrapping tags around and then add it back
    # afterwards.
    if url[-1] == ".":
        got_fullstop = True
        url = url[:-1]
    else:
        got_fullstop = False
    result = "<a href=\"%s\">%s</a>" % (url, url)
    if got_fullstop:
        result += "."
    return result


def find_markers(line, known_point, start_char, end_char, make_sane=True):
    start = line.rfind(start_char, 0, known_point)
    end = line.find(end_char, known_point)
    if make_sane:
        # Ensure that start & end either point at the start and
        # end of the entire string, or at the desired substring.
        if start == -1:
            start = 0
        else:
            # Point at the next char
            start += 1
        if end == -1:
            end = len(line)
    return start, end


def process_email(at_pos, line, result):
    start, end = find_markers(line, at_pos, " ", " ")
    # Now extract anything before 'start'
    if start != 0:
        result += line[:start]
    # Extract the email address
    addr = line[start:end]
    # and then remove that from the line.
    line = line[end:]
    result += htmlise_email(addr)
    return line, result


def process_url(url_pos, line, result):
    # This is slightly complicated by the fact that
    # we need to support Jira link markdown which
    # can support spaces in the readable text, so
    # we look for '[' first.
    start, end = find_markers(line, url_pos, "[", "]", make_sane=False)
    if start == -1 or end == -1:
        # Need to have both [ and ] to qualify for Jira link
        # markdown processing.
        start, end = find_markers(line, url_pos, " ", " ")
    # Now extract anything before 'start'
    if start != 0:
        result += line[:start]
    # Extract the url address - slicing doesn't
    # include the last character hence the +1
    addr = line[start:end+1]
    # and then remove that from the line.
    line = line[end+1:]
    result += htmlise_url(addr)
    return line, result


def htmlise_unordered_list(line):
    global nesting_level
    # Before we do anything else, if the current nesting
    # level is non-zero, close off the previous list entry.
    result = ""
    if nesting_level != 0:
        result = "</li>"
    # How many stars are there? We split on the first space
    # which should come after all of the stars.
    parts = line.split(" ", 1)
    # We know that the first character is *, so we'll assume
    # that everything up to the space is also * and that is
    # our nesting level.
    level = len(parts[0])
    if nesting_level < level:
        # Start a new list
        result += "<ul>"
    elif nesting_level > level:
        # End the previous list. Note that we DON'T append this
        # (unlike starting a new list) because HTML requires
        # the list to end before the list entry is ended.
        result = "</ul></li>"
    # Now start this list entry
    result += "<li>"
    nesting_level = level
    return result + " " + htmlise_non_list_line(parts[1])


def htmlise_non_list_line(line):
    result = ""
    while True:
        at_pos = line.find("@")
        url_pos = line.find("://")
        # If no markers, return what is left
        if at_pos == -1 and url_pos == -1:
            return result+line
        if at_pos != -1 and url_pos != -1:
            # Which comes first?
            if at_pos < url_pos:
                line, result = process_email(at_pos, line, result)
            else:
                line, result = process_url(url_pos, line, result)
        elif at_pos != -1:
            line, result = process_email(at_pos, line, result)
        else:
            line, result = process_url(url_pos, line, result)


def htmlise_line(line):
    global nesting_level
    result = ""

    if line == "":
        return ""
    elif line[0] == "*":
        # If the line is part of an unordered list, process the list
        # part first and then process the rest of the line.
        return htmlise_unordered_list(line)
    elif nesting_level != 0:
        # We've got a non-list line and the nesting level is
        # non-zero, so decrement the nesting level and close off
        # a list.
        nesting_level -= 1
        result = "</li></ul>"
    return result + htmlise_non_list_line(line)



def htmlise_value(value):
    global nesting_level
    # The nesting level should already be zero because we
    # decrement it as the list ends but just in case ...
    nesting_level = 0

    # Break the value into lines. If there is only one
    # line then just process it straight away. Otherwise
    # HTMLise each line then add "<br>" to the end of
    # all except the last one.
    parts = value.split("\n")
    if len(parts) == 1:
        return htmlise_line(value.strip("\r"))

    result = ""
    for p in parts:
        if result != "" and nesting_level == 0:
            result += "<br>"
        result += htmlise_line(p.strip("\r"))

    # Make sure we don't have an open list
    while nesting_level != 0:
        result += "</li></ul>"
        nesting_level -= 1
    return result


def construct_project_data(projects, metadata):
    results = []
    for p in projects:
        if p["key"] in metadata:
            blob = construct_project_blob(p, metadata)
            results.append(blob)
    # Sort the projects by title
    results = sorted(results, key=lambda x: x[PI_SLUG]["title"])
    return {
        "projects": results
    }


def construct_project_blob(p, metadata):
    blob = {
        "key": p["key"],
        "icon": p["avatarUrls"]["48x48"]
    }
    meta = metadata[p["key"]]
    property_list = meta_value(meta, "property_visibility", "system")
    properties = property_list.split("\n")
    # Now add the values
    for prop in properties:
        if ":" in prop:
            parts = prop.split(":")
            value = meta_value(meta, parts[1], parts[0])
            if parts[0] not in blob:
                blob[parts[0]] = {}
            blob[parts[0]][parts[1]] = htmlise_value(value)
    # Finish off with the title and description from the project
    if PI_SLUG not in blob:
        blob[PI_SLUG] = {}
    blob[PI_SLUG]["title"] = htmlise_value(p["name"])
    blob[PI_SLUG]["description"] = htmlise_value(p["description"])
    return blob

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
    repo_dir = os.getenv("GITHUB_WORKSPACE")
    os.chdir(repo_dir)
    run_git_command("git checkout master")
    return Repo(repo_dir)


def checkin_repo(repo):
    repo_dir = os.getenv("GITHUB_WORKSPACE")
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


def do_the_git_bits(data):
    repo = get_repo()
    working_dir = os.getenv("GITHUB_WORKSPACE")
    sync_project_pages(data, "%s/_pages/projects" % working_dir)
    with open(
            "%s/_data/projects.json" % working_dir,
            "w"
            ) as json_file:
        json.dump(
            data,
            json_file,
            indent=4,
            sort_keys=True
        )
    check_repo_status(repo)


def check_project_dir_exists(key, projects_directory):
    path = "%s/%s" % (projects_directory, key.lower())
    if os.path.isdir(path):
        return
    os.makedirs(path)
    with open("%s/posts.md" % path, "w") as posts_file:
        posts_file.write("---\n")
        posts_file.write("title: %s project posts\n" % key)
        posts_file.write("permalink: /projects/%s/posts/\n" % key.lower())
        posts_file.write("layout: related_project_posts\n")
        posts_file.write("key: %s\n" % key)
        posts_file.write("---\n")


def sync_project_pages(project_data, projects_directory):
    # Below _pages/projects, there is a directory for each project (lower-case name) and,
    # within that, a file called "posts.md" with this structure:
    #
    # ---
    # title: AI Project Posts
    # permalink: /projects/ai/posts/
    # layout: related_project_posts
    # key: AI
    # ---
    projects = project_data["projects"]
    project_keys_lower = []
    for p in projects:
        check_project_dir_exists(p["key"], projects_directory)
        project_keys_lower.append(p["key"].lower())
    #
    # Remove any directories that exist for projects that don't ...
    subdirs = [f.name for f in os.scandir(projects_directory) if f.is_dir()]
    for s in subdirs:
        if s not in project_keys_lower:
            shutil.rmtree("%s/%s" % (projects_directory, s))


def main():
    jira_auth = initialise_auth()
    jira_projects = get_all_projects(jira_auth)
    if len(jira_projects) == 0:
        print("Failed to retrieve any projects from Jira")
        sys.exit(1)
    jira_metadata = get_metadata(jira_projects, jira_auth)
    # There seems to be a bug in the Jira REST API where getting all
    # projects does not include the description so, now we have a list
    # of the projects with metadata, re-fetch the Jira project info.
    jira_projects = get_specific_projects(jira_metadata, jira_auth)
    project_data = construct_project_data(jira_projects, jira_metadata)
    do_the_git_bits(project_data)


if __name__ == '__main__':
    main()
