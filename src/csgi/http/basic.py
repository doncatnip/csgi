from ..core import Env

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
        raise Env.NotFound( env['http']['method'] )
