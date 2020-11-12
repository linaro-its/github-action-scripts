#!/usr/bin/python3

import requests
from requests.auth import HTTPBasicAuth
from ldap3 import Connection, SUBTREE
import re
import json
import vault_auth
from io import StringIO

server = "https://collaborate.linaro.org"
auth = ""
connection = None

member_status_page_part_1 = (
    '<p class="auto-cursor-target"><br /></p>'
    '<ac:structured-macro ac:name="run">'
    '<ac:parameter ac:name="replace">s1:choice:?Member:select:'
)
member_status_page_part_2 = (
    '</ac:parameter>'
    '<ac:parameter ac:name="atlassian-macro-output-type">INLINE</ac:parameter>'
    '<ac:rich-text-body>'
    '<p class="auto-cursor-target"><br /></p>'
    '<ac:structured-macro ac:name="jython">'
    '<ac:parameter ac:name="output">wiki</ac:parameter>'
    '<ac:parameter ac:name="var1">$s1</ac:parameter>'
    '<ac:parameter ac:name="script">'
    '#confluence-member-breakdowns/display_member_status.jython'
    '</ac:parameter><ac:parameter ac:name="atlassian-macro-output-type">'
    'INLINE</ac:parameter></ac:structured-macro>'
    '<p class="auto-cursor-target"><br /></p>'
    '</ac:rich-text-body></ac:structured-macro>'
    '<p><br /></p>'
)

membership_levels_page_part_1 = (
    '<p class="auto-cursor-target"><br /></p>'
    '<ac:structured-macro ac:name="run">'
    '<ac:parameter ac:name="replace">s1:choice:?Membership:select:'
)
membership_levels_page_part_2 = (
    '</ac:parameter>'
    '<ac:parameter ac:name="atlassian-macro-output-type">INLINE</ac:parameter>'
    '<ac:rich-text-body>'
    '<p class="auto-cursor-target"><br /></p>'
    '<ac:structured-macro ac:name="jython">'
    '<ac:parameter ac:name="output">wiki</ac:parameter>'
    '<ac:parameter ac:name="var1">$s1</ac:parameter>'
    '<ac:parameter ac:name="script">'
    '#confluence-member-breakdowns/display_status_members.jython'
    '</ac:parameter><ac:parameter ac:name="atlassian-macro-output-type">'
    'INLINE</ac:parameter></ac:structured-macro>'
    '<p class="auto-cursor-target"><br /></p>'
    '</ac:rich-text-body></ac:structured-macro>'
    '<p><br /></p>'
)


def clean_up_page_content(content):
    # Remove ac:schema-version="?"
    inter1 = re.sub(r' ac:schema-version="\d"', '', content)
    # Remove ac:macro-id="?-?-?-?-?"
    return re.sub(
        r' ac:macro-id="[0-9a-f]+-[0-9a-f]+-[0-9a-f]+-[0-9a-f]+-[0-9a-f]+"',
        '',
        inter1)


def assert_equal_long_string(a, b):
    NOT, POINT = '-', '*'
    if a != b:
        print(a)
        o = ''
        for i, e in enumerate(a):
            try:
                if e != b[i]:
                    o += POINT
                else:
                    o += NOT
            except IndexError:
                o += '*'

        o += NOT * (len(a)-len(o))
        if len(b) > len(a):
            o += POINT * (len(b)-len(a))

        print(o)
        print(b)


def save_page(key, body):
    result = requests.get(
        "%s/rest/api/content/%s?expand=body.storage,version" % (server, key),
        auth=auth)
    if result.status_code == 200:
        j = result.json()
        current_content = clean_up_page_content(j["body"]["storage"]["value"])
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
                "%s/rest/api/content/%s" % (server, key),
                auth=auth,
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


def get_vault_secret(user_id):
    secret = vault_auth.get_secret(
        user_id,
        iam_role="vault_confluence_ldap_automation",
        url="https://login.linaro.org:8200"
    )
    return secret["data"]["pw"]


def initialise_ldap():
    global connection
    username = "cn=moinmoin,ou=binders,dc=linaro,dc=org"
    password = get_vault_secret("secret/ldap/{}".format(username))
    connection = Connection(
            'ldaps://login.linaro.org',
            user=username,
            password=password,
            auto_bind=True
        )


def initialise_confluence():
    global auth
    username = "it.support.bot"
    password = get_vault_secret("secret/ldap/{}".format(username))
    auth = HTTPBasicAuth(username, password)


def find_members():
    # Returns a list of Member names from LDAP where a Member is defined
    # as someone having at least one Organizational Status value.
    members = {}
    with connection:
        if connection.search(
                "ou=accounts,dc=linaro,dc=org",
                search_filter="(objectClass=organizationalUnit)",
                search_scope=SUBTREE,
                attributes=[
                    "ou",
                    "organizationalStatus",
                    "displayName"
                    ]
                ):
            for entry in connection.entries:
                if ("organizationalStatus" in entry and
                        "displayName" in entry and
                        entry["organizationalStatus"].values != []):
                    name = entry["displayName"].value
                    ou = entry["ou"].value
                    if ou not in members:
                        members[ou] = name
    return members


def find_levels():
    # Returns a list of the different membership levels declared for
    # the Members.
    levels = []
    with connection:
        if connection.search(
                "ou=accounts,dc=linaro,dc=org",
                search_filter="(objectClass=organizationalUnit)",
                search_scope=SUBTREE,
                attributes=["organizationalStatus"]
                ):
            for entry in connection.entries:
                for level in entry["organizationalStatus"].values:
                    if level not in levels:
                        levels.append(level)
            # Sort the list
            levels.sort()
    return levels


def main():
    # Get the credentials from the vault
    initialise_ldap()
    initialise_confluence()

    # Rebuild member status page
    #
    # Get a list of all of the Members from LDAP
    members = find_members()
    new_page = StringIO()
    new_page.write(member_status_page_part_1)
    # Need to generate a list of tuples that are the dictionary
    # sorted by value (i.e. the display name)
    sorted_by_value = sorted(
        members.items(),
        key=lambda kv: kv[1]
    )
    for v in sorted_by_value:
        new_page.write(":%s:%s" % (v[0], v[1]))
    new_page.write(member_status_page_part_2)
    save_page("105414715", new_page.getvalue())

    # Rebuild membership levels page
    #
    # Get a list of all of the levels from LDAP
    levels = find_levels()
    new_page = StringIO()
    new_page.write(membership_levels_page_part_1)
    for level in levels:
        new_page.write(":%s:%s" % (level, level))
    new_page.write(membership_levels_page_part_2)
    save_page("105414727", new_page.getvalue())


if __name__ == '__main__':
    main()
