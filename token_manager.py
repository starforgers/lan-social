"""
Token Manager for LSNP Client
Handles token generation, validation, expiration, and revocation.
Thread-safe implementation for concurrent access.
"""

import time
import hashlib
import threading
from typing import Set, Dict, Optional


class TokenManager:
    """Manages LSNP tokens for authentication and authorization (thread-safe)."""
    
    def __init__(self, user_id: str, logger=None):
        """Initialize the token manager."""
        self.user_id = user_id
        self.revoked_tokens: Set[str] = set()
        self.issued_tokens: Dict[str, Dict] = {}  # token -> metadata
        self.logger = logger
        
        # Thread safety
        self._lock = threading.RLock()  # Reentrant lock for nested calls
    
    def generate_token(self, scope: str, ttl: int = 3600) -> str:
        """Generate a new token with the specified scope and TTL (thread-safe)."""
        with self._lock:
            current_time = int(time.time())
            expiry_time = current_time + ttl
            
            # Token format: user_id|timestamp+ttl|scope
            token = f"{self.user_id}|{expiry_time}|{scope}"
            
            # Store metadata about issued token
            self.issued_tokens[token] = {
                'scope': scope,
                'issued_at': current_time,
                'expires_at': expiry_time,
                'ttl': ttl
            }
            
            # Log token generation in verbose mode
            if self.logger and self.logger.is_enabled():
                generation_details = {
                    'action': 'token_generation',
                    'scope': scope,
                    'ttl': ttl,
                    'expires_at': expiry_time,
                    'user_id': self.user_id
                }
                self.logger.log_info("Token generated", generation_details)
            elif self.logger:
                # Debug: logger exists but not enabled
                print(f"[DEBUG] Logger exists but not enabled: {self.logger.is_enabled()}")
            else:
                # Debug: no logger
                print(f"[DEBUG] No logger available in TokenManager")
            
            return token
    
    def validate_token(self, token: str, expected_scope: str, sender_user_id: str, should_log: bool = True, debug: bool = False) -> bool:
        """
        Validate a token for the three critical criteria:
        1. Not expired
        2. Correct scope
        3. Not revoked
        
        Args:
            should_log: Whether to log validation details (used to respect privacy rules)
        """
        with self._lock:
            # Log token validation attempt in verbose mode only if should_log is True
            if should_log and self.logger and self.logger.is_enabled():
                validation_details = {
                    'action': 'token_validation',
                    'expected_scope': expected_scope,
                    'sender_user_id': sender_user_id,
                    'token_preview': token[:20] + "..." if token and len(token) > 20 else token
                }
                self.logger.log_info("Validating token", validation_details)
            
            if not token:
                if should_log and self.logger and self.logger.is_enabled():
                    self.logger.log_error("Token validation FAILED: empty token")
                return False
            
            # Check if token is revoked
            if token in self.revoked_tokens:
                if should_log and self.logger and self.logger.is_enabled():
                    self.logger.log_error("Token validation FAILED: token revoked")
                return False
            
            # Parse token format: user_id|timestamp+ttl|scope
            try:
                parts = token.split('|')
                if len(parts) != 3:
                    if should_log and self.logger and self.logger.is_enabled():
                        self.logger.log_error(f"Token validation FAILED: invalid format (expected 3 parts, got {len(parts)})")
                    return False
                
                token_user_id, expiry_str, token_scope = parts
                
                # Log parsed token details in verbose mode only if should_log is True
                if should_log and self.logger and self.logger.is_enabled():
                    token_details = {
                        'parsed_user_id': token_user_id,
                        'parsed_scope': token_scope,
                        'expiry_timestamp': expiry_str
                    }
                    self.logger.log_info("Token parsed", token_details)
                
                # Verify the token belongs to the sender
                if token_user_id != sender_user_id:
                    if should_log and self.logger and self.logger.is_enabled():
                        self.logger.log_error(f"Token validation FAILED: user ID mismatch (token: {token_user_id}, sender: {sender_user_id})")
                    return False
                
                # Check expiration
                expiry_time = int(expiry_str)
                current_time = int(time.time())
                if current_time > expiry_time:
                    if should_log and self.logger and self.logger.is_enabled():
                        self.logger.log_error(f"Token validation FAILED: token expired (current: {current_time}, expiry: {expiry_time})")
                    return False
                
                # Check scope
                if token_scope != expected_scope:
                    if should_log and self.logger and self.logger.is_enabled():
                        self.logger.log_error(f"Token validation FAILED: scope mismatch (token: {token_scope}, expected: {expected_scope})")
                    return False
                
                # Validation successful
                if should_log and self.logger and self.logger.is_enabled():
                    time_until_expiry = expiry_time - current_time
                    success_details = {
                        'result': 'SUCCESS',
                        'scope_verified': token_scope,
                        'user_verified': token_user_id,
                        'time_until_expiry_seconds': time_until_expiry
                    }
                    self.logger.log_info("Token validation SUCCESS", success_details)
                
                return True
                
            except (ValueError, IndexError) as e:
                if should_log and self.logger and self.logger.is_enabled():
                    self.logger.log_error(f"Token validation FAILED: parsing error - {str(e)}")
                return False
    
    def revoke_token(self, token: str):
        """Revoke a token, making it invalid (thread-safe)."""
        with self._lock:
            was_our_token = token in self.issued_tokens
            self.revoked_tokens.add(token)
            
            # Log token revocation in verbose mode
            if self.logger and self.logger.is_enabled():
                revocation_details = {
                    'action': 'token_revocation',
                    'token_preview': token[:20] + "..." if len(token) > 20 else token,
                    'was_our_token': was_our_token
                }
                
                if was_our_token:
                    token_metadata = self.issued_tokens[token]
                    revocation_details.update({
                        'scope': token_metadata['scope'],
                        'issued_at': token_metadata['issued_at'],
                        'expires_at': token_metadata['expires_at']
                    })
                    del self.issued_tokens[token]
                
                self.logger.log_info("Token revoked", revocation_details)
    
    def cleanup_expired_tokens(self):
        """Remove expired tokens from internal storage (thread-safe)."""
        with self._lock:
            current_time = int(time.time())
            
            # Clean up issued tokens
            expired_tokens = []
            for token, metadata in self.issued_tokens.items():
                if current_time > metadata['expires_at']:
                    expired_tokens.append(token)
            
            if expired_tokens and self.logger and self.logger.is_enabled():
                cleanup_details = {
                    'action': 'token_cleanup',
                    'expired_count': len(expired_tokens),
                    'cleanup_time': current_time
                }
                self.logger.log_info("Token cleanup: expired tokens removed", cleanup_details)
            
            for token in expired_tokens:
                del self.issued_tokens[token]
    
    def list_active_tokens(self) -> Dict[str, Dict]:
        """Get list of active (non-expired) tokens."""
        current_time = int(time.time())
        active_tokens = {}
        
        for token, metadata in self.issued_tokens.items():
            if current_time <= metadata['expires_at']:
                active_tokens[token] = metadata
        
        return active_tokens
    
    def get_token_info(self, token: str) -> Optional[Dict]:
        """Get information about a specific token."""
        return self.issued_tokens.get(token)
    
    def is_token_expired(self, token: str) -> bool:
        """Check if a token is expired."""
        try:
            parts = token.split('|')
            if len(parts) != 3:
                return True
            
            expiry_time = int(parts[1])
            current_time = int(time.time())
            return current_time > expiry_time
            
        except (ValueError, IndexError):
            return True
    
    def get_token_hash(self, token: str) -> str:
        """Get a hash of the token for storage in revocation lists."""
        return hashlib.sha256(token.encode('utf-8')).hexdigest()
    
    def revoke_all_tokens_for_scope(self, scope: str):
        """Revoke all tokens for a specific scope."""
        tokens_to_revoke = []
        
        for token, metadata in self.issued_tokens.items():
            if metadata['scope'] == scope:
                tokens_to_revoke.append(token)
        
        for token in tokens_to_revoke:
            self.revoke_token(token)
    
    def get_revocation_count(self) -> int:
        """Get the number of revoked tokens."""
        return len(self.revoked_tokens)
    
    def export_revocation_list(self) -> list:
        """Export the revocation list for sharing with other peers."""
        return list(self.revoked_tokens)
    
    def import_revocation_list(self, revoked_tokens: list):
        """Import a revocation list from another peer."""
        self.revoked_tokens.update(revoked_tokens)
