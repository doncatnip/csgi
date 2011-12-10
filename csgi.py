import jsonrpcio

from gevent import socket, spawn, joinall, sleep

from gevent.queue import Queue
from gevent.event import AsyncResult
from gevent.pywsgi import _BAD_REQUEST_RESPONSE, format_date_time

import re, os, time

from uuid import uuid4 as uuid
from mimetools import Message

import logging
log = logging.getLogger( __name__ )

#TODO: tests; clients; organize to submodules ofc.; stuff

class Undefined:
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
    
    def __init__( self, resource, include_env=True ):
        self.resource = resource
        self.include_env = include_env

    def __call__( self, env, read, write ):
        for (args, kwargs) in read():
            if self.include_env:
                args = list(args)
                args.insert( 0, env )
                
            result = self.resource( *args, **kwargs )
            write( result )

class _Env:
    # TODO: move NotFound *handling* elsewere
    class NotFound( Exception ):
        def __init__( self, what ):
            self.what = what
            Exception.__init__(self, what)

    class Router:

        def __init__( self, *handlers, **params ):
            self.handler = []
            self.named_routes = {}

            routes = set()
            
            for i in range( len(handlers) ):
                (key, handler) = handlers[i]
                if key in routes:
                    raise SyntaxError( 'Routes must be unique' )

                routes.add( key )
                if not hasattr( key, 'match' ) :
                    self.named_routes[ key ] = handler
                else:
                    self.handler.append( (key, handler ) )

            self.by = params.pop('by')
            self.each = params.pop('each',None)
            self.on_not_found = params.pop\
                ( 'on_not_found'
                , lambda env, read, write: self._log_error( 'route not found .. env: %s' % (env,) )
                )

            if params:
                raise SyntaxError( 'Invalid keyword arguments: %s' % params.keys()  )

        def __call__( self, env, read, write ):
            value = self.by( env )
            handler = self.named_routes.get( value, None )
            
            env['route'] = {'path': value }

            if not handler:
                for (key,handler_) in self.handler:
                    match = key.match( value )
                    if match:
                        groups = match.groupdict()
                        if groups:
                            env['route'].update( groups )
                        
                        handler = handler_
                        break

            if not handler:
                self.on_not_found( env, read, write )
                return

            if self.each:
                env['route']['hander'] = handler
                self.each( env, read, write )
            else:
                try:
                    handler( env, read, write )
                except _Env.NotFound:
                    self.on_not_found( env, read, write )

        def _log_error( self, error ):
            log.error( error )

    def __call__( self, *args ):
        env = args[0]
        value = env
        for part in self.path:
            value = value[ part ]
        if callable( value ):
            return value( *args )
        else:
            return value

    def __init__( self, path=None, name=None ):
        if path is None:
            self.path = ()
        else:
            self.path = path+(name,)

    def __getitem__( self, name ):
        return _Env( self.path, name )

    def set( self, updater, handler ):
        return env.Setter( self.path, updater, handler )

    class Setter:
        def __init__( self, path, updater, handler ):
            self.path = path
            self.updater = updater
            self.handler = handler

        def __call__( self, env, r, w ):
            env_to_update = env
            value = self.updater( env )

            if self.path:
                for part in self.path[:-1]:
                    env_to_update = env_to_update[ part ]
                env_to_update[ self.path[-1] ] = value
            else:
                env = value

            self.handler( env, r, w )
    

env = _Env()


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

    def __call__( self, env, read, write ):
        for data in read():
            args, kwargs = data
            args = list(args)
            path = args.pop(0)
            
            rpc_env = env.get('rpc',None)
            if rpc_env is None:
                env['rpc'] = { 'path': path }
            else:
                env['rpc']['path'] = path

            self.handler[ path ]( env, lambda: (( args, kwargs ),), write  )




def spawnme( function ):
    f = ( function, )
    return lambda *args, **kwargs: spawn( *f+args, **kwargs )



class transport:


    class Line:

        def __init__( self, handler ):
            self.handler = handler

        def __call__( self, env, socket ):
            self.handler\
                ( env
                , lambda: self._readlines( socket )
                , lambda data: socket.write( data+'\r\n' )
                )

        def _readlines( self, socket ):
            while True:
                line = socket.readline()
                if not line:
                    break
                yield line

    class HTTP:
        # TODO: client
        MessageClass = Message

        def __init__( self, handler, force_chunked=False, on_handler_fail=None ):
            self.handler = handler
            self.force_chunked = force_chunked
            self.on_handler_fail = on_handler_fail

        def __call__( self, env, socket ):
            env.setdefault( 'http', {} )

            env['http'] = env_http =\
                { 'request': { 'header': None }
                , 'response': { 'header': None }
                , 'is_header_send': False
                , 'is_header_read': False
                , 'is_handler_done': False
                , 'status': 200
                , 'force_chunked': self.force_chunked
                , '_write_disable': False
                }

            abort = False
            if 'remoteclient' in env:
                env_http['is_header_read'] = True
                env_http['mode'] = 'response'
                env_http['response']['header'] = []
                
                header = socket.readline()
                if not header:
                    return

                elif not self._read_request_header( env_http, socket, header ):
                    socket.write( _BAD_REQUEST_RESPONSE )
                    env_http['status'] = 400
                    abort = True
            else:
                env_http['mode'] = 'request'

            has_error = False
            if not abort:
                env_http['_read'] = read = lambda: self._read( env_http, socket )
                env_http['_write'] = write = lambda data: self._write( env_http, socket, data )
                try:
                    self.handler( env, read, write )
                except:
                    env_http['has_error'] = has_error = True
                    env_http['keepalive'] = False

                    if self.on_handler_fail:
                        try:
                            self.on_handler_fail( env, read, write )
                        except:
                            env_http['status'] = 500
                    else:
                        env_http['status'] = 500

            else:
                env_http['keepalive'] = False

            if has_error:
                log.exception('Could not handle HTTP request')

            self._finish_response( env, socket )

        def _finish_response( self, env, socket ):
            env_http = env['http']
            env_http['is_handler_done'] = True
            if not env_http['is_header_send']:
                self._write_nonchunked_response( env_http, socket )
            else:
                socket.write(  "0\r\n\r\n"  )

            if env_http['keepalive']:
                self( env, socket )

        def _write( self, env, socket, data ):
            if not isinstance( data, basestring ):
                raise Exception('Received non-text response: %s' % data )

            if not env['is_header_send']:
                if env['mode'] == 'response' and not env['force_chunked']:
                    # more than 1 write = chunked response
                    # TODO: set env['force_chunked'] when handler sets
                    # transfer-encoding header to chunked
                    if not 'result_on_hold' in env:
                        env['result_on_hold'] = data
                        return

                    self._send_headers( env, socket )

                    lastresult = env.pop('result_on_hold')
                    socket.write(  "%x\r\n%s\r\n" % (len(lastresult), lastresult) )
                else:
                    self._send_headers( env, socket )

            socket.write(  "%x\r\n%s\r\n" % (len(data), data) )

        def _read( self, env, socket ):
            if not env['is_header_read']:
                header = socket.readline()
                self._read_response_header( env, header )
                env['is_header_read'] = True

            if not env['content_length']:
                while True:
                    length = socket.readline()
                    if length == '0':
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
            log.error(err % (raw_requestline,) )

        def _read_request_header(self, env, socket, raw_requestline):

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

            log.debug("%s\n%s" % (headers.items(), env))
            env['request']['header'] = headers

            return True

        def _serialize_headers( self, env, socket):
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

            if not 'Content-Type' in response_headers_list:
                response_headers.append(('Content-Type', 'text/html; charset=UTF-8') )

            status_text = 'OK'
            towrite = [ '%s %s %s\r\n' % (env['request_version'], env['status'], status_text) ]
            for header in response_headers:
                towrite.append('%s: %s\r\n' % header)

            if keepalive is not None:
                env['keepalive'] = keepalive
                
            return ''.join(towrite)

        def _send_headers( self, env, socket ):
            socket.write( '%s\r\n' % self._serialize_headers( env, socket ) )
            env['is_header_send'] = True
            
        def _write_nonchunked_response( self, env, socket ):
            content = env.pop('result_on_hold','' )
            
            env['response']['header'].append(('Content-Length', str(len(content))))
            response = "%s\r\n%s"\
                %   ( self._serialize_headers( env, socket )
                    , content
                    )

            socket.write ( response )


class ConnectionPool:

    def __init__( self, socket, handler, create_env=lambda: {} ):
        self.socket = socket
        self.handler = handler
        self.create_env = create_env
        self.connections = set() # TODO the actual pool

    def __call__( self, *args, **kwargs ):
        socket = self.socket.connect()
        env = self.create_env()
        env.update\
            ( { 'socket': self.socket
              , 'localclient': { 'args': args, 'kwargs': kwargs, 'result': AsyncResult() } 
              }
            )

        spawn\
            ( self.handler
            , env
            , socket
            )
        
        return env['localclient']['result'].get()






def Listen( *args, **kwargs):
    l = Listener( *args, **kwargs )
    l.start()
    return l

class Listener:
    def __init__( self, socket, handler, create_env=None ):
        self.socket = socket
        self.handler = handler
        if not create_env:
            create_env = lambda: {}
        self.create_env = create_env

    def start( self ):
        self._disconnected = AsyncResult()
        self.connected = True
        for (connection,address) in self.socket.accept():
            spawn( self._handle_connection, connection, address )
        self.stop()

    def _handle_connection( self, connection, address ):
        try:
            env = self.create_env()
            env.update\
                ( remoteclient = { 'address':address }
                , socket = connection
                )

            self.handler( env, connection )
        except:
            log.exception( 'Could not handle connection at %s from %s' % (self.socket, address ) )
        finally:
            connection.close()
            
    def stop( self ):
        log.info('Stop listening at %s' % (self.socket.address,))
        # TODO: run some kind of hooks for a clear handler shutdown
        self.socket.close()

        self._disconnected.set(True)
        self.connected = False

    def wait_for_disconnect( self ):
        return self._disconnected.get()


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
            raise SyntaxError('%s is not a valid address ( (tcp://host[:port]|ipc://file) is required )' % address ) 
        ( protocol, host ) = m.groups()

    return ( protocol.lower(), host.lower(), port )


class Connection:

    def __init__( self, gsocket ):
        self.gsocket = gsocket
        self.rfile = gsocket.makefile()

        self.readline = self.rfile.readline
        self.read = self.rfile.read

        log.debug("incoming connection")

    def write( self, data ):
        self.rfile.write( data )
        self.rfile.flush()

    def close( self ):
        self.rfile.close()
        self.gsocket.close()


class Socket:
    # TODO: move user, group into ipc address query string
    def __init__( self, address, user=None, backlog=255 ):
        self.listeningsock = None
        self.address = address
        self.backlog = backlog
        self.user = user

        ( self.protocol, self.host, self.port ) = parseSocketAddress( self.address )

        if self.protocol not in ('ipc','tcp'):
            raise SyntaxError( 'Protocol %s not supported' % (self.protocol) )

    def connect( self ):
        if self.protocol == 'ipc':
            gsocket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            gsocket.connect( self.host )

        return Connection( gsocket )

    def accept( self ):

        if self.protocol == 'ipc':
            try:
                os.remove( self.host )
            except OSError:
                pass

            #s.bind( self.host )

            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                os.remove( self.host )
            except OSError:
                pass
                s.bind( self.host )
                os.chmod(self.host,0770)
                if self.user:
                    import pwd

                    pe = pwd.getpwnam( self.user )
                    os.chown(self.host, pe.pw_uid, pe.pw_gid)
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.host, self.port))

        s.listen( self.backlog )

        self.listeningsock = s

        log.info( "Listening on %s ..." % self.address )
        exec_count=0

        while True:
            try:
                (connection, addr)  = s.accept()
                yield (Connection( socket.socket(_sock=connection) ), addr )
            except:
                log.exception('Could not accept a connection...')
                sleep(0.5*exec_count)
                exec_count+=1
            else:
                exec_count=0



    def close( self ):
        if self.listeningsock:
            self.listeningsock.shutdown( socket.SHUT_RDWR )
            self.listeningsock = None

            if self.protocol == 'ipc':
                try:
                    os.remove( self.host )
                except OSError:
                    pass



class wsgi:
    class Server:
        def __init__( self, handler ):
            self.handler = handler

        def __call__( self, env, read, write ):
            write('wsgi stub at %s' % env['http']['path'] )


class http:
    class Method:
        def __init__( self, POST=None, GET=None, on_not_found=None ):
            self.handler = {}
            if POST:
                self.handler['POST'] = POST
            if GET:
                self.handler['GET'] = GET
            if not on_not_found:
                on_not_found = self._on_not_found
            self.on_not_found = on_not_found

        def __call__( self, env, read, write ):
            method = env['http']['method']
            handler = self.handler.get( method, None )
            if handler:
                handler( env, read, write )
            else:
                self._on_not_found( env, read, write )

        def _on_not_found( self, env, read, write ):
            raise _Env.NotFound( env['http']['method'] )

class marshal:

    class Json:
        def __init__( self, handler, loads=None, dumps=None):
            self.handler = handler
            self.loads = loads or jsonrpcio.loads
            self.dumps = dumps or jsonrpcio.dumps

        def __call__( self, env, read, write ):
            self.handler\
                ( env
                , lambda : ( self.loads( r ) for r in read() )
                , lambda data: write (self.dumps( data ) )
                )

class jsonrpc:

    @staticmethod
    def on_handler_fail( env, read, write ):
        write\
            ( env['rpc']['parser'].encodeError\
                ( env['rpc']['failure']
                , requestID=env['rpc']['requestID']
                )
            )

    class Server:

        def __init__( self, handler, on_handler_fail=None, loads=None, dumps=None ):
            self.handler = handler
            self._nowrite = lambda data: None
            if not on_handler_fail:
                on_handler_fail = jsonrpc.on_handler_fail
                
            self.on_handler_fail = on_handler_fail
            self.parser = jsonrpcio.Parser( loads=loads, dumps=dumps )

        def __call__( self, env, read, write ):
            env['rpc'] = {'type': 'jsonrpc'}

            for request in read():
                ( success
                , data
                , parser
                , isBatch
                ) = self.parser.decodeRequest( request )
                env['rpc']['isBatch'] = isBatch
                
                if not success:
                    write( data )
                    continue
                
                if isBatch:
                    for (partial, writeback) in data:
                        self._call_handler( env, partial, writeback, parser )

                    write( data.encode() )
                else:
                    if data['id'] is not None:
                        jsonwrite =\
                            lambda result: write\
                                ( parser.encodeResponse\
                                    ( { 'id': data['id']
                                      , 'result': result
                                      }
                                    )
                                )
                    else:
                        jsonwrite = self._nowrite

                    self._call_handler( env, data, jsonwrite, parser )


        def _call_handler( self, env, data, jsonwrite, parser ):
            env['rpc']['path'] = data['method']
            env['rpc']['requestID'] = data['id']
            env['rpc']['version'] = data['version']
        
            params = data['params']
            # jsonrpc supports either args or kwargs
            if isinstance(params,dict):
                kwargs = params
                args = ()
            else:
                kwargs = {}
                args = params

            jsonread = lambda: ((args,kwargs),)
            try:
                self.handler( env, jsonread, jsonwrite )
            except Exception as e:
                log.exception('Could not handle JSON-RPC request')
                env['rpc']['failure'] = e
                env['rpc']['parser'] = parser
                self.on_handler_fail( env, jsonread, jsonwrite )




"""

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


class rpc:
    class LongPoll:

        class Connection:
            def __init__( self, env, connections, handler, timeout ):
                self.ack_timeout = timeout
                self.connections = connections
                self.handler = handler
                self.server_event_queue = Queue()
                self.client_event_queue = Queue()
                self.ack_id = None
                self.env = deepcopydict( env )
                self._id = uuid().hex

                spawn( self._kill_idle )
                spawn\
                    ( self.handler
                    , self.env
                    , lambda: self.client_event_queue
                    , self.server_event_queue.put )


            def _check_next( self, confirm_ID ):
                result = self.server_event_queue.get()
                self.ack_id = confirm_ID
                self.current_result.set( (confirm_ID, result ) )
                self._kill_idle()

            def next( self, confirm_ID, current_ID ):
                if confirm_ID == self.ack_id:
                    self.ack_id = None
                    self.ack_done.set(True)
                    self.current_result = AsyncResult()
                    spawn( self._check_next, current_ID )

                return self.current_result.get( )

            def emit( self, event ):
                self.client_event_queue.put( event )

            def _kill_idle( self ):
                self.ack_done = AsyncResult()
                try:
                    self.ack_done.get( timeout=self.ack_timeout )
                except:
                    self.client_event_queue.put( StopIteration )
                    self.server_event_queue.put( StopIteration )
                    del self.connections[ self._id ]

        def __init__( self, handler, ack_timeout=20 ):
            self.handler = handler
            self.connections = {}
            self.ack_timeout = ack_timeout

        def connect( self, env, read, write ):
            for request in read():
                connection = self.Connection( env, self.connections, self.handler, self.ack_timeout )
                self.connections[ connection._id ] = connection
                write( (connection._id, self.ack_timeout) )

        def next( self, env, read, write ):
            current_ID = env['rpc']['requestID']
            for (args,kwargs) in read():
                (connection_ID,confirm_ID) = args
                connection = self.connections[connection_ID]

                result = connection.next( confirm_ID, current_ID )
                write( result )

        # should be sent as notification
        def emit( self, env, read, write ):
            for (args,kwargs) in read():
                (connection_ID,event) = args
                connection = self.connections[connection_ID]
                connection.emit( event )

class event:

    class _Channel( Queue ):
        class Closed( Exception ):
            def __init__( self ):
                Exception.__init__( self, 'Channel is closed' )

        is_open = True

        def __init__( self, name, write ):
            self.name = name
            self._write = write
            Queue.__init__( self )

        def emit( self, event ):
            if not self.is_open:
                raise self.Closed()

            self._write( {'channel': self.name, 'event': event } )


    class _ChannelConnector:
        def __init__( self, env, read, write ):
            self.env = env
            self.read = read
            self.write = write
            self.channels = {}

        def open( self, name ):
            channel = self.channels.get( name, None )
            if channel:
                return channel

            channel = event._Channel( name, self.write )
            self.channels[ name ] = channel
            return channel

        def _keepreading( self ):
            for message in self.read():
                channel = message['channel']
                channel = self.channels.get( channel, None )
                if channel:
                    channel.put( message['event'] )
                
            for channel in self.channels.itervalues():
                self.channel.is_open = False
                self.channel.put( StopIteration )

    class Client:
        def __call__( self, env, read, write ):
            client = event._ChannelConnector( env, read, write )
            env['localclient']['result'].set( client )
            client._keepreading()

    class Channel:

        def __init__( self, handlers ):
            self.handlers = handlers

        def __call__( self, env, read, write ):
            channels = {}
            for ( channel, handler) in self.handlers.iteritems():
                channels[ channel ] = event._Channel( channel, write )

            for ( channel, handler ) in self.handlers.iteritems():
                spawn( handler, env, channels[ channel ] )

            self._keepreading( read, channels )

        def _keepreading( self, read, channels ):
            for message in read():
                channel = message['channel']
                channels[ channel ].put( message['event'] )
                
            for channel in channels.itervalues():
                channel.is_open = False
                channel.put( StopIteration )


from inspect import isclass

class LazyResource:
    def __init__( self, module, config=None ):
        self.module = module
        self.loaded = {}
        self.config = config

    def __getattr__( self, name ):
        if not name in self.loaded:
            try:
                __import__('%s.%s' % (self.module.__name__, name) )

                value = LazyResource\
                    ( getattr( self.module, name )
                    , self.config
                    )

            except ImportError:
                value = getattr( self.module, name )
                if isclass( value ):
                    if self.config and hasattr(value, '__init__'):
                        value = value( self.config )
                    else:
                        value = value()

            self.loaded[ name ] = value

        return self.loaded[ name ]


class Farm:
    def __init__( self, *servers ):
        self.servers = servers

    def start( self ):
        jobs = []
        for server in self.servers:
            jobs.append( spawn( server.start ) )

        joinall( jobs )

    def stop( self ):
        for server in self.servers:
            server.stop()
