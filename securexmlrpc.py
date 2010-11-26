#!/usr/bin/env python

import SocketServer
import BaseHTTPServer
import SimpleHTTPServer
import SimpleXMLRPCServer
import socket, os



from OpenSSL import SSL
from threading import Event, currentThread, Thread, Condition
from thread import start_new_thread as start
from SimpleXMLRPCServer import SimpleXMLRPCRequestHandler, SimpleXMLRPCServer, SimpleXMLRPCDispatcher
from xmlrpclib import Binary


from logging import debug, info, warning, error

# static stuff
DEFAULTKEYFILE='cert/localhost-server.key.unsecure'    # Replace with your PEM formatted key file
DEFAULTCERTFILE='cert/localhost-server.crt'  # Replace with your PEM formatted certificate file
DEFAULTCAFILE='cert/rpc-ca.crt'  # Replace with your PEM formatted certificate file


class SecureXMLRPCRequestHandler(SimpleXMLRPCRequestHandler):
    """Secure Doc XML-RPC request handler class.
    It it very similar to DocXMLRPCRequestHandler but it uses HTTPS for transporting XML data.
    """
    def setup(self):
        self.connection = self.request
        self.rfile = socket._fileobject(self.request, "rb", self.rbufsize)
        self.wfile = socket._fileobject(self.request, "wb", self.wbufsize)

    def address_string(self):
        "getting 'FQDN' from host seems to stall on some ip addresses, so... just (quickly!) return raw host address"
        host, port = self.client_address
        #return socket.getfqdn(host)
        return host

    def do_POST(self):
        """Handles the HTTPS POST request.
        It was copied out from SimpleXMLRPCServer.py and modified to shutdown the socket cleanly.
        """
        try:
            # get arguments
            data = self.rfile.read(int(self.headers["content-length"]))
            # In previous versions of SimpleXMLRPCServer, _dispatch
            # could be overridden in this class, instead of in
            # SimpleXMLRPCDispatcher. To maintain backwards compatibility,
            # check to see if a subclass implements _dispatch and dispatch
            # using that method if present.
            response = self.server._marshaled_dispatch(data, getattr(self, '_dispatch', None))
        except: # This should only happen if the module is buggy
            # internal error, report as HTTP server error
            self.send_response(500)
            self.end_headers()
        else:
            # got a valid XML RPC response
            self.send_response(200)
            self.send_header("Content-type", "text/xml")
            self.send_header("Content-length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

            # shut down the connection
            self.wfile.flush()
            self.connection.shutdown() # Modified here!

    def report_404 (self):
        # Report a 404 error
        self.send_response(404)
        response = 'No such page'
        self.send_header("Content-type", "text/plain")
        self.send_header("Content-length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)
        # shut down the connection
        self.wfile.flush()
        self.connection.shutdown() # Modified here!

    def log_request (self, code = '-', size = '-'):
        info( '%s - %s' % (self.address_string(), self.requestline) )



class CustomThreadingMixIn:
    """Mix-in class to handle each request in a new thread."""
    # Decides how threads will act upon termination of the main process
    daemon_threads = True

    def process_request_thread(self, request, client_address):
        """Same as in BaseServer but as a thread.
        In addition, exception handling is done here.
        """
        try:
            self.finish_request(request, client_address)
            self.close_request(request)
        except (socket.error, SSL.SysCallError), why:
            error( 'socket.error finishing request from "%s"; Error: %s' %
                    (client_address, str(why)) )
            self.close_request(request)
        except:
            self.handle_error(request, client_address)
            self.close_request(request)

    def process_request(self, request, client_address):
        """Start a new thread to process the request."""
        t = Thread(target = self.process_request_thread, args = (request, client_address))
        if self.daemon_threads:
            t.setDaemon(1)
        t.start()



class SecureXMLRPCServer(CustomThreadingMixIn, SimpleXMLRPCServer):
    def __init__(self, registerInstance, server_address, keyFile=DEFAULTKEYFILE,
            certFile=DEFAULTCERTFILE, caFile = DEFAULTCAFILE, logRequests=True):
        """Secure Documenting XML-RPC server.
        It it very similar to DocXMLRPCServer but it uses HTTPS for transporting XML data.
        """
        SimpleXMLRPCServer.__init__(self, server_address, SecureXMLRPCRequestHandler, logRequests)
        self.logRequests = logRequests

        self.register_introspection_functions()

        # init stuff, handle different versions:
        try:
            SimpleXMLRPCDispatcher.__init__(self)
        except TypeError:
            # An exception is raised in Python 2.5 as the prototype of the __init__
            # method has changed and now has 3 arguments (self, allow_none, encoding)
            SimpleXMLRPCDispatcher.__init__(self, False, None)
        SocketServer.BaseServer.__init__(self, server_address, SecureXMLRPCRequestHandler)
        self.register_instance(registerInstance) # for some reason, have to register instance down here!

        # SSL socket stuff
        ctx = SSL.Context(SSL.SSLv23_METHOD)
        ctx.use_privatekey_file(keyFile)
        ctx.use_certificate_file(certFile)
        # verify
        ctx.load_verify_locations(caFile)
        ctx.set_verify(SSL.VERIFY_PEER|SSL.VERIFY_FAIL_IF_NO_PEER_CERT, self._verify)
        self.socket = SSL.Connection(ctx, socket.socket(self.address_family, self.socket_type))
        self.server_bind()
        self.server_activate()

        # requests count and condition, to allow for keyboard quit via CTL-C
        self.requests = 0
        self.rCondition = Condition()
    def _verify(self, connection, x509, errnum, errdepth, ok):
        debug( '_verify (ok=%d):' % ok)
        debug( '  subject: %s' % x509.get_subject())
        debug( '  issuer: %s' % x509.get_issuer())
        debug( '  errnum %s, errdepth %d' % (errnum, errdepth))
        return ok

    def startup(self):
        'run until quit signaled from keyboard...'
        info( 'server starting' )
        while True:
            try:
                self.rCondition.acquire()
                start(self.handle_request, ()) # we do this async, because handle_request blocks!
                while not self.requests:
                    self.rCondition.wait(timeout=3.0)
                if self.requests: self.requests -= 1
                self.rCondition.release()
            except KeyboardInterrupt:
                warning( "quit signaled, i'm done." )
                return

    def get_request(self):
        request, client_address = self.socket.accept()
        self.rCondition.acquire()
        self.requests += 1
        self.rCondition.notifyAll()
        self.rCondition.release()
        return (request, client_address)

    def listMethods(self):
        'return list of method names (strings)'
        methodNames = self.funcs.keys()
        methodNames.sort()
        return methodNames

    def methodHelp(self, methodName):
        'method help'
        if methodName in self.funcs:
            return self.funcs[methodName].__doc__
        else:
            raise Exception('method "%s" is not supported' % methodName)

