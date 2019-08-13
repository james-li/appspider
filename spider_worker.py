# coding=utf-8

'''
Created on 2014-4-20

@author: Jamesl
'''

import os
import logging

import traceback
import MySQLdb
from spider_utils import appinfo_parser, link_parser, http_response, \
    urlutils, apkinfo, hzconverter
from spider_utils import app_info


class spider_worker:
    def __init__(self, name, w_queue):
        wq_dict = {"analyser": "downloaded", "fetcher": "to_download", "dbworker": "todb",
                   "app_downloader": "to_download", "app_dbworker": "todb"}
        self.name = name
        self.work_queue_name = wq_dict[name]
        self.w_queue = w_queue

    def get_job(self):
        return self.w_queue.pop(self.work_queue_name)

    def do_job(self, obj):
        pass

    def work_done(self):
        return self.w_queue.done()

    def get_name(self):
        return self.name


class url_analyser(spider_worker):
    def __init__(self, w_queue, a_filter=None):
        spider_worker.__init__(self, "analyser", w_queue)
        self.a_filter = a_filter

    def should_download(self, url):
        if self.a_filter:
            if not self.a_filter.match(url):
                return False
        if self.w_queue.have(url):
            return False
        return True

    def should_analysis(self, url):
        if url.startswith("http://app.shafa.com/view/"):
            return True
        else:
            return False

    def do_job(self, obj):
        (url, http_res) = obj
        self.w_queue.push("processing", (url, None))
        app_info = dict()
        lp = None
        try:
            if http_res.is_html():
                if self.should_analysis(url):
                    lp = appinfo_parser(url)
                else:
                    lp = link_parser(url)
                lp.feed(http_res.get_dataobj().read())
                app_info = lp.get_parser_result()
                for link in lp.get_link_list():
                    if self.should_download(url):
                        self.w_queue.push("to_download", (link, None))
        except:
            traceback.print_exc()
        if app_info and app_info.has_key("zh_name"):
            #                    for key in app_info.keys():
            #                        print key,":",app_info[key]
            self.w_queue.pushapp(app_info)
            logging.info("get app info form app " + app_info["zh_name"])
        #                    global dbh
        #                    dbh.add_app_to_db(app_info)
        self.w_queue.move("processing", "processed", (url, None))


class url_fetcher(spider_worker):
    def __init__(self, w_queue):
        spider_worker.__init__(self, "fetcher", w_queue)

    def do_job(self, obj):
        url = obj[0]
        self.w_queue.push("downloading", (url, None))
        http_res = http_response(url)
        if not http_res.get_response():
            self.w_queue.move("downloading", "to_download", (url, None))
            return
        if http_res.is_html():
            self.w_queue.move("downloading", "downloaded", (url, http_res))
        elif http_res.get_fileext() in ["png", "apk", "jpeg", "jpg"]:
            http_res.save_to_file()
            self.w_queue.move("downloading", "processed", (url, None))
        else:
            self.w_queue.move("downloading", "processed", (url, None))


class db_worker(spider_worker):
    def __init__(self, dbh, w_queue):
        spider_worker.__init__(self, "dbworker", w_queue)
        self.dbh = dbh

    def get_pkg_name(self, app_path):
        try:
            pl = app_path.rstrip('.apk').split('.')
            pl.pop()
            return ".".join(pl)
        except:
            return app_path.rstrip('.apk');

    def add_app_to_db(self, app_info):
        if not self.dbh.conn:
            return False
        app_path = self.dbh.escape_string(urlutils.url_to_path(app_info['appurl']))
        if not os.path.isfile(app_path):
            return False
        icon_path = self.dbh.escape_string(urlutils.url_to_path(app_info["iconurl"]))
        category = self.dbh.escape_string(app_info["category"])
        zh_name = self.dbh.escape_string(app_info["zh_name"])
        en_name = self.dbh.escape_string(app_info["en_name"])
        score = app_info["rating"]
        description = self.dbh.escape_string(app_info["description"].strip())
        changelog = self.dbh.escape_string(app_info["changelog"].strip())
        #        vendor=self.escape_string(app_info["app_vendor"])
        pkg_name = self.get_pkg_name(os.path.basename(app_path))
        app_feature = app_info.get("app-support-list").strip()
        ownerid = 0

        developer = app_info.get("publisher")
        if developer:
            developer = developer.strip()
            did = self.dbh.get_sql_result("select id from Developer where name='%s'" % (developer))
            if did:
                ownerid = did[0]
            else:
                user = hzconverter.get_first_later(developer)
                self.dbh.exec_sql("insert into User(status,name,password) values(1,'%s',password('123456'))" % (user))
                did = self.dbh.get_sql_result("select id from User where name='%s'" % (user))
                if not did:
                    logging.error("can not add developer for app %s" % (zh_name))
                    return False
                self.dbh.exec_sql("insert into Developer(id,status,name) values(%d,1,'%s')" % (did[0], developer))
                ownerid = did[0]
        else:
            ownerid = 0

        size = os.path.getsize(app_path)
        sql = ""
        try:
            apk_info = apkinfo(app_path)
            if not apk_info.get_apk_info():
                return True
            version_code = apk_info.get_version_code()
            version = apk_info.get_version()
            min_sdk_version = apk_info.get_sdk_version()
            target_sdk_version = apk_info.get_target_sdk_version()
            max_sdk_version = apk_info.get_max_sdk_version()
            acronym = apk_info.get_acrconym()
            sql = "insert into AppInstance(pkgName,versionName,applicationLabel,applicationLabelEn,\
            description,changelog,path,size,versionCode,minSdkVersion,targetSdkVersion,maxSdkVersion,acronym,score,status,ownerId,lid)\
                values('%s','%s','%s','%s','%s','%s','%s',%d,%d,%d,%d,%d,'%s',%d,1,%d,1)" \
                  % (pkg_name, version, zh_name, en_name, description, changelog, os.path.basename(app_path), \
                     size, version_code, min_sdk_version, target_sdk_version, max_sdk_version, acronym, score, ownerid)
        except:
            traceback.print_exc()

        if not sql:
            return False

        aid = self.dbh.get_sql_result("select id from AppInstance where pkgName='%s'" % (pkg_name))
        if aid:
            logging.info("app %s is already insert" % (zh_name))
            return True

        self.dbh.exec_sql(sql)
        aid = self.dbh.get_sql_result("select id from AppInstance where pkgName='%s'" % (pkg_name))
        if not aid:
            logging.error("insert %s's info failed" % (pkg_name))
            return False
        sql = "insert into Image(aid,imageType,path,status) values(%d,%d,'%s',1)" % (
        aid[0], 1, os.path.basename(icon_path))
        self.dbh.exec_sql(sql)
        for img_url in app_info["thumbnail"]:
            sql = "insert into Image(aid,imageType,path,status) values(%d,%d,'%s',%d)" % (aid[0], 2, \
                                                                                          os.path.basename(
                                                                                              urlutils.url_to_path(
                                                                                                  img_url)), 1)
            self.dbh.exec_sql(sql)

        cid = self.dbh.get_sql_result("select id from Category where name='%s'" % (category))
        if cid:
            self.dbh.exec_sql("insert into AppCategory(aid,cid) values(%s,%s)" % (aid[0], cid[0]))
        for feature in app_feature.split():
            tid = self.dbh.get_sql_result("select id from Trait where name='%s'" % (feature))
            if tid:
                self.dbh.exec_sql("insert into AppTrait(aid,tid) value(%s,%s)" % (aid[0], tid[0]))

        self.dbh.conn.commit()
        return True

    def do_job(self, app_info):
        try:
            self.add_app_to_db(app_info)
        except MySQLdb.Error, e:
            logging.error("Mysql Error %d:%s" % (e.args[0], e.args[1]))
            if e.args[0] == 2006 or e.args[0] == 2013:
                logging.critical("reconnect database")
                self.dbh.disconnect_db()
                self.dbh.connect_db()
                self.w_queue.pushapp(app_info)
        except Exception:
            traceback.print_exc()


class app_downloader(spider_worker):
    def __init__(self, w_queue, root="."):
        spider_worker.__init__(self, "app_downloader", w_queue)
        self.root = root

    def do_job(self, obj):
        self.w_queue.push("downloading", obj)
        url, app_info = obj
        http_res = http_response(url)
        try:
            if not http_res.get_response():
                self.w_queue.move("downloading", "to_download", (url, app_info))
                return
            real_name = http_res.get_filename()
            fn_with_version = None
            if real_name.endswith(".apk"):
                if app_info.has_key("identifier"):
                    filename = "apk/" + app_info.get("identifier") + ".apk"
                    fn_with_version = "apk/%s.%s.apk" % (
                    app_info.get("identifier"), app_info.get("apk").get("version_code"))
                elif app_info.has_key("package"):
                    filename = "apk/" + app_info.get("package") + ".apk"
                    fn_with_version = "apk/%s.%s.apk" % (app_info.get("package"), app_info.get("versioncode"))
                else:
                    filename = "apk/" + real_name
                    fn_with_version = filename
                app_info["app_path"] = fn_with_version
            else:
                filename = "img/" + real_name
                fn_with_version = filename
            filename = self.root + "/" + filename
            fn_with_version = self.root + "/" + fn_with_version
            fsize0 = 0
            fsize1 = 0
            dsize = http_res.get_size()
            try:
                fsize0 = os.path.getsize(filename)
            except:
                pass
            try:
                fsize1 = os.path.getsize(fn_with_version)
            except:
                pass

            if fsize1 == dsize:
                logging.debug("%s has been downloaded,skip to download" % (fn_with_version))
            elif fsize0 == dsize:
                if filename != fn_with_version:
                    logging.debug("%s has been downloaded,rename to %s" % (filename, fn_with_version))
                    os.rename(filename, fn_with_version)
            else:
                http_res.save_to_file(fn_with_version)
            if real_name.endswith(".apk"):
                self.w_queue.move("downloading", "todb", (url, app_info))
            else:
                self.w_queue.move("downloading", "processed", (url, None))
        except Exception, what:
            logging.warning("download %s failed:%s, try again" % (url, str(what)))
            self.w_queue.move("downloading", "processed", (url, None))
            return


class app_db_worker(spider_worker):
    def __init__(self, dbh, w_queue):
        spider_worker.__init__(self, "app_dbworker", w_queue)
        self.dbh = dbh

    def str2int(self, str_):
        try:
            if str_:
                return int(str_)
            else:
                return 0
        except:
            return 0

    def get_app_info_7po(self, app_raw_info):
        """
        for k,v in app_raw_info.iteritems():
            if isinstance(v, list):
                print k,":","".join(v)
            else:
                print k,":",v
                """
        ainfo = app_info()
        try:
            apk_info = apkinfo(app_raw_info.get("app_path"))
            if not apk_info.get_apk_info():
                return None
            ainfo.set("pkg_name", app_raw_info.get("package"))
            ainfo.set("app_path", os.path.basename(app_raw_info.get("app_path")))
            ainfo.set("version", app_raw_info.get("versionname"))
            ainfo.set("zh_name", app_raw_info.get("name"))
            ainfo.set("en_name", app_raw_info.get("package"))
            ainfo.set("acronym", app_raw_info.get("name"))
            ainfo.set("version_code", self.str2int(app_raw_info.get("versioncode")))
            ainfo.set("min_sdk_version", apk_info.get_sdk_version())
            ainfo.set("target_sdk_version", apk_info.get_target_sdk_version())
            ainfo.set("max_sdk_version", apk_info.get_max_sdk_version())
            ainfo.set("score", int(float(app_raw_info.get("score")) / 2))
            size = self.str2int(app_raw_info.get("appsize"))
            if size == 0:
                size = apk_info.get_size()
            ainfo.set("size", size)
            ainfo.append("category", app_raw_info.get("category"))
            ainfo.set("description", app_raw_info.get("desc"))
            ainfo.set("app_features", app_raw_info.get("style").split())
            ainfo.set("icon_path", os.path.basename(app_raw_info.get("logo")))
            ainfo.set("img_path", [os.path.basename(f) for f in app_raw_info.get("captures").split(';')])
            ainfo.set("developer", app_raw_info.get("owner"))
            return ainfo
        except:
            traceback.print_exc()
            return ainfo

    def get_app_info_shafa(self, app_raw_info):
        ainfo = app_info()
        # print ainfo.info
        """
        info={
                   "pkg_name":"",
                   "app_path":"",
                   "version":"",
                   "zh_name":"",
                   "en_name":"",
                   "acronym":"",
                   "version_code":0,
                   "min_sdk_version":0,
                   "target_sdk_version":0,
                   "max_sdk_version":0,
                   "score":0,
                   "size":0,
                   "category":"",
                   "description":"",
                   "changelog":"",
                   "app_features":list(),
                   "icon_path":"",
                   "img_path":list(),
                   "developer":""     
                   }
        """
        f2c_list = {u"鼠标": u"鼠标操作", u"遥控器": u"遥控操作", u"手柄": u"手柄操作"}
        try:
            ainfo.set("pkg_name", app_raw_info.get("identifier"))
            ainfo.set("app_path", os.path.basename(app_raw_info.get("app_path")))
            ainfo.set("version", app_raw_info.get("apk").get("version"))
            ainfo.set("zh_name", app_raw_info.get("title"))
            ainfo.set("en_name", app_raw_info.get("second_title"))
            ainfo.set("acronym", hzconverter.get_first_later(app_raw_info.get("title")))
            ainfo.set("type", app_raw_info.get("type_name"))
            ainfo.set("version_code", app_raw_info.get("apk").get("version_code"))
            ainfo.set("min_sdk_version", self.str2int(app_raw_info.get("apk").get("sdk_version")))
            ainfo.set("target_sdk_version", self.str2int(app_raw_info.get("apk").get("target_sdk_version")))
            ainfo.set("size", app_raw_info.get("apk").get("file_size"))
            ainfo.set("score", app_raw_info.get("review"))
            ainfo.append("category", app_raw_info.get("category_name"))
            ainfo.set("description", app_raw_info.get("description"))
            ainfo.set("changelog", app_raw_info.get("change_logs"))
            ainfo.set("app_features", app_raw_info.get("support_list"))
            if app_raw_info.get("type_name") == u"游戏":
                for feature in ainfo.get("app_features"):
                    ctrl_category = f2c_list.get(feature)
                    if ctrl_category:
                        ainfo.append("category", ctrl_category)

            ainfo.set("icon_path", os.path.basename(app_raw_info.get("info").get("icon")))
            ainfo.set("img_path", [os.path.basename(f) for f in app_raw_info.get("screenshots")])
            ainfo.set("developer", app_raw_info.get("publisher"))
            return ainfo
        except:
            traceback.print_exc()
            return None

    def get_app_info(self, app_raw_info):
        if app_raw_info.get("source") == "7po":
            return self.get_app_info_7po(app_raw_info)
        elif app_raw_info.get("source") == "shafa":
            return self.get_app_info_shafa(app_raw_info)
        else:
            return None

    def add_app_to_db(self, app_raw_info):
        app_info = self.get_app_info(app_raw_info)
        if not app_info:
            return False
        return app_info.save_to_db(self.dbh)

    def do_job(self, obj):
        app_raw_info = obj[1]
        try:
            self.add_app_to_db(app_raw_info)
            self.w_queue.push("processed", obj)
        except MySQLdb.Error, e:
            logging.error("Mysql Error %d:%s" % (e.args[0], e.args[1]))
            logging.debug(str(app_raw_info))

            if e.args[0] == 2006 or e.args[0] == 2013:
                logging.critical("reconnect database")
                self.dbh.disconnect_db()
                self.dbh.connect_db()
                self.w_queue.push("todb", obj)
        except Exception:
            traceback.print_exc()
