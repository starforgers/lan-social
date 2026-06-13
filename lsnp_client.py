"""
LSNP (Lightweight Social Networking Protocol) Client Implementation
Clean version with minimal output - Based on the LSNP RFC specification.
"""

import threading
import time
import base64
import random
import argparse
import os
import signal
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from peer import peer
from protocol import ProtocolHandler
from message_handler import MessageHandler
from token_manager import TokenManager
from game_manager import GameManager
from file_manager import FileManager
from verbose_logger import VerboseLogger


class LSNPClient:
    """Main LSNP client implementation."""
    
    def __init__(self, username: str, ip: str = None, port: int = 50999, verbose: bool = False):
        """Initialize the LSNP client."""
        self.username = username
        self.port = port
        self.verbose = verbose
        
        # Initialize verbose logger
        self.logger = VerboseLogger()
        if verbose:
            self.logger.enable()
        
        # Initialize peer first to determine actual binding
        self.peer = peer(ip=ip, port=port, broadcast=True)
        
        # Use the effective IP from peer (what we actually bound to)
        self.ip = self.peer.get_effective_ip()
        self.user_id = f"{username}@{self.ip}"
        
        # Initialize components AFTER user_id is set
        self.message_handler = MessageHandler(self)
        self.token_manager = TokenManager(self.user_id, self.logger)
        self.file_manager = FileManager(self)
        self.game_manager = GameManager(self)
        
        # Test logger connection in verbose mode
        if verbose and self.logger.is_enabled():
            self.logger.log_info("LSNP Client components initialized", {
                "user_id": self.user_id,
                "verbose_mode": True,
                "token_manager_logger": "connected" if self.token_manager.logger else "not connected"
            })
        
        # State management
        self.display_name = username
        self.status = "Online"
        self.avatar_data = None
        self.avatar_type = None
        
        # Social graph
        self.followers = set()
        self.following = set()
        self.known_peers = {}  # user_id -> peer_info
        self.posts = []  # Store received posts
        self.dms = []  # Store received DMs
        
        # Group management
        self.groups = {}  # group_id -> group_info
        
        # Periodic tasks
        self.last_ping_time = 0
        self.ping_interval = 300  # 5 minutes
        
        # Running flag
        self.running = False
    
    def start(self):
        """Start the LSNP client."""
        self.running = True
        
        # Start receiving messages
        self.peer.receive_loop(self._handle_incoming_message)
        
        # Start periodic tasks
        self._start_periodic_tasks()
        
        # Send initial discovery sequence
        self.last_ping_time = time.time()  # Update ping time to prevent immediate periodic ping
        time.sleep(0.5)
        self.broadcast_profile()
        
        if self.verbose:
            self._log(f"LSNP Client started: {self.user_id}")
        
    def stop(self):
        """Stop the LSNP client."""
        self.running = False
        
        # Shutdown game manager gracefully
        if hasattr(self, 'game_manager'):
            self.game_manager.shutdown()
        
        # Stop peer networking
        self.peer.stop()
        
        # Shutdown verbose logger
        if self.verbose:
            self._log("LSNP Client stopped")
            self.logger.shutdown()
    
    def _start_periodic_tasks(self):
        """Start periodic background tasks."""
        def periodic_worker():
            while self.running:
                current_time = time.time()
                
                # Send PING every 5 minutes
                if current_time - self.last_ping_time >= self.ping_interval:
                    self.send_ping()
                    self.last_ping_time = current_time
                
                # Clean up expired tokens
                self.token_manager.cleanup_expired_tokens()
                
                time.sleep(10)  # Check every 10 seconds
        
        thread = threading.Thread(target=periodic_worker, daemon=True)
        thread.start()
    
    def _handle_incoming_message(self, raw_message: str, parsed_message: Dict, addr: Tuple[str, int]):
        """Handle incoming messages."""
        sender_ip = addr[0]
        sender_port = addr[1]
        message_type = parsed_message.get('TYPE', 'UNKNOWN')
        
        # Validate message format
        if not ProtocolHandler.validate_message(raw_message):
            if self.verbose:
                print(f"[DEBUG] Invalid LSNP message format from {sender_ip}:{sender_port}")
            return
        
        # Check for self-messages (don't process our own messages)
        from_user = parsed_message.get('FROM', parsed_message.get('USER_ID', ''))
        if from_user == self.user_id:
            return
        
        if self.verbose:
            # Log full message content for debugging, but respect privacy rules
            from_user = parsed_message.get('FROM', parsed_message.get('USER_ID', ''))
            
            # For POST messages, only log if we're allowed to see them
            if message_type == 'POST':
                user_id = parsed_message.get('USER_ID')
                # Only log posts from users we follow or our own posts
                if user_id in self.following or user_id == self.user_id:
                    self.logger.log_receive(parsed_message, f"{from_user} ({sender_ip}:{sender_port})")
                # Don't log posts from users we don't follow
            else:
                # For all other message types, log normally
                self.logger.log_receive(parsed_message, f"{from_user} ({sender_ip}:{sender_port})")
        
        # Handle the message based on type
        try:
            self.message_handler.handle_message(parsed_message, sender_ip)
        except Exception as e:
            if self.verbose:
                self.logger.log_error(f"Error handling message", {"error": str(e), "message_type": message_type})
                import traceback
                traceback.print_exc()
    
    def _log(self, message: str):
        """Log a message with timestamp."""
        if self.verbose:
            self.logger.log_info(message)
        else:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] {message}")

    # Core messaging methods
    def send_ping(self):
        """Send a PING message."""
        message_data = {
            "TYPE": "PING",
            "USER_ID": self.user_id
        }
        self.peer.send_message(**message_data)
        if self.verbose:
            self.logger.log_send(message_data)
    
    def broadcast_profile(self):
        """Broadcast user profile."""
        message_data = {
            "TYPE": "PROFILE",
            "USER_ID": self.user_id,
            "DISPLAY_NAME": self.display_name,
            "STATUS": self.status
        }
        
        # Add avatar if available
        if self.avatar_data and self.avatar_type:
            message_data.update({
                "AVATAR_TYPE": self.avatar_type,
                "AVATAR_ENCODING": "base64",
                "AVATAR_DATA": self.avatar_data
            })
        
        self.peer.send_message(**message_data)
        if self.verbose:
            self.logger.log_send(message_data)
    
    def send_post(self, content: str, ttl: int = 3600):
        """Send a public post."""
        token = self.token_manager.generate_token("broadcast", ttl)
        message_id = self._generate_message_id()
        timestamp = int(time.time())
        
        message_data = {
            "TYPE": "POST",
            "USER_ID": self.user_id,
            "CONTENT": content,
            "TTL": str(ttl),
            "MESSAGE_ID": message_id,
            "TIMESTAMP": str(timestamp),
            "TOKEN": token
        }
        
        # Store our own post locally (since we filter out our own messages in handler)
        post_data = {
            'user_id': self.user_id,
            'content': content,
            'timestamp': timestamp,
            'message_id': message_id,
            'likes': set(),  # Set of user_ids who liked this post
            'like_count': 0  # Count of likes for easy access
        }
        self.posts.append(post_data)
        
        self.peer.send_message(**message_data)
        if self.verbose:
            self.logger.log_send(message_data)
        print(f"Posted: {content}")
    
    def send_dm(self, target_user: str, content: str, ttl: int = 3600):
        """Send a direct message with proper port handling."""
        target_ip = self._get_peer_ip(target_user)
        if not target_ip:
            print(f"Cannot determine IP for user: {target_user}")
            return
        
        # Try different ports that the target might be listening on
        target_ports = [50999, 51000, 51001, 51002]  # Common LSNP ports
        
        token = self.token_manager.generate_token("chat", ttl)
        message_id = self._generate_message_id()
        
        message_data = {
            "TYPE": "DM",
            "FROM": self.user_id,
            "TO": target_user,
            "CONTENT": content,
            "TIMESTAMP": str(int(time.time())),
            "MESSAGE_ID": message_id,
            "TOKEN": token
        }
        
        # Send to multiple ports to ensure delivery
        sent_count = 0
        for port in target_ports:
            try:
                self.peer.sock.sendto(
                    ProtocolHandler.format_message(**message_data).encode('utf-8'),
                    (target_ip, port)
                )
                sent_count += 1
            except Exception as e:
                if self.verbose:
                    self.logger.log_error(f"Failed to send DM to {target_ip}:{port}", {"error": str(e)})
        
        if self.verbose:
            self.logger.log_send(message_data, f"{target_user} ({target_ip})")
        
        if sent_count > 0:
            # Store the sent DM
            dm_data = {
                'from_user': self.user_id,
                'to_user': target_user,
                'content': content,
                'timestamp': int(time.time()),
                'message_id': message_id
            }
            self.dms.append(dm_data)
            
            target_name = self.known_peers.get(target_user, {}).get('display_name', target_user.split('@')[0])
            print(f"Sent DM to {target_name}: {content}")
        else:
            print(f"Failed to send DM to {target_user}")
    
    def follow_user(self, target_user: str, ttl: int = 3600):
        """Follow a user."""
        # Clean the target_user input to prevent any corruption
        target_user = target_user.strip()
        
        # Normalize target_user to full user_id format
        if '@' not in target_user:
            # User provided just a display name, find the full user_id
            full_user_id = None
            for user_id, peer_info in self.known_peers.items():
                if peer_info.get('display_name', '').lower() == target_user.lower():
                    full_user_id = user_id
                    break
            
            if not full_user_id:
                print(f"Cannot find user '{target_user}'. Use full user_id (e.g., user@ip) or ensure they're discovered first.")
                return
            
            target_user = full_user_id
            print(f"Following {target_user} (resolved from display name)")
        
        target_ip = self._get_peer_ip(target_user)
        if not target_ip:
            print(f"Cannot determine IP for user: {target_user}")
            return
        
        token = self.token_manager.generate_token("follow", ttl)
        message_id = self._generate_message_id()
        
        message_data = {
            "TYPE": "FOLLOW",
            "MESSAGE_ID": message_id,
            "FROM": self.user_id,
            "TO": target_user,
            "TIMESTAMP": str(int(time.time())),
            "TOKEN": token
        }
        
        self.peer.send_message(target_ip=target_ip, **message_data)
        self.following.add(target_user)
        
        if self.verbose:
            self.logger.log_send(message_data, f"{target_user} ({target_ip})")
            self.logger.log_info(f"Added {target_user} to following list. Current following: {list(self.following)}")
        
        target_name = self.known_peers.get(target_user, {}).get('display_name', target_user.split('@')[0])
        print(f"Now following {target_name} ({target_user})")
    
    def unfollow_user(self, target_user: str, ttl: int = 3600):
        """Unfollow a user."""
        target_ip = self._get_peer_ip(target_user)
        if not target_ip:
            print(f"Cannot determine IP for user: {target_user}")
            return
        
        token = self.token_manager.generate_token("follow", ttl)
        message_id = self._generate_message_id()
        
        message_data = {
            "TYPE": "UNFOLLOW",
            "MESSAGE_ID": message_id,
            "FROM": self.user_id,
            "TO": target_user,
            "TIMESTAMP": str(int(time.time())),
            "TOKEN": token
        }
        
        self.peer.send_message(target_ip=target_ip, **message_data)
        self.following.discard(target_user)
        
        if self.verbose:
            self.logger.log_send(message_data, f"{target_user} ({target_ip})")
        
        target_name = self.known_peers.get(target_user, {}).get('display_name', target_user.split('@')[0])
        print(f"Unfollowed {target_name}")
    
    def like_post(self, target_user: str, post_timestamp: int, ttl: int = 3600):
        """Like a post."""
        # First check if we've already liked this post
        target_post = None
        for post in self.posts:
            if str(post.get('timestamp')) == str(post_timestamp) and post.get('user_id') == target_user:
                target_post = post
                break
        
        if target_post:
            # Ensure post has like tracking (for backward compatibility)
            if 'likes' not in target_post:
                target_post['likes'] = set()
                target_post['like_count'] = 0
            
            # Check if we've already liked this post
            if self.user_id in target_post['likes']:
                print("You have already liked this post.")
                return
        
        target_ip = self._get_peer_ip(target_user)
        if not target_ip:
            print(f"Cannot determine IP for user: {target_user}")
            return
        
        token = self.token_manager.generate_token("broadcast", ttl)
        
        message_data = {
            "TYPE": "LIKE",
            "FROM": self.user_id,
            "TO": target_user,
            "POST_TIMESTAMP": str(post_timestamp),
            "ACTION": "LIKE",
            "TIMESTAMP": str(int(time.time())),
            "TOKEN": token
        }
        
        self.peer.send_message(target_ip=target_ip, **message_data)
        
        # Update local tracking immediately (optimistic update)
        if target_post:
            target_post['likes'].add(self.user_id)
            target_post['like_count'] = len(target_post['likes'])
        
        if self.verbose:
            self.logger.log_send(message_data, f"{target_user} ({target_ip})")
        
        target_name = self.known_peers.get(target_user, {}).get('display_name', target_user.split('@')[0])
        print(f"Liked post from {target_name}")
    
    def unlike_post(self, target_user: str, post_timestamp: int, ttl: int = 3600):
        """Unlike a post."""
        # First check if we've actually liked this post
        target_post = None
        for post in self.posts:
            if str(post.get('timestamp')) == str(post_timestamp) and post.get('user_id') == target_user:
                target_post = post
                break
        
        if target_post:
            # Ensure post has like tracking (for backward compatibility)
            if 'likes' not in target_post:
                target_post['likes'] = set()
                target_post['like_count'] = 0
            
            # Check if we've actually liked this post
            if self.user_id not in target_post['likes']:
                print("You haven't liked this post yet.")
                return
        else:
            print("Post not found.")
            return
        
        target_ip = self._get_peer_ip(target_user)
        if not target_ip:
            print(f"Cannot determine IP for user: {target_user}")
            return
        
        token = self.token_manager.generate_token("broadcast", ttl)
        
        message_data = {
            "TYPE": "LIKE",
            "FROM": self.user_id,
            "TO": target_user,
            "POST_TIMESTAMP": str(post_timestamp),
            "ACTION": "UNLIKE",
            "TIMESTAMP": str(int(time.time())),
            "TOKEN": token
        }
        
        self.peer.send_message(target_ip=target_ip, **message_data)
        
        # Update local tracking immediately (optimistic update)
        if target_post:
            target_post['likes'].discard(self.user_id)
            target_post['like_count'] = len(target_post['likes'])
        
        if self.verbose:
            self.logger.log_send(message_data, f"{target_user} ({target_ip})")
        
        target_name = self.known_peers.get(target_user, {}).get('display_name', target_user.split('@')[0])
        print(f"Unliked post from {target_name}")
    
    def _generate_message_id(self) -> str:
        """Generate a random 64-bit message ID in hex format."""
        return format(random.getrandbits(64), '016x')
    
    def set_status(self, status: str):
        """Update user status and broadcast profile."""
        self.status = status
        self.broadcast_profile()
        print(f"Status updated to: {status}")
    
    def set_avatar(self, file_path: str):
        """Set user avatar from file."""
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
                
            # Check file size (should be under ~20KB)
            if len(data) > 20480:
                print("Avatar file too large (>20KB)")
                return False
            
            # Encode to base64
            self.avatar_data = base64.b64encode(data).decode('utf-8')
            
            # Determine MIME type based on extension
            ext = os.path.splitext(file_path)[1].lower()
            mime_types = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif'
            }
            self.avatar_type = mime_types.get(ext, 'image/jpeg')
            
            self.broadcast_profile()
            print(f"Avatar set from {file_path}")
            return True
            
        except Exception as e:
            print(f"Error setting avatar: {e}")
            return False
    
    def discover_peers(self):
        """Actively discover peers by sending PING and PROFILE."""
        print("Discovering peers...")
        self.send_ping()
        time.sleep(0.5)
        self.broadcast_profile()
        print("Discovery messages sent")
    
    def _get_peer_ip(self, user_id: str) -> str:
        """Get the IP address to use for communicating with a peer."""
        # Check if we have peer info
        if user_id in self.known_peers:
            peer_info = self.known_peers[user_id]
            # Always use the declared IP from user_id (respecting user's choice)
            return peer_info['ip']
        
        # Fall back to extracting IP from user_id
        if "@" in user_id:
            return user_id.split("@")[1]
        
        return None
    
    # Interactive CLI methods
    def show_status(self):
        """Show current client status."""
        print(f"\n=== LSNP Client Status ===")
        print(f"User ID: {self.user_id}")
        print(f"Display Name: {self.display_name}")
        print(f"Status: {self.status}")
        print(f"Known Peers: {len(self.known_peers)}")
        print(f"Following: {len(self.following)}")
        print(f"Followers: {len(self.followers)}")
        print(f"Groups: {len(self.groups)}")
        print(f"Active Games: {self.game_manager.get_game_count()}")
        print("========================\n")
    
    def list_peers(self):
        """List known peers."""
        print("\n=== Known Peers ===")
        if not self.known_peers:
            print("No peers discovered yet.")
        else:
            for user_id, info in self.known_peers.items():
                display_name = info.get('display_name', user_id)
                status = info.get('status', 'Unknown')
                avatar_indicator = " 🖼️" if info.get('avatar_data') else ""
                print(f"{display_name}{avatar_indicator} ({user_id}) - {status}")
        print("==================\n")
    
    def list_posts(self):
        """List recent posts."""
        print("\n=== Recent Posts ===")
        if not self.posts:
            print("No posts yet.")
        else:
            for post in sorted(self.posts, key=lambda x: x.get('timestamp', 0), reverse=True)[:10]:
                user_id = post.get('user_id', 'Unknown')
                display_name = self.known_peers.get(user_id, {}).get('display_name', user_id)
                content = post.get('content', '')
                timestamp = post.get('timestamp', 0)
                time_str = datetime.fromtimestamp(timestamp).strftime('%H:%M:%S')
                
                # Ensure post has like tracking (for backward compatibility)
                if 'likes' not in post:
                    post['likes'] = set()
                    post['like_count'] = 0
                
                # Show like information
                like_count = post.get('like_count', 0)
                likes_set = post.get('likes', set())
                
                # Create like status text (just count, no names)
                like_status = f" ({like_count} likes)" if like_count > 0 else ""
                
                # Check if current user has liked this post
                user_liked = self.user_id in likes_set
                
                print(f"[{time_str}] {display_name}: {content}{like_status}")
                
                # Show like/unlike command for all posts
                if not user_liked:
                    print(f"    > like {user_id} {timestamp}")
                else:
                    print(f"    > unlike {user_id} {timestamp} (you liked this)")
                    
                if self.verbose:
                    print(f"     Verbose: User {user_id}, timestamp {timestamp}")
        print("===================\n")
    
    def list_likeable_posts(self):
        """List posts from users you're following with like commands."""
        print("\n=== Posts You Can Like ===")
        if not self.posts:
            print("No posts available to like.")
            return
        
        likeable_posts = []
        for post in self.posts:
            user_id = post.get('user_id', 'Unknown')
            # Can like posts from users we follow OR our own posts (any visible post can be liked)
            if user_id in self.following or user_id == self.user_id:
                likeable_posts.append(post)
        
        if not likeable_posts:
            print("No posts available to like.")
            print("=========================\n")
            return
        
        # Sort by timestamp, most recent first
        likeable_posts.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        
        for i, post in enumerate(likeable_posts[:10], 1):  # Show last 10
            user_id = post.get('user_id', 'Unknown')
            display_name = self.known_peers.get(user_id, {}).get('display_name', user_id.split('@')[0])
            content = post.get('content', '')
            timestamp = post.get('timestamp', 0)
            time_str = datetime.fromtimestamp(timestamp).strftime('%H:%M:%S')
            
            # Ensure post has like tracking (for backward compatibility)
            if 'likes' not in post:
                post['likes'] = set()
                post['like_count'] = 0
            
            # Show like information
            like_count = post.get('like_count', 0)
            likes_set = post.get('likes', set())
            
            # Create like status text
            like_status = ""
            if like_count > 0:
                like_status = f" ({like_count} likes)"
                # Show who liked it (up to 3 names, then "and X others")
                if likes_set:
                    like_names = []
                    for like_user_id in list(likes_set)[:3]:
                        like_display_name = self.known_peers.get(like_user_id, {}).get('display_name', like_user_id.split('@')[0])
                        like_names.append(like_display_name)
                    
                    if len(likes_set) > 3:
                        like_status += f" - {', '.join(like_names)} and {len(likes_set) - 3} others"
                    else:
                        like_status += f" - {', '.join(like_names)}"
            
            # Check if current user has liked this post
            user_liked = self.user_id in likes_set
            
            print(f"{i}. [{time_str}] {display_name}: {content}{like_status}")
            if not user_liked:
                print(f"   > like {user_id} {timestamp}")
            else:
                print(f"   > unlike {user_id} {timestamp} (you liked this)")
            print()
        
        print("=========================\n")
        
    def view_user(self, user_id: str):
        """View all posts and DMs from/to a specific user that you're allowed to see."""
        # Check if user exists in known peers
        if user_id not in self.known_peers and user_id != self.user_id:
            print(f"User {user_id} not found in known peers. Try 'discover' first.")
            return
        
        # Get display name
        if user_id == self.user_id:
            display_name = "You"
        else:
            display_name = self.known_peers.get(user_id, {}).get('display_name', user_id.split('@')[0])
        
        print(f"\n=== Content from {display_name} ({user_id}) ===")
        
        # Collect posts and DMs with timestamps
        content_items = []
        
        # Add posts (only if we're following them or it's our own posts)
        if user_id in self.following or user_id == self.user_id:
            for post in self.posts:
                if post.get('user_id') == user_id:
                    # Ensure post has like tracking (for backward compatibility)
                    if 'likes' not in post:
                        post['likes'] = set()
                        post['like_count'] = 0
                    
                    content_items.append({
                        'type': 'POST',
                        'timestamp': post.get('timestamp', 0),
                        'content': post.get('content', ''),
                        'from_user': user_id,
                        'to_user': None,
                        'like_count': post.get('like_count', 0),
                        'likes': post.get('likes', set())
                    })
        else:
            print(f"Note: Not following {display_name}, so posts are not visible.")
        
        # Add DMs (both sent to and received from this user)
        for dm in self.dms:
            if dm.get('from_user') == user_id or dm.get('to_user') == user_id:
                content_items.append({
                    'type': 'DM',
                    'timestamp': dm.get('timestamp', 0),
                    'content': dm.get('content', ''),
                    'from_user': dm.get('from_user'),
                    'to_user': dm.get('to_user')
                })
        
        # Sort by timestamp
        content_items.sort(key=lambda x: x['timestamp'])
        
        if not content_items:
            print("No content available for this user.")
        else:
            print(f"Found {len(content_items)} items:")
            print()
            
            for item in content_items:
                timestamp = datetime.fromtimestamp(item['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                
                if item['type'] == 'POST':
                    # Show like information for posts
                    like_count = item.get('like_count', 0)
                    like_status = f" ({like_count} likes)" if like_count > 0 else ""
                    
                    # Show who liked it if there are likes
                    if like_count > 0 and item.get('likes'):
                        likes_set = item.get('likes', set())
                        like_names = []
                        for like_user_id in list(likes_set)[:3]:
                            like_display_name = self.known_peers.get(like_user_id, {}).get('display_name', like_user_id.split('@')[0])
                            like_names.append(like_display_name)
                        
                        if len(likes_set) > 3:
                            like_status += f" - {', '.join(like_names)} and {len(likes_set) - 3} others"
                        else:
                            like_status += f" - {', '.join(like_names)}"
                    
                    print(f"[{timestamp}] POST: {item['content']}{like_status}")
                    
                elif item['type'] == 'DM':
                    from_name = "You" if item['from_user'] == self.user_id else self.known_peers.get(item['from_user'], {}).get('display_name', item['from_user'].split('@')[0])
                    to_name = "You" if item['to_user'] == self.user_id else self.known_peers.get(item['to_user'], {}).get('display_name', item['to_user'].split('@')[0])
                    
                    if item['from_user'] == self.user_id:
                        print(f"[{timestamp}] DM to {to_name}: {item['content']}")
                    else:
                        print(f"[{timestamp}] DM from {from_name}: {item['content']}")
                
                print()
        
        print("=" * 50 + "\n")
    def set_verbose(self, enabled: bool):
        """Enable or disable verbose mode."""
        old_verbose = self.verbose
        self.verbose = enabled
        
        if enabled and not old_verbose:
            # Turning verbose on
            self.logger.enable()
            print("Verbose mode enabled")
            self.logger.log_info("Verbose mode enabled during runtime")
        elif not enabled and old_verbose:
            # Turning verbose off
            self.logger.log_info("Verbose mode disabled during runtime")
            self.logger.disable()
            print("Verbose mode disabled")
        else:
            # No change
            status = "enabled" if enabled else "disabled"
            print(f"Verbose mode is already {status}")

    def view_avatar(self, user_id: str, save_to_file: str = None):
        """View avatar information for a user and optionally save to file."""
        # Check if user is trying to view their own avatar
        if (user_id == self.user_id or 
            user_id.lower() == self.display_name.lower()):
            
            # Viewing own avatar
            if not self.avatar_data:
                print("You have no avatar set. Use 'avatar <file>' to set one.")
                return False
            
            display_name = "You"
            avatar_type = self.avatar_type or 'unknown'
            avatar_encoding = 'base64'  # Own avatar is always base64
            avatar_data = self.avatar_data
            target_user_id = self.user_id
        else:
            # Find user by display name or user_id
            target_peer = None
            target_user_id = None
            
            # Check if it's a direct user_id match
            if user_id in self.known_peers:
                target_peer = self.known_peers[user_id]
                target_user_id = user_id
            else:
                # Search by display name
                for uid, peer_info in self.known_peers.items():
                    if peer_info.get('display_name', '').lower() == user_id.lower():
                        target_peer = peer_info
                        target_user_id = uid
                        break
            
            if not target_peer:
                print(f"User '{user_id}' not found in known peers. Try 'discover' first.")
                return False
            
            display_name = target_peer.get('display_name', target_user_id.split('@')[0])
            
            # Check if user has an avatar
            if not target_peer.get('avatar_data'):
                print(f"{display_name} has no avatar set.")
                return False
            
            avatar_type = target_peer.get('avatar_type', 'unknown')
            avatar_encoding = target_peer.get('avatar_encoding', 'unknown')
            avatar_data = target_peer.get('avatar_data', '')
        
        print(f"\n=== Avatar for {display_name} ===")
        print(f"Type: {avatar_type}")
        print(f"Encoding: {avatar_encoding}")
        print(f"Size: {len(avatar_data)} characters")
        
        # Try to decode and get actual file size
        if avatar_encoding.lower() == 'base64':
            try:
                decoded_data = base64.b64decode(avatar_data)
                file_size = len(decoded_data)
                print(f"File size: {file_size} bytes ({file_size/1024:.1f} KB)")
                
                # Save to file if requested
                if save_to_file:
                    try:
                        with open(save_to_file, 'wb') as f:
                            f.write(decoded_data)
                        print(f"Avatar saved to: {save_to_file}")
                        return True
                    except Exception as e:
                        print(f"Error saving avatar: {e}")
                        return False
                        
            except Exception as e:
                print(f"Error decoding avatar: {e}")
        
        print(f"Preview: {avatar_data[:50]}..." if len(avatar_data) > 50 else f"Data: {avatar_data}")
        print("=" * 30)
        
        if not save_to_file:
            print("Tip: Use 'saveavatar <user> <filename>' to save avatar to file")
        
        return True

    def list_following(self):
        """List users you're following."""
        print("\n=== Following ===")
        if not self.following:
            print("Not following anyone yet.")
        else:
            for user_id in sorted(self.following):
                display_name = self.known_peers.get(user_id, {}).get('display_name', user_id.split('@')[0])
                print(f"{display_name} ({user_id})")
        print("================\n")

    def create_group(self, group_id: str, group_name: str, members: list, ttl: int = 3600):
        """Create a new group with specified members."""
        # Validate group_id (alphanumeric)
        if not group_id.replace('_', '').isalnum():
            print("Group ID must be alphanumeric (underscores allowed)")
            return False
        
        # Check if group ID already exists
        if group_id in self.groups:
            print(f"Group with ID '{group_id}' already exists")
            return False
        
        # MOVE THIS LINE UP - Ensure creator is in member list BEFORE creating message
        if self.user_id not in members:
            members.append(self.user_id)
        
        # Store group locally
        self.groups[group_id] = {
            'name': group_name,
            'members': members.copy(),
            'creator': self.user_id,
            'created_at': time.time()
        }
        
        # Generate token and message (now members includes Alice)
        token = self.token_manager.generate_token("group", ttl)
        
        message_data = {
            "TYPE": "GROUP_CREATE",
            "FROM": self.user_id,
            "GROUP_ID": group_id,
            "GROUP_NAME": group_name,
            "MEMBERS": ",".join(members),  # This will now include Alice
            "TIMESTAMP": str(int(time.time())),
            "TOKEN": token
        }

        # for member in members:
        #     if member != self.user_id:
        #         target_ip = self._get_peer_ip(member)
        #         print(f"[DEBUG] Sending to {member} at IP {target_ip}")
        #         self._send_group_message_to_member(member, message_data)
        
        # Send to all members
        for member in members:
            if member != self.user_id:  # Don't send to ourselves
                self._send_group_message_to_member(member, message_data)
        
        print(f"Created group '{group_name}' with {len(members)} members")
        return True

    def update_group(self, group_id: str, add_members: list = None, remove_members: list = None, ttl: int = 3600):
        """Update group membership by adding or removing members."""
        if group_id not in self.groups:
            print(f"Group {group_id} not found")
            return False
        
        group = self.groups[group_id]
        
        # Check if we have permission (creator or member)
        if self.user_id not in group['members']:
            print("You are not a member of this group")
            return False
        
        # Prepare lists
        add_members = add_members or []
        remove_members = remove_members or []
        
        if not add_members and not remove_members:
            print("No changes specified")
            return False
        
            # Update local group state
        old_members = group['members'].copy()
        
        for member in add_members:
            if member not in group['members']:
                group['members'].append(member)
        
        for member in remove_members:
            if member in group['members']:
                group['members'].remove(member)
        
        token = self.token_manager.generate_token("group", ttl)
        message_data = {
            "TYPE": "GROUP_UPDATE",
            "FROM": self.user_id,
            "GROUP_ID": group_id,
            "GROUP_NAME": group['name'],
            "MEMBERS": ",".join(group['members']),
        }

        if add_members:
            message_data["ADD"] = ",".join(add_members)
        if remove_members:
            message_data["REMOVE"] = ",".join(remove_members)
            
        message_data["TIMESTAMP"] = str(int(time.time()))
        message_data["TOKEN"] = token
                
        # Send to current members (both old and new)
        all_affected_members = set(old_members + group['members'])
        for member in all_affected_members:
            if member != self.user_id:
                self._send_group_message_to_member(member, message_data)
        
        print(f"Updated group '{group['name']}' membership")
        return True

    def send_group_message(self, group_id: str, content: str, ttl: int = 3600):
        """Send a message to all members of a group."""
        if group_id not in self.groups:
            print(f"Group {group_id} not found")
            return False
        
        group = self.groups[group_id]
        
        # Check if we're a member
        if self.user_id not in group['members']:
            print("You are not a member of this group")
            return False
        
        # Generate message
        token = self.token_manager.generate_token("group", ttl)
        message_data = {
            "TYPE": "GROUP_MESSAGE",
            "FROM": self.user_id,
            "GROUP_ID": group_id,
            "CONTENT": content,
            "TIMESTAMP": str(int(time.time())),
            "TOKEN": token
        }
        
        # Send to all members except ourselves
        sent_count = 0
        for member in group['members']:
            if member != self.user_id:
                success = self._send_group_message_to_member(member, message_data)
                if success:
                    sent_count += 1
        
        print(f"Sent message to group '{group['name']}'")
        return True

    def _send_group_message_to_member(self, member_user_id: str, message_data: dict) -> bool:
        """Send a group message to a specific member."""
        target_ip = self._get_peer_ip(member_user_id)
        if not target_ip:
            if self.verbose:
                print(f"Cannot determine IP for group member: {member_user_id}")
            return False
        
        try:
            # Send to multiple ports like DMs
            target_ports = [50999, 51000, 51001, 51002]
            sent_count = 0
            
            for port in target_ports:
                try:
                    self.peer.sock.sendto(
                        ProtocolHandler.format_message(**message_data).encode('utf-8'),
                        (target_ip, port)
                    )
                    sent_count += 1
                except Exception as e:
                    if self.verbose:
                        print(f"[DEBUG] Failed to send group message to {target_ip}:{port} - {e}")
            
            return sent_count > 0
            
        except Exception as e:
            if self.verbose:
                print(f"Error sending group message to {member_user_id}: {e}")
            return False
    def list_groups(self):
        """List all groups the user is a member of."""
        if not self.groups:
            print("You are not a member of any groups.")
            return
        
        print("\n=== Your Groups ===")
        for group_id, group_info in self.groups.items():
            print(f"Group: {group_info['name']} (ID: {group_id})")
            print(f"  Members: {len(group_info['members'])}")
            print(f"  Creator: {group_info.get('creator', 'Unknown')}")
            
            # Show member list
            member_names = []
            for member in group_info['members']:
                if member in self.known_peers:
                    name = self.known_peers[member]['display_name']
                else:
                    name = member.split('@')[0]
                member_names.append(name)
            
            print(f"  Members: {', '.join(member_names)}")
            print()
        print("=" * 20)

    def leave_group(self, group_id: str):
        """Leave a group by removing yourself from membership."""
        if group_id not in self.groups:
            print(f"Group {group_id} not found")
            return False
        
        group = self.groups[group_id]
        
        # Remove ourselves and notify others
        self.update_group(group_id, remove_members=[self.user_id])
        
        # Remove from local storage
        group_name = group['name']
        del self.groups[group_id]
        
        print(f"Left group '{group_name}'")
        return True

def main():
    """Main function to run the LSNP client."""
    parser = argparse.ArgumentParser(description='LSNP Client')
    parser.add_argument('username', help='Username for the client')
    parser.add_argument('--ip', help='IP address to bind to')
    parser.add_argument('--port', type=int, default=50999, help='Port to use (default: 50999)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose mode')
    
    args = parser.parse_args()
    
    # Create and start client
    client = LSNPClient(args.username, args.ip, args.port, args.verbose)
    
    # Set up signal handler for graceful shutdown
    def signal_handler(sig, frame):
        print("\nShutting down gracefully...")
        client.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        client.start()
        
        # Interactive CLI loop
        print(f"\nLSNP Client started as {client.user_id}")
        print("Type 'help' for available commands")
        print("Press Ctrl+C to exit gracefully\n")
        
        while client.running:
            try:
                command = input("").strip()
                
                if not command:
                    continue
                
                parts = command.split(' ', 1)
                cmd = parts[0].lower()
                
                if cmd == 'help':
                    # Check if user wants help for a specific category
                    if len(parts) > 1:
                        category = parts[1].lower()
                        
                        if category in ['system', 'sys']:
                            help_text = """System Commands:

help                        Show this help
status                      Show client status and statistics
verbose [on|off]            Toggle verbose mode or show current status
quit / exit                 Exit the client
"""
                        
                        elif category in ['network', 'discovery', 'peers']:
                            help_text = """Discovery & Networking:

discover                    Actively discover peers on network
peers                       List all known peers
"""
                        
                        elif category in ['profile', 'avatar', 'status']:
                            help_text = """Profile & Status:

setstatus <status>          Update your status message
saveavatar <file>           Set your avatar from image file
viewavatar <user>           View avatar information for a user
"""
                        
                        elif category in ['social', 'follow', 'following']:
                            help_text = """Social Features:

follow <user>               Follow a user (display name or user@ip)
unfollow <user>             Unfollow a user
following                   List users you're following
like <user> <timestamp>     Like a specific post
unlike <user> <timestamp>   Unlike a specific post
"""
                        
                        elif category in ['posts', 'messages', 'dm']:
                            help_text = """Posts & Messages:

posts                       List recent posts from followed users
likeable                    List posts you can like with commands
post <message>              Send a public post
dm <user> <message>         Send direct message to user
view <user>                 View all posts and DMs from/to a user
"""
                        
                        elif category in ['groups', 'group']:
                            help_text = """Group Management:

groups                      List all your groups
creategroup <id> <name> <members>  Create new group (comma-separated members)
addtogroup <id> <members>   Add members to existing group
removefromgroup <id> <members>  Remove members from group
groupmsg <id> <message>     Send message to group
leavegroup <id>             Leave a group
"""
                        
                        elif category in ['games', 'game', 'tictactoe']:
                            help_text = """Games:

games                       List active games
game <opponent>             Start tic-tac-toe game with opponent
move <game_id> <pos>        Make move in game (position 1-9)
forfeit <game_id>           Forfeit an active game
"""
                        
                        elif category in ['files', 'file', 'transfer']:
                            help_text = """File Transfer:

sendfile <user> <file> [chunk_size]  Send file to user
offers                      List pending file offers
accept <id>                 Accept a pending file offer
reject <id>                 Reject a pending file offer
transfers                   List active file transfers
setchunksize <bytes>        Set default chunk size (128-65536)
getchunksize                Show current default chunk size
"""
                        
                        elif category in ['logs', 'logging', 'verbose'] and client.verbose:
                            help_text = """Verbose Logging Commands:

logs [lines]                Show recent log entries (default: 20)
logstats                    Show logging statistics
logsearch <query>           Search logs for specific text
logclear                    Clear all logs
logexport <file>            Export logs to file
logfile <file|off>          Enable/disable logging to file
"""
                        
                        else:
                            help_text = f"""
Unknown help category: {category}

Available help categories:
  help system                 # System commands (help, status, quit)
  help network                # Discovery and peer management
  help profile                # Profile and avatar management
  help social                 # Following and social features
  help posts                  # Posts and direct messages
  help groups                 # Group management and messaging
  help games                  # Tic-tac-toe games
  help files                  # File transfer system"""
                            if client.verbose:
                                help_text += "\n  help logs                   # Verbose logging commands"
                        
                        print(help_text)
                    
                    else:
                        # Show main help with category overview only
                        help_text = """LSNP Client Help Categories:

  help system        - Basic system commands (help, status, verbose, quit)
  help network       - Peer discovery and networking
  help profile       - Avatar and status management
  help social        - Following users and social features
  help posts         - Public posts and direct messages
  help groups        - Group management and messaging
  help games         - Tic-tac-toe games
  help files         - File transfer system"""
                        
                        if client.verbose:
                            help_text += "\n  help logs          - Verbose logging and debugging"
                        
                        help_text += "\n\nType 'help <category>' for detailed commands in each area."
                        
                        print(help_text)
                
                elif cmd == 'status':
                    client.show_status()
                
                elif cmd == 'peers':
                    client.list_peers()
                
                elif cmd == 'discover':
                    client.discover_peers()
                
                elif cmd == 'posts':
                    client.list_posts()
                
                elif cmd == 'likeable':
                    client.list_likeable_posts()
                
                elif cmd == 'post' and len(parts) > 1:
                    client.send_post(parts[1])
                
                elif cmd == 'dm' and len(parts) > 1:
                    dm_parts = parts[1].split(' ', 1)
                    if len(dm_parts) >= 2:
                        client.send_dm(dm_parts[0], dm_parts[1])
                    else:
                        print("Usage: dm <user> <message>")
                
                elif cmd == 'view' and len(parts) > 1:
                    client.view_user(parts[1])
                
                elif cmd == 'viewavatar' and len(parts) > 1:
                    client.view_avatar(parts[1])
                
                elif cmd == 'saveavatar' and len(parts) > 1:
                    client.set_avatar(parts[1])
                
                elif cmd == 'follow' and len(parts) > 1:
                    client.follow_user(parts[1])
                
                elif cmd == 'unfollow' and len(parts) > 1:
                    client.unfollow_user(parts[1])
                
                elif cmd == 'following':
                    client.list_following()
                
                elif cmd == 'verbose':
                    if len(parts) > 1:
                        arg = parts[1].lower()
                        if arg in ['on', 'true', '1', 'enable']:
                            client.set_verbose(True)
                        elif arg in ['off', 'false', '0', 'disable']:
                            client.set_verbose(False)
                        else:
                            print("Usage: verbose <on|off>")
                    else:
                        # Show current status
                        status = "enabled" if client.verbose else "disabled"
                        print(f"Verbose mode is currently {status}")
                
                elif cmd == 'like' and len(parts) > 1:
                    like_parts = parts[1].split(' ', 1)
                    if len(like_parts) >= 2:
                        try:
                            timestamp = int(like_parts[1])
                            client.like_post(like_parts[0], timestamp)
                        except ValueError:
                            print("Invalid timestamp")
                    else:
                        print("Usage: like <user> <timestamp>")
                
                elif cmd == 'unlike' and len(parts) > 1:
                    unlike_parts = parts[1].split(' ', 1)
                    if len(unlike_parts) >= 2:
                        try:
                            timestamp = int(unlike_parts[1])
                            client.unlike_post(unlike_parts[0], timestamp)
                        except ValueError:
                            print("Invalid timestamp")
                    else:
                        print("Usage: unlike <user> <timestamp>")
                
                elif cmd == 'setstatus' and len(parts) > 1:
                    client.set_status(parts[1])
                
                elif cmd == 'setchunksize' and len(parts) > 1:
                    try:
                        chunk_size = int(parts[1])
                        client.file_manager.set_default_chunk_size(chunk_size)
                    except ValueError:
                        print("Invalid chunk size. Must be a number.")
                
                elif cmd == 'getchunksize':
                    chunk_size = client.file_manager.get_default_chunk_size()
                    print(f"Current default chunk size: {chunk_size} bytes")
                
                elif cmd == 'game' and len(parts) > 1:
                    # Start a tic-tac-toe game
                    client.game_manager.create_game(parts[1])
                
                elif cmd == 'move' and len(parts) > 1:
                    # Make a move in an active game
                    move_parts = parts[1].split(' ')
                    if len(move_parts) >= 2:
                        game_id = move_parts[0]
                        try:
                            position = int(move_parts[1])
                            client.game_manager.make_move(game_id, position)
                        except ValueError:
                            print("Invalid position number")
                    else:
                        print("Usage: move <game_id> <position>")
                
                elif cmd == 'forfeit' and len(parts) > 1:
                    game_id = parts[1].strip()
                    if not client.game_manager.forfeit_game(game_id):
                        print("Unable to forfeit (check game id or game is already over).")
                
                elif cmd == 'games':
                    client.game_manager.list_games()
                
                elif cmd == 'sendfile' and len(parts) > 1:
                    # Send a file with optional chunk size
                    # Usage: sendfile <user> <filepath> [chunk_size]
                    args = parts[1].split()
                    if len(args) >= 2:
                        target_user = args[0]
                        file_path = args[1]
                        chunk_size = None
                        
                        # Third argument is chunk size if provided
                        if len(args) >= 3:
                            try:
                                chunk_size = int(args[2])
                            except ValueError:
                                print("Invalid chunk size. Must be a number.")
                                continue
                        
                        client.file_manager.offer_file(target_user, file_path, "", chunk_size=chunk_size)
                    else:
                        print("Usage: sendfile <user> <filepath> [chunk_size]")
                        print("  chunk_size: Chunk size in bytes (128-65536, default: 1024)")
                
                elif cmd == 'offers':
                    client.file_manager.list_pending_offers()
                
                elif cmd == 'accept' and len(parts) > 1:
                    file_id = parts[1].strip()
                    if not client.file_manager.accept_file_offer(file_id):
                        print("No such pending offer.")
                
                elif cmd == 'reject' and len(parts) > 1:
                    file_id = parts[1].strip()
                    if not client.file_manager.reject_file_offer(file_id):
                        print("No such pending offer.")
                
                elif cmd == 'transfers':
                    client.file_manager.list_transfers()
                
                # Verbose logging commands
                elif cmd == 'logs':
                    if client.verbose:
                        lines = 20  # default
                        if len(parts) > 1:
                            try:
                                lines = int(parts[1])
                            except ValueError:
                                print("Invalid line count, using default (20)")
                        client.logger.show_logs(lines)
                    else:
                        print("Verbose mode not enabled. Use --verbose flag to enable.")
                
                elif cmd == 'logstats':
                    if client.verbose:
                        client.logger.show_stats()
                    else:
                        print("Verbose mode not enabled. Use --verbose flag to enable.")
                
                elif cmd == 'logsearch' and len(parts) > 1:
                    if client.verbose:
                        search_parts = parts[1].split(' ', 1)
                        query = search_parts[0]
                        lines = 10  # default search results
                        if len(search_parts) > 1:
                            try:
                                lines = int(search_parts[1])
                            except ValueError:
                                pass
                        client.logger.search_logs_display(query, lines)
                    else:
                        print("Verbose mode not enabled. Use --verbose flag to enable.")
                
                elif cmd == 'logclear':
                    if client.verbose:
                        client.logger.clear_logs()
                    else:
                        print("Verbose mode not enabled. Use --verbose flag to enable.")
                
                elif cmd == 'logexport' and len(parts) > 1:
                    if client.verbose:
                        client.logger.export_logs(parts[1])
                    else:
                        print("Verbose mode not enabled. Use --verbose flag to enable.")
                
                elif cmd == 'logfile' and len(parts) > 1:
                    if client.verbose:
                        if parts[1].lower() == 'off':
                            client.logger.set_log_file(None)
                            print("Log file disabled.")
                        else:
                            client.logger.set_log_file(parts[1])
                            print(f"Logging to file: {parts[1]}")
                    else:
                        print("Verbose mode not enabled. Use --verbose flag to enable.")

                elif cmd == 'creategroup' and len(parts) > 1:
                    # creategroup <group_id> <group_name> <member1,member2,...>
                    group_parts = parts[1].split(' ', 2)
                    if len(group_parts) >= 3:
                        group_id = group_parts[0]
                        group_name = group_parts[1]
                        members = [m.strip() for m in group_parts[2].split(',')]
                        client.create_group(group_id, group_name, members)
                    else:
                        print("Usage: creategroup <group_id> <group_name> <member1,member2,...>")

                elif cmd == 'addtogroup' and len(parts) > 1:
                    # addtogroup <group_id> <member1,member2,...>
                    group_parts = parts[1].split(' ', 1)
                    if len(group_parts) >= 2:
                        group_id = group_parts[0]
                        add_members = [m.strip() for m in group_parts[1].split(',')]
                        client.update_group(group_id, add_members=add_members)
                    else:
                        print("Usage: addtogroup <group_id> <member1,member2,...>")

                elif cmd == 'removefromgroup' and len(parts) > 1:
                    # removefromgroup <group_id> <member1,member2,...>
                    group_parts = parts[1].split(' ', 1)
                    if len(group_parts) >= 2:
                        group_id = group_parts[0]
                        remove_members = [m.strip() for m in group_parts[1].split(',')]
                        client.update_group(group_id, remove_members=remove_members)
                    else:
                        print("Usage: removefromgroup <group_id> <member1,member2,...>")

                elif cmd == 'groupmsg' and len(parts) > 1:
                    # groupmsg <group_id> <message>
                    group_parts = parts[1].split(' ', 1)
                    if len(group_parts) >= 2:
                        group_id = group_parts[0]
                        content = group_parts[1]
                        client.send_group_message(group_id, content)
                    else:
                        print("Usage: groupmsg <group_id> <message>")

                elif cmd == 'groups':
                    client.list_groups()

                elif cmd == 'leavegroup' and len(parts) > 1:
                    group_id = parts[1].strip()
                    client.leave_group(group_id)
                            
                elif cmd in ['quit', 'exit']:
                    break
                
                else:
                    print("Unknown command. Type 'help' for available commands.")
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")
    
    except KeyboardInterrupt:
        pass
    finally:
        client.stop()

if __name__ == "__main__":
    main()