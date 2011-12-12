from StringIO import StringIO

import sys, gevent, logging

from gevent import socket

log = logging.getLogger(__name__)

# since read() will potentially yield chunks and wsgi is not up for chunked
# requests, we have to make a single stream out of it
class Input(object):

    def __init__(self, read, chunked_input=False):
        self.reader = iter(read())
        self.current_chunk = None
      
    def read_rest( self, length, line=False ):
        if self.current_chunk:
            data = self.current_chunk.readline( length ) if line\
                    else self.current_chunk.read( length )
            if not data:
                self.current_chunk = None
            else:
                return data
        return ''

    def read( self, length=None ):
        buffer = []
        data = self.read_rest( length )
        if data:
            length -= len(data)
            buffer.append( data )

        if length is None:
            self.current_chunk = None
            for data in self.reader:
                buffer.append( self.reader.next() )
        else:
            rest = None
            while True:
                v = self.reader.next()
                if not v:
                    break
                length -= len(v)
                if length<=0:
                    if length<0:
                        rest = v[(-length):]
                        v = v[:-length]
                    buffer.append(v)
                    break
                buffer.append( v )

            if rest:
                self.current_chunk = StringIO( rest )

        return ''.join( buffer )

    def readline( self, length=None ):
        data = self.read_rest( length, True )
        if data:
            return data

        v = self.reader.next()
        if not v:
            return v

        self.current_chunk = StringIO( v )
        return self.current_chunk.readline( length )

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
        self.server_name = None

    def __call__( self, env, read, write ):
        sock = env['socket']
        if not hasattr(sock,'fqdn'):
            sock.fqdn = getattr( sock, 'host', '' )
            sock.port = getattr( sock, 'port', '' )

            try:
                sock.fqdn = socket.getfqdn( sock.fqdn )
            except socket.error:
                pass

        env.setdefault('wsgi',{})

        environ = env['wsgi'].get('environ',None)
        env_http = env['http']
        headers = env_http['request']['header']

        if not environ:
            env['wsgi']['environ'] = environ =\
                { 'GATEWAY_INTERFACE': 'CGI/1.1'
                , 'SERVER_PROTOCOL': env['http']['request_version']
                , 'SERVER_SOFTWARE': self._environ_software
                , 'SERVER_NAME': sock.fqdn
                , 'SERVER_PORT': sock.port
                , 'REMOTE_ADDR': env['remoteclient']['address'][0]
                , 'wsgi.version': (1, 0)
                , 'wsgi.multithread': False
                , 'wsgi.multiprocess': False
                , 'wsgi.run_once': False
                , 'wsgi.errors': sys.stderr
                , 'wsgi.url_scheme': 'http' # TODO: https ( socket first )
                }

        environ['SCRIPT_NAME'] = self.approot or env.get('route',{}).get('approot','')
        environ['wsgi.input'] = Input( read, environ\
                    .get('HTTP_TRANSFER_ENCODING', '').lower() == 'chunked' )

        environ['PATH_INFO'] = env_http['path'][len(environ['SCRIPT_NAME']):]
        environ['QUERY_STRING'] = env_http['query']

        environ['REQUEST_METHOD'] = env_http['method']
        if headers.typeheader is not None:
            environ['CONTENT_TYPE'] = headers.typeheader

        length = headers.getheader('content-length')
        if length:
            environ['CONTENT_LENGTH'] = length



        keys_added = set()
        for (key,value) in headers.items():
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
                    keys_added.add( key )

        try:
            result = self.handler( environ, lambda status, headers, exc_info=None\
                : self._start_response( env, write, status, headers, exc_info ) )
        finally:
            for key in keys_added:
                del environ[key]

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

