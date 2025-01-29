""" Generate the JSON file used to drive the Projects data. """

import base64
import copy
import sys

import requests
# from requests.auth import HTTPBasicAuth

import json_generation_lib
# from linaro_vault_lib import get_vault_secret
import ssmparameterstorelib

ADDED_TO_JSON = {}

NOT_ADDED_TO_JSON = {}

NESTING_LEVEL = 0

PROJECT_INFORMATION = "Project Information"

PROJECT_TEMPLATE = {
    PROJECT_INFORMATION: {
        "Project Homepage": None,
        "How to participate": None,
        "description": None,
        "title": None
    },
    "icon": None,
    "key": None,
    "membership": None
}

# What do the various MD fields map onto name-wise
FIELD_NAMES = {
    "Home Page": "Project Homepage",
    "Projects Keys": "key",
    "Steering Entity": "How to participate"
}

# Where do the various MD fields map? If a field is listed
# here then the value from Jira is processed to make sure
# it can be displayed OK on the webpage.
FIELD_LOCATIONS = {
    "Projects Keys": None,
    "Theme": PROJECT_INFORMATION,
    "Home Page": PROJECT_INFORMATION,
    # "Project tag line": PROJECT_INFORMATION,
    "Steering Entity": PROJECT_INFORMATION
}

# Membership level mappings
MEMBERSHIP_MAPPINGS = {
    "Consumer Group": "lcg",
    "Edge & Fog Computing Group": "ledge",
    "Data Center Group": "ldcg",
    "IoT & Embedded Group": "lite"
}

IGNORE_MEMBERSHIP_MAPPINGS = {
    "Core Membership": "code",
    "Club Membership": "club",
    "Project Membership": "project"
}

# def initialise_auth():
#     """ Return encoded authentication """
#     username = get_vault_secret(
#         "secret/user/atlassian-cloud-it-support-bot",
#         iam_role="arn:aws:iam::968685071553:role/vault_jira_project_updater",
#         key="id")
#     password = get_vault_secret(
#         "secret/user/atlassian-cloud-it-support-bot",
#         iam_role="arn:aws:iam::968685071553:role/vault_jira_project_updater",
#         key="pw")
#     # Construct a string of the form username:password
#     combo = "%s:%s" % (username, password)
#     # Encode it to Base64
#     combo_bytes = combo.encode('ascii')
#     base64_bytes = base64.b64encode(combo_bytes)
#     return base64_bytes.decode('ascii')

def initialise_auth():
    """ Return encoded authentication """
    username = ssmparameterstorelib.get_secret_from_ssm_parameter_store(
        "/secret/user/atlassian-cloud-it-support-bot", key="id"
    )
    password = ssmparameterstorelib.get_secret_from_ssm_parameter_store(
        "/secret/user/atlassian-cloud-it-support-bot", key="pw"
    )
    # Construct a string of the form username:password
    combo = "%s:%s" % (username, password)
    # Encode it to Base64
    combo_bytes = combo.encode('ascii')
    base64_bytes = base64.b64encode(combo_bytes)
    return base64_bytes.decode('ascii')

def jira_get(url, jira_auth):
    """ Get JSON-encoded data back from Jira """
    headers = {
        'Authorization': 'Basic %s' % jira_auth,
        'content-type': 'application/json'
    }
    try:
        response = requests.get(
            "https://linaro.atlassian.net/%s" % url,
            headers=headers)
        if response.status_code != 200:
            print("Getting %s failed with code %s" % (url, response.status_code))
            sys.exit(1)
        return response.json()
    except Exception as exc: # pylint: disable=broad-except
        print("While fetching %s, got exception: %s" % (url, str(exc)))
        sys.exit(1)

def get_metadata_fields(jira_auth):
    """ Get all of the MD fields from Jira """
    cf_dict = {}
    data = jira_get("rest/api/3/field", jira_auth)
    for field in data:
        name = field["name"]
        if name[:3] == "MD-":
            if name in cf_dict:
                print("WARNING! Multiple occurrences of '%s'" % name)
            cf_dict[name] = field["id"]
            # Commented out because not all of the MD fields are being used
            # md_name = name[3:]
            # if md_name not in FIELD_LOCATIONS:
            #     print("WARNING! Cannot find %s in field mappings construct" % name)
    # Make sure that all of the field mappings have custom fields ...
    for key in FIELD_LOCATIONS:
        if "MD-%s" % key not in cf_dict:
            print("WARNING! Cannot find %s in field mappings" % key)
    return cf_dict

def get_meta_projects(jira_auth):
    """ Get project metadata from Jira """
    result = jira_get(
        "rest/api/2/search?jql=project=META+and+status!=Done&maxResults=1000", jira_auth
    )
    return result["issues"]

def meta_field(project, key, md_fields):
    """ Find the custom field with this key and return the value """
    md_key = "MD-%s" % key
    # Get the custom field reference for the key
    if md_key not in md_fields:
        print("Cannot find '%s' in metadata custom fields" % key)
        return None
    cf_id = md_fields[md_key]
    # print("%s maps to %s" % (md_key, cf_id))
    if cf_id not in project["fields"]:
        print("No value for '%s' in project's metadata issue" % key)
        return None
    value = project["fields"][cf_id]
    if value is None:
        return None
    if isinstance(value, dict):
        # User picker fields have different structures ...
        if "emailAddress" in project["fields"][cf_id]:
            # Return the entire dict so that we can identify it
            # as a user object.
            return project["fields"][cf_id]
        return project["fields"][cf_id]["value"]
    if isinstance(value, list):
        # Lists are of dictionaries of values so need to build the list value
        result = []
        for list_value in value:
            result.append(list_value["value"])
        return result
    return value


def process_membership(project, md_fields):
    """ Get the membership access from Jira & convert to groups """
    access = meta_field(project, "Membership Access", md_fields)
    if access is None:
        return []
    result = []
    for level in access:
        if level in MEMBERSHIP_MAPPINGS:
            result.append(MEMBERSHIP_MAPPINGS[level])
        elif level not in IGNORE_MEMBERSHIP_MAPPINGS:
            print(f"Don't know how to map '{level}' onto a LDAP group")
    return result


def get_project_key(project, md_fields):
    """ Retrieve the singleton project key from Jira's list """
    proj_key = meta_field(project, "Projects Keys", md_fields)
    if proj_key is None:
        return None
    # The project key is, for some strange reason, a list so just
    # return the first element.
    return proj_key[0]


def ok_to_proceed(project, md_fields):
    """ Check the various fields to make sure we can process this project """
    if meta_field(project, "Published", md_fields) != "Yes":
        NOT_ADDED_TO_JSON[project["key"]] = "Not marked as published"
        return False
    proj_key = get_project_key(project, md_fields)
    if proj_key  is None:
        NOT_ADDED_TO_JSON[project["key"]] = "No Jira project key"
        return False
    # print("Proceeding with %s, a.k.a. %s" % (project["key"], proj_key))
    return True

def htmlise_email(name, addr):
    """ Convert email name/address into HTML """
    if addr[-1] == ".":
        got_fullstop = True
        addr = addr[:-1]
    else:
        got_fullstop = False
    if name is None:
        result = "<a href=\"mailto:%s\">%s</a>" % (addr, addr)
    else:
        result = (
            "%s <a class=\"email-icon\" href=\"mailto:%s\">"
            "<span class=\"icon-mail\"></span></a>" % (name, addr))
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
    result += htmlise_email(None, addr)
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

def create_how_to_participate(steering_entity):
    """ Create the text for How to Participate """
    visit = (
        "<p>Visit the [Linaro Membership|https://www.linaro.org/membership/] "
        "page for more information.</p>"
    )
    text = (
        "<p>Participation in this project can be achieved through Linaro Membership. "
        "The project is managed by %s.</p><p></p>"
    )
    if steering_entity is None:
        return visit
    return text % steering_entity + visit

def process_field(project_dict, parent_level, field_name, field_value):
    """ Convert the value into something usable for HTML """
    if parent_level is None:
        dict_level = project_dict
    else:
        dict_level = project_dict[parent_level]
    if field_name == "How to participate":
        field_value = create_how_to_participate(field_value)
    if isinstance(field_value, dict):
        # We are assuming this is a user blob
        dict_level[field_name] = htmlise_email(
            field_value["displayName"], field_value["emailAddress"])
    elif isinstance(field_value, list):
        dict_level[field_name] = field_value
    elif field_value is not None:
        dict_level[field_name] = htmlise_value(field_value)

def construct_blob(project, md_fields, icon):
    """ Create a project blob for this project """
    proj_key = get_project_key(project, md_fields)
    # We don't display projects that don't have an icon
    if icon is None:
        print(f"WARNING! Using Linaro Sprinkle as fallback icon for {proj_key}")
        icon = "https://www.linaro.org/assets/images/Linaro-Sprinkle.png"
    # DEEPCOPY the project template otherwise Python updates the "master" version
    # Using dict() or copy() only does a shallow copy.
    result = copy.deepcopy(PROJECT_TEMPLATE)
    summary = project["fields"]["summary"]
    if summary is not None:
        process_field(result, PROJECT_INFORMATION, "title", summary)
    description = project["fields"]["description"]
    if description is not None:
        process_field(result, PROJECT_INFORMATION, "description", description)
    result["icon"] = icon
    result["membership"] = process_membership(project, md_fields)
    for field in FIELD_LOCATIONS:
        where = FIELD_LOCATIONS[field]
        field_value = meta_field(project, field, md_fields)
        if field in FIELD_NAMES:
            field_name = FIELD_NAMES[field]
        else:
            field_name = field
        process_field(result, where, field_name, field_value)
    # Don't display projects that don't have anything to say! We don't check
    # the "how to participate" value because that will always have a value.
    info = result[PROJECT_INFORMATION]
    if info["Project Homepage"] is None and \
            info["description"] is None:
        NOT_ADDED_TO_JSON[project["key"]] = f"No displayable information for {proj_key}"
        return None
    return result

def get_jira_icon(project, md_fields, jira_auth):
    """ Figure out the URL for the project's icon """
    key = get_project_key(project, md_fields)
    headers = {
        'Authorization': 'Basic %s' % jira_auth,
        'content-type': 'application/json'
    }
    response = requests.get(
        "https://linaro.atlassian.net/rest/api/2/project/%s" % key,
        headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        return data["avatarUrls"]["48x48"]
    return None

def construct_project_data(jira_projects, md_fields, jira_auth):
    """ Convert the separate project data into a single Python object. """
    results = []
    for project in jira_projects:
        if ok_to_proceed(project, md_fields):
            icon = get_jira_icon(project, md_fields, jira_auth)
            blob = construct_blob(project, md_fields, icon)
            if blob is not None:
                proj_key = get_project_key(project, md_fields)
                ADDED_TO_JSON[project["key"]] = proj_key
                results.append(blob)
    # Sort the projects by title
    results = sorted(results, key=lambda x: x[PROJECT_INFORMATION]["title"])
    return {
        "projects": results
    }

def main():
    """ Main code. """
    jira_auth = initialise_auth()
    md_fields = get_metadata_fields(jira_auth)
    jira_projects = get_meta_projects(jira_auth)
    data = construct_project_data(jira_projects, md_fields, jira_auth)
    working_dir = json_generation_lib.working_dir()
    if json_generation_lib.do_the_git_bits(
        data, "%s/website/_data/projects.json" % working_dir):
        if len(NOT_ADDED_TO_JSON) != 0:
            print("Projects not published:")
            for proj in NOT_ADDED_TO_JSON:
                print(f"   {proj}: {NOT_ADDED_TO_JSON[proj]}")
        if len(ADDED_TO_JSON) == 0:
            print("No projects published!")
        else:
            print("Projects published:")
            for proj in ADDED_TO_JSON:
                print(f"   {proj} aka {ADDED_TO_JSON[proj]}")
        

if __name__ == '__main__':
    main()
