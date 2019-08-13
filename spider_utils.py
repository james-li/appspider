# coding=utf8
'''
Created on 2014年4月21日

@author: jamesl
'''
import urllib2
import re
import logging
import time
import os
from StringIO import StringIO
from gzip import GzipFile
import MySQLdb
from threading import Lock
from sgmllib import SGMLParser
from urlparse import urljoin
from subprocess import PIPE, Popen
import threading
from urllib2 import HTTPError
import traceback


class http_response:
    def __init__(self, url, postdata=None):
        self.url = url
        self.postdata = postdata
        self.response = None

    @staticmethod
    def set_proxy(proxy):
        proxy_support = urllib2.ProxyHandler({"http": proxy})
        opener = urllib2.build_opener(proxy_support, urllib2.HTTPHandler)
        urllib2.install_opener(opener)

    def get_response(self):
        if self.response:
            return self.response
        base_url = urlutils.get_base_url(self.url)
        # "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/34.0.1847.116 Safari/537.36", \

        req_headers = { \
            "User-Agent": "Dalvik/1.6.0 (Linux; U; Android 4.2.2; MiBOX1S Build/CADEV)", \
            "Referer": base_url, \
            "Accept-Encoding": "gzip" \
 \
            }
        real_url = urlutils.real_url(self.url)
        req = urllib2.Request(headers=req_headers, url=real_url, data=self.postdata)
        self.response = urllib2.urlopen(req, timeout=100)
        return self.response

    def get_url(self):
        return self.url

    def get_content_type(self):
        return self.get_response().info().getheader("Content-Type")

    def is_html(self):
        content_type = self.get_content_type()
        if content_type and content_type.startswith("text/html"):
            return True
        else:
            return False

    def get_filename(self):
        return os.path.basename(self.get_response().geturl())

    def get_fileext(self):
        return self.get_filename().split(".")[-1]

    def get_size(self):
        try:
            size = self.get_response().info().getheader("Content-Length")
            if not size:
                return 0
            else:
                return int(size)
        except:
            return 0

    def get_encode(self):
        return self.get_response().info().getheader("Content-Encoding")

    def get_dataobj(self):
        if not self.get_response():
            return None

        """
        buf.seek(0,os.SEEK_END)
        pos=buf.tell()
        print pos
        buf.seek(0,os.SEEK_SET)
        """
        if self.get_encode() == "gzip":
            buf = StringIO(self.get_response().read())
            return StringIO(GzipFile(fileobj=buf).read())
        else:
            return self.get_response()

    def build_dir(self, path):
        if os.path.isdir(path):
            return path + "/index.html"
        rindex = path.rfind('/')
        if rindex != -1:
            dirname = path[0:rindex]
            filename = path[rindex + 1:]
            if not filename:
                filename = "index.html"
        else:
            dirname = ""
            filename = path
        if not dirname:
            return filename
        elif os.path.isdir(dirname):
            pass
        else:
            mdir = ""
            for d in dirname.split('/'):
                mdir = mdir + d
                if os.path.isfile(mdir):
                    os.rename(mdir, mdir + ".html")
                if not os.path.isdir(mdir):
                    os.mkdir(mdir)
                mdir = mdir + '/'
        return dirname + "/" + filename

    def save_to_file(self, filename=None):
        for i in range(5):
            try:
                if not self.get_response():
                    return
                if not filename:
                    path = urlutils.url_to_path(self.url)
                    filename = self.build_dir(path)
                with open(filename, "wb") as filep:
                    filep.write(self.get_dataobj().read())
                return
            except HTTPError, err:
                if err.code == 404:
                    return
                else:
                    self.close()
                    continue

    def close(self):
        if self.response:
            self.response.close()
            self.response = None

    def __del__(self):
        #        if self.response:
        #            self.response.close()
        logging.debug("http_response %s is closed" % (self.url))


class dbhandle:
    def __init__(self, dbhost, dbuser, dbpwd, db):
        self.config = [dbhost, dbuser, dbpwd, db]
        self.connect_db()

    def connect_db(self):
        self.conn = MySQLdb.connect(host=self.config[0], user=self.config[1], passwd=self.config[2], port=3306,
                                    charset='utf8')
        self.conn.select_db(self.config[3])
        self.cur = self.conn.cursor()

    def disconnect_db(self):
        self.cur.close()
        self.conn.close()

    def exec_sql(self, sql):
        logging.debug("execute sql:" + sql)
        count = self.cur.execute(sql)
        return count

    def get_sql_result(self, sql):
        count = self.exec_sql(sql)
        if count == 0:
            return None
        return [self.cur.fetchone()[0]]

    def escape_string(self, str_):
        return self.conn.escape_string(str_)

    def __del__(self):
        self.disconnect_db()


class work_queue:
    def __init__(self, size):
        self.size = size
        self.queueset = {"to_download": dict(), "downloading": dict(), "downloaded": dict(), "processing": dict(),
                         "todb": dict(), "processed": dict()}
        self.lock = Lock()

    def push(self, queue_name, obj):  # obj=(url,info)
        if not self.queueset.has_key(queue_name):
            return
        url = obj[0]
        logging.debug("push %s to queue %s" % (url, queue_name))
        url_hash = hash(url)
        queue = self.queueset[queue_name]
        try:
            with self.lock:
                queue[url_hash] = obj
        except:
            pass

    def pop(self, queue_name):
        if not self.queueset.has_key(queue_name):
            return None
        queue = self.queueset[queue_name]
        try:
            with self.lock:
                obj = None
                for k in queue:
                    key = k
                    obj = queue[k]
                    break
                if obj:
                    logging.debug("pop data %s from queue %s" % (obj[0], queue_name))
                    queue.pop(key)
                    return obj
                else:
                    return None
        except Exception, what:
            logging.error(str(what))
            return None

    def move(self, from_qname, to_qname, obj):
        from_queue = self.queueset.get(from_qname)
        to_queue = self.queueset.get(to_qname)

        if not self.queueset.has_key(from_qname):
            return
        elif not self.queueset.has_key(to_qname):
            return self.remove(from_qname, obj)
        else:
            url = obj[0]
            logging.debug("move data %s from %s to %s" % (url, from_qname, to_qname))
            url_hash = hash(url)
            with self.lock:
                if from_queue.has_key(url_hash):
                    from_queue.pop(url_hash)
                    to_queue[url_hash] = obj
                else:
                    logging.warn("bug occurs,move object does not exist")

    #                    traceback.print_exc(file=sys.stdout)

    def remove(self, queue_name, obj):
        if queue_name == "todb" or not self.queueset.has_key(queue_name):
            return
        queue = self.queueset[queue_name]
        url = obj[0]
        url_hash = hash(url)
        try:
            with self.lock:
                if queue.has_key(url_hash):
                    queue.pop(url_hash)
        except:
            return

    def getsize(self, queue_name):
        if not self.queueset.has_key(queue_name):
            return 0
        with self.lock:
            return len(self.queueset[queue_name])

    def have(self, url):
        url_hash = hash(url)
        with self.lock:
            for key in ["to_download", "processing", "processed", "downloading", "downloaded"]:
                if self.queueset[key].has_key(url_hash):
                    return True

    def dump(self, queue_name):
        if queue_name == "all":
            logging.debug(self.queueset)
        else:
            logging.debug(self.queueset[queue_name])

    def done(self):
        with self.lock:
            logging.debug("%s==>to download:%d downloading:%d downloaded:%d processing:%d processed:%d todb:%d" \
                          % (str(threading.current_thread()), len(self.queueset["to_download"]), \
                             len(self.queueset["downloading"]), len(self.queueset["downloaded"]),
                             len(self.queueset["processing"]), \
                             len(self.queueset["processed"]), len(self.queueset["todb"])))
            if len(self.queueset["todb"]) == 0 and \
                    len(self.queueset["to_download"]) == 0 and \
                    len(self.queueset["downloaded"]) == 0 and \
                    len(self.queueset["processing"]) == 0 and \
                    len(self.queueset["processed"]) > 10 and \
                    len(self.queueset["downloading"]) == 0:
                return True
            else:
                return False


class apkinfo:
    def __init__(self, apk_name, aapt="/opt/android/sdk/build-tools/android-4.4/aapt"):
        self.apk_name = apk_name
        self.aapt = aapt
        self.apk_info = None

    def get_apk_info(self):
        if self.apk_info:
            return self.apk_info
        p = Popen([self.aapt, "dump", "badging", self.apk_name], stdout=PIPE, stderr=None)
        ret = p.wait()
        if ret != 0:
            return None
        self.apk_info = dict()
        for line in p.stdout.readlines():
            line = line.rstrip('\n')
            try:
                (v, k) = line.split(':')
                self.apk_info[v] = k
            except:
                continue
        return self.apk_info

    def get_size(self):
        return os.path.getsize(self.apk_name)

    def get_info_int(self, key):
        try:
            v = self.get_apk_info().get(key)
            if v:
                return int(v.strip("'"))
            else:
                return 0
        except:
            return 0

    def get_info_str(self, key):
        v = self.get_apk_info().get(key)
        if v:
            return v.strip().strip("'")
        else:
            return None

    def get_version_code(self):
        v = self.get_info_str("package")
        if not v:
            return 0
        try:
            s = v.split(" ")[1].split('=')[1].strip("'")
            return int(s)
        except:
            return 0

    def get_version(self):
        v = self.get_info_str("package")
        if not v:
            return 0
        try:
            return v.split(" ")[2].split('=')[1].strip("'")
        except:
            return None

    def get_sdk_version(self):
        return self.get_info_int("sdkVersion")

    def get_target_sdk_version(self):
        return self.get_info_int("targetSdkVersion")

    def get_max_sdk_version(self):
        return self.get_info_int("maxSdkVersion")

    def get_acrconym(self):
        app_label = None
        for k in ("application-label-zh_CN", "application-label-zh", "application-label"):
            app_label = self.get_info_str(k)
            if app_label:
                break;
        if not app_label:
            return None
        try:
            return hzconverter.get_first_later(app_label)
        except:
            return None


class url_filter:
    def __init__(self):
        self.match_pts = list()
        self.reject_pts = list()

    def add_regex(self, regex, reg_type="match"):
        pattern = re.compile(regex)
        if reg_type == "match":
            self.match_pts.append(pattern)
        else:
            self.reject_pts.append(pattern)

    def match(self, url):
        for pattern in self.reject_pts:
            m = pattern.match(url)
            if m:
                return False
        for pattern in self.match_pts:
            if pattern.match(url):
                return True
        return False


class urlutils:
    pt = re.compile(r"(http://)?(.*\.)(png|jpeg|jpg|apk).*$")
    pt1 = re.compile(r"(http://.*)/.*$")

    def __init__(self):
        pass

    # staticmethod

    @staticmethod
    def url_to_path(url):
        m = urlutils.pt.match(url)
        if m:
            return m.group(2) + m.group(3)
        else:
            return url.lstrip("http://").split('#')[0]

    @staticmethod
    def real_url(url):
        m = urlutils.pt.match(url)
        if m:
            if m.group(1):
                return m.group(1) + m.group(2) + m.group(3)
            else:
                return "http://" + m.group(2) + m.group(3)
        else:
            return url.split('#')[0]

        # url_pattern=re.compile(r"http://([^#?!]+).*$")

    @staticmethod
    def get_base_url(url):
        m = urlutils.pt1.match(url)
        if m:
            return m.group(1)
        else:
            return url


class link_parser(SGMLParser):
    def __init__(self, base_url):
        SGMLParser.__init__(self)
        self.link_list = []
        self.base_url = base_url

    def get_link_list(self):
        return self.link_list

    def get_parser_result(self):
        return None

    def get_abs_link(self, path):
        path = path.split('#')[0]
        if path.startswith('http'):
            return path
        else:
            return urljoin(self.base_url, path)

    def start_a(self, attrs):
        url = ""
        for k, v in attrs:
            if k == 'href' and v:
                url = self.get_abs_link(v)
                self.link_list.append(url)

    def start_img(self, attrs):
        url = ""
        for k, v in attrs:
            if k == 'src' and v:
                url = self.get_abs_link(v)
                self.link_list.append(url)


class appinfo_parser(link_parser):
    def __init__(self, base_url):
        link_parser.__init__(self, base_url)
        self.app_info = {"url": base_url, "zh_name": "", "en_name": "", "description": "", "appurl": "", \
                         "changelog": "", "screenshot": [], "thumbnail": [], "version": "", "iconurl": "",
                         "category": "", "rating": 0}
        self.app_stack = dict()

    def get_app_info(self):
        # for k in self.app_info.keys():
        #    print k,":",self.app_info.get(k)
        return self.app_info

    def get_parser_result(self):
        return self.get_app_info()

    def start_a(self, attrs):
        url = ""
        app_url = False
        thumbnail = False
        for k, v in attrs:
            if k == 'href' and v:
                url = self.get_abs_link(v)
                self.link_list.append(url)
            if k == 'itemprop' and v == 'downloadUrl':
                app_url = True
            elif k == 'class' and v == 'thumbnail':
                thumbnail = True

        if not self.app_info:
            return

        if app_url and url:
            self.app_info["appurl"] = url
        elif thumbnail and url:
            if not self.app_info.has_key('thumbnail'):
                self.app_info['thumbnail'] = list()
            self.app_info['thumbnail'].append(url)
        else:
            pass

    def start_img(self, attrs):
        url = ""
        app_icon = False
        app_screenshot = False
        for k, v in attrs:
            if k == 'src' and v:
                url = self.get_abs_link(v)
                self.link_list.append(url)
            elif k == 'class' and v == 'app-icon':
                app_icon = True
            elif k == 'itemprop' and v == 'screenshot':
                app_screenshot = True
            else:
                pass
        if not self.app_info:
            return
        if app_icon and url:
            self.app_info["iconurl"] = url
        elif app_screenshot and url:
            if not self.app_info.has_key('screenshot'):
                self.app_info['screenshot'] = list()
            self.app_info['screenshot'].append(url)
        else:
            pass

    def end_htmltag(self, infolist):
        if not self.app_info:
            return
        for k in self.app_stack.keys():
            if k in infolist:
                self.app_stack[k] -= 1
                if self.app_stack[k] == 0:
                    self.app_stack.pop(k)

    def start_meta(self, attrs):
        is_rating = False
        rating = None
        for k, v in attrs:
            if k == "itemprop" and v == "ratingValue":
                is_rating = True
            elif k == "content" and v:
                rating = v
            else:
                pass
        if is_rating and rating:
            self.app_info["rating"] = int(rating)

    def start_div(self, attrs):
        if not self.app_info:
            return
        init = False
        for k, v in attrs:
            if k == 'itemprop' and v == 'description':
                self.app_stack['description'] = 1
                init = True
            elif k == 'class' and v == 'app-support-list':
                self.app_stack['app-support-list'] = 1
                init = True
            elif k == 'class' and v == 'version':
                self.app_stack["version"] = 1
                init = True

            else:
                pass
        if not init:
            for k in ["description", "app-support-list", "version"]:
                if self.app_stack.has_key(k):
                    self.app_stack[k] += 1

    def end_div(self):
        self.end_htmltag(["description", "app-support-list", "version"])

    def handle_data(self, text):
        if not self.app_info:
            return
        for k in self.app_stack.keys():
            if k in ['app_name']:
                continue
            if self.app_info.has_key(k):
                self.app_info[k] += text
            else:
                self.app_info[k] = text

    def start_section(self, attrs):
        if not self.app_info:
            return
        init = False
        for k, v in attrs:
            if k == 'class' and v == 'app-changelog':
                self.app_stack['changelog'] = 1
                init = True
        if not init and self.app_stack.has_key('changelog'):
            self.app_stack['changelog'] += 1

    def end_section(self):
        self.end_htmltag(["changelog"])

    def start_h1(self, attrs):
        if not self.app_info:
            return
        init = False
        for k, v in attrs:
            if k == 'itemprop' and v == 'name':
                self.app_stack['app_name'] = 1
                init = True
        if not init:
            if self.app_stack.has_key('app_name'):
                self.app_stack['app_name'] += 1

    def end_h1(self):
        self.end_htmltag(["app_name"])

    def start_span(self, attrs):
        if not self.app_info:
            return
        for k, v in attrs:
            if self.app_stack.has_key('app_name'):
                if k == 'title':
                    self.app_info['zh_name'] = v
                    return
            if k == 'itemprop' and v == 'applicationCategory':
                self.app_stack['category'] = 1
            elif k == 'itemprop' and v == 'softwareVersion':
                self.app_stack['version'] = 1
            elif k == 'itemprop' and v == 'publisher':
                self.app_stack['publisher'] = 1
            else:
                pass

    def end_span(self):
        self.end_htmltag(["category", "version", "publisher"])

    def start_small(self, attrs):
        if not self.app_info:
            return
        for k, v in attrs:
            if self.app_stack['app_name']:
                if k == 'title':
                    self.app_info["en_name"] = v
                    return


class app_info:
    def __init__(self):
        self.info = {
            "pkg_name": "",
            "app_path": "",
            "version": "",
            "zh_name": "",
            "en_name": "",
            "acronym": "",
            "version_code": 0,
            "min_sdk_version": 0,
            "target_sdk_version": 0,
            "max_sdk_version": 0,
            "score": 0,
            "size": 0,
            "category": list(),
            "description": "",
            "changelog": "",
            "app_features": list(),
            "icon_path": "",
            "img_path": list(),
            "developer": ""
        }

    def set(self, key, value):
        if isinstance(self.get(key), int) and not value:
            self.info[key] = 0
        else:
            self.info[key] = value

    def append(self, key, value):
        self.info[key].append(value)

    def get(self, key):
        return self.info.get(key)

    def save_to_db(self, dbh):
        if not dbh.conn:
            return False
        aid = dbh.get_sql_result("select id from AppInstance where pkgName='%s' and versionCode=%s" \
                                 % (self.get("pkg_name"), self.get("version_code")))
        if aid:
            logging.info("app %s is already insert" % (self.get("zh_name")))
            return True
        if self.get("developer"):
            did = dbh.get_sql_result("select id from Developer where name='%s'" % (self.get('developer')))
            if did:
                ownerid = did[0]
            else:
                user = hzconverter.get_first_later(self.get('developer'))
                dbh.exec_sql("insert into User(status,name,password) values(1,'%s',password('123456'))" % (user))
                did = dbh.get_sql_result("select id from User where name='%s'" % (user))
                if not did:
                    logging.error("can not add developer for app %s" % (self.get('zh_name')))
                    return False
                dbh.exec_sql(
                    "insert into Developer(id,status,name) values(%d,1,'%s')" % (did[0], self.get('developer')))
                ownerid = did[0]
        else:
            ownerid = 0
        sql = None
        try:
            sql = "insert into AppInstance(pkgName,versionName,applicationLabel,applicationLabelEn,\
                description,changelog,path,size,versionCode,minSdkVersion,targetSdkVersion,maxSdkVersion,acronym,score,status,ownerId,lid)\
                    values('%s','%s','%s','%s','%s','%s','%s',%s,%s,%s,%s,%s,'%s',%s,1,%s,1)" \
                  % (self.get("pkg_name"), self.get("version"), self.get("zh_name"), self.get("en_name"), \
                     self.get("description"), self.get("changelog"), self.get("app_path"), \
                     self.get("size"), self.get("version_code"), self.get("min_sdk_version"), \
                     self.get("target_sdk_version"), self.get("max_sdk_version"), self.get("acronym"),
                     self.get("score"), ownerid)
        except Exception:
            traceback.print_exc()
        if sql:
            dbh.exec_sql(sql)
        aid = dbh.get_sql_result("select id from AppInstance where pkgName='%s' and versionCode=%s" \
                                 % (self.get("pkg_name"), self.get("version_code")))
        if not aid:
            logging.error("insert %s's info failed" % (self.get("pkg_name")))
            return False
        sql = "insert into Image(aid,imageType,path,status) values(%d,%d,'%s',1)" % (aid[0], 1, self.get("icon_path"))
        dbh.exec_sql(sql)
        for img_url in self.get("img_path"):
            sql = "insert into Image(aid,imageType,path,status) values(%d,%d,'%s',%d)" % (aid[0], 2, \
                                                                                          img_url, 1)
            dbh.exec_sql(sql)
        for category in self.get("category"):
            cid = dbh.get_sql_result("select id from Category where name='%s'" % (category))
            if cid:
                dbh.exec_sql("insert into AppCategory(aid,cid) values(%s,%s)" % (aid[0], cid[0]))
            else:
                logging.warning("can not find category %s form %s" % (self.get("category"), self.get("zh_name")))
        for feature in self.get("app_features"):
            if not feature:
                continue
            tid = dbh.get_sql_result("select id from Trait where name='%s'" % (feature))
            if tid:
                dbh.exec_sql("insert into AppTrait(aid,tid) value(%s,%s)" % (aid[0], tid[0]))
            else:
                logging.warning("can not find trait %s form %s" % (self.get("feature"), self.get("zh_name")))

        dbh.conn.commit()
        return True


class hzconverter:
    def __init__(self):
        pass

    @staticmethod
    def get_first_later(chinese_str):
        py_sector_table = [1601, 1637, 1833, 2078, 2274, 2302, 2433, 2594, 2787, 3106, 3212, 3472, 3635, 3722, 3730,
                           3858, 4027, 4086, 4390, 4558, 4684, 4925, 5249, 5590]
        first_later_table = ["a", "b", "c", "d", "e", "f", "g", "h", "j", "k", "l", "m", "n", "o", "p", "q", "r", "s",
                             "t", "w", "x", "y", "z"]
        py_second_sector_table = "CJWGNSPGCGNE[Y[BTYYZDXYKYGT[JNNJQMBSGZSCYJSYY[PGKBZGY[YWJKGKLJYWKPJQHY[W[DZLSGMRYPYWWCCKZNKYYGTTNJJNYKKZYTCJNMCYLQLYPYQFQRPZSLWBTGKJFYXJWZLTBNCXJJJJTXDTTSQZYCDXXHGCK[PHFFSS[YBGXLPPBYLL[HLXS[ZM[JHSOJNGHDZQYKLGJHSGQZHXQGKEZZWYSCSCJXYEYXADZPMDSSMZJZQJYZC[J[WQJBYZPXGZNZCPWHKXHQKMWFBPBYDTJZZKQHY" \
                                 "LYGXFPTYJYYZPSZLFCHMQSHGMXXSXJ[[DCSBBQBEFSJYHXWGZKPYLQBGLDLCCTNMAYDDKSSNGYCSGXLYZAYBNPTSDKDYLHGYMYLCXPY[JNDQJWXQXFYYFJLEJPZRXCCQWQQSBNKYMGPLBMJRQCFLNYMYQMSQYRBCJTHZTQFRXQHXMJJCJLXQGJMSHZKBSWYEMYLTXFSYDSWLYCJQXSJNQBSCTYHBFTDCYZDJWYGHQFRXWCKQKXEBPTLPXJZSRMEBWHJLBJSLYYSMDXLCLQKXLHXJRZJMFQHXHWY" \
                                 "WSBHTRXXGLHQHFNM[YKLDYXZPYLGG[MTCFPAJJZYLJTYANJGBJPLQGDZYQYAXBKYSECJSZNSLYZHSXLZCGHPXZHZNYTDSBCJKDLZAYFMYDLEBBGQYZKXGLDNDNYSKJSHDLYXBCGHXYPKDJMMZNGMMCLGWZSZXZJFZNMLZZTHCSYDBDLLSCDDNLKJYKJSYCJLKWHQASDKNHCSGANHDAASHTCPLCPQYBSDMPJLPZJOQLCDHJJYSPRCHN[NNLHLYYQYHWZPTCZGWWMZFFJQQQQYXACLBHKDJXDGMMY" \
                                 "DJXZLLSYGXGKJRYWZWYCLZMSSJZLDBYD[FCXYHLXCHYZJQ[[QAGMNYXPFRKSSBJLYXYSYGLNSCMHZWWMNZJJLXXHCHSY[[TTXRYCYXBYHCSMXJSZNPWGPXXTAYBGAJCXLY[DCCWZOCWKCCSBNHCPDYZNFCYYTYCKXKYBSQKKYTQQXFCWCHCYKELZQBSQYJQCCLMTHSYWHMKTLKJLYCXWHEQQHTQH[PQ[QSCFYMNDMGBWHWLGSLLYSDLMLXPTHMJHWLJZYHZJXHTXJLHXRSWLWZJCBXMHZQXSDZP" \
                                 "MGFCSGLSXYMJSHXPJXWMYQKSMYPLRTHBXFTPMHYXLCHLHLZYLXGSSSSTCLSLDCLRPBHZHXYYFHB[GDMYCNQQWLQHJJ[YWJZYEJJDHPBLQXTQKWHLCHQXAGTLXLJXMSL[HTZKZJECXJCJNMFBY[SFYWYBJZGNYSDZSQYRSLJPCLPWXSDWEJBJCBCNAYTWGMPAPCLYQPCLZXSBNMSGGFNZJJBZSFZYNDXHPLQKZCZWALSBCCJX[YZGWKYPSGXFZFCDKHJGXDLQFSGDSLQWZKXTMHSBGZMJZRGLYJB" \
                                 "PMLMSXLZJQQHZYJCZYDJWBMYKLDDPMJEGXYHYLXHLQYQHKYCWCJMYYXNATJHYCCXZPCQLBZWWYTWBQCMLPMYRJCCCXFPZNZZLJPLXXYZTZLGDLDCKLYRZZGQTGJHHGJLJAXFGFJZSLCFDQZLCLGJDJCSNZLLJPJQDCCLCJXMYZFTSXGCGSBRZXJQQCTZHGYQTJQQLZXJYLYLBCYAMCSTYLPDJBYREGKLZYZHLYSZQLZNWCZCLLWJQJJJKDGJZOLBBZPPGLGHTGZXYGHZMYCNQSYCYHBHGXKAMTX" \
                                 "YXNBSKYZZGJZLQJDFCJXDYGJQJJPMGWGJJJPKQSBGBMMCJSSCLPQPDXCDYYKY[CJDDYYGYWRHJRTGZNYQLDKLJSZZGZQZJGDYKSHPZMTLCPWNJAFYZDJCNMWESCYGLBTZCGMSSLLYXQSXSBSJSBBSGGHFJLYPMZJNLYYWDQSHZXTYYWHMZYHYWDBXBTLMSYYYFSXJC[DXXLHJHF[SXZQHFZMZCZTQCXZXRTTDJHNNYZQQMNQDMMG[YDXMJGDHCDYZBFFALLZTDLTFXMXQZDNGWQDBDCZJDXBZGS" \
                                 "QQDDJCMBKZFFXMKDMDSYYSZCMLJDSYNSBRSKMKMPCKLGDBQTFZSWTFGGLYPLLJZHGJ[GYPZLTCSMCNBTJBQFKTHBYZGKPBBYMTDSSXTBNPDKLEYCJNYDDYKZDDHQHSDZSCTARLLTKZLGECLLKJLQJAQNBDKKGHPJTZQKSECSHALQFMMGJNLYJBBTMLYZXDCJPLDLPCQDHZYCBZSCZBZMSLJFLKRZJSNFRGJHXPDHYJYBZGDLQCSEZGXLBLGYXTWMABCHECMWYJYZLLJJYHLG[DJLSLYGKDZPZXJ" \
                                 "YYZLWCXSZFGWYYDLYHCLJSCMBJHBLYZLYCBLYDPDQYSXQZBYTDKYXJY[CNRJMPDJGKLCLJBCTBJDDBBLBLCZQRPPXJCJLZCSHLTOLJNMDDDLNGKAQHQHJGYKHEZNMSHRP[QQJCHGMFPRXHJGDYCHGHLYRZQLCYQJNZSQTKQJYMSZSWLCFQQQXYFGGYPTQWLMCRNFKKFSYYLQBMQAMMMYXCTPSHCPTXXZZSMPHPSHMCLMLDQFYQXSZYYDYJZZHQPDSZGLSTJBCKBXYQZJSGPSXQZQZRQTBDKYXZK" \
                                 "HHGFLBCSMDLDGDZDBLZYYCXNNCSYBZBFGLZZXSWMSCCMQNJQSBDQSJTXXMBLTXZCLZSHZCXRQJGJYLXZFJPHYMZQQYDFQJJLZZNZJCDGZYGCTXMZYSCTLKPHTXHTLBJXJLXSCDQXCBBTJFQZFSLTJBTKQBXXJJLJCHCZDBZJDCZJDCPRNPQCJPFCZLCLZXZDMXMPHJSGZGSZZQLYLWTJPFSYASMCJBTZKYCWMYTCSJJLJCQLWZMALBXYFBPNLSFHTGJWEJJXXGLLJSTGSHJQLZFKCGNNNSZFDEQ" \
                                 "FHBSAQTGYLBXMMYGSZLDYDQMJJRGBJTKGDHGKBLQKBDMBYLXWCXYTTYBKMRTJZXQJBHLMHMJJZMQASLDCYXYQDLQCAFYWYXQHZ"

        if isinstance(chinese_str, unicode):
            str_ = chinese_str.encode("gbk")
        else:
            str_ = chinese_str.decode("utf-8").encode("gbk")
        length, pos = len(str_), 0
        rs = ""
        while pos < length:
            firstc = str_[pos:pos + 1]
            first = ord(firstc)
            if first > 160:
                second = ord(str_[pos + 1:pos + 2])
                pos += 2
                if pos > length:
                    print "invalid char %s" % (chinese_str)
                    raise Exception(100, "invalid char %s" % (chinese_str))
                sec_code = (first - 160) * 100 + second - 160
                if sec_code > 1600 and sec_code < 5590:
                    for i in range(len(py_sector_table)):
                        if sec_code < py_sector_table[i + 1]:
                            rs += first_later_table[i]
                            break
                else:
                    sec_code = (first - 160 - 56) * 94 + second - 161
                    if sec_code >= 0 and sec_code <= 3007:
                        rs += py_second_sector_table[sec_code].lower()
                    else:
                        continue

            elif firstc.isalpha() or firstc.isdigit():
                rs += firstc.lower()
                pos += 1
            else:
                pos += 1
                continue

        return rs
