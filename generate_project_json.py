""" Generate the JSON file used to drive the Projects data. """
import os
import shutil
import sys

import requests
from ldap3 import SUBTREE, Connection
from requests.auth import HTTPBasicAuth

import json_generation_lib

PI_SLUG = "Project Information"
NESTING_LEVEL = 0


def initialise_ldap():
    """ Return a LDAP Connection. """
    username = "cn=bamboo-bind,ou=binders,dc=linaro,dc=org"
    password = json_generation_lib.get_vault_secret("secret/ldap/{}".format(username))
    return Connection(
            'ldaps://login.linaro.org',
            user=username,
            password=password,
            auto_bind=True
        )


def initialise_auth():
    """ Return a HTTP Auth. """
    username = "it.support.bot"
    password = json_generation_lib.get_vault_secret("secret/ldap/{}".format(username))
    return HTTPBasicAuth(username, password)


def jira_get(url, jira_auth):
    """ Fetch from the Jira Projects server. """
    headers = {'content-type': 'application/json'}
    try:
        response = requests.get(
            "https://projects.linaro.org/%s" % url,
            headers=headers, auth=jira_auth)
        if response.status_code != 200:
            print("Getting %s failed with code %s" % (url, response.status_code))
            sys.exit(1)
        return response.json()
    except Exception as exc: # pylint: disable=broad-except
        print("While fetching %s, got exception: %s" % (url, str(exc)))
        sys.exit(1)


def get_all_projects(jira_auth):
    """ Get all of the Jira projects. """
    return jira_get("rest/api/2/project", jira_auth)


def meta_value(meta_data, key, group="Project Visibility"):
    """ Return the value for a given meta key and group. """
    for meta in meta_data:
        if meta["key"] == key and meta["group"] == group:
            return meta["value"]
    return ""


def get_metadata(jira_projects, jira_auth):
    """
    # Iterate through the projects, looking for projects
    # that have got metadata defined.
    """
    meta_results = {}
    for proj in jira_projects:
        meta = jira_get(
            "rest/metadata/latest/project/%s?includeHidden=true" % proj["key"], jira_auth)
        # Only include projects thare are active, open and published
        if meta != []:
            pv_open = meta_value(meta, "Open")
            pv_active = meta_value(meta, "Active")
            pv_published = meta_value(meta, "Published")
            pv_visibility = meta_value(meta, "property_visibility", "system")
            if (pv_open == "Yes" and
                    pv_active == "Yes" and
                    pv_published == "Yes" and
                    pv_visibility != ""):
                meta_results[proj["key"]] = meta
            else:
                print("Ignoring %s - open='%s', active='%s', published='%s', visibility='%s'" % (
                    proj["key"], pv_open, pv_active, pv_published, pv_visibility))
        else:
            print("Ignoring %s - no metadata" % proj["key"])
    return meta_results


def get_specific_projects(metadata, jira_auth):
    """ For projects specified in the metadata, get the corresponding Jira data. """
    results = []
    for key in metadata.keys():
        project = jira_get(
            "rest/api/2/project/%s" % key, jira_auth)
        results.append(project)
    return results


def lookup_email(email):
    """ Try to get a display name back for the given email address. """
    with initialise_ldap() as ldap_conn:
        if ldap_conn.search(
            "dc=linaro,dc=org",
            search_filter="(mail=%s)" % email,
            search_scope=SUBTREE,
            attributes=["displayName"]):
            return ldap_conn.entries[0].displayName.value
    return None


def htmlise_email(email):
    """
    If the email address ends with a full-stop, remove it
    before wrapping tags around and then add it back
    afterwards.
    """
    if email[-1] == ".":
        got_fullstop = True
        email = email[:-1]
    else:
        got_fullstop = False
    name = lookup_email(email)
    if name is None:
        result = "<a href=\"mailto:%s\">%s</a>" % (email, email)
    else:
        result = (
            "%s <a class=\"email-icon\" href=\"mailto:%s\">"
            "<span class=\"icon-mail\"></span></a>" % (name, email))
    if got_fullstop:
        result += "."
    return result


def htmlise_markdown(url):
    """ Convert a markdown URL into a HTML URL """
    # Split on the |
    parts = url.split("|")
    if len(parts) != 2:
        sys.exit("'%s' looks like markdown but isn't." % url)
    part1 = parts[0][1:]
    part2 = parts[1][:-1]
    return "<a href=\"%s\">%s</a>" % (part2, part1)


def htmlise_url(url):
    """ Convert a URL into HTML tags. """
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
    """ Find the specified chars in the line. """
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
    """ Extract and convert an email address to HTML. """
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
    """ Extract and convert a URL to HTML. """
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
    """ Convert an unordered list to HTML. """
    global NESTING_LEVEL # pylint: disable=global-statement
    # Before we do anything else, if the current nesting
    # level is non-zero, close off the previous list entry.
    result = ""
    if NESTING_LEVEL != 0:
        result = "</li>"
    # How many stars are there? We split on the first space
    # which should come after all of the stars.
    parts = line.split(" ", 1)
    # We know that the first character is *, so we'll assume
    # that everything up to the space is also * and that is
    # our nesting level.
    level = len(parts[0])
    if NESTING_LEVEL < level:
        # Start a new list
        result += "<ul>"
    elif NESTING_LEVEL > level:
        # End the previous list. Note that we DON'T append this
        # (unlike starting a new list) because HTML requires
        # the list to end before the list entry is ended.
        result = "</ul></li>"
    # Now start this list entry
    result += "<li>"
    NESTING_LEVEL = level
    return result + " " + htmlise_non_list_line(parts[1])


def htmlise_non_list_line(line):
    """
    Process a line that isn't in a list, looking for email
    addresses and URLs so that they can be converted into
    the appropriate HTML.
    """
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
    """ Scan the line, converting segments to HTML where needed. """
    global NESTING_LEVEL # pylint: disable=global-statement
    result = ""

    if line == "":
        return ""
    if line[0] == "*":
        # If the line is part of an unordered list, process the list
        # part first and then process the rest of the line.
        return htmlise_unordered_list(line)
    if NESTING_LEVEL != 0:
        # We've got a non-list line and the nesting level is
        # non-zero, so decrement the nesting level and close off
        # a list.
        NESTING_LEVEL -= 1
        result = "</li></ul>"
    return result + htmlise_non_list_line(line)


def htmlise_value(value):
    """ Process the value, converting appropriate segments to HTML. """
    global NESTING_LEVEL # pylint: disable=global-statement
    # The nesting level should already be zero because we
    # decrement it as the list ends but just in case ...
    NESTING_LEVEL = 0

    # Break the value into lines. If there is only one
    # line then just process it straight away. Otherwise
    # HTMLise each line then add "<br>" to the end of
    # all except the last one.
    parts = value.split("\n")
    if len(parts) == 1:
        return htmlise_line(value.strip("\r"))

    result = ""
    for par in parts:
        if result != "" and NESTING_LEVEL == 0:
            result += "<br>"
        result += htmlise_line(par.strip("\r"))

    # Make sure we don't have an open list
    while NESTING_LEVEL != 0:
        result += "</li></ul>"
        NESTING_LEVEL -= 1
    return result


def string_to_list(value):
    """ Convert a multi-line string into a list. """
    conversion = value.split("\n")
    # Remove any blank entries
    while "" in conversion:
        conversion.remove("")
    return conversion

def construct_project_data(projects, metadata):
    """ Convert the separate project data into a single Python object. """
    results = []
    for proj in projects:
        if proj["key"] in metadata:
            blob = construct_project_blob(proj, metadata)
            results.append(blob)
    # Sort the projects by title
    results = sorted(results, key=lambda x: x[PI_SLUG]["title"])
    return {
        "projects": results
    }


def construct_project_blob(proj, metadata):
    """ Construct the per-project Python object. """
    blob = {
        "key": proj["key"],
        "icon": proj["avatarUrls"]["48x48"]
    }
    meta = metadata[proj["key"]]
    property_list = meta_value(meta, "property_visibility", "system")
    properties = property_list.split("\n")
    # Now add the values
    for prop in properties:
        if ":" in prop:
            parts = prop.split(":")
            value = meta_value(meta, parts[1], parts[0])
            if parts[0] not in blob:
                blob[parts[0]] = {}
            if prop == "Project Information:Theme":
                blob[parts[0]][parts[1]] = string_to_list(value)
            else:
                blob[parts[0]][parts[1]] = htmlise_value(value)
    # Finish off with the title and description from the project
    if PI_SLUG not in blob:
        blob[PI_SLUG] = {}
    blob[PI_SLUG]["title"] = htmlise_value(proj["name"])
    blob[PI_SLUG]["description"] = htmlise_value(proj["description"])
    return blob


def check_project_dir_exists(key, projects_directory):
    """
    Ensure that the directory exists for the specified project and,
    if it doesn't, create and initialise the posts file.
    """
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
    """
    Ensure project directories exist for projects that exist, and remove
    directories for those projects that no longer exist.
    """
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
    for proj in projects:
        check_project_dir_exists(proj["key"], projects_directory)
        project_keys_lower.append(proj["key"].lower())
    #
    # Remove any directories that exist for projects that don't ...
    subdirs = [f.name for f in os.scandir(projects_directory) if f.is_dir()]
    for sub in subdirs:
        if sub not in project_keys_lower:
            shutil.rmtree("%s/%s" % (projects_directory, sub))


def main():
    """ Main code. """
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
    working_dir = json_generation_lib.working_dir()
    sync_project_pages(project_data, "%s/website/_pages/projects" % working_dir)
    json_generation_lib.do_the_git_bits(
        project_data, "%s/website/_data/projects.json" % working_dir)


if __name__ == '__main__':
    main()
