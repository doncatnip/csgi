class Server:
    def __init__( self, handler ):
        self.handler = handler

    def __call__( self, env, read, write ):
        write('wsgi stub at %s' % env['http']['path'] )

