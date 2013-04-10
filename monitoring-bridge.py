#!/usr/bin/env python

import time
import json
import optparse

import bottle

import bernhard

# Parse command line arguments
parser = optparse.OptionParser()
parser.add_option("--riemann-host", dest="riemann_host", default="localhost", help="Host that Riemann is running on")
parser.add_option("--riemann-port", dest="riemann_port", default=5555, help="Port that Riemann is running on")
parser.add_option("--foreground", dest="foreground", action='store_true', default=False, help="Don't daemonize.")
parser.add_option("--debug", dest="debug", action='store_true', default=False, help="Increase logger verbosity")
(options, args) = parser.parse_args()

riemann = bernhard.Client(host=options.riemann_host, port=options.riemann_port, transport=bernhard.TCPTransport)

bridge = bottle.Bottle()

@bridge.get('/ping')
def ping():
	event = {}
	event['service'] = 'monitoring-bridge'
	event['state'] = 'ok'
	event['description'] = 'HTTP to Riemann Bridge'
	event['ttl'] = 600
	event['host'] = 'http_pinger'
	event['tags'] = ['nonotify']

	riemann.send(event)

	results = riemann.query("'(service = \"monitoring-bridge\")'")

	response = {'event_age': time.time() - results[0].event.time}
	
	for field in event.keys():
		response[field] = str(getattr(results[0], field))
	
	return json.dumps(response, ensure_ascii=False)

bridge.run(host='localhost', port=8080, debug=True, reloader=True)