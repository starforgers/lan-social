# LSNP (Lightweight Social Networking Protocol)

This is a Python implementation of the Lightweight Social Networking Protocol (LSNP).

## Features

- **Peer Discovery**: Automatic discovery of peers on the local network
- **Messaging**: Send public posts and private direct messages  
- **Social Features**: Follow/unfollow users, like posts
- **Group Communication**: Create and manage groups for messaging
- **File Sharing**: Send files to other users with chunked transfer
- **Gaming**: Built-in Tic-Tac-Toe game support
- **Token-based Security**: Authentication and authorization system
- **Verbose Mode**: Detailed logging for debugging

## File Structure

```text
├── lsnp_client.py          # Main LSNP client implementation
├── peer.py                 # UDP networking layer
├── protocol.py             # Message formatting and parsing
├── message_handler.py      # Incoming message processing
├── token_manager.py        # Token generation and validation
├── game_manager.py         # Tic-Tac-Toe game logic
├── file_manager.py         # File transfer handling
├── verbose_logger.py       # Advanced logging system
├── run_client.py           # Helper startup script
├── specs.txt               # LSNP protocol specification
└── README.md              # This file
```

## Requirements

- Python 3.6 or higher
- No external Python dependencies (uses only standard library)

## How to Run

### Basic Usage

```bash
# Run the client directly
python lsnp_client.py alice

# Run with verbose mode (shows all protocol messages)
python lsnp_client.py alice --verbose

# Specify IP address and port
python lsnp_client.py bob --ip 192.168.1.101 --port 50999
```

### Testing with Multiple Clients

Open multiple terminal windows on different devices on the same subnet and run different users:

**Terminal 1:**
```bash
python lsnp_client.py alice --verbose
```

**Terminal 2:**
```bash
python lsnp_client.py bob --verbose
```

**Terminal 3:**
```bash
python lsnp_client.py charlie
```

## Available Commands

Once the client is running, you can use these commands:

### Help System

- `help` - Show available help categories
- `help <category>` - Show detailed help for specific category
  - `help system` - Basic system commands
  - `help network` - Peer discovery and networking
  - `help profile` - Avatar and status management
  - `help social` - Following and social features
  - `help posts` - Posts and direct messages
  - `help groups` - Group management
  - `help games` - Tic-tac-toe games
  - `help files` - File transfer system

### System Commands

- `status` - Show client status (peers, followers, etc.)
- `peers` - List all discovered peers
- `discover` - Actively discover peers on the network
- `verbose [on|off]` - Toggle verbose mode
- `quit` or `exit` - Exit the client

### Social Features

- `post <message>` - Send a public post
- `posts` - Show recent posts from followed users
- `likeable` - Show posts you can like with copy-pasteable commands
- `dm <user> <message>` - Send a direct message
- `follow <user_id>` - Follow another user
- `unfollow <user_id>` - Unfollow a user
- `following` - List users you're following
- `like <user_id> <timestamp>` - Like a specific post
- `unlike <user_id> <timestamp>` - Unlike a specific post
- `view <user>` - View all posts and DMs with a user

### Group Management

- `groups` - List all your groups
- `creategroup <id> <name> <members>` - Create new group
- `addtogroup <id> <members>` - Add members to existing group
- `removefromgroup <id> <members>` - Remove members from group
- `groupmsg <id> <message>` - Send message to group
- `leavegroup <id>` - Leave a group

### Profile Management

- `setstatus <status>` - Update your status message
- `saveavatar <filepath>` - Set profile picture from image file
- `viewavatar <user>` - View avatar information for a user

### File Sharing

- `sendfile <user_id> <filepath> [description]` - Send a file
- `offers` - List pending file offers
- `accept <file_id>` - Accept a file offer
- `reject <file_id>` - Reject a file offer
- `transfers` - Show active file transfers

**Note**: File offers require **manual acceptance**. When someone sends you a file, you'll see the offer details and need to explicitly accept or reject it using the commands above. Accepted files are saved to the `downloads/` directory.

### Liking Posts

The LIKE system allows you to express appreciation for posts from users you follow:

1. **See available posts**: Use `likeable` to see posts you can like with ready-to-copy commands
2. **Like a post**: Use `like <user_id> <timestamp>` (copy from likeable output)
3. **Unlike a post**: Use `unlike <user_id> <timestamp>` to retract a like

**Important**: You can only like posts from users you're following, and you cannot like your own posts.

**Example**:
```bash
> follow alice@192.168.1.100       # Follow Alice first
> likeable                         # Shows Alice's posts with like commands
> like alice@192.168.1.100 1728938391  # Like Alice's specific post
```

When someone likes your post, you'll see: `alice likes your post [Hello everyone!]`

### Games

- `games` - List active games
- `game <opponent_user_id>` - Start a tic-tac-toe game
- `move <game_id> <position>` - Make a move (position 1-9)
- `forfeit <game_id>` - Forfeit an active game

## Example Session

```bash
# Start the client
python lsnp_client.py alice

# Wait a moment for peer discovery, then:
> help                             # Show help categories
> help groups                      # Get detailed group help
> status                           # Check connected peers
> discover                         # Manually trigger peer discovery if needed
> post Hello everyone!             # Send a public post
> follow bob@192.168.1.101         # Follow Bob
> posts                            # See recent posts
> like bob@192.168.1.101 1728938391 # Like Bob's post (copy timestamp from likeable)
> dm bob@192.168.1.101 Hi Bob!     # Send Bob a direct message
> creategroup team "Project Team" bob@192.168.1.101,charlie@192.168.1.102
> groupmsg team "Meeting at 3pm"   # Send group message
> game bob@192.168.1.101           # Start a game with Bob
> move g123 5                      # Make a move in the center (position 5)
```

## Network Requirements

- All clients must be on the same local network
- UDP port 50999 must be available
- Firewall should allow UDP broadcast and unicast on port 50999

## Debug Mode

Always use `--verbose` for debugging:

```bash
python lsnp_client.py alice --verbose
```

This will show all network messages being sent/received.

## References

- LSNP RFC Specification
- RFC 4648 - Base64 Encoding
- UDP Protocol Documentation
