from StringIO import StringIO
from gevent import socket

import sys, gevent, logging

log = logging.getLogger(__name__)

class Input(object):

    def __init__(self, read, chunked_input=False):
        self.reader = iter(read())
        self.current_chunk = None

    def get_chunk( self ):
        if not self.current_chunk:
            v = self.reader.next()
            if not v:
                return ''
            self.current_chunk = StringIO( v )
        return  self.current_chunk

    def read( self, length=None ):
        v = self.get_chunk().read( length )
        if not v:
            self.current_chunk = None
        return v

    def readline( self, length=None ):
        v = self.get_chunk().readline( length )
        if not v:
            self.current_chunk = None

    def readlines( self, hint=None ):
        return list( self )

    def __iter__( self ):
        return self

    def next( self ):
        line = self.readline()

        if not line:
            raise StopIteration
        return line

class Server:
    _environ_software = \
        'gevent/%d.%d Python/%d.%d' % (gevent.version_info[:2] + sys.version_info[:2])

    def __init__( self, handler, approot=None ):
        self.handler = handler
        self.approot = approot

    def __call__( self, env, read, write ):
        server_name = getattr( env['socket'], 'host', '' )
        try:
            server_name = socket.getfqdn( server_name )
        except socket.error:
            pass

        env.setdefault('wsgi',{})

        environ = env['wsgi'].get('environ',None)
        env_http = env['http']
        headers = env_http['request']['header']

        if not environ:
            env['wsgi']['environ'] = environ =\
                { 'GATEWAY_INTERFACE': 'CGI/1.1'
                , 'SERVER_SOFTWARE': self._environ_software
                , 'SCRIPT_NAME': self.approot or env.get('route',{}).get('approot','')
                , 'SERVER_NAME': server_name
                , 'SERVER_PORT': getattr( env['socket'], 'port', '' )
                , 'wsgi.version': (1, 0)
                , 'wsgi.multithread': False
                , 'wsgi.multiprocess': False
                , 'wsgi.run_once': False
                , 'wsgi.errors': sys.stderr
                , 'wsgi.url_scheme': 'http' # TODO: https ( socket first )
                }

        environ['wsgi.input'] = Input( read, environ\
                    .get('HTTP_TRANSFER_ENCODING', '').lower() == 'chunked' )

        environ['PATH_INFO'] = env_http['path'][len(environ['SCRIPT_NAME']):]
        environ['QUERY_STRING'] = env_http['query']

        environ['REQUEST_METHOD'] = env_http['method']
        if headers.typeheader is not None:
            environ['CONTENT_TYPE'] = self.headers.typeheader

        length = headers.getheader('content-length')
        if length:
            environ['CONTENT_LENGTH'] = length
        environ['SERVER_PROTOCOL'] = 'HTTP/1.0'

        environ['REMOTE_ADDR'] = env['remoteclient']['address'][0]

        for (key,value) in headers.items():
            #key, value = header.split(':', 1)
            key = key.replace('-', '_').upper()
            if key not in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
                value = value.strip()
                key = 'HTTP_' + key
                if key in environ:
                    if 'COOKIE' in key:
                        environ[key] += '; ' + value
                    else:
                        environ[key] += ',' + value
                else:
                    environ[key] = value

        result = self.handler( environ, lambda status, headers, exc_info=None\
                : self._start_response( env, write, status, headers, exc_info ) )

        for data in result:
            if data:
                write(data)

    def _start_response(self, env, write, status, headers, exc_info=None):
        if exc_info:
            try:
                if env['http']['is_header_send']:
                    # Re-raise original exception if headers sent
                    raise exc_info[0], exc_info[1], exc_info[2]
            finally:
                # Avoid dangling circular ref
                exc_info = None

        env['http']['status'] = status
        env['http']['response']['header'] = headers

        return write

