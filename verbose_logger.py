"""
Verbose Logger for LSNP Protocol
Provides comprehensive logging of all network messages and protocol actions
with scrollable, non-blocking interface and human-readable format.
"""

import threading
import time
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import deque


class VerboseLogger:
    """
    A scrollable, non-blocking verbose logger for LSNP protocol messages.
    Logs all network messages with full content and color-coded prefixes.
    """
    
    def __init__(self, max_logs: int = 1000):
        """Initialize the verbose logger."""
        self.enabled = False
        self.max_logs = max_logs
        self.logs = deque(maxlen=max_logs)
        self.lock = threading.Lock()
        
        # Color codes for different message types
        self.colors = {
            'SEND': '\033[94m',      # Blue
            'RECV': '\033[92m',      # Green
            'ERROR': '\033[91m',     # Red
            'INFO': '\033[93m',      # Yellow
            'RESET': '\033[0m'       # Reset color
        }
        
        # Statistics
        self.stats = {
            'total_messages': 0,
            'sent_messages': 0,
            'received_messages': 0,
            'error_messages': 0,
            'info_messages': 0
        }
    
    def enable(self):
        """Enable verbose logging."""
        self.enabled = True
        self.log_info("Verbose logging enabled")
    
    def disable(self):
        """Disable verbose logging."""
        if self.enabled:
            self.log_info("Verbose logging disabled")
        self.enabled = False
    
    def is_enabled(self):
        """Check if verbose logging is enabled."""
        return self.enabled
    
    def _format_message(self, prefix: str, message_dict: Dict[str, Any], direction: str = "") -> str:
        """Format a message dictionary for logging."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        color = self.colors.get(prefix, '')
        reset = self.colors['RESET']
        
        # Format the message dictionary as readable key-value pairs
        message_str = ""
        for key, value in message_dict.items():
            message_str += f"  {key}: {value}\n"
        
        # Create the log entry
        log_entry = f"[{timestamp}] {color}{prefix}{reset}"
        if direction:
            log_entry += f" {direction}"
        log_entry += f"\n{message_str}"
        
        return log_entry
    
    def _add_log(self, log_entry: str, log_type: str):
        """Add a log entry to the internal storage."""
        if not self.enabled:
            return
            
        with self.lock:
            self.logs.append({
                'timestamp': datetime.now(),
                'entry': log_entry,
                'type': log_type
            })
            self.stats['total_messages'] += 1
            if log_type in self.stats:
                self.stats[f'{log_type}_messages'] += 1
    
    def log_send(self, message_dict: Dict[str, Any], destination: str = ""):
        """Log an outgoing message."""
        if not self.enabled:
            return
            
        direction = f"to {destination}" if destination else ""
        log_entry = self._format_message("SEND", message_dict, direction)
        self._add_log(log_entry, "sent")
        print(log_entry)
    
    def log_receive(self, message_dict: Dict[str, Any], source: str = ""):
        """Log an incoming message."""
        if not self.enabled:
            return
            
        direction = f"from {source}" if source else ""
        log_entry = self._format_message("RECV", message_dict, direction)
        self._add_log(log_entry, "received")
        print(log_entry)
    
    def log_error(self, message: str, details: Dict[str, Any] = None):
        """Log an error message."""
        if not self.enabled:
            return
            
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        color = self.colors['ERROR']
        reset = self.colors['RESET']
        
        log_entry = f"[{timestamp}] {color}ERROR{reset} {message}"
        if details:
            log_entry += "\n"
            for key, value in details.items():
                log_entry += f"  {key}: {value}\n"
        
        self._add_log(log_entry, "error")
        print(log_entry)
    
    def log_info(self, message: str, details: Dict[str, Any] = None):
        """Log an informational message."""
        if not self.enabled:
            return
            
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        color = self.colors['INFO']
        reset = self.colors['RESET']
        
        log_entry = f"[{timestamp}] {color}INFO{reset} {message}"
        if details:
            log_entry += "\n"
            for key, value in details.items():
                log_entry += f"  {key}: {value}\n"
        
        self._add_log(log_entry, "info")
        print(log_entry)
    
    def get_logs(self, count: int = None) -> List[str]:
        """Get recent logs."""
        with self.lock:
            logs = list(self.logs)
            if count:
                logs = logs[-count:]
            return [log['entry'] for log in logs]
    
    def get_stats(self) -> Dict[str, int]:
        """Get logging statistics."""
        with self.lock:
            return self.stats.copy()
    
    def search_logs(self, query: str, case_sensitive: bool = False) -> List[str]:
        """Search logs for a specific query."""
        with self.lock:
            results = []
            search_query = query if case_sensitive else query.lower()
            
            for log in self.logs:
                entry = log['entry']
                search_text = entry if case_sensitive else entry.lower()
                
                if search_query in search_text:
                    results.append(entry)
            
            return results
    
    def clear_logs(self):
        """Clear all logs."""
        with self.lock:
            self.logs.clear()
            self.stats = {
                'total_messages': 0,
                'sent_messages': 0,
                'received_messages': 0,
                'error_messages': 0,
                'info_messages': 0
            }
        
        if self.enabled:
            self.log_info("Logs cleared")
    
    def export_logs(self, filename: str = None) -> str:
        """Export logs to a file."""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"lsnp_verbose_logs_{timestamp}.txt"
        
        with self.lock:
            logs = list(self.logs)
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"LSNP Verbose Logs Export\n")
                f.write(f"Generated: {datetime.now().isoformat()}\n")
                f.write(f"Total logs: {len(logs)}\n")
                f.write("=" * 50 + "\n\n")
                
                for log in logs:
                    # Remove color codes for file export
                    clean_entry = log['entry']
                    for color in self.colors.values():
                        clean_entry = clean_entry.replace(color, '')
                    f.write(clean_entry + "\n\n")
            
            return filename
        except Exception as e:
            self.log_error(f"Failed to export logs to {filename}", {"error": str(e)})
            return None
    
    def set_log_file(self, filename: str = None):
        """Set a file to continuously log to (in addition to console)."""
        # This is a placeholder for file logging functionality
        # Could be implemented if needed
        if filename:
            self.log_info(f"Log file set to: {filename}")
        else:
            self.log_info("Log file disabled")
    
    def shutdown(self):
        """Shutdown the logger."""
        if self.enabled:
            self.log_info("Verbose logger shutting down")
        self.enabled = False
    
    def show_logs(self, count: int = 20):
        """Display recent logs to console."""
        logs = self.get_logs(count)
        if not logs:
            print("No logs available.")
            return
        
        print(f"\n=== Recent Logs (last {len(logs)}) ===")
        for log in logs:
            print(log)
        print("=" * 30 + "\n")
    
    def show_stats(self):
        """Display logging statistics."""
        stats = self.get_stats()
        print(f"\n=== Verbose Logging Statistics ===")
        print(f"Total messages: {stats['total_messages']}")
        print(f"Sent messages: {stats['sent_messages']}")
        print(f"Received messages: {stats['received_messages']}")
        print(f"Error messages: {stats['error_messages']}")
        print(f"Info messages: {stats['info_messages']}")
        print(f"Log capacity: {self.max_logs}")
        print("=" * 30 + "\n")
    
    def search_logs_display(self, query: str, max_results: int = 10):
        """Search logs and display results."""
        results = self.search_logs(query)
        if not results:
            print(f"No logs found matching '{query}'")
            return
        
        display_results = results[:max_results] if max_results else results
        print(f"\n=== Search Results for '{query}' ({len(display_results)}/{len(results)}) ===")
        for result in display_results:
            print(result)
            print("-" * 30)
        print("=" * 30 + "\n")
