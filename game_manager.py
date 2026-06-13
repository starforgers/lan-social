"""
Game Manager for LSNP Client
Handles Tic-Tac-Toe game logic and state management.
Thread-safe implementation for concurrent game handling.
"""

import time
import threading
from typing import List, Optional, Tuple, Dict
from concurrent.futures import ThreadPoolExecutor
import queue


class TicTacToeGame:
    """Manages a single Tic-Tac-Toe game session with thread-safety."""
    
    def __init__(self, game_id: str, player_id: str, opponent_id: str, player_symbol: str):
        """Initialize a new game."""
        self.game_id = game_id
        self.player_id = player_id
        self.opponent_id = opponent_id
        self.player_symbol = player_symbol
        self.opponent_symbol = 'O' if player_symbol == 'X' else 'X'
        
        # Game state
        self.board = [' '] * 9  # 3x3 board as linear array
        self.current_turn = 1
        self.game_over = False
        self.winner = None
        self.winning_line = None
        
        # Determine who goes first (X always goes first)
        self.is_creator = player_symbol == 'X'  # Creator gets X and goes first
        
        # Track moves for duplicate detection
        self.moves = {}  # turn -> (position, symbol)
        
        # Game timing
        self.created_at = time.time()
        self.last_move_time = time.time()
        
        # Thread safety
        self._lock = threading.RLock()  # Reentrant lock for nested calls
        self._move_queue = queue.Queue()  # Queue for processing moves sequentially
    
    def make_move(self, position: int, symbol: str, turn: int) -> bool:
        """Make a move on the board (thread-safe)."""
        with self._lock:
            # Check if game is already over
            if self.game_over:
                return False
            
            # Validate position bounds
            if position < 0 or position > 8:
                return False
            
            # CHECK FOR DUPLICATE MOVES FIRST (before checking if position is occupied)
            if turn in self.moves:
                existing_pos, existing_symbol = self.moves[turn]
                # If it's the same move, acknowledge but don't apply again
                return existing_pos == position and existing_symbol == symbol
            
            # Validate turn order (must be sequential)
            if turn != self.current_turn:
                return False
            
            # Validate symbol matches expected player for this turn
            expected_symbol = 'X' if turn % 2 == 1 else 'O'
            if symbol != expected_symbol:
                return False
            
            # NOW check if position is already occupied (for non-duplicate moves)
            if self.board[position] != ' ':
                return False
            
            # Apply the move
            self.board[position] = symbol
            self.moves[turn] = (position, symbol)
            self.current_turn += 1
            self.last_move_time = time.time()
            
            # Check for game end conditions
            self._check_game_end()
            
            return True
    
    def _check_game_end(self):
        """Check if the game has ended (win, loss, or draw)."""
        # Check for wins
        winning_combinations = [
            [0, 1, 2], [3, 4, 5], [6, 7, 8],  # Rows
            [0, 3, 6], [1, 4, 7], [2, 5, 8],  # Columns
            [0, 4, 8], [2, 4, 6]              # Diagonals
        ]
        
        for combo in winning_combinations:
            if (self.board[combo[0]] == self.board[combo[1]] == self.board[combo[2]] != ' '):
                self.game_over = True
                self.winner = self.board[combo[0]]
                self.winning_line = ','.join(map(str, combo))
                return
        
        # Check for draw
        if ' ' not in self.board:
            self.game_over = True
            self.winner = 'DRAW'
    
    def display_board(self):
        """Display the current board state."""
        with self._lock:
            print(f"\nGame {self.game_id} - You are '{self.player_symbol}':")
            print(f"{self.board[0]} | {self.board[1]} | {self.board[2]}")
            print("-----------")
            print(f"{self.board[3]} | {self.board[4]} | {self.board[5]}")
            print("-----------")
            print(f"{self.board[6]} | {self.board[7]} | {self.board[8]}")
            print("\nPositions:")
            print("0 | 1 | 2")
            print("-----------")
            print("3 | 4 | 5")
            print("-----------")
            print("6 | 7 | 8")
            
            if self.game_over:
                if self.winner == 'DRAW':
                    print("Game ended in a draw!")
                else:
                    winner_name = "You" if self.winner == self.player_symbol else "Opponent"
                    if winner_name == "You":
                        print("Game over! You win!")
                    else:
                        print("Game over! Opponent wins!")
            else:
                current_symbol = 'X' if self.current_turn % 2 == 1 else 'O'
                if current_symbol == self.player_symbol:
                    print(f"Your turn ('{self.player_symbol}') - Turn {self.current_turn}")
                    print(f">Type: move {self.game_id} <position>")
                else:
                    print(f"Opponent's turn ('{self.opponent_symbol}') - Turn {self.current_turn}")
                    print("Waiting for opponent...")
                # Forfeit hint while game is active
                print(f">Type: forfeit {self.game_id} to concede")

            print()

    def get_valid_moves(self) -> List[int]:
        """Get list of valid move positions (thread-safe)."""
        with self._lock:
            return [i for i in range(9) if self.board[i] == ' ']
    
    def is_player_turn(self) -> bool:
        """Check if it's the player's turn."""
        with self._lock:
            # Turn 1, 3, 5... = X's turn (odd turns)
            # Turn 2, 4, 6... = O's turn (even turns)
            current_symbol = 'X' if self.current_turn % 2 == 1 else 'O'
            is_my_turn = current_symbol == self.player_symbol
            
            # if hasattr(self, 'client') and getattr(self.client, 'verbose', False):
            #     self.client.logger.log_info(f"Turn {self.current_turn}: {current_symbol}'s turn, I am {self.player_symbol}, My turn: {is_my_turn}")
            
            return is_my_turn
    
    def handle_result(self, result: str, symbol: str, winning_line: str = None):
        """Handle a game result message from opponent (thread-safe)."""
        with self._lock:
            self.game_over = True
            
            if result == 'WIN':
                # Sender (opponent) reports they won
                self.winner = self.opponent_symbol
                self.winning_line = winning_line
                print("Game over! Opponent wins!")
            elif result == 'DRAW':
                self.winner = 'DRAW'
                print("Game ended in a draw!")
            elif result == 'LOSS':
                # Sender (opponent) reports they lost => we win
                self.winner = self.player_symbol
                self.winning_line = winning_line
                print("Game over! You win!")
        
        # Do not call display_board() here to avoid double printing; the board
        # was already shown upon applying the last move.
    
    def get_game_state(self) -> dict:
        """Get the current game state as a dictionary (thread-safe)."""
        with self._lock:
            return {
                'game_id': self.game_id,
                'player_id': self.player_id,
                'opponent_id': self.opponent_id,
                'player_symbol': self.player_symbol,
                'opponent_symbol': self.opponent_symbol,
                'board': self.board.copy(),
                'current_turn': self.current_turn,
                'game_over': self.game_over,
                'winner': self.winner,
                'winning_line': self.winning_line,
                'created_at': self.created_at,
                'last_move_time': self.last_move_time
            }

class GameManager:
    """Manages multiple game sessions for an LSNP client with thread-safety."""
    
    def __init__(self, client):
        """Initialize the game manager."""
        self.client = client
        self.games = {}  # game_id -> TicTacToeGame
        self.pending_invitations = {}  # game_id -> invitation_data
        
        # Thread safety
        self._games_lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="GameManager")
        
        # Track message IDs generated by this manager for ACK routing
        self._sent_message_ids = set()
        self._message_ids_lock = threading.Lock()
    
    def shutdown(self):
        """Shutdown the game manager and clean up resources."""
        if self._executor:
            self._executor.shutdown(wait=True)
    
    def create_game(self, opponent_id: str, player_symbol: str = 'X') -> str:
        """Create a new game and send invitation (thread-safe)."""
        with self._games_lock:
            # Generate game ID (g + number 0-255)
            game_id = self._generate_game_id()
            
            # Create game instance
            game = TicTacToeGame(game_id, self.client.user_id, opponent_id, player_symbol)
            # Attach client for optional verbose logging inside game
            game.client = self.client
            self.games[game_id] = game
        
        # Show board immediately for the creator so they see their turn
        print(f"Game {game_id} created. You are playing as '{player_symbol}'")
        game.display_board()
        
        # Send invitation asynchronously
        self._executor.submit(self._send_invitation, opponent_id, game_id, player_symbol)
        
        return game_id
    
    def _generate_game_id(self) -> str:
        """Generate a unique game ID (thread-safe)."""
        import random
        with self._games_lock:
            game_number = random.randint(0, 255)
            game_id = f"g{game_number}"
            
            # Ensure uniqueness
            while game_id in self.games:
                game_number = random.randint(0, 255)
                game_id = f"g{game_number}"
            
            return game_id
        
    def _send_to_multiple_ports(self, target_ip: str, message_data: dict):
        """Send message to multiple ports to ensure delivery (same as file manager)."""
        from protocol import ProtocolHandler
        
        message = ProtocolHandler.format_message(**message_data)
        ports = [50999, 51000, 51001, 51002]  # Common LSNP ports
        
        sent_count = 0
        for port in ports:
            try:
                self.client.peer.sock.sendto(message.encode('utf-8'), (target_ip, port))
                sent_count += 1
            except Exception as e:
                if self.client.verbose:
                    self.client.logger.log_error(f"Failed to send to {target_ip}:{port}", {"error": str(e)})
    
        if self.client.verbose:
            print(f"[DEBUG] Sent {message_data['TYPE']} to {target_ip} (multiple ports)")
    
    def _send_invitation(self, opponent_id: str, game_id: str, symbol: str):
        """Send a Tic-Tac-Toe invitation."""
        try:
            if "@" not in opponent_id:
                return
            
            # Use the SAME IP resolution as DMs
            target_ip = self.client._get_peer_ip(opponent_id)
            if not target_ip:
                print(f"Cannot determine IP for user: {opponent_id}")
                return
            
            token = self.client.token_manager.generate_token("game")
            message_id = self.client._generate_message_id()
            self._track_message_id(message_id)  # Track for ACK routing
            
            message_data = {
                "TYPE": "TICTACTOE_INVITE",
                "FROM": self.client.user_id,
                "TO": opponent_id,
                "GAMEID": game_id,
                "MESSAGE_ID": message_id,
                "SYMBOL": symbol,
                "TIMESTAMP": str(int(time.time())),
                "TOKEN": token
            }
            
            # Use the SAME multi-port sending as DMs
            self._send_to_multiple_ports(target_ip, message_data)
            
            if self.client.verbose:
                self.client._log(f"SEND > TICTACTOE_INVITE to {opponent_id}")
                
        except Exception as e:
            if hasattr(self.client, '_log'):
                self.client._log(f"Error sending game invitation: {e}")
    
    def make_move(self, game_id: str, position: int) -> bool:
        """Make a move in a game (thread-safe)."""
        with self._games_lock:
            if game_id not in self.games:
                return False
            game = self.games[game_id]
        
        # Check if it's player's turn
        if not game.is_player_turn():
            print("It's not your turn!")
            return False
        
        # Validate position
        if position not in game.get_valid_moves():
            print("Invalid move position!")
            return False
        
        # Store the current turn before making the move
        current_turn = game.current_turn
        
        # Make the move locally
        success = game.make_move(position, game.player_symbol, current_turn)
        if not success:
            return False
        
        # Send move to opponent asynchronously with the correct turn number
        self._executor.submit(self._send_move, game, position, current_turn)
        
        # Display updated board
        game.display_board()
        
        # Check if game ended and send result asynchronously
        if game.game_over:
            self._executor.submit(self._send_result, game)
        
        return True
    
    def _send_move(self, game: TicTacToeGame, position: int, turn: int):
        """Send a move to the opponent (fixed version)."""
        try:
            if "@" not in game.opponent_id:
                return
            
            # Use the SAME IP resolution method as invitations
            target_ip = self.client._get_peer_ip(game.opponent_id)
            if not target_ip:
                if self.client.verbose:
                    self.client._log(f"Cannot determine IP for {game.opponent_id}")
                return
            
            token = self.client.token_manager.generate_token("game")
            message_id = self.client._generate_message_id()
            self._track_message_id(message_id)  # Track for ACK routing
            
            message_data = {
                "TYPE": "TICTACTOE_MOVE",
                "FROM": self.client.user_id,
                "TO": game.opponent_id,
                "GAMEID": game.game_id,
                "MESSAGE_ID": message_id,
                "POSITION": str(position),
                "SYMBOL": game.player_symbol,
                "TURN": str(turn),
                "TOKEN": token
            }
            
            # Use the SAME multi-port sending as invitations
            self._send_to_multiple_ports(target_ip, message_data)
            
            if self.client.verbose:
                self.client._log(f"SEND > TICTACTOE_MOVE to {game.opponent_id}: pos={position}, turn={turn}")
                
        except Exception as e:
            if hasattr(self.client, '_log'):
                self.client._log(f"Error sending game move: {e}")
    
    def _send_result(self, game: TicTacToeGame):
        """Send game result to opponent (fixed version)."""
        try:
            if "@" not in game.opponent_id:
                return
            
            # Use the SAME IP resolution method
            target_ip = self.client._get_peer_ip(game.opponent_id)
            if not target_ip:
                return
            
            # Determine result from player's perspective
            if game.winner == game.player_symbol:
                result = "WIN"
            elif game.winner == 'DRAW':
                result = "DRAW"
            else:
                result = "LOSS"
            
            message_id = self.client._generate_message_id()
            self._track_message_id(message_id)  # Track for ACK routing
            
            message_data = {
                "TYPE": "TICTACTOE_RESULT",
                "FROM": self.client.user_id,
                "TO": game.opponent_id,
                "GAMEID": game.game_id,
                "MESSAGE_ID": message_id,
                "RESULT": result,
                "SYMBOL": game.player_symbol,
                "TIMESTAMP": str(int(time.time()))
            }
            
            if game.winning_line:
                message_data["WINNING_LINE"] = game.winning_line
            
            # Use multi-port sending
            self._send_to_multiple_ports(target_ip, message_data)
            
            if self.client.verbose:
                self.client._log(f"SEND > TICTACTOE_RESULT to {game.opponent_id}")
                
        except Exception as e:
            if hasattr(self.client, '_log'):
                self.client._log(f"Error sending game result: {e}")
    
    def list_games(self):
        """List all active games (thread-safe)."""
        with self._games_lock:
            if not self.games:
                print("No active games.")
                return
            
            print("\n=== Active Games ===")
            for game_id, game in self.games.items():
                opponent_name = self.client.known_peers.get(game.opponent_id, {}).get('display_name', game.opponent_id)
                status = "Finished" if game.game_over else "In Progress"
                turn_info = ""
                if not game.game_over:
                    turn_info = " (Your turn)" if game.is_player_turn() else " (Opponent's turn)"
                
                print(f"Game {game_id}: vs {opponent_name} - {status}{turn_info}")
            print("===================\n")
    
    def handle_invitation(self, message: dict, sender_ip: str):
        """Handle incoming game invitation."""
        from_user = message.get('FROM')
        game_id = message.get('GAMEID')
        symbol = message.get('SYMBOL')
        
        with self._games_lock:
            # Create game instance with correct symbol assignment
            opponent_symbol = 'O' if symbol == 'X' else 'X'
            game = TicTacToeGame(game_id, self.client.user_id, from_user, opponent_symbol)
            # Attach client for optional verbose logging inside game
            game.client = self.client
            self.games[game_id] = game
        
        print(f"Game {game_id} created. You are playing as '{opponent_symbol}'")
        game.display_board()
    
    def get_game_count(self) -> int:
        """Get the number of active games (thread-safe)."""
        with self._games_lock:
            return len(self.games)
    
    def get_game(self, game_id: str) -> Optional[TicTacToeGame]:
        """Get a specific game by ID (thread-safe)."""
        with self._games_lock:
            return self.games.get(game_id)
        
    def handle_ack(self, message_id: str, status: str):
        """Handle ACK messages for game operations."""
        # Only handle ACKs for messages we actually sent
        if not self.is_tracking_message(message_id):
            return
        
        # Remove the message ID from tracking since we've received the ACK
        with self._message_ids_lock:
            self._sent_message_ids.discard(message_id)
    
    def forfeit_game(self, game_id: str) -> bool:
        """Forfeit an active game and notify the opponent (thread-safe)."""
        with self._games_lock:
            game = self.games.get(game_id)
            if not game:
                print("No such game.")
                return False
        
        with game._lock:
            if game.game_over:
                print("Game already over.")
                return False
            # Mark as loss locally
            game.game_over = True
            game.winner = game.opponent_symbol
            game.winning_line = None
            game.last_move_time = time.time()
        
        print(f"You forfeited Game {game_id}. Game over! Opponent wins!")
        
        # Notify opponent asynchronously (RESULT will be LOSS from our perspective)
        self._executor.submit(self._send_result, game)
        return True
    
    def is_tracking_message(self, message_id: str) -> bool:
        """Check if this manager sent a message with the given ID."""
        with self._message_ids_lock:
            return message_id in self._sent_message_ids
    
    def _track_message_id(self, message_id: str):
        """Track a message ID that this manager sent."""
        with self._message_ids_lock:
            self._sent_message_ids.add(message_id)
            # Keep only recent message IDs (last 100) to prevent memory leak
            if len(self._sent_message_ids) > 100:
                # Remove oldest (this is a simple approach, could be improved with timestamps)
                self._sent_message_ids.pop()
