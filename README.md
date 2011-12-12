csgi - client/server gateway interface
======================================

I'm writing this, because im tired of the common practice today to
tightly couple the http transport into the wsgi servers and making various
bidirectional protocols dependand on wsgi - reducing their flexibility and
counteracting DRY.

WSGI really should be only a handler ontop of a HTTP transport. Also, i'd like
to be flexible when it comes to protocols. If i have some worker within my
app-network, reachable via unixsocket and one day i feel this is no more
good enough, i want to be able to hook these same resources up to some amqp
connector instead. Decorators and thelike are not helping here.

The idea goes as followes: find an wsgi-ish way to bubble a connection
( which eventually might become a request) from the very bottom ( the listener )
all the way up to some handler ( which could be a html page, or some
subscriber/publisher ). This architecture should work for client and server
implementations in a similar way.

Every transport receives ( env, connection ) per connection as arguments and
passes a read and write method to its handler while populating env with
transport-specific stuff.

read is a callable which returns a list or generator, write is a callable,
receiving one argument.

A request/connection is considered finished when its handler returns.

Components should be as independant as possible.

Status: prototype; License: Public Domain

Implemented so far:

* basic stuff: some socket/listen/connect abstraction, line transport \o/,
generic routing by env-variables, json marshalling, a daemon helper using
python-daemon

* http: transport, wsgi server, simple method hook (http.Method)

* rpc: jsonrpc server, longpoll interface

* events ( aka publish/subscribe ): channel interface - usable with json
marshalling ( e.g. via unix socket ) or jsonrpc longpolling so far

* +it should be quite easy to implement further protocols/transports.

Everything quite alpha, but take a look at examples/crude_demo if you still
want to know more.
