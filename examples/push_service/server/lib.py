from uuid import uuid4
from Cookie import Cookie
import logging

log = logging.getLogger( __name__ )
def get_session( env ):
    session = env.get\
        ( 'push_service.session'
        , Cookie(env['http']['request']['header']\
            .get('cookie')).get('push_service.session')
        )
    if session:
        session = session.value
    else:
        env['push_service.session'] = session = str(uuid4())
        env['http']['response']['header'].append\
                ( ('Set-Cookie','push_service.session=%s;' % session) )

    return session
        
