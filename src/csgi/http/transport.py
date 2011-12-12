from gevent.pywsgi import _BAD_REQUEST_RESPONSE, _CONTINUE_RESPONSE, MAX_REQUEST_LINE, format_date_time
from mimetools import Message
from urllib import unquote

import time, logging



class Transport:
    # TODO: client
    MessageClass = Message
    log = logging.getLogger( '%s.HTTP' % __name__ )

    def __init__( self, handler, force_chunked=False, on_handler_fail=None ):
        self.handler = handler
        self.force_chunked = force_chunked
        self.on_handler_fail = on_handler_fail

    def __call__( self, env, connection ):
        env.setdefault( 'http', {} )

        env['http'] = env_http =\
            { 'request': { 'header': None }
            , 'response': { 'header': None }
            , 'is_header_send': False
            , 'is_header_read': False
            , 'is_handler_done': False
            , 'status': '200 OK'
            , 'force_chunked': self.force_chunked
            , '_write_disable': False
            }

        abort = False
        if 'remoteclient' in env:
            env_http['is_header_read'] = True
            env_http['mode'] = 'response'
            env_http['response']['header'] = []
            
            header = connection.readline( MAX_REQUEST_LINE )
            if not header:
                return

            elif not self._read_request_header( env_http, connection, header ):
                connection.write( _BAD_REQUEST_RESPONSE )
                connection.flush()
                return
        else:
            env_http['mode'] = 'request'

        has_error = False
        if not abort:
            env_http['_read'] = read = lambda: self._read( env_http, connection )
            env_http['_write'] = write = lambda data: self._write( env_http, connection, data )
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
            self.log.exception('Could not handle HTTP request')

        self._finish_response( env, connection )

    def _finish_response( self, env, connection ):
        env_http = env['http']
        env_http['is_handler_done'] = True
        if not env_http['is_header_send']:
            self._write_nonchunked_response( env_http, connection )
        else:
            connection.write(  "0\r\n\r\n"  )
            connection.flush()

        if env_http['keepalive']:
            self( env, connection )

    def _write( self, env, connection, data ):
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

                self._send_headers( env, connection )

                lastresult = env.pop('result_on_hold')
                connection.write(  "%x\r\n%s\r\n" % (len(lastresult), lastresult) )
            else:
                self._send_headers( env, connection )

        connection.write(  "%x\r\n%s\r\n" % (len(data), data) )
        connection.flush()

    def _read( self, env, connection ):
        if not env['is_header_read']:
            header = connection.readline()
            self._read_response_header( env, header )
            env['is_header_read'] = True
        if env['continue']:
            connection.write( _CONTINUE_RESPONSE )
            connection.flush()

        if not env['content_length']:
            while True:
                length = connection.readline()
                if length == '0':
                    return
                data = connection.read( int( length,16 ) )
                if not data or len(data)!=length:
                    raise IOError("unexpected end of file while parsing chunked data")
                yield data
        else:
            data = connection.read( env['content_length'] )
            if not data or len(data)!=env['content_length']:
                raise IOError("unexpected end of file while parsing chunked data")
            yield data

    def _check_http_version(self, version):
        if not version.startswith("HTTP/"):
            return False
        version = tuple(int(x) for x in version[5:].split("."))  # "HTTP/"
        if version[1] < 0 or version < (0, 9) or version >= (2, 0):
            return False
        
        return True

    def _log_error( self, err, raw_requestline=''):
        self.log.error(err % (raw_requestline,) )

    def _read_request_header(self, env, connection, raw_requestline):

        requestline = raw_requestline.rstrip()
        words = requestline.split()
        if len(words) == 3:
            command, path, request_version = words
            if not self._check_http_version( request_version ):
                self._log_error('Invalid http version: %r', raw_requestline)
                return

        elif len(words) == 2:
            command, path = words
            if command != "GET":
                self._log_error('Expected GET method: %r', raw_requestline)
                return

            request_version = "HTTP/0.9"
            # QQQ I'm pretty sure we can drop support for HTTP/0.9
        else:
            self._log_error('Invalid HTTP method: %r', raw_requestline)
            return

        headers = self.MessageClass( connection, 0)
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

        if '?' in path:
            path, query = path.split('?', 1)
        else:
            path, query = path, ''
        
        env.update\
            ( method=command
            , content_length=content_length
            , keepalive=not close_connection
            , request_version = request_version
            , path=unquote( path )
            , query=query
            )

        env['continue']=headers.get("expect",'').lower()=="continue"
        env['request']['header'] = headers

        self.log.debug("%s\n%s" % (headers.items(), env))
        return True

    def _serialize_headers( self, env, connection):
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

        status = env['status']
        if isinstance( status, int ):
            code = ''
        elif ' ' in status:
            status, code = status.split(' ',1)
            status = int(status)
        else:
            code, status  = '', int( status )

        if env['status'] not in [204, 304]:
            # the reply will include message-body; make sure we have either Content-Length or chunked
            if 'Content-Length' not in response_headers_list:
                if env['request_version'] != 'HTTP/1.0':
                    response_headers.append(('Transfer-Encoding', 'chunked'))

        if not 'Content-Type' in response_headers_list:
            response_headers.append(('Content-Type', 'text/html; charset=UTF-8') )

        towrite = [ '%s %s %s\r\n' % (env['request_version'], status, code ) ]
        for header in response_headers:
            towrite.append('%s: %s\r\n' % header)

        if keepalive is not None:
            env['keepalive'] = keepalive
            
        return ''.join(towrite)

    def _send_headers( self, env, connection ):
        connection.write( '%s\r\n' % self._serialize_headers( env, connection ) )
        env['is_header_send'] = True
        
    def _write_nonchunked_response( self, env, connection ):
        content = env.pop('result_on_hold','' )
        
        env['response']['header'].append(('Content-Length', str(len(content))))
        response = "%s\r\n%s"\
            %   ( self._serialize_headers( env, connection )
                , content
                )

        connection.flush()
        connection.write ( response )
