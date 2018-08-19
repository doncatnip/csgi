import logging

log = logging.getLogger(__name__)

class Line:

    def __init__( self, handler ):
        self.handler = handler

    def __call__( self, env, connection ):
        self.handler\
            ( env
            , lambda: self._readlines( connection )
            , lambda data: connection.write( data+'\r\n' ) and connection.flush()
            )

    def _readlines( self, socket ):
        while True:
            line = socket.readline()
            if not line:
                break
            yield line

