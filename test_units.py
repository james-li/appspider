# coding=utf-8
'''
Created on 2014-4-20

@author: Jamesl
'''
import unittest
from spider_utils import hzconverter


class Test(unittest.TestCase):

    def testfirstlater(self):
        self.assertEqual(hzconverter.get_first_later(u"飞视电+视浏览器l"), "fsdsllql")
        self.assertEqual(hzconverter.get_first_later(u"作战指挥官"), "zzzhg")


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
