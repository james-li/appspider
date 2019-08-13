# coding=utf-8

from optparse import OptionParser
import traceback


class spider_env:
    def __init__(self):
        self.env = {"root": ".",
                    "fetcher_number": 1,
                    "analyser_number": 1,
                    "dbworker_number": 1,
                    "timeout": 10,
                    "proxy": "",
                    "logfile": "log.txt",
                    "dbhost": "192.168.4.17",
                    "dbuser": "root",
                    "dbpwd": "root",
                    "dbname": "CloudBoxTest"}
        self.options = (("-f", "--fetcher", "fetcher_number", "int"), \
                        ("-a", "--analyser", "analyser_number", "int"), \
                        ("-d", "--dbworker", "dbworker_number", "int"), \
                        ("-r", "--root", "root", "str"), \
                        ("-t", "--timeout", "timeout", "int"), \
                        ("-P", "--proxy", "proxy", "str"), \
                        ("-l", "--logfile", "logfile", "str"), \
                        ("-H", "--dbhost", "dbhost", "str"), \
                        ("-u", "--dbuser", "dbuser", "str"), \
                        ("-p", "--dbpassword", "dbpwd", "str"), \
                        ("-n", "--dbname", "dbname", "str"))

    def get(self, key):
        return self.env.get(key)

    def oset(self, o, value):
        ol = filter(lambda x: x[0] == o, self.options)
        if ol:
            self.set(ol[0][2], value)
        return value

    def set(self, key, value):
        if self.env.has_key(key):
            self.env[key] = value

    def dump(self):
        for k, v in self.env.iteritems():
            print k, ":", v

    def usage(self, cmd):
        print("usage: %s options" % (cmd))
        print("options list:")
        for opt in self.options:
            print("[%s|%s] %s:" % (opt[0], opt[1], opt[2]))

    def parse(self, args):
        try:
            parser = OptionParser()
            for opt in self.options:
                def fun(option=opt):
                    parser.add_option(option[0], option[1], action="callback", type=option[3], \
                                      callback=lambda o, v, p, *args, **kwargs: self.set(option[2], p))

                fun(opt)

            parser.parse_args(args)
            # print opts
        except:
            traceback.print_exc()
            self.usage(args[0])
            return False
        return True


if __name__ == "__main__":
    env = spider_env()
    env.parse("me -f 10 -d 10".split())
    env.dump()
