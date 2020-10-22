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

import os
from datetime import datetime

import boto3
from bs4 import BeautifulSoup


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
    s3_object = s3_client.head_object(Bucket=bucket, Key=filename)
    s3_object["Metadata"]["last-modified"] = web_dt
    s3_client.copy_object(
        Key=filename, Bucket=bucket,
        CopySource={'Bucket': bucket, 'Key': filename},
        CacheControl=s3_object["CacheControl"],
        ContentType=s3_object["ContentType"],
        Metadata=s3_object["Metadata"],
        MetadataDirective='REPLACE')


profile_name = os.getenv("AWS_STATIC_SITE_PROFILE")
session = boto3.session.Session(profile_name=profile_name)
s3_client = session.client('s3')
bucket = os.getenv("AWS_STATIC_SITE_URL")
if os.path.isdir("blog"):
    scan_directory("blog")
if os.path.isdir("news"):
    scan_directory("news")
