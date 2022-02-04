#!/usr/bin/python3
#
# Scan the specified directories and, for each HTML file, find the "time"
# object so that the "x-amz-meta-last-modified" field on the corresponding
# S3 object can be set.
#
# Example "time" object:
# <time datetime="2014-03-26 15:30:47 +0000" itemprop="datePublished">Wednesday, March 26, 2014</time>
#
# We need it in this fomat: Wed, 09 Sep 2020 13:00:07 GMT

import sys
import os
from datetime import datetime

import boto3
from bs4 import BeautifulSoup


PROFILE_NAME = os.getenv("AWS_STATIC_SITE_PROFILE")
SESSION = boto3.session.Session(profile_name=PROFILE_NAME)
S3_CLIENT = SESSION.client('s3')
BUCKET = os.getenv("AWS_STATIC_SITE_URL")


def get_all_html_files(path):
    result = []
    for root, dirs, files in os.walk(path):
        process_html_files(result, files, root)
        process_html_files(result, dirs, root)
    return result


def process_html_files(result, files, root):
    for name in files:
        if name.endswith((".html", ".htm")):
            f = os.path.join(root, name)
            if f not in result:
                result.append(f)


def scan_directory(path):
    html_files = get_all_html_files(path)
    for hf in html_files:
        process_file(hf)


def process_file(filename):
    with open(filename, "r") as fh:
        data = fh.read()
    soup = BeautifulSoup(data, 'html.parser')
    if soup.time is None:
        return

    print(filename)
    # We have a time object
    dt = soup.time["datetime"]
    # Convert the dt string to the format we need
    dt_obj = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S +0000")
    web_dt = dt_obj.strftime("%a, %d %b %Y %H:%M:%S GMT")
    # Update the metadata on the S3 object
    s3_object = S3_CLIENT.head_object(Bucket=BUCKET, Key=filename)
    s3_object["Metadata"]["last-modified"] = web_dt
    S3_CLIENT.copy_object(
        Key=filename, Bucket=BUCKET,
        CopySource={'Bucket': BUCKET, 'Key': filename},
        CacheControl=s3_object["CacheControl"],
        ContentType=s3_object["ContentType"],
        Metadata=s3_object["Metadata"],
        MetadataDirective='REPLACE')


def main(path):
    if path[-1] != "/":
        path += "/"
    if os.path.isdir(f"{path}blog"):
        scan_directory(f"{path}blog")
    if os.path.isdir(f"{path}news"):
        scan_directory(f"{path}news")

if __name__ == '__main__':
    if len(sys.argv) == 1:
        sys.exit("Path to build directory must be specified")
    main(sys.argv[1])
