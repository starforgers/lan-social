"""
Final fixed peer.py with working broadcast communication
"""

import socket
import threading
import time
from protocol import ProtocolHandler

class peer:
    def __init__(self, ip=None, port=50999, broadcast=True, verbose: bool = False):
        self.requested_ip = ip  # Store the requested IP
        self.port = port
        self.verbose = verbose
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Set socket options for better network behavior
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Enable broadcast if needed
        if broadcast:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        # Set a reasonable timeout to prevent blocking
        self.sock.settimeout(1.0)

        # For broadcast to work properly, we need to bind to 0.0.0.0 (all interfaces)
        # but we'll report the requested IP in get_effective_ip()
        self.bind_ip = "0.0.0.0"  # Always bind to all interfaces for broadcast
        self.effective_ip = ip or self._get_local_ip()  # IP to report in user_id
        
        try:
            self.sock.bind((self.bind_ip, self.port))
            if self.verbose:
                print(f"Successfully bound to {self.bind_ip}:{self.port} (effective IP: {self.effective_ip})")
        except OSError as e:
            if self.verbose:
                print(f"Error binding to {self.bind_ip}:{self.port} - {e}")
            raise
        
        # For compatibility with existing code
        self.ip = self.bind_ip
        
        self.running = False
        
        # Single broadcast target per spec (limited broadcast). Drop extra ports.
        self.broadcast_ip = "255.255.255.255"

    def _get_local_ip(self):
        """Get the local IP address more reliably."""
        try:
            # Method 1: Connect to remote address
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            try:
                # Method 2: Use hostname
                hostname = socket.gethostname()
                return socket.gethostbyname(hostname)
            except:
                return "127.0.0.1"
    
    def _get_broadcast_address(self):
        """Preserved for backward compatibility (class C style)."""
        if self.effective_ip == "127.0.0.1":
            return "127.255.255.255"
        try:
            parts = self.effective_ip.split('.')
            return f"{parts[0]}.{parts[1]}.{parts[2]}.255"
        except:
            return "255.255.255.255"
    
    def get_effective_ip(self):
        """Get the IP that should be used in user_id."""
        return self.effective_ip

    def send(self, message: str, target_ip="255.255.255.255", target_port=None):
        """Send a message as plaintext to a target IP."""
        if not self.running:
            return
            
        if target_port is None:
            target_port = self.port
        if not message.endswith("\n\n"):
            message += "\n\n"
        
        try:
            if target_ip == "255.255.255.255":
                # Single broadcast as per spec: always port 50999
                self.sock.sendto(message.encode('utf-8'), (self.broadcast_ip, 50999))
            else:
                self.sock.sendto(message.encode('utf-8'), (target_ip, target_port))
        except socket.error as e:
            if self.running and self.verbose:
                print(f"[Send error to {target_ip}:{target_port}] {e}")

    def send_message(self, target_ip="255.255.255.255", target_port=None, **kwargs):
        """Send a formatted message according to the protocol."""
        if not self.running:
            return
            
        message = ProtocolHandler.format_message(**kwargs)
        
        # Handle broadcast vs unicast differently
        try:
            if target_ip == "255.255.255.255":
                # Broadcast strictly to 255.255.255.255:50999 per spec
                self.sock.sendto(message.encode('utf-8'), (self.broadcast_ip, 50999))
            else:
                # This is unicast - send to specific target
                if target_port is None:
                    target_port = self.port
                self.sock.sendto(message.encode('utf-8'), (target_ip, target_port))
        except socket.error as e:
            if self.running and self.verbose:
                if target_ip == "255.255.255.255":
                    print(f"[Broadcast error] {e}")
                else:
                    print(f"[Unicast error to {target_ip}:{target_port}] {e}")
    
    def receive_loop(self, callback):
        """Continuously listen for incoming UDP messages and run callback."""
        self.running = True

        def listen():
            if self.verbose:
                print(f"Starting receive loop on {self.bind_ip}:{self.port} (effective: {self.effective_ip})")
            while self.running:
                try:
                    data, addr = self.sock.recvfrom(65535)
                    try:
                        message = data.decode('utf-8')
                    except UnicodeDecodeError:
                        continue
                        
                    # Only process messages that look like LSNP format
                    if not message.endswith('\n\n'):
                        continue
                        
                    # Parse the message and pass both raw and parsed versions to callback
                    parsed_message = ProtocolHandler.parse_message(message)
                    callback(message, parsed_message, addr)
                except socket.timeout:
                    continue
                except socket.error as e:
                    if self.running:
                        if self.verbose:
                            print(f"[Socket error] {e}")
                        continue
                    else:
                        break
                except Exception as e:
                    if self.running:
                        if self.verbose:
                            print(f"[Error in receive_loop] {e}")
                        continue
                    else:
                        break

        thread = threading.Thread(target=listen, daemon=True, name="PeerReceiver")
        thread.start()

    def stop(self):
        """Stop the peer and close the socket properly."""
        self.running = False
        try:
            self.sock.close()
        except:
            pass

    def is_running(self):
        """Check if the peer is currently running."""
        return self.running