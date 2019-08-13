# coding=utf-8
'''
Created on 2014年5月4日

@author: jamesl
'''
import hashlib
import collections
import urllib
import json
import urllib2
import traceback
from urllib2 import HTTPError
import logging
import time
from spider_utils import http_response


class app_fetcher:
    '''
    classdocs
    '''

    def __init__(self, name, worker_queue):
        '''
        Constructor
        '''
        self.name = name
        self.w_queue = worker_queue

    def app_fetch(self):
        pass

    def get_json(self, url, data=None):
        for i in range(5):
            try:
                return json.load(http_response(url, data).get_dataobj())
            except HTTPError, err:
                logging.error("download %s failed:%s" % (url, str(err)))
                if err.code != 404:
                    time.sleep(i + 1)
                    continue
                else:
                    return None
            except Exception, what:
                logging.error("download %s failed:%s" % (url, str(what)))
                return None
        return None

    def push_app(self, url, app_info):
        app_info["source"] = self.name
        self.w_queue.push("to_download", (url, app_info))


class app_fetcher_shafa(app_fetcher):
    def __init__(self, worker_queue):
        app_fetcher.__init__(self, "shafa", worker_queue)
        self.key_map = {"http://app.shafa.com/api/market/list": "e6bBQ9865Y75NNP66pq3CO2E5J28oVKl",
                        "http://app.shafa.com/api/market/app": "e6bBQ9865Y75NNP66pq3CO2E5J28oVKl",
                        "http://app.shafa.com/api/market/get_app_reviews": "e6bBQ9865Y75NNP66pq3CO2E5J28oVKl"}
        self.my_device = "Xiaomi Digital MiBOX1S"
        self.version = 63

    def md5sum(self, param_string, salt):
        m = hashlib.md5()
        m.update(param_string + salt)
        return m.hexdigest()

    def gen_url(self, url, postconf):
        salt = self.key_map.get(url)
        if not salt:
            return None
        sorted_postconf = collections.OrderedDict(sorted(postconf.items(), key=lambda e: e[0]))
        param_string = urllib.urlencode(sorted_postconf)
        sign = self.md5sum(param_string, salt)
        return url + "?" + param_string + "&sign=" + sign

    def get_app_list(self, limit, offset, atype=0):
        postconf = {"category": "ALL",
                    "channel": "",
                    "lang": "zh-CN",
                    "device_name": self.my_device,
                    "limit": limit,
                    "offset": offset,
                    "sort_by": 1,
                    "type": atype,
                    "version": self.version}
        url = self.gen_url("http://app.shafa.com/api/market/list", postconf)
        app_list_json = self.get_json(url)
        if not app_list_json:
            return None
        return app_list_json.get("list")

    def get_app_review(self, aid):
        postconf = {"channel": "",
                    "device_name": self.my_device,
                    "app_id": aid,
                    "lang": "zh-CN",
                    "limit": 100,
                    "offset": 0,
                    "version": self.version}
        url = self.gen_url("http://app.shafa.com/api/market/get_app_reviews", postconf)
        app_review_json = self.get_json(url)
        if not app_review_json:
            return None
        return app_review_json

    def get_app_info(self, aid):
        # "http://app.shafa.com/api/market/app?
        # channel=&device_name=Xiaomi+Digital+MiBOX1S&id=5355d0939c52517271000001&lang=zh-CN&version=63&sign=1c944a57b30fac6725e414d2839b5040"
        postconf = {"channel": "",
                    "device_name": self.my_device,
                    "id": aid,
                    "lang": "zh-CN",
                    "version": self.version}
        url = self.gen_url("http://app.shafa.com/api/market/app", postconf)
        app_info_json = self.get_json(url)
        if not app_info_json:
            return None
        return app_info_json.get("info")

    def app_fetch(self):
        try:
            for atype in [0, 1, 2]:
                index = 0
                for offset_id in range(0, 10):
                    app_list = self.get_app_list(36, offset_id * 36, atype)
                    if not app_list:
                        break
                    for app in app_list:
                        aid = app.get("id")
                        if not aid:
                            break
                        app_info = dict(app.items() + self.get_app_info(aid).items())

                        for k, v in app_info.iteritems():
                            if isinstance(v, list):
                                print k, ":", " ".join(v)
                            else:
                                print k, ":", v
                        print "#########################################################"

                        for url in [app_info.get("apk").get("file_url")] + app_info.get("screenshots") + [
                            app_info.get("icon")]:
                            self.push_app(url, app_info)
                        index += 1


        except Exception:
            traceback.print_exc()


class app_fetcher_7po(app_fetcher):
    def __init__(self, worker_queue):
        app_fetcher.__init__(self, "7po", worker_queue)
        self.category_list = {"video": u"影视音乐",
                              "game": u"游戏娱乐",
                              "daily": u"生活日常",
                              "social": u"网络社交",
                              "education": u"教育学习",
                              "tools": u"系统工具"}

    def get_category_apps(self, category):
        pages = 1
        page = 0
        apps_num = 0
        while page < pages:
            postdata = urllib.urlencode({
                "versioncode": 27,
                "category": category,
                "sort": "new",
                "type": "Ojz",
                "page": "%d-20" % (page + 1),
                "mod": "download"
            })
            app_list = self.get_json(url="http://www.guozi.tv/interface.php?", data=postdata)
            if not app_list:
                break
            # print app_list.keys()
            if page == 0:
                pages = app_list.get("page").get("pagesize")
                total = int(app_list.get("page").get("total"))
            for app_info in app_list.get("apps"):
                for url in app_info.get("captures").split(";") + [app_info.get("url")] + [app_info.get("logo")]:
                    url = url.replace("&amp;", "&")
                    if not url:
                        continue
                    app_info["category"] = self.category_list.get(category)
                    self.push_app(url, app_info)
                    # obj=w_queue.pop("to_download")
                #                print obj
                apps_num += 1
            page += 1
        if apps_num != total:
            pass

    def app_fetch(self):
        for category in self.category_list.keys():
            self.get_category_apps(category)
