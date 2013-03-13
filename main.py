#! /usr/bin/env python
# coding=utf-8

import os
import sys
import os.path
import hashlib
import datetime
import time
import logging
import re
import pymongo

import markdown

from vanellope.article import *
from vanellope.member import *
from vanellope.comment import *
from vanellope.ext import db

import tornado.httpserver
import tornado.ioloop
import tornado.options
import tornado.web
import tornado.escape

sys.path.append(os.getcwd())
from tornado.options import define, options

options['log_file_prefix'].set(os.path.join(os.path.dirname(__file__), 'page302.log'))
define("port", default=8000, help="run on the given port", type=int)


class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
        (r"/", IndexHandler),
        (r"/register", RegisterHandler),
        (r"/article/([0-9]+)", ArticleHandler),
        (r"/article", ArticleHandler),
        (r"/home", HomeHandler),
        (r"/u/(.*)", MemberHandler),
        (r"/home/(.*)", HomeHandler),
        (r"/login", LoginHandler),
        (r"/test/?([^/]*)", TestHandler),
        (r"/logout", LogoutHandler),
        (r"/update/(.*)", ArticleUpdateHandler),
        (r"/comment/(.*)", CommentHandler)]

        SETTINGS = dict(
        static_path = os.path.join(os.path.dirname(__file__), 'static'),
        template_path = os.path.join(os.path.dirname(__file__), 'templates'),
        login_url = "/login",
        debug = True)

        tornado.web.Application.__init__(self, handlers, **SETTINGS)


class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        member = db.member.find_one({"auth": self.get_cookie('auth')})
        if member:
            return member
        else:
            return None


class TestHandler(BaseHandler):
    def get(self, slug):
        self.write("this is test page" + slug)       

class MemberHandler(BaseHandler):
    def get(self, uname):
        master = self.get_current_user()

        page = self.get_argument("p", 1)
        skip_articles = (int(page) -1 )*10
        author = db.member.find_one({"name_safe": uname})
        articles = db.article.find({"status":"normal",
                                    "author": author['uid']}).sort("date",-1).limit(skip_articles)

        total = db.article.find({"author": author['uid']}).count()
        pages  = total // 10 + 1
        if total % 10 > 0:
            pages += 1

        self.render("memberHomePage.html",
                    title = author['name']+u"专栏",
                    articles = articles,
                    master = master,
                    pages = pages,
                    author = author)


class IndexHandler(BaseHandler):
    def get(self):
        page = self.get_argument("p", 1)
        skip_articles = (int(page) -1 )*10
        master = self.get_current_user()
        #master = member.check_auth(self.get_cookie('auth'))
        articles = db.article.find({"status":"normal"})
        articles.sort("date",-1).skip(skip_articles).limit(10)

        top_x_hotest = db.article.find({"status":"normal"})
        top_x_hotest.sort("heat", -1).limit(10)

        total = db.article.count()
        pages  = total // 10 + 1
        if total % 10 > 0:
            pages += 1

        self.render("index.html", 
                    title = 'PAGE302',
                    master = master, 
                    pages = pages,
                    articles = articles,
                    hotest = top_x_hotest)


class LoginHandler(BaseHandler):
    def get(self):
        self.render("login.html", title="Login", errors=None, master=False)

    def post(self):
        template = "login.html"
        errors = []
        
        post_values = ['name','pwd']
        args = {}
        for v in post_values:
            try:
                args[v] = self.get_argument(v)
            except:
                errors.append("complete the blanks")
                self.render(template, 
                            title="Login", 
                            master=False, 
                            errors=errors)
        try:
            member = db.member.find_one({'name':args['name']})
            input_auth = hashlib.sha512(args['name'] + 
                        hashlib.sha512(args['pwd']).hexdigest()).hexdigest()
        except:
            errors.append("db error")
            self.render(template, 
                        title = "Login",
                        master = False, 
                        errors = errors)

        if member and (member['auth'] == input_auth):
            self.set_cookie(name = "auth", 
                            value = member['auth'], 
                            expires_days = 365)
            self.redirect('/')
        else:
            errors.append("error with user name or password") 
            self.render(template, 
                        title = "Login", 
                        master = False, 
                        errors = errors)
  


class LogoutHandler(BaseHandler):
    def get(self):
        self.clear_all_cookies()
        self.redirect('/')


class HomeHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, page="index"):
        pages = ('write', 'manage', 'setting', 'index')
        template = ("home/%s.html" % page)
        master = self.get_current_user()
        if (page == "manage"):
            articles = self.normal_articles(master['uid'])
            self.render(template, 
                        title = 'HOME | manage', 
                        master = master,
                        articles = articles)
        else:
            self.render(template, 
                        title="Home",
                        master = master)

    @tornado.web.authenticated
    def post(self):
        master = self.get_current_user()
        if master:
            brief = self.get_argument('brief', default=None)
            db.member.update({"uid":master['uid']},{"$set":{"brief":brief}})
            member = db.member.find_one({'uid': master['uid']})
        else:
            self.send_error(403)
            self.findish()

    def get_author_all_articles(self, owner_id):
        return db.article.find({"author": owner_id}).sort("date", -1)

    def normal_articles(self, owner_id):
        return db.article.find(
                {"author": owner_id, "status":"normal"}).sort("date", -1)
        
class ArticleHandler(BaseHandler):
    # display article
    def get(self, article_sn):
        master = self.get_current_user()
            
        article = db.article.find_one(
                    {"status": "normal", 'sn': int(article_sn)})
        if not article:
            self.send_error(404)
            self.finish()

        author = db.member.find_one({'uid': article['author'] })
        comments_cursor = db.comment.find({
                          'article_id': int(article_sn)}).sort('date',1)
        comments = []
        for comment in comments_cursor:
            comment['date'] += datetime.timedelta(hours=8)
            comment['date'] = comment['date'].strftime("%Y-%m-%d %H:%M")
            comments.append(comment)

        article['heat'] += 1
        db.article.save(article)

        adjoins = find_adjoins(article['date'])

        md = markdown.Markdown(safe_mode = "escape")
        article['body'] = md.convert(article['body'])
        article['date'] += datetime.timedelta(hours=8)
        article['date'] = article['date'].strftime("%Y-%m-%d %H:%M")
        article['review'] += datetime.timedelta(hours=8)
        article['review'] = article['review'].strftime("%Y-%m-%d %H:%M")

        self.render("article.html", 
                    pre = adjoins[0],
                    fol = adjoins[1],
                    master = master,
                    comments = comments, 
                    title = article['title'],
                    author = author, 
                    article = article)
    #create article
    @tornado.web.authenticated
    def post(self):
        # get post arguments
        post_values = ['intro-img', 'title', 'brief', 'content']
        args = {}
        for v in post_values:
            try:
                args[v] = self.get_argument(v)
            except:
                pass

        article = Article()
        article.set_title(args['title'])
        article.set_brief(args['brief'])
        article.set_content(args['content'])
        article.set_avatar(self.save_uploaded_avatar())

        try:     
            master = self.get_current_user()
            article.set_author(master['uid'])
            article.save()
            self.redirect('/')
        except:
            logging.warning("Unexpecting Error")

    @tornado.web.authenticated
    def delete(self, article_sn):
        delete_article(article_sn)
        self.set_status(200)
        self.finish()

    def find_adjoins(self, current_date):
        try:
            pre = db.article.find({'date':
                {'$lt': current_date}}).sort("date",-1)[0]['sn']
        except:
            pre = None
        try:
            fol = db.article.find({'date': 
                {"$gt": current_date}}).sort("date", 1)[0]['sn']
        except:
            fol = None
        return (pre, fol)

    def save_uploaded_avatar(self, arg="intro-img"):
        # save uploaded file's binary data on local storage.
        # data specified by "arg", default value is "intro-img"
        # when file saved return it's relative link, aka the "url".
        # if no data with request use default link specified by settings.py file.
        try:
            uploaded = self.request.files[arg][0]
            file_md5 = hashlib.md5(uploaded['body']).hexdigest()
            file_ext = uploaded['filename'].split('.')[-1]
            file_name = ("intro-%f-%s.%s" % (time.time(), file_md5, file_ext))
            url = os.path.join("/", 
                               os.path.basename(settings.STATIC_PATH),
                               os.path.basename(settings.IMAGE_PATH),
                               os.path.basename(settings.ARTICLE_AVATAR_PATH),
                               file_name)
            fp = os.path.join(settings.ARTICLE_AVATAR_PATH, file_name)
            pic =  open(fp, 'wb')
            pic.write(uploaded['body'])
            pic.close()
        except:
            url = None #settings.DEFAULE_ARTICLE_AVATAR
        return url

class ArticleUpdateHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, article_sn):
        master = self.get_current_user()
        template = "home/edit.html"
        article = db.article.find_one({'sn': int(article_sn)})
        author = db.member.find_one({'_id': article['author']})

        self.render(template, 
                    master = master,
                    title = "Edit",
                    author = author,
                    article = article)

    @tornado.web.authenticated
    def post(self, article_sn):
        post_values = ['title', 'brief', 'content']
        args = {}
        for v in post_values:
            try:
                args[v] = self.get_argument(v)
            except:
                continue

        master = self.get_current_user()
        article = db.article.find_one({"sn":int(article_sn)})
        
        if master:
            article['title']  = args['title']
            article['brief'] = args['brief']
            article['body'] = args['content']
            article['review'] = datetime.datetime.utcnow()
            db.article.update({"sn":int(article_id)}, article)
            self.redirect("/article/%s" % article_id)
        else:
            self.send_error(403)

class CommentHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self, article_sn):
        master = self.get_current_user()
        # if comment has no content then return back silently.
        try:
            cmt = self.get_argument('comment')
        except:
            self.redirect(self.request.headers['Referer'])

        comment = Comment(int(article_sn))

        if master:
            # basic commenter information
            commenter = {
                "uid": master['uid'],
                "name": master['name'],
                "name_safe": master['name_safe'],
                "avatar": master['avatar']
            }
            comment.set_commenter(commenter)
            comment.set_content(cmt)
            comment.save()
            self.redirect("/article/%s" % article_sn)
        else:
            self.send_error(403)


class RegisterHandler(BaseHandler):
    def get(self):
        self.render("register.html", 
                    title = 'Register',
                    errors = None,
                    master = None)
    @tornado.web.asynchronous
    def post(self):
        errors = []
        member = Member()                       

        post_values = ['name','pwd','cpwd','email']
        args = {}
        try:
            for v in post_values:
                args[v] = self.get_argument(v, None)
        except:
            errors.append("complete the blanks")
            html = render_string("register.html", title = "Reqister", 
                        member = None, errors = errors)
            print html
            self.write(html)

        # check and set 'name'. 
        # If anything went wrong error messages list returned
        errors += member.check_name(args['name'])

        if args['pwd'] and (args['pwd'] == args['cpwd']):
            member.set_pwd(args['pwd'])
        else:
            errors.append("password different")

        # authentication email
        if args['email']:
            # check and set 'email'. 
            # If anything went wrong error messages list returned
            errors += member.check_email(args['email'])
        else:
            errors.append("no email")

        if errors:
            self.render("register.html", #template file
                        title = "Register", # web page title
                        errors = errors,    
                        member = None)
        else:
            member.save()
            self.set_cookie(name="auth", 
                            value=member.get_auth(), 
                            expires_days = 365)
            self.redirect('/')


if __name__ == "__main__":
    tornado.options.parse_command_line()
    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(options.port)
    tornado.ioloop.IOLoop.instance().start()


