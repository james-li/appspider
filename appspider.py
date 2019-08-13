#!/usr/bin/env python
# encoding: utf-8
'''
appspider.appspider -- shortdesc

appspider.appspider is a description

It defines classes_and_methods

@author:     user_name

@copyright:  2014 organization_name. All rights reserved.

@license:    license

@contact:    user_email
@deffield    updated: Updated
'''
import logging
import os
from getopt import getopt
import sys
import socket
from MySQLdb import MySQLError
from spider_utils import http_response, url_filter, work_queue, \
    dbhandle
from spider_thread import spider_thread
from spider_worker import url_fetcher, url_analyser, db_worker

db_host = "192.168.4.17"
db_user = "root"
db_passwd = "root"
db_schema = "CloudBox"


def usage(cmd):
    print(
                "usage: %s [-f|--fetcher] fetcher_number [-a|--analyser] analyser_number [-d|--dbworker] dbworker_num [-p|--proxy] proxy [-t|--timeout] timeout" % (
            cmd))


def main(args):
    logging.basicConfig(filename=os.path.join(os.getcwd(), "log.txt"), level=logging.DEBUG)
    fetcher_num = 1
    analyser_num = 1
    dbworker_num = 1
    timeout = 10
    try:
        opts, args = getopt(args[1:], "f:a:d:t:p:", ["fetcher=", "analyser=", "dbworker=", "timeout=", "proxy="])
        for o, v in opts:
            if o in ("-f", "--fetcher"):
                fetcher_num = int(v)
            elif o in ("-a", "--analyser"):
                analyser_num = int(v)
            elif o in ("-d", "--dbworker"):
                dbworker_num = int(v)
            elif o in ("-t", "--timeout"):
                timeout = int(v)
            elif o in ("-p", "--proxy"):
                http_response.set_proxy(v)
            else:
                usage(args[0])
                sys.exit(-1)
    except:
        usage(args[0])
        sys.exit(-1)
    socket.setdefaulttimeout(timeout)
    base_url = "http://app.shafa.com/list"

    a_filter = url_filter()
    a_filter.add_regex(r"http://app.shafa.com/list.*", "match")
    a_filter.add_regex(r"http://app.shafa.com/view/.*", "match")
    a_filter.add_regex(r"http://.*.sfcdn.org/.*", "match")
    w_queue = work_queue(10)
    w_queue.push("to_download", (base_url, None))
    dbh = None
    try:
        # dbh=dbhandle("192.168.4.17","root","root","CloudBox")
        dbh = dbhandle(db_host, db_user, db_passwd, db_schema)
    except MySQLError, e:
        print("Mysql connect Error %d:%s" % (e.args[0], e.args[1]))
        sys.exit(-1)
    threads = list()
    for i in range(fetcher_num):
        threads.append(spider_thread(url_fetcher(w_queue)))
    for i in range(analyser_num):
        threads.append(spider_thread(url_analyser(w_queue, a_filter=a_filter)))
    for i in range(dbworker_num):
        threads.append(spider_thread(db_worker(dbh, w_queue)))
    for t in threads:
        t.start()
    for t in threads:
        t.join()


if __name__ == "__main__":
    main(sys.argv)
