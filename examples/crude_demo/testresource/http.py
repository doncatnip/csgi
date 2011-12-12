def _404( env, read, write ):
    env['http']['status'] = 404
    write( '<html><body>404 - Not found</body></html>' )

def _500( env, read, write ):
    env['http']['status'] = 500
    write( '<html><body>500 - Internal server error </body></html>' )

class Hello:

    def __call__( self, env, read, write ):
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


