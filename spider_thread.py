'''
Created on 2014-4-20

@author: Jamesl
'''

from threading import Thread, Lock
import logging
import time


class spider_thread_controller:
    def __init__(self):
        self.done = False
        self.lock = Lock()

    def set_done_flag(self, flag):
        with self.lock:
            self.done = flag

    def get_done_flag(self):
        with self.lock:
            return self.done


class spider_thread(Thread):
    def __init__(self, worker):
        Thread.__init__(self)
        self.worker = worker

    def set_controller(self, controller):
        self.controller = controller

    def done(self):
        if not self.controller:
            return self.worker.work_done()
        else:
            return self.worker.work_done() and self.controller.get_done_flag()

    def run(self):
        logging.info("%s thread started:%s" % (self.worker.get_name(), self.getName()))
        while not self.done():
            job = self.worker.get_job()
            sleep_time = 2
            if job:
                logging.info("%s thread(%s) handling %s" % (self.worker.get_name(), self.getName(), str(job[0])))
                self.worker.do_job(job)
                sleep_time = 0.1
            time.sleep(sleep_time)
        logging.info("thread %s will terminate" % (self.getName()))
