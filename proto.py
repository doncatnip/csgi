"""
csgi - client/server gateway interface

I'm writing this, because im tired of the common practice today to
tightly couple the http transport into the wsgi servers and making various
bidirectional protocols dependand on wsgi - reducing their flexibility and
counteracting DRY.

WSGI really should be only a handler ontop of a HTTP transport.

The idea goes as followes: find an wsgi-ish way to bubble a 'request' from the
very bottom ( the listener ) all the way up to some handler ( which could be
a html page, or an amqp subscriber/publisher ).

Every transport receives (socket, env) per connection as arguments and delivers
a read and write method to its handler while populating env with transport-
specific stuff.

read is a callable which returns a list or generator, write is a callable,
receiving one argument.

A request/connection is considered finished when its handler returns.

Status: prototype
License: Public Domain
"""

#from jsonrpc_decoder import JsonRPC

from gevent.queue import Queue
from gevent import spawn, spawn_later, sleep
from gevent.event import AsyncResult
from gevent import socket
from gevent.pywsgi import _BAD_REQUEST_RESPONSE, format_date_time

import re, os, time

from mimetools import Message

from StringIO import StringIO



port = 8081
class MISSING:
    pass

def deepcopydict(org):
    '''
    much, much faster than deepcopy, for a dict of the simple python types.
    '''
    out = org.copy()
    for k,v in org.iteritems():
        if isinstance( v, dict ):
            out[k] =  deepcopydict( v )
        elif isinstance( v, list):
            out[k] = v[:]

    return out

class Call:
    
    def __init__( self, resource, includeEnv=False ):
        self.resource = resource
        self.includeEnv = includeEnv

    def __call__( self, read, write, env ):
        for (args, kwargs) in read():
            if self.includeEnv:
                args = list(args)
                args.insert( 0, env )
                
            result = self.resource( *args, **kwargs )
            write( result )


class EnvRouter:

    def __init__( self, *handler, **params ):
        self.handler = {}
        handler = list(handler)
        lastValue = handler.pop(0)
        
        i = 0
        while handler:
            value = handler.pop(0)
            if i%2 == 0:
                self.handler[ lastValue ] = value

            lastValue = value
            i+=1

        self.by = params['by']
        self.on_not_found = params.get('on_not_found', lambda read, write, env: self._log_error( 'route not found .. env: %s' % (env,) ) )

    def __call__( self, read, write, env ):
        handler = self.handler.get( self.by( env ), None )
        if not handler:
            self.on_not_found( read, write, env )
            return

        self.handler[ self.by( env ) ]( read, write, env )

    def _log_error( self, error ):
        print error

class RPCRouter:

    def __init__( self, *handler ):
        self.handler = {}
        handler = list(handler)
        lastValue = handler.pop(0)
        
        i = 0
        while handler:
            value = handler.pop(0)
            if i%2 == 0:
                self.handler[ lastValue ] = value

            lastValue = value
            i+=1

    def __call__( self, read, write, env ):
        for data in read():
            args, kwargs = data
            args = list(args)
            path = args.pop(0)
            
            rpc_env = env.get('rpc',None)
            if rpc_env is None:
                env['rpc'] = { 'path': path }
            else:
                env['rpc']['path'] = path

            self.handler[ path ]( lambda: (( args, kwargs ),), write, env  )



class LocalSocket:

    def __init__( self, handler ):
        self.handler = handler

    def __call__( self ):
        return _LocalSocket( self.handler )


class _LocalSocket:
    """ test handlers locally """
    #TODO: use actual buffers instead of queues

    class _LocalServerSocket:
        pass

    def __init__( self, handler ):
        self.env = { 'socket': self }

        serverSocket = self._LocalServerSocket()

        self.clientqueue = clientqueue = Queue()
        self.serverqueue = serverqueue = Queue()

        self.read = self.readline = lambda: serverqueue
        self.write = lambda data: clientqueue.put( data )

        serverSocket.read = serverSocket.readline = lambda: clientqueue
        serverSocket.write = lambda data: serverqueue.put( data )

        spawn( handler, serverSocket, self.env  )

    def __iter__( self ):
        return self.serverqueue

    def release( self ):
        self.clientqueue.put( StopIteration )
        self.serverqueue.put( StopIteration )
        self.env = { 'socket': self }

def spawnme( function ):
    f = ( function, )
    return lambda *args, **kwargs: spawn( *f+args, **kwargs )

class ClientDummy:

    def __call__( self, socket, env ):
        self._readservermessages( socket, env )

        for request in env['client'].input_queue:
            socket.write( request )

    @spawnme
    def _readservermessages( self, socket, env ):
        for response in socket.read():
            env['client'].output_queue.put( response )


class transport:

    class Dummy:

        def __init__( self, handler ):
            self.handler = handler

        def __call__( self, socket, env ):
            self.handler( socket.__iter__(), socket.write, env )


    class Line:

        def __init__( self, handler ):
            self.handler = handler

        def __call__( self, socket, env ):
            self.handler\
                ( lambda: self._readlines( socket )
                , lambda data: socket.write( data+'\r\n' )
                , env )

        def _readlines( self, socket ):
            for line in socket.readline():
                yield line

    class HTTP:
        # TODO: pipelining, client
        MessageClass = Message

        def __init__( self, handler, force_chunked=False ):
            self.handler = handler
            self.force_chunked = force_chunked

        def __call__( self, socket, env ):
            env.setdefault( 'http', {} )
            base_env = env['http'].get('_base_env',False)
            if not base_env:
                env['_base_env'] = deepcopydict( env ) 
            else:
                env = deepcopydict( base_env )

            env['http'] = env_http =\
                { 'request': { 'header': None }
                , 'response': { 'header': None }
                , 'is_header_send': False
                , 'is_header_read': False
                , 'is_handler_done': False
                , 'status': 200
                , 'force_chunked': self.force_chunked
                }

            abort = False
            if 'remoteclient' in env:
                env_http['is_header_read'] = True
                env_http['mode'] = 'response'
                env_http['response']['header'] = []
                
                header = socket.readline()
                if not header:
                    return

                elif not self._read_request_header( socket, env_http, header ):
                    socket.write( _BAD_REQUEST_RESPONSE )
                    env['status'] = 400
                    abort = True
            else:
                env_http['mode'] = 'request'

            if not abort:
                self.handler\
                    ( lambda: self._read( socket, env_http )
                    , lambda data: self._write( data, socket, env_http )
                    , env )

            else:
                env_http['keepalive'] = False
            
            self._finish_response( socket, env )

        def _finish_response( self, socket, env ):
            env_http = env['http']
            env_http['is_handler_done'] = True
            if not env_http['is_header_send']:
                self._write_nonchunked_response( socket, env_http )
            else:
                socket.write(  "0\r\n\r\n"  )

            if env_http['keepalive']:
                self( socket, env )


        def _write( self, data, socket, env ):
            if not env['is_header_send']:
                if env['mode'] == 'response' and not env['force_chunked']:
                    # more than 1 write = chunked response
                    # TODO: set env['force_chunked'] when handler sets
                    # transfer-encoding header to chunked
                    if not 'result_on_hold' in env:
                        env['result_on_hold'] = data
                        return

                    self._send_headers( socket, env )

                    lastresult = env.pop('result_on_hold')
                    socket.write(  "%x\r\n%s\r\n" % (len(lastresult), lastresult) )
                else:
                    self._send_headers( socket, env )

            socket.write(  "%x\r\n%s\r\n" % (len(data), data) )

        def _read( self, socket, env ):
            if not env['is_header_read']:
                header = socket.readline( )
                self._read_response_header( header, env )
                env['is_header_read'] = True

            if not env['content_length']:
                while True:
                    length = socket.readline()
                    if length == 0:
                        return
                    yield socket.read( int( length ) )
            
            yield socket.read( env['content_length'] )

        def _check_http_version(self, version):
            if not version.startswith("HTTP/"):
                return False
            version = tuple(int(x) for x in version[5:].split("."))  # "HTTP/"
            if version[1] < 0 or version < (0, 9) or version >= (2, 0):
                return False
            
            return True

        def _log_error( self, err, raw_requestline=''):
            print( 'ERROR: %s' % (err % (raw_requestline,) ) )

        def _read_request_header(self, socket, env, raw_requestline):

            requestline = raw_requestline.rstrip()
            words = requestline.split()
            
            if len(words) == 3:
                command, path, request_version = words
                if not self._check_http_version( request_version ):
                    self._log_error('Invalid http version: %r', raw_requestline)
                    return

            elif len(words) == 2:
                command, self.path = words
                if command != "GET":
                    self._log_error('Expected GET method: %r', raw_requestline)
                    return

                request_version = "HTTP/0.9"
                # QQQ I'm pretty sure we can drop support for HTTP/0.9
            else:
                self._log_error('Invalid HTTP method: %r', raw_requestline)
                return

            headers = self.MessageClass( socket, 0)
            if headers.status:
                self._log_error('Invalid headers status: %r', headers.status)
                return

            if headers.get("transfer-encoding", "").lower() == "chunked":
                try:
                    del headers["content-length"]
                except KeyError:
                    pass

            content_length = headers.get("content-length")
            if content_length is not None:
                content_length = int(content_length)
                if content_length < 0:
                    self._log_error('Invalid Content-Length: %r', content_length)
                    return
                if content_length and command in ('GET', 'HEAD'):
                    self._log_error('Unexpected Content-Length')
                    return

            if request_version == "HTTP/1.1":
                conntype = headers.get("Connection", "").lower()
                if conntype == "close":
                    close_connection = True
                else:
                    close_connection = False
            else:
                close_connection = True

            env.update\
                ( method=command
                , content_length=content_length
                , keepalive=not close_connection
                , request_version = request_version
                , path=path
                )

            print headers.items()
            env['request']['header'] = headers

            return True

        def _serialize_headers( self, socket, env):
            keepalive = env.get('keepalive', None)

            response_headers =\
                    [   ( '-'.join([x.capitalize() for x in key.split('-')]), value
                        ) for key, value in env[ env['mode'] ]['header'] ]

            response_headers_list = [x[0] for x in response_headers ]
            
            if 'Date' not in response_headers_list:
                response_headers.append(('Date', format_date_time(time.time())))

            elif keepalive is False or env['request_version'] == 'HTTP/1.0':
                if 'Connection' not in response_headers_list:
                    response_headers.append(('Connection', 'close'))
                keepalive = False

            elif ('Connection', 'close') in response_headers:
                keepalive = False

            if env['status'] not in [204, 304]:
                # the reply will include message-body; make sure we have either Content-Length or chunked
                if 'Content-Length' not in response_headers_list:
                    if env['request_version'] != 'HTTP/1.0':
                        response_headers.append(('Transfer-Encoding', 'chunked'))

            towrite = [ '%s %s\r\n' % (env['request_version'], env['status']) ]
            for header in response_headers:
                towrite.append('%s: %s\r\n' % header)

            if keepalive is not None:
                env['keepalive'] = keepalive
                
            return ''.join(towrite)

        def _send_headers( self, socket, env ):
            socket.write( '%s\r\n' % self._serialize_headers( socket, env ) )
            env['is_header_send'] = True
            
        def _write_nonchunked_response( self, socket, env ):
            content = env.pop('result_on_hold','' )
            env['response']['header'].append(('Content-Length', str(len(content))))
            response = "%s\r\n%s"\
                    %   ( self._serialize_headers( socket, env )
                        , content
                        )

            print response
            socket.write ( response )


class IOQueue:

    def __init__( self, releaseCB ):
        self.input_queue = Queue()
        self.output_queue = Queue()
        self.read = self.__iter__ = lambda: self.output_queue

        self.releaseCB = releaseCB

    def __call__( self, *args, **kwargs ):
        self.input_queue.put( (args, kwargs) )
        return self.output_queue.get()

    def write( self, *args, **kwargs ):
        self.input_queue.put( (args, kwargs) )
        return self

    def close( self ):
        self.input_queue.put( StopIteration )
        self.output_queue.put( StopIteration )
        self.releaseCB( )

class ConnectionPool:

    def __init__( self, socket, handler, clientClass=IOQueue ):
        self.socket = socket
        self.handler = handler
        self.clientClass = clientClass

    def __call__( self, *args, **kwargs ):
        _socket = self.socket.connect()
        client = self.clientClass( _socket.release )

        spawn\
            ( self.handler
            , _socket )

        if args or kwargs:
            result = client( *args, **kwargs )
            client.close()
            return result
        
        return client

def Listen( *args, **kwargs):
    l = _Listen( *args, **kwargs )
    l.start()

class _Listen:
    def __init__( self, socket, handler, create_env=None ):
        self.socket = socket
        self.handler = handler
        if not create_env:
            create_env = lambda: {}
        self.create_env = create_env

    def start( self ):
        self.connected = True

        for (connection,address) in self.socket.accept():
            spawn( self._handle_connection, connection, address )

    def _handle_connection( self, connection, address ):
        env = self.create_env()
        env.update\
            ( remoteclient = { 'address':address }
            , socket = connection
            )
        self.handler( connection, env )
        connection.close()
            
    def stop( self ):
        self.connected = False
        self.socket.close()


re_host_tcp = re.compile(r'^(tcp):\/\/([a-z\.]+|([0-9]+\.){3}[0-9]+):([0-9]+)$',re.I)
re_host_ipc = re.compile(r'^(ipc):\/\/(.*)$',re.I)

def parseSocketAddress( address ):
    port = None
    m = re_host_tcp.match( address )
    if m:
        ( protocol, host, waste, port ) = m.groups()
        port = int(port)
    else:
        m = re_host_ipc.match( address )
        if not m:
            raise SyntaxError('%s is not a valid address ( (tcp://host[:port]|ipc://file) is required )' % host ) 
        ( protocol, host ) = m.groups()

    return ( protocol.lower(), host.lower(), port )


class Connection:

    def __init__( self, gsocket ):
        self.gsocket = gsocket
        self.rfile = gsocket.makefile()

        self.readline = self.rfile.readline
        self.read = self.rfile.read
        self.write = gsocket.sendall
        self.close = gsocket.close
    
        print "incoming request"


class Socket:
    def __init__( self, address ):
        self.address = address
        ( self.protocol, self.host, self.port ) = parseSocketAddress( self.address )

        if self.protocol not in ('ipc','tcp'):
            raise SyntaxError( 'Protocol %s not supported' % (self.protocol) )

    def connect( self ):
        if self.protocol == 'ipc':
            gsocket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            gsocket.connect( self.host )

        return Connection( gsocket )

    def accept( self ):
        print "accept ..."
        if self.protocol == 'ipc':
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                os.remove( self.host )
            except OSError:
                pass
            s.bind( self.host  )
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind((self.host, self.port))

        s.listen(1)

        print "listening on %s ..." % self.address
        while True:
            (connection, address) = s.accept()
            yield (Connection( connection ), address)

        if self.protocol == 'ipc':
            try:
                os.remove( self.host )
            except OSError:
                pass


def echo_handler( arg ):
    seconds = 0 #random.randint( 0, 2 )
    #sleep( seconds )
    return "echo after %s seconds: %s" % ( seconds, arg)

def hellohttp( read, write, env ):
    body = ()
    if env['http']['method'] == 'POST':
        posted = ''.join( read() )
        body = '<h1>%s</h1>' % posted
    else:
        body = ''.join\
            ( ( '<label for="testform">say something:</label>'
              , '<form method="post"><input id="testform" type="text" name="testinput"/></form>'
              )
            )

    write\
        ( '<html><header></header><body>%s</body></html>'\
            % body
        )


#testServer = transport.Dummy( RPCRouter( 'test.echo', Call( echo_handler ) ) )

def _404( read, write, env ):
    env['http']['status'] = 404
    write( '<html><body>404 - Not found</body></html>' )

server = Listen\
    ( Socket( 'tcp://localhost:%s' % port)
    , transport.HTTP\
        ( EnvRouter\
            ( '/', hellohttp
            , by=lambda env: env['http']['path']
            , on_not_found=_404
            )
        )
    )

#client = ConnectionPool\
#    ( Socket( 'ipc://testsocket' )
#    , transport.HTTP( http.Client() )
#    )


"""
def starttest():
    clientIO = client()

    i=0
    for result in clientIO.write( 'test.echo', i ):
        print ('response: %s' % (result,))
        i+=1
        if i==10:
            break

        print ('write next ...')
        clientIO.write( 'test.echo', i )
        print ('next done ...')

    clientIO.close()

"""


"""

class jsonrpc:

    class Server:

        def __init__( self, handler ):
            self.handler = handler

        def __call__( self, read, write, env ):
            for request in read:
                
                ( data
                , requestID
                , version
                , isBatch ) = JsonRPC.decodeRequest( request )

                env.rpc.requestID = requestID
                
                self.handler\
                    ( isBatch and ( data, ) or data
                    , lambda: write( JsonRPC.encodeResult( data, requestID, version ) )
                    , env )



    class Client:
        _ID = 0

        def __call__( self, read, write, env ):
            requestID = self._.ID

            for (path, args, kwargs) in env.socket:
                write( JsonRPC.encodeRequest\
                        ( (path, args, kwargs), requestID ) )

            self.__class__._ID += 1

        def read( self ):
            (response,self.env_rpc.version) = JSONRPCHandler.decodeResult\
                ( self.socket.read( ) )
                    
            return response

        def write( self, data ):
            args = data.pop(0,())
            kwargs = data.pop(0,{})

            content  = JSONRPCHandler.encodeBody\
                    ( self.env_rpc.path, args, kwargs, self.env_rpc.version )
        
            self.socket.write( data )





"""
