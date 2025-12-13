"""
Logging utilities for Streamlit webapp
"""
import logging
import streamlit as st
import time
import html as html_module


from streamlit.errors import NoSessionContext

class StreamlitLogHandler(logging.Handler):
    """
    Custom logging handler that captures log messages and sends them to a ProgressAnimator.
    """

    def __init__(self, progress_animator):
        """
        Initialize the handler.

        Args:
            progress_animator: ProgressAnimator instance to send logs to
        """
        super().__init__()
        self.progress_animator = progress_animator

    def emit(self, record):
        """
        Emit a log record.

        Args:
            record: LogRecord to emit
        """
        # Don't emit if animator is cleared/inactive
        if not self.progress_animator or not self.progress_animator.container:
            return

        try:
            # Check for Streamlit context before attempting to write to UI
            # This prevents "Thread-1: missing ScriptRunContext!" warnings from background threads
            # that shouldn't be writing to the UI anyway
            try:
                # Try new location (Streamlit 1.38+)
                from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx
                if not get_script_run_ctx(suppress_warning=True):
                    return
            except ImportError:
                try:
                    # Try old location (Streamlit < 1.38)
                    from streamlit.runtime.scriptrunner.script_run_context import get_script_run_ctx
                    # Old versions might not have suppress_warning, but it's worth a shot or check signature
                    # If it fails with TypeError, we catch it? No, get_script_run_ctx takes no args in very old versions.
                    # But 1.50 is what we have.
                    pass 
                    # Let's keep it simple for the old catch block, we know 1.50 has it.
                    # For safety, I'll use try/except TypeError in the inner block just in case.
                    try:
                         if not get_script_run_ctx(suppress_warning=True):
                             return
                    except TypeError:
                         if not get_script_run_ctx():
                             return
                except ImportError:
                    pass

            # Format the log message
            msg = self.format(record)
            # Send to progress animator
            self.progress_animator.add_log(msg)
        except NoSessionContext:
            # Ignore logs from background threads that don't have a Streamlit context
            # This prevents "NoSessionContext" errors when using ThreadPoolExecutor
            pass
        except Exception as e:
            # Suppress "Event loop is closed" errors which happen during shutdown
            if "Event loop is closed" in str(e):
                return
            self.handleError(record)


class ProgressAnimator:
    """
    Animated progress indicator that displays messages with pulsing effects.
    Each message appears at 100% visibility, then pulses (80% -> 100%) until replaced.
    """

    def __init__(self, container=None):
        """
        Initialize the progress animator.

        Args:
            container: Streamlit container to use. If None, creates a new empty container.
        """
        self.container = container if container is not None else st.empty()
        self.current_message = None
        self.current_emoji = None
        self.logs = []
        self.max_logs = 50  # Keep last 50 log entries

    def add_log(self, message: str):
        """
        Add a log message to the display.

        Args:
            message: The log message to add
        """
        self.logs.append(message)
        # Keep only the last max_logs entries
        if len(self.logs) > self.max_logs:
            self.logs = self.logs[-self.max_logs:]
        # Re-render with the new log
        self._render()

    def show(self, message: str, emoji: str = "🔍", url: str = None):
        """
        Display an animated progress message that pulses until next update.

        Args:
            message: The progress message to display (will be truncated if too long)
            emoji: Emoji to show with the message
            url: Optional URL to display below the message (shown at 40% opacity)
        """
        # Truncate message if too long (keep it concise for animation effect)
        max_length = 120
        if len(message) > max_length:
            message = message[:max_length-3] + "..."

        self.current_message = message
        self.current_emoji = emoji
        self.current_url = url

        self._render()

    def _render(self):
        """Internal method to render the current state."""
        if not self.container:
            return

        # Build URL display if provided
        url_html = ""
        if hasattr(self, 'current_url') and self.current_url:
            # Truncate URL for display
            display_url = self.current_url if len(self.current_url) <= 80 else self.current_url[:77] + "..."
            display_url = html_module.escape(display_url)
            url_html = f'<div class="progress-urls">{display_url}</div>'

        # Build logs display
        logs_html = ""
        if self.logs:
            # Get the last log and intelligently truncate it
            last_log = self.logs[-1]
            processed_log = self._process_log_message(last_log)
            safe_log = html_module.escape(processed_log)
            logs_html = f'<div class="progress-logs"><div class="progress-log-entry">{safe_log}</div></div>'

        # Escape message and emoji
        safe_message = html_module.escape(self.current_message) if self.current_message else ""
        safe_emoji = html_module.escape(self.current_emoji) if self.current_emoji else ""

        # Display with pulsing animation (stays visible until next call)
        html = f"""
        <div class="progress-container">
            <div class="progress-item progress-item-pulsing">
                <span class="progress-emoji">{safe_emoji}</span>
                <span>{safe_message}</span>
            </div>
            {url_html}
            {logs_html}
        </div>
        """

        try:
            self.container.html(html)
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                pass
            else:
                raise e
        except Exception:
            pass

    def _process_log_message(self, log_message: str) -> str:
        """
        Process a log message to make it display-friendly.
        
        Intelligently truncates long messages while preserving:
        - Timestamps
        - Logger names
        - Log levels (WARNING, ERROR, INFO)
        - Meaningful message content
        
        Args:
            log_message: Raw log message from the logger
            
        Returns:
            Processed log message suitable for display
        """
        import re
        
        # Pattern to match standard log format: timestamp - logger - level - message
        # Handle both comma and period in timestamp (e.g., "22:08:24,779" or "22:08:24.779")
        log_pattern = r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-\s*([^\s]+)\s*-\s*(\w+)\s*-\s*(.+)$'
        
        match = re.match(log_pattern, log_message)
        if match:
            timestamp, logger_name, level, message = match.groups()
            
            # For very long messages, show only the most relevant part
            # Priority: show warnings/errors in full, truncate info messages
            if level in ['WARNING', 'ERROR', 'CRITICAL']:
                # Keep warnings/errors mostly intact, just limit extreme length
                max_message_length = 200
            else:
                # For INFO/DEBUG, be more aggressive with truncation
                max_message_length = 100
                
                # If message contains query string, truncate it
                if 'query=' in message.lower():
                    # Find the query portion and truncate it
                    query_pattern = r'(query=)([^,\)]+)'
                    query_match = re.search(query_pattern, message, re.IGNORECASE)
                    if query_match:
                        prefix_text = message[:query_match.start()]
                        query_prefix = query_match.group(1)
                        query_value = query_match.group(2)
                        suffix_text = message[query_match.end():]
                        
                        # Truncate the query value if it's too long
                        max_query_length = 40
                        if len(query_value) > max_query_length:
                            query_value = query_value[:max_query_length] + "..."
                        
                        # Reconstruct the message
                        message = prefix_text + query_prefix + query_value + suffix_text
            
            # Final truncation if still too long
            if len(message) > max_message_length:
                message = message[:max_message_length] + "..."
            
            # Reconstruct the log with all components
            return f"{timestamp} - {logger_name} - {level} - {message}"
        else:
            # If it doesn't match the expected format, just truncate the whole thing
            max_length = 150
            if len(log_message) > max_length:
                return log_message[:max_length] + "..."
            return log_message

    def clear(self):
        """Clear the progress display and deactivate the animator."""
        if self.container:
            self.container.empty()
        self.container = None
        self.current_message = None
        self.current_emoji = None
        self.logs = []



