from . import jsonrpcio

import logging

log = logging.getLogger( __name__ )

def _on_handler_fail( env, read, write ):
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
            on_handler_fail = _on_handler_fail
            
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

                self._call_handler( env, data, jsonwrite, write, parser )


    def _call_handler( self, env, data, jsonwrite, write, parser ):
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
            self.on_handler_fail( env, jsonread, write )




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

