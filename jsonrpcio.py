import logging
import json
import datetime

log = logging.getLogger(__name__)

JSONRPC_VERSION_1_0 = "1.0"     # http://groups.google.com/group/json-rpc/web/json-1-0-spec
JSONRPC_VERSION_2_0 = "2.0"     # http://groups.google.com/group/json-rpc/web/json-rpc-2-0

# TODO: not supported yet
# JSONRPC_VERSION_1_1 = "1.1"   # http://groups.google.com/group/json-rpc/web/json-rpc-1-1-wd

class Undefined:
    pass

class Unknown:
    pass





class JSONRPC_BaseError( BaseException ):
    extra = {}

    def __init__( self, message=None, code=None, extra=None, version=Undefined ):
        self.version = version

        if code is not None:
            self.code = code
        if message is not None:
            self.message = message
        if extra is not None:
            self.extra = extra


class JSONRPCProtocol_Error( JSONRPC_BaseError ):
    code = -32603
    message = "JSON-RPC protocol error"

class JSONRPCProtocol_UnexpectedError( JSONRPCProtocol_Error ):
    code = -32603
    message = "Unexpected server error"

class JSONRPCProtocol_ParseError( JSONRPCProtocol_Error ):
    code = -32700
    message = "JSON-RPC parse error"

class JSONRPCProtocol_EncodeError( JSONRPCProtocol_ParseError ):
    message = "Cannot encode response to JSON"

class JSONRPCProtocol_DecodeError( JSONRPCProtocol_ParseError ):
    message = "Cannot decode request from JSON"

class JSONRPCProtocol_MethodNotFound( JSONRPCProtocol_Error ):
    code = -32601
    message = "Method not found"


class JSONRPCProtocol_UnknownVersion( JSONRPCProtocol_Error ):
    code = -32000
    message = "Unknown JSON-RPC version"

class JSONRPCProtocol_ResourceNotFound( JSONRPCProtocol_Error ):
    code = -32001
    message = "Resource not found"

class JSONRPCProtocol_FeatureNotSupported( JSONRPCProtocol_Error ):
    code = -32002
    message = "Feature not supported"


class JSONRPCApplication_Error( JSONRPC_BaseError ):
    code = 100
    message = "Application error"
    exception = None

class JSONRPCApplication_UnexpectedError( JSONRPCApplication_Error ):
    code = 999
    message = "Unexpected application error"



def defaultErrorConstructor( exceptionObj ):
    extra = dict(exceptionObj.extra)
    return (exceptionObj.code, exceptionObj.message, extra )


class JSONDateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        else:
            return json.JSONEncoder.default(self, obj)

def datetime_decoder(d):
    if isinstance(d, list):
        pairs = enumerate(d)
    elif isinstance(d, dict):
        pairs = d.items()
    result = []
    for k,v in pairs:
        if isinstance(v, basestring):
            try:
                # The %f format code is only supported in Python >= 2.6.
                # For Python <= 2.5 strip off microseconds
                # v = datetime.datetime.strptime(v.rsplit('.', 1)[0],
                #     '%Y-%m-%dT%H:%M:%S')
                v = datetime.datetime.strptime(v, '%Y-%m-%dT%H:%M:%S.%f')
            except ValueError:
                try:
                    v = datetime.datetime.strptime(v, '%Y-%m-%d').date()
                except ValueError:
                    pass
        elif isinstance(v, (dict, list)):
            v = datetime_decoder(v)
        result.append((k, v))
    if isinstance(d, list):
        return [x[1] for x in result]
    elif isinstance(d, dict):
        return dict(result)


class Parser:

    @classmethod
    def decodeRequest\
            ( klass
            , body
            , errorConstructor=defaultErrorConstructor
            , extra=None
            ):

        protocolError = Undefined
        result = Undefined
        if extra is None:
            extra = {}

        success = True
        try:
            parsed = klass.decode( body )
        except JSONRPCProtocol_Error as e:
            protocolError = e
        else:
            for parser in PARSERS:
                log.debug("trying %s" % parser.version)
                try:
                    (success,result,isBatch) = parser.decodeRequest\
                        ( parsed
                        , errorConstructor
                        , extra
                        )
                    protocolError = Undefined
                    log.debug('done')
                    break
                except JSONRPCProtocol_Error as e:
                    log.debug('protocol error (%s) , trying next ...' % e.message)
                    protocolError = e
                except Exception as e:
                    protocolError = JSONRPCProtocol_UnexpectedError()
                    break

        if protocolError is not Undefined:
            parser = parser or PARSERS[0]
            success = False
            result =  parser.constructError\
                ( protocolError
                , errorConstructor
                )

        return ( success, result, parser, False )

    @classmethod
    def encode( klass, response ):
        try:
            return json.dumps(response, cls=JSONDateTimeEncoder)
        except (TypeError,ValueError):
            raise JSONRPCProtocol_EncodeError()

    @classmethod
    def decode( klass, body ):
        try:
            return json.loads(body, object_hook=datetime_decoder)
        except (TypeError,ValueError):
            raise JSONRPCProtocol_DecodeError( )


decodeRequest = Parser.decodeRequest

class _1_0(Parser):

    version = JSONRPC_VERSION_1_0

    @classmethod
    def constructError( klass, exceptionObj, errorConstructor, **requestInfo ):
        if not isinstance( exceptionObj, JSONRPC_BaseError ):
            exception = exceptionObj
            exceptionObj = JSONRPCApplication_UnexpectedError()
            exceptionObj.exception = exception

        exceptionObj.version = klass.version
        requestID = requestInfo.get( 'requestID',Unknown )

        try:
            return klass.encodeError\
                ( requestID, *errorConstructor( exceptionObj ) )
        except JSONRPCProtocol_EncodeError as e:
            return klass.encodeError\
                ( requestID, *errorConstructor( e ) )




    @classmethod
    def encodeError( klass, requestID, code, message, extra=None  ):
        if requestID is None: # is a notification
            return None
        if requestID is Unknown:
            requestID = None

        error = {'code':code, 'message':message }
        if isinstance(extra,dict):
            error['error'] = extra
        return klass.encode( {'result':None, 'id':requestID, 'error': error } )

    @classmethod
    def encodeResult( klass, result ):
        requestID = result.get('id',None)
        if requestID is None: # is a notification
            return None
        return klass.encode( {'result':result['result'],'id':requestID, 'error': None } )

    @classmethod
    def decodeRequest\
            ( klass
            , parsed
            , errorConstructor
            , extra
            ):

        if not isinstance( parsed, dict ):
            raise JSONRPCProtocol_ParseError\
                ( "JSON root must be an Object"
                )

        parsed = dict(parsed)
        requestID = parsed.pop('id', Undefined)
        method = parsed.pop('method', Undefined)
        params = parsed.pop('params', Undefined)

        if Undefined in ( requestID, method, params ):
            raise JSONRPCProtocol_ParseError\
                ( "Members 'id','method' and 'params' are required"
                )

        if parsed:
            raise JSONRPCProtocol_ParseError\
                ( "Too many fields received"
                )

        # from now on we can be sure its a 1.0 request
        # so render everything as 1.0 response ( no raise )

        if not isinstance( method, basestring ):
            return\
                ( False
                , klass.constructError\
                    ( JSONRPCProtocol_ParseError\
                        ( "'method' must be a String"
                        )
                    , errorConstructor
                    , requestID=requestID
                    )
                , False
                )

        if not isinstance( params, list ):
            return\
                ( False
                , klass.constructError\
                    ( JSONRPCProtocol_ParseError\
                        ( "'params' must be an Array"
                        )
                    , errorConstructor
                    , requestID=requestID
                    )
                )
        result =\
            { 'method': method
            , 'params': params
            , 'version': klass.version
            }
        if requestID is not Undefined:
            result['id'] = requestID

        return\
            ( True
            , result
            , False
            )

    @classmethod
    def encodeResponse( klass, result, errorConstructor=None ):
        try:
            return klass.encodeResult( result )
        except JSONRPCProtocol_EncodeError as e:
            return klass.constructError\
                ( e
                , errorConstructor
                , requestID=result.get( 'requestID',Unknown )
                )




class _2_0(_1_0):
    version = JSONRPC_VERSION_2_0

    @classmethod
    def encodeError( klass, requestID, code, message, extra=None  ):
        if requestID is Undefined:
            # is a notification
            return None

        if requestID is Unknown:
            requestID = None

        error = {'code':code, 'message':message }

        if isinstance(extra,dict):
            error['data'] = extra

        return klass.encode( {'id':requestID, 'error': error, 'jsonrpc': klass.version } )

    @classmethod
    def encodeResult( klass, result ):
        requestID = result.get('id',None)
        if requestID is None:
            return None

        return klass.encode(  {'id': result['id'], 'result':result['result'], 'jsonrpc': klass.version } )
 
    @classmethod
    def decodeRequest\
            ( klass
            , parsed
            , errorConstructor
            , extra
            ):

        if isinstance( parsed, list ):
            raise JSONRPCProtocol_FeatureNotSupported\
                ( "Batched requests are not supported yet"
                )

        if not isinstance( parsed, dict ):
            raise JSONRPCProtocol_ParseError\
                ( "JSON root must be an Object"
                )

        parsed = dict(parsed)

        requestID = parsed.pop('id', Undefined)
        version = parsed.pop('jsonrpc', Undefined)
        method = parsed.pop('method', Undefined)
        params = parsed.pop('params', Undefined)

        if Undefined in ( method, params, version ):
            raise JSONRPCProtocol_ParseError\
                ( "Members 'jsonrpc', 'method' and 'params' are required"
                )

        if parsed:
            raise JSONRPCProtocol_ParseError\
                ( "Too many fields received"
                )

        if version != klass.version:
            raise JSONRPCProtocol_UnknownVersion\
                ( "Invalid JSON-RPC Version specified"
                , extra={'version':version}
                )

        # from now on we can be sure its a 2.0 request
        # so render everything as 2.0 response ( no raise )

        if not isinstance( method, basestring ):
            return klass.constructError\
                ( JSONRPCProtocol_ParseError\
                    ( "'method' must be a String"
                    )
                , errorConstructor
                , requestID=requestID
                )

        if not isinstance( params, (list,dict) ):
            return klass.constructError\
                ( JSONRPCProtocol_ParseError\
                    ( "'params' must be an array or dict"
                    )
                , errorConstructor
                , requestID=requestID
                )

        result =\
            { 'method': method
            , 'params': params
            , 'version': klass.version
            }
        if requestID is not Undefined:
            result['id'] = requestID

        return\
            ( True
            , result
            , False
            )

PARSERS = \
    ( _2_0
    , _1_0
    )



