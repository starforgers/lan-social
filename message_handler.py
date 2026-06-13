"""
Message Handler for LSNP Client
Handles incoming message processing and response generation.
Thread-safe implementation for concurrent message handling.
"""

import time
import threading
from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor


class MessageHandler:
    """Handles processing of incoming LSNP messages with thread-safety."""
    
    def __init__(self, client):
        """Initialize the message handler."""
        self.client = client
        
        # Thread safety for message processing
        self._executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="MessageHandler")
        self._response_lock = threading.Lock()
    
    def handle_message(self, message: Dict[str, str], sender_ip: str):
        """Route messages to appropriate handlers based on type."""
        message_type = message.get('TYPE', '').upper()
        
        # Verify sender IP matches FROM field for security (log warning but allow)
        from_field = message.get('FROM', message.get('USER_ID', ''))
        if '@' in from_field:
            declared_ip = from_field.split('@')[1]
            if declared_ip != sender_ip:
                if self.client.verbose:
                    self.client.logger.log_info(f"IP mismatch warning: declared {declared_ip}, actual {sender_ip} (allowing)")
        
        # Don't process our own messages (additional safety check)
        # Exception: Allow LIKE messages from ourselves (for self-like notifications)
        if from_field == self.client.user_id and message_type != 'LIKE':
            return
        
        # Route to specific handlers
        handlers = {
            'PROFILE': self._handle_profile,
            'PING': self._handle_ping,
            'ACK': self._handle_ack,
            'POST': self._handle_post,
            'DM': self._handle_dm,
            'FOLLOW': self._handle_follow,
            'UNFOLLOW': self._handle_unfollow,
            'LIKE': self._handle_like,
            'FILE_OFFER': self._handle_file_offer,
            'FILE_CHUNK': self._handle_file_chunk,
            'FILE_RECEIVED': self._handle_file_received,
            'TICTACTOE_INVITE': self._handle_tictactoe_invite,
            'TICTACTOE_MOVE': self._handle_tictactoe_move,
            'TICTACTOE_RESULT': self._handle_tictactoe_result,
            'GROUP_CREATE': self._handle_group_create,
            'GROUP_UPDATE': self._handle_group_update,
            'GROUP_MESSAGE': self._handle_group_message,
            'REVOKE': self._handle_revoke
        }
        
        handler = handlers.get(message_type)
        if handler:
            handler(message, sender_ip)
        else:
            self.client._log(f"Unknown message type: {message_type}")
    
    def _handle_profile(self, message: Dict[str, str], sender_ip: str):
        """Handle PROFILE messages."""
        user_id = message.get('USER_ID')
        if not user_id:
            return
        
        # Check if this is a new peer
        is_new_peer = user_id not in self.client.known_peers
        
        # Store old peer info for comparison BEFORE updating
        old_peer = self.client.known_peers.get(user_id, {}) if not is_new_peer else {}
        
        # Extract declared IP from user_id for consistency
        declared_ip = sender_ip  # Default to actual sender IP
        if '@' in user_id:
            declared_ip = user_id.split('@')[1]
        
        # Update known peers - use declared IP as primary communication address
        peer_info = {
            'display_name': message.get('DISPLAY_NAME', user_id),
            'status': message.get('STATUS', ''),
            'last_seen': time.time(),
            'ip': declared_ip,  # Use declared IP for communication (respects user's --ip choice)
            'actual_ip': sender_ip  # Store actual IP for reference/debugging only
        }
        
        # Handle avatar if present
        if message.get('AVATAR_DATA'):
            avatar_type = message.get('AVATAR_TYPE', 'image/jpeg')
            avatar_encoding = message.get('AVATAR_ENCODING', 'base64')
            
            # Validate avatar encoding (LSNP 5.1 spec: currently always base64)
            if avatar_encoding.lower() == 'base64':
                peer_info['avatar_type'] = avatar_type
                peer_info['avatar_encoding'] = avatar_encoding
                peer_info['avatar_data'] = message.get('AVATAR_DATA')
                
                if self.client.verbose:
                    avatar_size = len(message.get('AVATAR_DATA', ''))
                    self.client.logger.log_info(f"Avatar received: {avatar_type}, {avatar_size} chars")
            else:
                # Unsupported encoding - ignore avatar but continue processing
                if self.client.verbose:
                    self.client.logger.log_info(f"Unsupported avatar encoding '{avatar_encoding}', ignoring avatar")
        
        self.client.known_peers[user_id] = peer_info
        
        # If this is a new peer, respond with our profile to help them discover us
        if is_new_peer:
            # Small delay to avoid network congestion
            if self.client.verbose:
                self.client.logger.log_info(f"New peer discovered: {peer_info['display_name']} ({user_id})")
        
        # Display peer information with avatar indicator
        display_name = peer_info['display_name']
        status = peer_info['status']
        avatar_indicator = " 🖼️" if peer_info.get('avatar_data') else ""
        
        if not self.client.verbose:
            if is_new_peer:
                print(f"{display_name}{avatar_indicator} is here! - Status: {status}")
            else:
                # Check for specific changes and show appropriate messages
                old_display_name = old_peer.get('display_name', '')
                old_status = old_peer.get('status', '')
                old_has_avatar = bool(old_peer.get('avatar_data'))
                new_has_avatar = bool(peer_info.get('avatar_data'))
                
                # Show status change specifically
                if old_status != status:
                    print(f"{display_name} changed status to: {status}")
                
                # Show other profile changes
                elif (old_display_name != display_name or old_has_avatar != new_has_avatar):
                    print(f"{display_name}{avatar_indicator} updated profile - Status: {status}")
    
    def _handle_ping(self, message: Dict[str, str], sender_ip: str):
        """Handle PING messages."""
        user_id = message.get('USER_ID')
        if user_id:
            # Update last seen time if we know this peer
            
            # New peer detected via PING, respond with PROFILE
            import threading
            def delayed_response():
                import time
                time.sleep(0.2 + (hash(self.client.user_id) % 5) * 0.1)  # Random delay 0.2-0.7s
                self.client.broadcast_profile()
            
            threading.Thread(target=delayed_response, daemon=True).start()
            
            if self.client.verbose:
                self.client.logger.log_info(f"PING from unknown peer {user_id}, responding with PROFILE")
    
    def _handle_ack(self, message: Dict[str, str], sender_ip: str):
        """Handle ACK messages."""
        message_id = message.get('MESSAGE_ID')
        status = message.get('STATUS')
        
        if self.client.verbose:
            self.client.logger.log_receive(message, sender_ip)
        
        # Handle acknowledgments - only route to relevant managers
        if message_id:
            # Check if this is a file-related ACK by looking at message ID patterns or context
            # File manager handles file transfer ACKs
            if hasattr(self.client, 'file_manager'):
                # Only send to file manager if it's actually handling this message ID
                if self.client.file_manager.is_tracking_message(message_id):
                    self.client.file_manager.handle_ack(message_id, status)
            
            # Check if this is a game-related ACK
            if hasattr(self.client, 'game_manager'):
                # Only send to game manager if it's actually handling this message ID
                if self.client.game_manager.is_tracking_message(message_id):
                    self.client.game_manager.handle_ack(message_id, status)
    
    def _handle_post(self, message: Dict[str, str], sender_ip: str):
        """Handle POST messages."""
        user_id = message.get('USER_ID')
        content = message.get('CONTENT')
        token = message.get('TOKEN')
        timestamp = message.get('TIMESTAMP')
        
        # Check if we're following this user first (for logging decision)
        is_following = user_id in self.client.following or user_id == self.client.user_id
        
        # Validate token - only log if we're following the user
        if not self._validate_token(token, 'broadcast', user_id, should_log=is_following):
            if self.client.verbose and is_following:
                self.client.logger.log_error(f"POST token validation failed for {user_id}")
            return
        
        # Check if we're following this user
        if not is_following:
            # Show debug info about why the post is being ignored
            following_list = list(self.client.following) if self.client.following else ["(none)"]
            return  # Don't show posts from users we don't follow
        
        # Store the post
        post_data = {
            'user_id': user_id,
            'content': content,
            'timestamp': int(timestamp) if timestamp else time.time(),
            'message_id': message.get('MESSAGE_ID'),
            'likes': set(),  # Set of user_ids who liked this post
            'like_count': 0  # Count of likes for easy access
        }
        self.client.posts.append(post_data)
        
        # Display the post (works in both verbose and non-verbose modes)
        display_name = self.client.known_peers.get(user_id, {}).get('display_name', user_id)
        
        
        # Log in verbose mode
        if self.client.verbose:
            self.client.logger.log_info(f"POST displayed: {display_name} posted '{content}'")

        print(f"{display_name} posted: {content}")

    def _handle_dm(self, message: Dict[str, str], sender_ip: str):
        """Handle DM messages."""
        from_user = message.get('FROM')
        to_user = message.get('TO')
        content = message.get('CONTENT')
        token = message.get('TOKEN')
        message_id = message.get('MESSAGE_ID')
        
        if self.client.verbose:
            self.client.logger.log_receive(message, sender_ip)
        
        # Check if message is for us
        if to_user != self.client.user_id:
            if self.client.verbose:
                self.client.logger.log_info(f"DM not for us (TO={to_user}, our ID={self.client.user_id})")
            return
        
        # Validate token
        if not self._validate_token(token, 'chat', from_user):
            if self.client.verbose:
                self.client.logger.log_error(f"DM token validation failed for {from_user}")
            return
        
        # Send ACK
        if message_id:
            self._send_ack(message_id, from_user, from_user)
        
        # Store the DM
        dm_data = {
            'from_user': from_user,
            'to_user': to_user,
            'content': content,
            'timestamp': int(message.get('TIMESTAMP', time.time())),
            'message_id': message_id
        }
        self.client.dms.append(dm_data)
        
        if self.client.verbose:
            self.client.logger.log_info(f"DM processed successfully")
    
        display_name = self.client.known_peers.get(from_user, {}).get('display_name', from_user)
        print(f"DM from {display_name}: {content}")

    def _handle_follow(self, message: Dict[str, str], sender_ip: str):
        """Handle FOLLOW messages."""
        from_user = message.get('FROM')
        to_user = message.get('TO')
        token = message.get('TOKEN')
        message_id = message.get('MESSAGE_ID')
        
        # Check if message is for us
        if to_user != self.client.user_id:
            return
        
        # Validate token
        if not self._validate_token(token, 'follow', from_user):
            return
        
        # Add to followers
        self.client.followers.add(from_user)
        
        # Send ACK
        if message_id:
            self._send_ack(message_id, from_user, from_user)
        
        # Display notification
        display_name = self.client.known_peers.get(from_user, {}).get('display_name', from_user.split('@')[0])
        print(f"User {display_name} has followed you")
    
    def _handle_unfollow(self, message: Dict[str, str], sender_ip: str):
        """Handle UNFOLLOW messages."""
        from_user = message.get('FROM')
        to_user = message.get('TO')
        token = message.get('TOKEN')
        message_id = message.get('MESSAGE_ID')
        
        # Check if message is for us
        if to_user != self.client.user_id:
            return
        
        # Validate token
        if not self._validate_token(token, 'follow', from_user):
            return
        
        # Remove from followers
        self.client.followers.discard(from_user)
        
        # Send ACK
        if message_id:
            self._send_ack(message_id, from_user, from_user)
        
        # Display notification
        display_name = self.client.known_peers.get(from_user, {}).get('display_name', from_user.split('@')[0])
        print(f"User {display_name} has unfollowed you")
    
    def _handle_like(self, message: Dict[str, str], sender_ip: str):
        """Handle LIKE messages."""
        from_user = message.get('FROM')
        to_user = message.get('TO')
        post_timestamp = message.get('POST_TIMESTAMP')
        action = message.get('ACTION')
        token = message.get('TOKEN')
        
        # Check if message is for us
        if to_user != self.client.user_id:
            return
        
        # Validate token
        if not self._validate_token(token, 'broadcast', from_user):
            return
        
        # Only allow likes from followers (or self)
        if from_user != self.client.user_id and from_user not in self.client.followers:
            if self.client.verbose:
                display_name = self.client.known_peers.get(from_user, {}).get('display_name', from_user.split('@')[0])
                self.client.logger.log_info(f"LIKE from {display_name} rejected - not a follower")
            return
        
        # Find the post being liked and update like tracking
        post_content = "your post"
        target_post = None
        for post in self.client.posts:
            if str(post.get('timestamp')) == str(post_timestamp):
                target_post = post
                post_content = f"your post [{post.get('content', 'your post')}]"
                
                # Ensure post has like tracking (for backward compatibility)
                if 'likes' not in post:
                    post['likes'] = set()
                    post['like_count'] = 0
                
                # Update like tracking based on action
                if action == 'LIKE':
                    if from_user not in post['likes']:
                        post['likes'].add(from_user)
                        post['like_count'] = len(post['likes'])
                    else:
                        # User already liked this post - ignore duplicate like
                        if self.client.verbose:
                            display_name = self.client.known_peers.get(from_user, {}).get('display_name', from_user.split('@')[0])
                            self.client.logger.log_info(f"Duplicate LIKE from {display_name} ignored - already liked this post")
                        return
                elif action == 'UNLIKE':
                    if from_user in post['likes']:
                        post['likes'].discard(from_user)
                        post['like_count'] = len(post['likes'])
                    else:
                        # User hasn't liked this post - ignore unlike
                        if self.client.verbose:
                            display_name = self.client.known_peers.get(from_user, {}).get('display_name', from_user.split('@')[0])
                            self.client.logger.log_info(f"UNLIKE from {display_name} ignored - never liked this post")
                        return
                break
        
        # Display notification according to spec
        display_name = self.client.known_peers.get(from_user, {}).get('display_name', from_user.split('@')[0])
        if action == 'LIKE':
            like_count_text = f" ({target_post['like_count']} likes)" if target_post else ""
            print(f"{display_name} likes {post_content}{like_count_text}")
        elif action == 'UNLIKE':
            like_count_text = f" ({target_post['like_count']} likes)" if target_post else ""
            print(f"{display_name} unlikes {post_content}{like_count_text}")
    
    def _handle_file_offer(self, message: Dict[str, str], sender_ip: str):
        """Handle FILE_OFFER messages."""
        from_user = message.get('FROM')
        to_user = message.get('TO')
        filename = message.get('FILENAME')
        filesize = message.get('FILESIZE')
        token = message.get('TOKEN')
        
        # Check if message is for us
        if to_user != self.client.user_id:
            return
        
        # Validate token
        if not self._validate_token(token, 'file', from_user):
            return
        
        # For now, auto-accept (in a real implementation, this would be user choice)
        # Pass to file manager
        if hasattr(self.client, 'file_manager'):
            self.client.file_manager.handle_file_offer(message, sender_ip)
    
    def _handle_file_chunk(self, message: Dict[str, str], sender_ip: str):
        """Handle FILE_CHUNK messages."""
        if hasattr(self.client, 'file_manager'):
            self.client.file_manager.handle_file_chunk(message, sender_ip)
    
    def _handle_file_received(self, message: Dict[str, str], sender_ip: str):
        """Handle FILE_RECEIVED messages."""
        if hasattr(self.client, 'file_manager'):
            self.client.file_manager.handle_file_received(message, sender_ip)
    
    def _handle_tictactoe_invite(self, message: Dict[str, str], sender_ip: str):
        """Handle TICTACTOE_INVITE messages."""
        from_user = message.get('FROM')
        to_user = message.get('TO')
        game_id = message.get('GAMEID')
        symbol = message.get('SYMBOL')
        token = message.get('TOKEN')
        message_id = message.get('MESSAGE_ID')
        
        # Check if message is for us
        if to_user != self.client.user_id:
            return
        
        # Validate token
        if not self._validate_token(token, 'game', from_user):
            return
        
        # Send ACK
        if message_id:
            self._send_ack(message_id, from_user, from_user)
        
        # Display invitation
        display_name = self.client.known_peers.get(from_user, {}).get('display_name', from_user.split('@')[0])
        print(f"{display_name} is inviting you to play tic-tac-toe.")
        
        # Create game instance (auto-accept for demo)
        from game_manager import GameManager
        opponent_symbol = 'O' if symbol == 'X' else 'X'
        if hasattr(self.client, 'game_manager'):
            self.client.game_manager.handle_invitation(message, sender_ip)
    
    def _handle_tictactoe_move(self, message: Dict[str, str], sender_ip: str):
        """Handle TICTACTOE_MOVE messages (fixed version)."""
        game_id = message.get('GAMEID')
        position = message.get('POSITION')
        symbol = message.get('SYMBOL')
        turn = message.get('TURN')
        from_user = message.get('FROM')
        token = message.get('TOKEN')
        message_id = message.get('MESSAGE_ID')
        
        # Validate token
        if not self._validate_token(token, 'game', from_user):
            return
        
        # Send ACK
        if message_id:
            self._send_ack(message_id, from_user, from_user)
        
        # Handle the move through game manager
        if hasattr(self.client, 'game_manager'):
            game = self.client.game_manager.get_game(game_id)
            if game:
                if self.client.verbose:
                    self.client.logger.log_info(f"Received move: pos={position}, symbol={symbol}, turn={turn}")
                    self.client.logger.log_info(f"Game current_turn={game.current_turn}, expected_turn={turn}")
                
                success = game.make_move(int(position), symbol, int(turn))
                if success:
                    game.display_board()
                    print(f"Opponent played at position {position}")
                    
                    # Check if game ended and send result
                    if game.game_over:
                        if hasattr(self.client, 'game_manager'):
                            self.client.game_manager._send_result(game)
                else:
                    if self.client.verbose:
                        self.client.logger.log_error(f"Invalid move received: position {position}, turn {turn}")
            else:
                print(f"Received move for unknown game: {game_id}")
        
    def _handle_tictactoe_result(self, message: Dict[str, str], sender_ip: str):
        """Handle TICTACTOE_RESULT messages."""
        game_id = message.get('GAMEID')
        result = message.get('RESULT')
        symbol = message.get('SYMBOL')
        winning_line = message.get('WINNING_LINE')
            
        if hasattr(self.client, 'game_manager'):
            game = self.client.game_manager.get_game(game_id)
            if game:
                game.handle_result(result, symbol, winning_line)
            else:
                print(f"Received result for unknown game: {game_id}")
    
    def _handle_group_create(self, message: Dict[str, str], sender_ip: str):
        """Handle GROUP_CREATE messages."""
        from_user = message.get('FROM')
        group_id = message.get('GROUP_ID')
        group_name = message.get('GROUP_NAME')
        members = message.get('MEMBERS', '').split(',')
        token = message.get('TOKEN')
        
        # Validate token
        if not self._validate_token(token, 'group', from_user):
            return
        
        # Check if we're in the member list
        if self.client.user_id in members:
            self.client.groups[group_id] = {
                'name': group_name,
                'members': members,
                'creator': from_user
            }
            
            # Non-verbose printing
            print(f"You've been added to {group_name}")

    def _handle_group_update(self, message: Dict[str, str], sender_ip: str):
        """Handle GROUP_UPDATE messages."""
        from_user = message.get('FROM')
        group_id = message.get('GROUP_ID')
        group_name = message.get('GROUP_NAME', group_id)
        add_members_str = message.get('ADD', '')
        remove_members_str = message.get('REMOVE', '')
        token = message.get('TOKEN')
        
        # Validate token
        if not self._validate_token(token, 'group', from_user):
            return
        
        # Parse member lists
        add_members = [m.strip() for m in add_members_str.split(',') if m.strip()] if add_members_str else []
        remove_members = [m.strip() for m in remove_members_str.split(',') if m.strip()] if remove_members_str else []
        
        if group_id not in self.client.groups:
            if self.client.user_id in add_members:
                # Get complete member list from MEMBERS field
                complete_members = [m.strip() for m in message.get('MEMBERS', '').split(',') if m.strip()]
                
                # If MEMBERS field is empty, fall back to creator + self
                if not complete_members:
                    complete_members = [from_user, self.client.user_id]
                
                self.client.groups[group_id] = {
                    'name': group_name,
                    'members': complete_members,  # Use complete list
                    'creator': from_user,
                    'created_at': time.time()
                }
                print(f"You've been added to {group_name}")
                return
        
        group = self.client.groups[group_id]
        
        # IMPORTANT: Update group membership properly
        for member in add_members:
            if member and member not in group['members']:
                group['members'].append(member)
                if self.client.verbose:
                    print(f"[DEBUG] Added {member} to group {group_id}")
        
        for member in remove_members:
            if member in group['members']:
                group['members'].remove(member)
                if self.client.verbose:
                    print(f"[DEBUG] Removed {member} from group {group_id}")
        
        # Check if we were removed
        if self.client.user_id in remove_members:
            group_name = group['name']
            del self.client.groups[group_id]
            print(f"You have been removed from {group_name}")
            return
        
        # Debug: Show current member list
        if self.client.verbose:
            print(f"[DEBUG] Group {group_id} members after update: {group['members']}")
        
        # Show appropriate message
        if self.client.user_id in add_members:
            print(f"You've been added to {group['name']}")
        else:
            print(f'The group "{group["name"]}" member list was updated.')

    def _handle_group_message(self, message: Dict[str, str], sender_ip: str):
        """Handle GROUP_MESSAGE messages."""
        from_user = message.get('FROM')
        group_id = message.get('GROUP_ID')
        content = message.get('CONTENT')
        token = message.get('TOKEN')
        
        # Validate token
        if not self._validate_token(token, 'group', from_user):
            print(f"[DEBUG] Token validation failed for {from_user}")
            return
        
        # Check if we're in this group
        if group_id not in self.client.groups:
            print(f"[DEBUG] Group {group_id} not found in local groups")
            return
        
        group = self.client.groups[group_id]
        print(f"[DEBUG] Group members: {group['members']}")
        
        # Verify sender is a group member
        if from_user not in group['members']:
            print(f"[DEBUG] {from_user} not in group members list")
            return
        
        # Non-verbose printing
        print(f'{from_user} sent "{content}"')
    
    def _handle_revoke(self, message: Dict[str, str], sender_ip: str):
        """Handle REVOKE messages."""
        token = message.get('TOKEN')
        if token:
            self.client.token_manager.revoke_token(token)
    
    def _validate_token(self, token: str, expected_scope: str, user_id: str, should_log: bool = True) -> bool:
        """Validate a token."""
        if not token:
            return False
        
        return self.client.token_manager.validate_token(token, expected_scope, user_id, should_log=should_log, debug=self.client.verbose)
    
    def _send_ack(self, message_id: str, to_user: str, sender_ip: str):
        """Send an ACK message."""
        # Use the declared IP from user_id instead of actual sender IP
        target_ip = self.client._get_peer_ip(to_user)
        if not target_ip:
            target_ip = sender_ip  # Fallback to sender IP if peer not known
        
        message_data = {
            "TYPE": "ACK",
            "MESSAGE_ID": message_id,
            "STATUS": "RECEIVED"
        }
        
        self.client.peer.send_message(target_ip=target_ip, **message_data)
        if self.client.verbose:
            self.client.logger.log_send(message_data, f"{target_ip} (ACK)")
