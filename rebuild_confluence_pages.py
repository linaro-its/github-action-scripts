"""
Update the Confluence pages showing membership levels, membership status
and member logos.
"""
#!/usr/bin/python3

import json
import re
from io import StringIO

import requests
from ldap3 import SUBTREE, Connection
from requests.auth import HTTPBasicAuth

# from linaro_vault_lib import get_vault_secret
import ssmparameterstorelib

IMAGE_URL = "https://static.linaro.org/common/member-logos"
SERVER = "https://linaro.atlassian.net/wiki"
AUTH = ""
CONNECTION = None

def assert_equal_long_string(string1, string2):
    """ Show where two strings differ """
    dash, asterisk = '-', '*'
    if string1 != string2:
        print(string1)
        diffs = ''
        for i, element in enumerate(string1):
            try:
                if element != string2[i]:
                    diffs += asterisk
                else:
                    diffs += dash
            except IndexError:
                diffs += '*'

        diffs += dash * (len(string1)-len(diffs))
        if len(string2) > len(string1):
            diffs += asterisk * (len(string2)-len(string1))

        print(diffs)
        print(string2)


_REGEX1 = (
    r' ac:macro-id="[0-9a-f]+-[0-9a-f]+-[0-9a-f]+-[0-9a-f]+-[0-9a-f]+"'
)

_REGEX5 = (
    r' ac:local-id="[0-9a-f]+-[0-9a-f]+-[0-9a-f]+-[0-9a-f]+-[0-9a-f]+"'
)

_REGEX2 = (
    r' ri:version-at-save="[0-9]+"'
)

_REGEX3 = (
    r' data-layout="default"'
)

_REGEX4 = (
    r' style="width: [.0-9]+px;"'
)

def clean_up_page_content(content):
    """
    Remove content from the Confluence storage format that
    we cannot reproduce when we are building the page. This
    content is, thankfully, not necessary when creating the
    page!
    """
    # Remove ac:schema-version="?"
    inter1 = re.sub(r' ac:schema-version="\d"', '', content)
    # Remove ac:macro-id and ac:local-id
    inter1a = re.sub(_REGEX1, '', inter1)
    inter2 = re.sub(_REGEX5, '', inter1a)
    # Remove ri:version-at-save="?"
    inter3 = re.sub(_REGEX2, '', inter2)
    # Remove data-layout
    inter4 = re.sub(_REGEX3, '', inter3)
    # Remove the table column widths ... risky :)
    return re.sub(_REGEX4, '', inter4)


def save_page(key, body):
    """ Save the page to Confluence if it has been updated """
    result = requests.get(
        "%s/rest/api/content/%s?expand=body.storage,version" % (SERVER, key),
        auth=AUTH)
    if result.status_code == 200:
        j = result.json()
        current_content = clean_up_page_content(j["body"]["storage"]["value"])
        if body != current_content:
            assert_equal_long_string(current_content, body)
            current_version = j["version"]["number"]
            new_version = int(current_version) + 1
            data = {
                "id": key,
                "type": "page",
                "title": j["title"],
                "body": {
                    "storage": {
                        "value": body,
                        "representation": "storage"
                    }
                },
                "version": {
                    "number": new_version
                }
            }
            headers = {'content-type': 'application/json'}
            post_result = requests.put(
                "%s/rest/api/content/%s" % (SERVER, key),
                auth=AUTH,
                data=json.dumps(data),
                headers=headers)
            if post_result.status_code == 200:
                print("%s: Page successfully updated." % key)
            else:
                print("%s: Updating page failed with status code %s" % (
                    key, post_result.status_code))
                print(post_result.text)
    else:
        print("%s: Couldn't retrieve content" % key)


# def initialise_ldap():
#     """ Initialise a LDAP connection """
#     global CONNECTION # pylint: disable=global-statement
#     username = "cn=moinmoin,ou=binders,dc=linaro,dc=org"
#     password = get_vault_secret("secret/ldap/{}".format(username),
#                                 iam_role="arn:aws:iam::968685071553:role/vault_confluence_ldap_automation")
#     CONNECTION = Connection(
#             'ldaps://login.linaro.org',
#             user=username,
#             password=password,
#             auto_bind="DEFAULT"
#         )


def initialise_ldap():
    """ Initialise a LDAP connection """
    global CONNECTION # pylint: disable=global-statement
    username = "cn=moinmoin,ou=binders,dc=linaro,dc=org"
    password = ssmparameterstorelib.get_secret_from_ssm_parameter_store(
         "/secret/ldap/moinmoin"         
    )
    CONNECTION = Connection(
            'ldaps://login.linaro.org',
            user=username,
            password=password,
            auto_bind="DEFAULT"
        )

# def initialise_confluence():
#     """ Initialise the Confluence authentication """
#     global AUTH # pylint: disable=global-statement
#     username = get_vault_secret("secret/user/atlassian-cloud-it-support-bot",
#                                 iam_role="arn:aws:iam::968685071553:role/vault_confluence_ldap_automation",
#                                 key="id")
#     password = get_vault_secret("secret/user/atlassian-cloud-it-support-bot",
#                                 iam_role="arn:aws:iam::968685071553:role/vault_confluence_ldap_automation")
#     AUTH = HTTPBasicAuth(username, password)


def initialise_confluence():
    """ Initialise the Confluence authentication """
    global AUTH # pylint: disable=global-statement
    username = ssmparameterstorelib.get_secret_from_ssm_parameter_store(
        "/secret/user/atlassian-cloud-it-support-bot", key="id"
    )
    password = ssmparameterstorelib.get_secret_from_ssm_parameter_store(
        "/secret/user/atlassian-cloud-it-support-bot"         
    )
    AUTH = HTTPBasicAuth(username, password)


def find_logos():
    """
    Returns a list of Member names and their OU name, which is used to
    name the file on S3. Only members that have a logo are included
    in the list. A member is defined as having at least one
    Organizational Status value.
    """
    members = {}
    with CONNECTION:
        if CONNECTION.search(
                "ou=accounts,dc=linaro,dc=org",
                search_filter="(objectClass=organizationalUnit)",
                search_scope=SUBTREE,
                attributes=[
                    "organizationalStatus",
                    "displayName",
                    "jpegPhoto",
                    "ou"
                    ]
                ):
            for entry in CONNECTION.entries:
                if ("organizationalStatus" in entry and
                        "displayName" in entry and
                        entry["organizationalStatus"].values != [] and
                        entry["jpegPhoto"].value is not None):
                    name = entry["displayName"].value
                    members[name] = entry["ou"].value
    return members


def find_members():
    """
    Returns a list of Member names from LDAP where a Member is defined
    as someone having at least one Organizational Status value.
    """
    members = {}
    with CONNECTION:
        if CONNECTION.search(
                "ou=accounts,dc=linaro,dc=org",
                search_filter="(objectClass=organizationalUnit)",
                search_scope=SUBTREE,
                attributes=[
                    "organizationalStatus",
                    "displayName"
                    ]
                ):
            for entry in CONNECTION.entries:
                if ("organizationalStatus" in entry and
                        "displayName" in entry and
                        entry["organizationalStatus"].values != []):
                    name = entry["displayName"].value
                    members[name] = list_to_comma_string(entry["organizationalStatus"].values)
    return members


def list_to_comma_string(this_list):
    """ Return a comma separated string from the list provided """
    result = ""
    for list_entry in this_list:
        if result != "":
            result += ", "
        result += list_entry
    return result


def find_levels():
    """
    Returns a list of the different membership levels declared for
    the Members.
    """
    levels = {}
    with CONNECTION:
        if CONNECTION.search(
                "ou=accounts,dc=linaro,dc=org",
                search_filter="(objectClass=organizationalUnit)",
                search_scope=SUBTREE,
                attributes=["organizationalStatus", "displayName"]
                ):
            for entry in CONNECTION.entries:
                for level in entry["organizationalStatus"].values:
                    if level not in levels:
                        levels[level] = []
                    levels[level].append(entry["displayName"].value)
    # Turn the list of members per level into a comma-separated string
    for level in levels:
        members = sorted(levels[level])
        levels[level] = list_to_comma_string(members)
    return levels


def main():
    """ Main! """
    # Get the credentials from the vault
    initialise_ldap()
    initialise_confluence()

    # Rebuild member status page
    #
    # Get a list of all of the Members from LDAP
    members = find_members()
    new_page = StringIO()
    new_page.write(
        "<p>The information on this page is taken from the LDAP system managed "
        "by IT Services. If you see any mistakes regarding the membership status for "
        "a given Member, please contact IT Services with the correct information. "
        "Thank you.</p>"
        "<ul>"
    )
    # Need to generate a list of tuples that are the dictionary
    # sorted by key (i.e. the display name)
    sorted_by_value = sorted(
        members.items(),
        key=lambda kv: kv[0]
    )
    for value in sorted_by_value:
        new_page.write("<li><p><strong>%s</strong> - %s</p></li>" % (value[0], value[1]))
    new_page.write("</ul>")
    save_page("14358150936", new_page.getvalue())

    # Rebuild member logo page
    #
    members = find_logos()
    new_page = StringIO()
    new_page.write(
        "<p>This page shows the logo stored in LDAP for each Member. "
        "If you need to update a logo, please submit it <strong>in JPEG "
        "format</strong> as an IT Support ticket.</p><p />"
    )
    # Need to generate a list of tuples that are the dictionary
    # sorted by key (i.e. the display name)
    sorted_by_value = sorted(
        members.items(),
        key=lambda kv: kv[0]
    )
    content_html = StringIO()
    content_html.write("&lt;center&gt;")
    for value in sorted_by_value:
        content_html.write("&lt;figure&gt;")
        content_html.write(f"&lt;img src=\\&quot;{IMAGE_URL}/{value[1]}.jpg\\&quot; alt=\\&quot;{value[0]}\\&quot; height=120&gt;")
        content_html.write(f"&lt;figcaption&gt;{value[0]}")
        content_html.write("&lt;/figcaption&gt;&lt;/figure&gt;")
    content_html.write("&lt;/center&gt;")

    # Unlike the other pages, we need to use the HTML macro because we
    # are loading the image files over HTTPS.
    new_page.write(
        '<ac:structured-macro ac:name="easy-html-macro">'
        '<ac:parameter ac:name="theme">'
        '{&quot;label&quot;:&quot;solarized_dark&quot;,&quot;value&quot;:&quot;solarized_dark&quot;}'
        '</ac:parameter>'
        '<ac:parameter ac:name="contentByMode">'
        '{&quot;html&quot;:'
        f"&quot;{content_html.getvalue()}&quot;,"
        '&quot;javascript&quot;:&quot;&quot;,'
        '&quot;css&quot;:&quot;&quot;}'
        '</ac:parameter></ac:structured-macro>'
    )
    save_page("28680519845", new_page.getvalue())

    # Rebuild membership levels page
    #
    # Get a list of all of the levels from LDAP
    levels = find_levels()
    new_page = StringIO()
    new_page.write(
        "<p>The information on this page is taken from the LDAP system managed "
        "by IT Services. If you see any mistakes regarding the membership status for "
        "a given Member, please contact IT Services with the correct information. "
        "Thank you.</p>"
        "<ul>"
    )
    for level in levels:
        new_page.write("<li><p><strong>%s</strong> - %s</p></li>" % (level, levels[level]))
    new_page.write("</ul>")
    save_page("14358150948", new_page.getvalue())


if __name__ == '__main__':
    main()
