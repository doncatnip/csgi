from .. import jsonrpcio

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
