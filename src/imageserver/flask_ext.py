#
# Quru Image Server
#
# Document:      flask_ext.py
# Date started:  06 Feb 2015
# By:            Matt Fozard
# Purpose:       Flask extensions
# Requires:      Flask
# Copyright:     Quru Ltd (www.quru.com)
# Licence:
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published
#   by the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see http://www.gnu.org/licenses/
#
# Last Changed:  $Date$ $Rev$ by $Author$
#
# Notable modifications:
# Date       By    Details
# =========  ====  ============================================================
# 12Mar2015  Matt  Added install_http_authentication and friends
# 13Apr2015  Matt  Added Jinja2 Markdown extension
#

import os.path
import time
from datetime import datetime

from itsdangerous import BadSignature, SignatureExpired
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer

from jinja2 import nodes
from jinja2.ext import Extension
from jinja2.exceptions import TemplateNotFound

import flask
from flask.json import JSONEncoder
from flask.wrappers import Request
from werkzeug.contrib.fixers import ProxyFix
from werkzeug.utils import cached_property

import markdown


def add_proxy_server_support(app, num_proxies=1):
    """
    Instructs the application to use the X-Forwarded-For, X-Forwarded-Proto,
    and X-Forwarded-Host headers provided by a front-end load balancer or
    proxy server. Do not enable this support if the application is not hosted
    behind a proxy server.
    """
    app.wsgi_app = ProxyFix(app.wsgi_app, num_proxies)


def fix_bad_query_strings(app):
    """
    Installs a custom implementation of Flask's Request class that converts
    badly encoded URL query strings such as "x=1&amp;y=2&amp;z=3" to the
    correct form "x=1&y=2&z=3".

    requests.args then contains {'x': '1', 'y': '2', 'z': '3'} in either case.
    """
    app.request_class = FixQueryStringRequest


def time_requests(app):
    """
    Installs a request hook to store the start time of the request on flask.g.
    """
    @app.before_request
    def start_request_stats():
        flask.g.request_started = time.time()


def enhance_json_encoder(app):
    """
    Installs the ISODateJSONEncoder class for use with Flask's jsonify function.
    """
    app.json_encoder = ExtraJSONEncoder


def install_http_authentication(app, auth_class):
    """
    Installs an instance of BaseHttpAuthentication to provide HTTP
    authentication ahead of Flask's main request handling.
    This must be done before installing CSRF protection (if required).
    See also the documentation for BaseHttpAuthentication.
    """
    cls = (auth_class if isinstance(auth_class, BaseHttpAuthentication)
           else globals().get(auth_class))
    if not cls:
        raise ValueError('Class flask_ext.%s was not found' % auth_class)
    auth_module = cls(app)

    @app.before_request
    def auth_request():
        auth_module.authenticate_request(flask.request)


def install_markdown_template_tag(app, markdown_path):
    """
    Installs the include_markdown template tag.
    See IncludeMarkdownExtension for details.
    """
    app.jinja_env.extend(markdown_base_dir=markdown_path)
    app.jinja_env.add_extension('imageserver.flask_ext.IncludeMarkdownExtension')


class BaseHttpAuthentication(object):
    """
    Base class for authenticating a Flask HTTP request, which sets
    flask.g.http_auth to some value on success. Sub-classes should override
    authenticate_request() and call set_authenticated() on success.
    If there are no HTTP authentication headers, or the authentication fails,
    flask.g.http_auth will not be set.

    Sub-classes can also set the disable_csrf attribute if authenticated
    requests do not then require CSRF protection.
    """
    def __init__(self, app):
        self.disable_csrf = False

    def set_authenticated(self, auth_obj):
        flask.g.http_auth = auth_obj
        flask.g.csrf_exempt = self.disable_csrf

    def authenticate_request(self, request):
        raise NotImplementedError(
            'BaseHttpAuthentication should not be used directly'
        )


class TimedTokenBasicAuthentication(BaseHttpAuthentication):
    """
    An implementation of BaseHttpAuthentication that looks for a signed token
    in the standard HTTP Basic Authentication username field.

    Callers can use generate_auth_token() to create this token, which also
    determines the value that will end up in flask.g.http_auth on success.
    """
    def __init__(self, app):
        BaseHttpAuthentication.__init__(self, app)
        self.disable_csrf = True
        self.secret_key = app.config['SECRET_KEY']
        self.expiry_seconds = app.config['API_TOKEN_EXPIRY_TIME']

    def generate_auth_token(self, auth_obj):
        """
        Generates a new encrypted authentication token that embeds token_obj
        and is valid for API_TOKEN_EXPIRY_TIME seconds.
        """
        s = Serializer(
            self.secret_key,
            salt='auth_token',
            expires_in=self.expiry_seconds
        )
        return s.dumps(auth_obj)

    def decode_auth_token(self, token):
        """
        Decrypts the given authentication token, returning the original token_obj,
        or None if the token is invalid or has expired.
        """
        s = Serializer(
            self.secret_key,
            salt='auth_token'
        )
        try:
            return s.loads(token)
        except SignatureExpired:
            return None
        except BadSignature:
            return None

    def authenticate_request(self, request):
        """
        Sets a Flask request as authenticated if there is a Basic Authentication
        HTTP header that contains a valid signed token in the username field.
        """
        # CORS preflight checks use Access-Control-* headers with the OPTIONS
        # method, and fail if a 401 is returned, so we need to ignore those
        if request.authorization and request.method != 'OPTIONS':
            token = request.authorization.username
            if token:
                auth_obj = self.decode_auth_token(token)
                if auth_obj:
                    self.set_authenticated(auth_obj)
                    return

            # The token was missing/invalid and g.csrf_exempt has not been set.
            # Now if this is an API PUT/POST, we want a JSON 401 response and
            # not an HTML 400 CSRF message. If the user has no web session,
            # they're not logged in, so we should be able to assume that any
            # "interesting" actions will be blocked anyway, and skip the CSRF
            # so that the correct response can be returned.
            # I don't like this bit and would welcome a better alternative.
            # Also, sorry for the leakage of application logic into here.
            api_call = request.path.startswith('/api/')
            if api_call and not flask.session:
                flask.g.csrf_exempt = self.disable_csrf


class ExtraJSONEncoder(JSONEncoder):
    """
    A replacement Flask JSONEncoder that encodes dates in ISO8601 format,
    and encodes exceptions as a dictionary.
    """
    def default(self, o):
        if isinstance(o, datetime):
            ds = o.isoformat()
            if '+' not in ds:
                ds += 'Z'
            return ds
        elif isinstance(o, Exception):
            return {
                'exception': {
                    'type': type(o).__name__,
                    'message': str(o.args[0] if len(o.args) == 1 else ''),
                    'repr': repr(o)
                }
            }
        return JSONEncoder.default(self, o)


class FixQueryStringRequest(Request):
    """
    Overrides the args property of Flask's Request to convert badly encoded
    URL query strings like "x=1&amp;y=2&amp;z=3" to "x=1&y=2&z=3" before use.
    This sad situation seems to come about from HTML4's requirement to escape
    ampersands, HTML5's declaring either way to be valid, and buggy clients
    that aren't sure what to do.
    """
    @cached_property
    def args(self):
        if self.environ.get('QUERY_STRING'):
            self.environ['QUERY_STRING'] = self.environ['QUERY_STRING'].replace('&amp;', '&')
        return super(Request, self).args


class IncludeMarkdownExtension(Extension):
    """
    A Jinja2 extension that implements a tag for including Markdown files into
    a template. The extension is similar to the standard "include" tag, except
    that it takes a path to a Markdown file instead of a Jinja template.

    E.g. {% include_markdown "path/to/myfile.md" %}

    The tag also supports an optional second parameter which can contain a
    dictionary of {'from': 'to'} text substitutions to make in the markdown
    before it is converted to HTML.

    E.g. {% include_markdown "path/to/myfile.md", subs_dict %}

    The tag requires a variable 'markdown_base_dir' in the Jinja environment
    containing the base path for finding Markdown files (where the 'path/to'
    will be looked for in the above examples).

    For implementation details see http://jinja.pocoo.org/docs/dev/extensions/
    but more helpfully, Google and Stack Overflow.

    To install this extension in a Flask environment, you need the lines:

    app.jinja_env.extend(markdown_base_dir='/path/to/')
    app.jinja_env.add_extension('imageserver.flask_ext.IncludeMarkdownExtension')
    """
    tags = set(['include_markdown'])

    def __init__(self, environment):
        super(IncludeMarkdownExtension, self).__init__(environment)

    def parse(self, parser):
        line_no = parser.stream.next().lineno
        tag_args = [parser.parse_expression()]

        # If there is a comma, the user provided a text substitutions dict
        if parser.stream.skip_if('comma'):
            tag_args.append(parser.parse_expression())

        return nodes.Output([
            nodes.MarkSafeIfAutoescape(
                self.call_method('to_html', tag_args)
            )
        ]).set_lineno(line_no)

    def to_html(self, md_path, subs_dict=None):
        # Read the Markdown file
        try:
            with open(
                os.path.join(self.environment.markdown_base_dir, md_path), 'rb'
            ) as f:
                md_text = f.read()
        except:
            raise TemplateNotFound(md_path)

        # Text substitutions
        if subs_dict:
            for fnd, repl in subs_dict.iteritems():
                md_text = md_text.replace(fnd, repl)

        # MD to HTML
        return markdown.markdown(md_text, output_format='html5')
