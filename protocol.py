"""
Protocol handler for the peer-to-peer network communication.
Implements the key-value format with "KEY: VALUE" separator and "\n\n" terminator.
"""

class ProtocolHandler:
    """Handles message formatting and parsing according to the protocol specification."""
    
    @staticmethod
    def format_message(**kwargs):
        """Format a message according to the protocol: KEY: VALUE format with \n\n terminator."""
        lines = []
        for key, value in kwargs.items():
            lines.append(f"{key.upper()}: {value}")
        return "\n".join(lines) + "\n\n"
    
    @staticmethod
    def parse_message(message):
        """Parse a received message into a dictionary of key-value pairs."""
        result = {}
        lines = message.strip().split('\n')
        for line in lines:
            if ':' in line:
                key, value = line.split(':', 1)
                result[key.strip().upper()] = value.strip()
        return result
    
    @staticmethod
    def validate_message(message):
        """Validate that a message follows the protocol format."""
        if not message or not isinstance(message, str):
            return False
            
        if not message.endswith('\n\n'):
            return False
        
        lines = message.strip().split('\n')
        if not lines:
            return False
            
        # Must have at least a TYPE field
        has_type = False
        for line in lines:
            if line.strip():  # Skip empty lines
                if ':' not in line:
                    return False
                key, _ = line.split(':', 1)
                if key.strip().upper() == 'TYPE':
                    has_type = True
        
        return has_type
