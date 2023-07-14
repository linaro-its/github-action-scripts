#!/usr/bin/env python3
from argparse import ArgumentParser
import argparse
import logging as log
import os
import sys
import subprocess
from datetime import date
import urllib.request, json 
import datetime
import glob
from squad_client.utils import first, parse_test_name, parse_metric_name, to_json, get_class_name, getid
from squad_client.core.api import SquadApi
from squad_client.core.models import Squad, ALL

################################################################################
# Argument parser
################################################################################
def get_parser():
    """ Takes care of script argument parsing. """
    parser = ArgumentParser(description='Script used to generate a dashboard from SQUAD for nightly builds.')

    parser.add_argument('-gp', '--group_project', required=True, action="store", nargs="+",
            default=None,
            help='''Define which groups and projects to use. The format must be <group>/<project>. Several projects can be specified like this.''')

    parser.add_argument('-e', '--environment', required=False, action="store", nargs="+",
            default=None,
            help='''Limit the report to the specified environments such as board, emulator etc. Add multiple environments separated by space.''')

    parser.add_argument('-ts', '--test_suites', required=False, action="store", nargs="+",
            default=None,
            help='''Limit the report to the specified test suites. Add multiple test suites separated by space.''')

    parser.add_argument('-o', '--output_file', required=True, type=argparse.FileType('w'),
            help='''Output file to store the output.''')

    parser.add_argument('-i', '--input_file', type=argparse.FileType('r'), required=True,
            help="Input header file.")

    parser.add_argument('-v', required=False, action="store_true",
            default=False,
            help='''Output some verbose debugging info''')

    parser.add_argument('--dry-run', required=False, action="store_true",
            default=False,
            help='''Do not create any files''')

    return parser


################################################################################
# Logger
################################################################################
def initialize_logger(args):
    LOG_FMT = ("[%(levelname)s] %(funcName)s():%(lineno)d   %(message)s")
    lvl = log.ERROR
    if args.v:
        lvl = log.DEBUG

    log.basicConfig(
        # filename="core.log",
        level=lvl,
        format=LOG_FMT,
        filemode='w')


################################################################################
# Helper functions
################################################################################
def getJSONFromURL(url):
    with urllib.request.urlopen(url) as u:
        data = json.load(u)
        #print(data)
    return data


################################################################################
# Data functions
################################################################################
class Cell:
    def __init__(self, environment, suitename, buildversion, testrunid, group, project):
        self.environment = environment
        self.suitename = suitename
        self.buildversion = buildversion
        self.testrunid = testrunid
        self.group = group
        self.project = project

    def __str__(self):
        alttext = f"{self.buildversion} Results for {self.suitename} running on {self.environment}"
        imagemd = f"![{alttext}](https://qa-reports.linaro.org/{self.group}/{self.project}/build/latest-finished/badge?environment={self.environment}&suite={self.suitename}&passrate&title&hide_zeros=1)"
        return f'[{imagemd}](https://qa-reports.linaro.org/{self.group}/{self.project}/build/{self.buildversion}/testrun/{self.testrunid}/suite/{self.suitename}/tests/ "{alttext}")'



################################################################################
# Render functions
################################################################################
def render_dashboard(groups_projects, output_file, numberOfDays, selectedEnvs, selectedSuites, input_file):
    print(groups_projects)
    print(output_file)
    print(selectedEnvs)
    print(selectedSuites)
    print(input_file)
    SquadApi.configure(url='https://qa-reports.linaro.org/')
    cells = {}
    for gp in groups_projects:
        groupName = gp.split('/')[0]
        projectName = gp.split('/')[1]
        group = Squad().group(groupName)
        project = group.project(projectName)
        builds = project.builds(status__finished=True, count=numberOfDays)
        buildsArray = builds.items()
        environments = project.environments(count=ALL)
        suites = project.suites(count=ALL)
        for id, build in buildsArray:

            for id_tr, tr in build.testruns().items():
                if tr.completed:
                    for id_t, t in tr.tests().items():
                        environment = environments[getid(t.environment)]
                        env_name = environment.slug
                        suite = suites[getid(t.suite)]
                        ts_name = suite.slug
                        if ts_name in selectedSuites and env_name in selectedEnvs:
                            cells[(env_name, ts_name)] = Cell(env_name, ts_name, build.version, id_tr, groupName, projectName)
    output_file.write(input_file.read())
    output_file.write(f"## Latest daily results\n\n")
    output_file.write("| Test suite |")
    secondrow = "|:---|"
    for e in selectedEnvs:
        output_file.write(f" &nbsp; &nbsp; &nbsp; &nbsp; {e} &nbsp; &nbsp; &nbsp; &nbsp; |")
        secondrow += ":---:|"
    output_file.write(f"\n{secondrow}\n")
    for s in selectedSuites:
        output_file.write(f"| {s} |")
        for e in selectedEnvs:
            if (e,s) in cells:
                output_file.write(f" {cells[(e,s)]} |")
            else:
                output_file.write(" N/A |")
        output_file.write("\n")


def main():
    argv = sys.argv
    parser = get_parser()

    args = parser.parse_args()
    print(args)
    initialize_logger(args)

    render_dashboard(args.group_project, args.output_file, 1, args.environment, args.test_suites, args.input_file)

if __name__ == "__main__":
    main()
