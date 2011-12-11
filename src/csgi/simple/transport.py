import logging

log = logging.getLogger(__name__)

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

