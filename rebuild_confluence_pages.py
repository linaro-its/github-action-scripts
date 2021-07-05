"""
Update the membership levels and status Confluence pages.
"""
#!/usr/bin/python3

import json
from io import StringIO

import requests
import vault_auth
from ldap3 import SUBTREE, Connection
from requests.auth import HTTPBasicAuth

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


def save_page(key, body):
    """ Save the page to Confluence if it has been updated """
    result = requests.get(
        "%s/rest/api/content/%s?expand=body.storage,version" % (SERVER, key),
        auth=AUTH)
    if result.status_code == 200:
        j = result.json()
        current_content = j["body"]["storage"]["value"]
        if body != current_content:
            # assertEqualLongString(current_content, body)
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


def get_vault_secret(user_id, key="pw"):
    """ Get a secret back from Vault """
    secret = vault_auth.get_secret(
        user_id,
        iam_role="vault_confluence_ldap_automation",
        url="https://login.linaro.org:8200"
    )
    return secret["data"][key]


def initialise_ldap():
    """ Initialise a LDAP connection """
    global CONNECTION # pylint: disable=global-statement
    username = "cn=moinmoin,ou=binders,dc=linaro,dc=org"
    password = get_vault_secret("secret/ldap/{}".format(username))
    CONNECTION = Connection(
            'ldaps://login.linaro.org',
            user=username,
            password=password,
            auto_bind=True
        )


def initialise_confluence():
    """ Initialise the Confluence authentication """
    global AUTH # pylint: disable=global-statement
    username = get_vault_secret("secret/user/atlassian-cloud-it-support-bot", "id")
    password = get_vault_secret("secret/user/atlassian-cloud-it-support-bot")
    AUTH = HTTPBasicAuth(username, password)


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
