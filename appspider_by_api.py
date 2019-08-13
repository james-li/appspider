# coding=utf-8
'''
Created on 2014年4月25日

@author: jamesl
'''
import sys
from spider_utils import work_queue
from spider_thread import spider_thread_controller, spider_thread
from spider_utils import dbhandle
from MySQLdb import MySQLError
from spider_worker import app_downloader, app_db_worker
import logging
import os
from spider_utils import http_response
from app_fetcher import app_fetcher, app_fetcher_7po, app_fetcher_shafa
import traceback
import gevent
from gevent import monkey
import threading
from spider_env import spider_env


def fetch_app(source, worker_queue):
    try:
        fetch_instance = globals()["app_fetcher_" + source](worker_queue)
        if fetch_instance:
            fetch_instance.app_fetch()
    except:
        traceback.print_exc()


def app_spider(sourcelist):
    global env
    worker_queue = work_queue(10)
    w_controller = spider_thread_controller()
    dbh = None
    try:
        dbh = dbhandle(env.get("dbhost"), env.get("dbuser"), env.get("dbpwd"), env.get("dbname"))
    except MySQLError, e:
        print("Mysql connect Error %d:%s" % (e.args[0], e.args[1]))
        sys.exit(-1)

    work_threads = list()
    for i in range(env.get("fetcher_number")):
        work_threads.append(spider_thread(app_downloader(worker_queue, env.get("root"))))
    for i in range(env.get("dbworker_number")):
        work_threads.append(spider_thread(app_db_worker(dbh, worker_queue)))
    for t in work_threads:
        t.set_controller(w_controller)
        t.start()
    threads = list()
    for source in sourcelist:
        t = threading.Thread(target=fetch_app, args=[source, worker_queue])
        threads.append(t)
        t.start()
    for t in threads:
        t.join()
    logging.info("############################get all app info done######################################")
    w_controller.set_done_flag(True)
    for t in work_threads:
        t.join()


if __name__ == "__main__":
    reload(sys)
    sys.setdefaultencoding("utf-8")
    env = spider_env()
    if not env.parse(sys.argv):
        sys.exit(-1)

    logging.basicConfig(filename=os.path.join(os.getcwd(), env.get("logfile")), level=logging.DEBUG)
    monkey.patch_socket()
    if env.get("proxy"):
        http_response.set_proxy(env.get("proxy"))
    t = gevent.spawn(app_spider, ["shafa"])
    gevent.joinall([t])
