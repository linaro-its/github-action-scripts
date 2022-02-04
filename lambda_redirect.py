""" Set up the Lambda handler for URL redirects """
#!/usr/bin/python3


import argparse
import os
import sys
import time
import zipfile
from tempfile import mkstemp

import boto3
import requests

_PROFILE = (
    "AWS_STATIC_SITE_PROFILE"
)
_SITE_URL = (
    "AWS_STATIC_SITE_URL"
)
_CFDIST = (
    "CF_DIST_ID_STATIC_LO"
)
_LAMBDA_ROLE = (
    "arn:aws:iam::%s:role/service-role/lambda-redirect-role"
)
_NODE_RUNTIME = (
    "nodejs12.x"
)


def get_env_var(env):
    """ Get the required environment variable's value """
    env_value = os.environ.get(env)
    if env_value is None:
        print("Cannot retrieve environment variable '%s'" % env)
        sys.exit(1)
    return env_value


def lambda_list_functions():
    """ Return a list of the Lambda functions in us-east-1 """
    profile = get_env_var(_PROFILE)
    session = boto3.Session(profile_name=profile)
    client = session.client('lambda', 'us-east-1')
    return client.list_functions()["Functions"]


def lambda_func_exists():
    """ Does the redirect function exist in Lambda? """
    funcs = lambda_list_functions()
    required_name = lambda_func_from_var()
    for func in funcs:
        if func["FunctionName"] == required_name:
            return True
    return False


def lambda_func_from_var():
    """ Build and return the Lambda function name """
    url = get_env_var(_SITE_URL)
    return url + "-redirect"


def function_needs_updating(rules_file):
    """ Does the Lambda function need updating? """
    # Start by reading the proposed rules file because
    # if we can't read it, it is a build failure
    if os.path.isfile(rules_file):
        with open(rules_file, 'r') as file:
            proposed_file = file.read()
    else:
        print("'%s' isn't a file" % rules_file)
        sys.exit(1)
    # Does the function exist already on Lambda?
    if not lambda_func_exists():
        return True
    # Get the existing rules file from Lambda
    session = boto3.Session(profile_name=get_env_var(_PROFILE))
    client = session.client('lambda', 'us-east-1')
    response = client.get_function(
        FunctionName=lambda_func_from_var()
    )
    # Is the runtime correct? If not, we need to update.
    if response["Configuration"]["Runtime"] != _NODE_RUNTIME:
        return True
    # Download the zip file
    result = requests.get(response["Code"]["Location"])
    handle, zip_file = mkstemp(".zip")
    os.close(handle)
    with open(zip_file, 'wb') as file:
        file.write(result.content)
    # Now read the rules file from it
    with zipfile.ZipFile(zip_file) as myzip:
        with myzip.open('rules.json') as file:
            # .decode converts the bytes to a string
            current_file = file.read().decode()
    os.remove(zip_file)
    # Now compare the files
    if proposed_file != current_file:
        return True
    return False


# Ensure that all of the files have read permissions:
# http://www.deplication.net/2016/08/aws-troubleshooting-lamba-deployment.html
# We do this by explicitly setting the file attributes as
# we add the file to the zip file.
# See https://stackoverflow.com/a/48435482/305975
def add_file_to_zip(ziphandle, source_file, zip_filename):
    """ Add the specified file to the zip file """
    with open(source_file, "r") as handle:
        data = handle.read()
    info = zipfile.ZipInfo(zip_filename)
    info.date_time = time.localtime()
    info.external_attr = 0o100644 << 16
    ziphandle.writestr(info, data)


# The script is being run from the same directory that the
# supporting files are in.
def rebuild_zip_file(rules_file):
    """ Rebuild the Lambda zip file """
    handle, zip_file = mkstemp(".zip")
    os.close(handle)
    with zipfile.ZipFile(zip_file, 'w') as myzip:
        add_file_to_zip(myzip, rules_file, "rules.json")
        add_file_to_zip(
            myzip,
            "lambda-redirect/rules.js",
            "rules.js")
        add_file_to_zip(
            myzip,
            "lambda-redirect/index.js",
            "index.js")
    return zip_file


def aws_account_id():
    """ Get the account ID for the specified profile """
    session = boto3.Session(profile_name=get_env_var(_PROFILE))
    client = session.client("sts")
    return client.get_caller_identity()["Account"]


def publish_zip_file(zip_file):
    """ Publish the zip file as a Lambda function """
    with open(zip_file, 'rb') as content_file:
        content = content_file.read()
    session = boto3.Session(profile_name=get_env_var(_PROFILE))
    client = session.client('lambda', 'us-east-1')
    if lambda_func_exists():
        # Update the code associated with the existing function
        response = update_lambda_code(client, content)
    else:
        # Create a brand new function
        response = create_lambda_code(client, content)
    # Delete the temporarily created Zip file
    os.remove(zip_file)
    func_arn = response["FunctionArn"]
    # When the function is first created, the ARN doesn't have the version
    # at the end, so we need to test for that and add if missing
    ver = ":" + response["Version"]
    if not func_arn.endswith(ver):
        func_arn += ver
    print("Function arn: %s" % func_arn)
    # Now add the CloudFront trigger ...
    add_cloudfront_trigger(session, func_arn)

def add_cloudfront_trigger(session, func_arn):
    """ Point the CF origin request trigger at the function """
    cf_client = session.client('cloudfront', 'us-east-1')
    config = cf_client.get_distribution_config(
        Id=get_env_var(_CFDIST)
    )
    distrib_config = config["DistributionConfig"]
    dcb = distrib_config["DefaultCacheBehavior"]
    #
    # The distribution can have more than one LFA now so we need to
    # be careful about how we update the distribution.
    item_block = {
        "EventType": "origin-request",
        "LambdaFunctionARN": func_arn
    }
    if "LambdaFunctionAssociations" not in dcb:
        # No LFAs at all
        dcb["LambdaFunctionAssociations"] = {
            "Items": [
                item_block
            ],
            "Quantity": 1
        }
        print("Initialising LFA block to add redirect function")
    else:
        found = False
        if "Items" not in dcb["LambdaFunctionAssociations"]:
            # LFAs but no items
            dcb["LambdaFunctionAssociations"]["Items"] = []
        else:
            # We have LFAs so try to find the origin-request
            for lfa in dcb["LambdaFunctionAssociations"]["Items"]:
                # We can only have one origin-request LFA so, if
                # we find it, we update the function ARN.
                if lfa["EventType"] == "origin-request":
                    lfa["LambdaFunctionARN"] = func_arn
                    found = True
                    print("Updating origin-request function association")
                    break
        if not found:
            lfa_block = dcb["LambdaFunctionAssociations"]
            lfa_block["Items"].append(item_block)
            lfa_block["Quantity"] = lfa_block["Quantity"] + 1
            print(
                "Adding redirect function, total of %s" %
                lfa_block["Quantity"])
    cf_client.update_distribution(
        DistributionConfig=distrib_config,
        Id=get_env_var(_CFDIST),
        IfMatch=config["ETag"]
    )
    print("CloudFront distribution updated")

def create_lambda_code(client, content):
    """ Create a brand new Lambda function """
    response = client.create_function(
        FunctionName=lambda_func_from_var(),
        Runtime=_NODE_RUNTIME,
        Role=_LAMBDA_ROLE % aws_account_id(),
        Handler="index.handler",
        Description="Redirection handler",
        Code={"ZipFile": content},
        Publish=True
    )
    print("Lambda function created")
    return response

def wait_for_update(client):
    """
    Wait for the Lambda update to finish before proceeding
    to the next step. AWS introduced step states so we have
    to wait otherwise the next step will fail.
    https://docs.aws.amazon.com/lambda/latest/dg/functions-states.html
    """
    while True:
        result = client.get_function(FunctionName=lambda_func_from_var())
        last_state = result["Configuration"]["LastUpdateStatus"]
        if last_state == "Successful":
            return
        print(f"Current Lambda update state is {last_state} ... sleeping for a bit")
        time.sleep(10)

def update_lambda_code(client, content):
    """ Update the code associated with the existing function """
    client.update_function_code(
        FunctionName=lambda_func_from_var(),
        ZipFile=content,
        Publish=True
    )
    wait_for_update(client)
    # Make sure the runtime version gets updated
    client.update_function_configuration(
        FunctionName=lambda_func_from_var(),
        Runtime=_NODE_RUNTIME
    )
    wait_for_update(client)
    response = client.publish_version(
        FunctionName=lambda_func_from_var()
    )
    print("Lambda function updated")
    return response

def main():
    """ Main! """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-r',
        '--redirect_file',
        nargs='?',
        default=None,
        help='specifies the JSON rules file'
    )
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    if args.redirect_file is None:
        parser.print_help()
        sys.exit()

    # Because git doesn't preserve datestamps when cloning or pulling,
    # we have to retrieve the existing rules file from Lambda and compare
    # it with the file we are being asked to upload
    if args.force or function_needs_updating(args.redirect_file):
        zip_file = rebuild_zip_file(args.redirect_file)
        publish_zip_file(zip_file)
    else:
        print("Skipping update of Lambda function")

if __name__ == '__main__':
    main()
