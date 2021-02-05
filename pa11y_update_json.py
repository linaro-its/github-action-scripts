""" Script to update a11y website JSON file. """
# The a11y.linaro.org website uses a JSON file to control what gets displayed
# on the front page.
#
# The JSON structure is:
# [
#     {
#         "site_id": "linaro.org",
#         "site_image": "https://foo",
#         "environments": [
#             {
#                 "button": "Staging",
#                 "report_url": "/staging.linaro.org/",
#                 "scan_date": "foo",
#                 "error_count": "13000"
#             },
#             {
#                 "button": "Production",
#                 "directory": "/production.linaro.org/",
#                 "scan_date": "foo",
#                 "error_count": "13000"
#             }
#         ]
#     }
# ]

import argparse
import json
import os
import time

import metadata_parser


def get_site_image_url(site):
    """ Get the URL to the site image for a given site. """
    try:
        page = metadata_parser.MetadataParser(url="https://%s" % site, search_head_only=True)
        return page.get_metadata_link("image")
    except SystemExit:
        # clean-up
        raise
    except KeyboardInterrupt: # pylint: disable=try-except-raise
        # clean-up
        raise
    except Exception: # pylint: disable=broad-except
        return ""


def get_error_count(site, working_directory):
    """ For a given site, get the number of errors. """
    with open("%s/%s.json" % (working_directory, site), 'r') as handle:
        data = json.load(handle)
        return data["errors"]


def get_file_datetime(site, working_directory):
    """ Get modification date time for site JSON file. """
    return time.strftime(
        "%H:%M %d-%b-%Y",
        time.gmtime(
            os.path.getmtime(
                "%s/%s.json" % (working_directory, site)
            )
        )
    )


def read_site_json_file():
    """ Read site configuration file. """
    try:
        with open('/srv/a11y.linaro.org/site-config.json', 'r') as handle:
            return json.load(handle)
    except SystemExit:
        # clean-up
        raise
    except KeyboardInterrupt: # pylint: disable=try-except-raise
        # clean-up
        raise
    except Exception: # pylint: disable=broad-except
        return []


def write_site_json_file(data):
    """ Write out the site configuration file. """
    # Sort the list based on the site ID before saving it.
    new_list = sorted(data, key=lambda k: k['site_id'])
    with open('/srv/a11y.linaro.org/site-config.json', 'w') as handle:
        json.dump(new_list, handle)


def update_data(config, site_name, working_directory):
    """ Add/update this scanned site to the config. """
    # Split the site name into the first part (staging/production) and
    # the rest.
    parts = site_name.split(".", 1)
    site_type = parts[0].capitalize()
    site_id = parts[1]
    if site_id == "ghactions.linaro.org":
        # If this is a website preview, do some further parsing to
        # figure out the PR number
        pr_parts = site_type.rsplit("-", 1)
        pr_num = pr_parts[1]
        site_type = "PR%s" % pr_num
        # and then figure out the correct site ID
        parts = pr_parts[0].replace("-", ".").split(".", 1)
        site_id = parts[1]        
    # Is the site already in the config?
    found_site_id = None
    found_site_type = None
    for site in config:
        if site["site_id"] == site_id:
            found_site_id = site
            for env in site["environments"]:
                if env["button"] == site_type:
                    found_site_type = env
                    break
            break
    if found_site_id is None:
        found_site_id = {
            "site_id": site_id,
            "environments": []
        }
        config.append(found_site_id)
    if found_site_type is None:
        found_site_type = {
            "button": site_type,
            "directory": "/%s/" % site_name
        }
        found_site_id["environments"].append(found_site_type)
    # Sort the environments so that they are consistently ordered on the page
    environments = found_site_id["environments"]
    found_site_id["environments"] = sorted(environments, key=lambda k: k['button'])
    # Just in case it got changed, update the site image URL
    found_site_id["site_image"] = get_site_image_url(site_id)
    found_site_type["error_count"] = get_error_count(site_name, working_directory)
    found_site_type["scan_date"] = get_file_datetime(site_name, working_directory)


def get_args():
    """ Get the script's commandline arguments. """
    parser = argparse.ArgumentParser()
    parser.add_argument("site", action="store")
    parser.add_argument("directory", action="store")
    args = parser.parse_args()
    return args.site, args.directory


def main():
    """ Main code. """
    site_name, working_directory = get_args()
    data = read_site_json_file()
    update_data(data, site_name, working_directory)
    write_site_json_file(data)


if __name__ == '__main__':
    main()
