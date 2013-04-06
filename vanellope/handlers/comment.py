#! /usr/bin/env python
# coding=utf-8

import re
import hashlib
import urllib
import datetime

import tornado.web
from tornado.escape import xhtml_escape

from vanellope import db
from vanellope.model import Comment 
from vanellope.model import Member
from vanellope.model import Article
from vanellope.handlers import BaseHandler



class CommentHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self, article_sn):
        comment = Comment()
        current_user = self.get_current_user() # wrappered
        cmt = self.get_argument('comment', None)
        cmt = xhtml_escape(cmt)
        name_patt = r"[ ]+@([a-zA-Z0-9]{1,16})[ ]+"
        patt2 = r"[ ]+(@[a-zA-Z0-9]{1,16})[ ]+"
        lines = cmt.splitlines()
        cmts = []
        for line in lines:
            line = " " + line + " "
            while True:
                m = re.search(name_patt, line)
                if not m:
                    break
                name  = m.groups()
                if name:
                    member = db.member.find_one({"name":name[0]})
                    if member:
                        link = "&nbsp;<a href='/member/%d'><code>@%s</code></a>&nbsp;" % (member['uid'], name[0])
                    else:
                        link = "&nbsp;<code>@%s</code>&nbsp;" % (name[0],)
                line = re.sub(name_patt, link, line, 1)  
            cmts.append(line) 
        cmt = "\n\r".join(cmts)
        # basic commenter information
        commenter = {
            "uid": current_user['uid'],
            "name": current_user['name'],
            "avatar": current_user['avatar'],
        }

        comment.set_article(int(article_sn))
        comment.set_commenter(commenter)
        comment.set_body(cmt)
        comment.put()
        self.redirect("/article/%s" % article_sn)


handlers = [
    (r"/comment/(.*)", CommentHandler),
]