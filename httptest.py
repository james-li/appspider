# coding=utf-8
'''
Created on 2014年4月29日

@author: jamesl
'''
from urllib2 import HTTPError
import sys
import urllib2
import thread
from threading import Timer
import time
from multiprocessing import Process


def download(url):
    try:
        res = urllib2.urlopen(url)
        print res.read()
        return True
    except HTTPError, err:
        if err.code == 404:
            raise err
        else:
            return False
    except Exception, what:
        print what
        return False


class ht:
    def __init__(self):
        pass

    def do(self, string):
        time.sleep(11)
        print string


def terminate(proc):
    print "timeout"
    proc.terminate()


if __name__ == "__main__":
    h = ht()
    p = Process(target=h.do, args=['hello'])
    try:
        t = Timer(10, terminate, [p])
        p.start()
        p.join()
        t.cancel()
    #        if download(sys.argv[1]):
    #            print "download successed"
    #        else:
    #            print "download failed"
    except HTTPError, err:
        print err
    except:
        print "timeout"
