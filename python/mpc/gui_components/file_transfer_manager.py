"""File transfer manager for exchanging timestamp files between peer sites."""

import logging
import base64
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class FileTransferManager:
    """Manages file transfer operations between peer sites."""
    
    def __init__(self, peer_connection=None, plot_updater=None, status_callback: Optional[Callable] = None):
        """
        Initialize file transfer manager.
        
        Args:
            peer_connection: PeerConnection instance for network communication
            plot_updater: PlotUpdater instance to get saved file information
            status_callback: Optional callback for status updates (text, color)
        """
        self.peer_connection = peer_connection
        self.plot_updater = plot_updater
        self.status_callback = status_callback
        
        # Remote files directory
        self.remote_dir = Path.home() / "Documents" / "AgodSolt" / "data" / "remote"
        self.remote_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"FileTransferManager initialized, remote dir: {self.remote_dir}")
    
    def update_status(self, text: str, color: str = 'black'):
        """Update transfer status display."""
        if self.status_callback:
            try:
                self.status_callback(text, color)
            except Exception as e:
                logger.error(f"Error updating status: {e}")
    
    def request_remote_files(self):
        """Request timestamp files from remote peer."""
        if not self.peer_connection or not self.peer_connection.is_connected():
            self.update_status("❌ No peer connection", 'red')
            logger.error("Cannot request files - no peer connection")
            return False
        
        self.update_status("📤 Requesting files...", 'blue')
        
        try:
            # Request peer to send their saved timestamp files
            success = self.peer_connection.send_command('FILE_TRANSFER_REQUEST', {})
            if success:
                logger.info("Sent FILE_TRANSFER_REQUEST to peer")
                return True
            else:
                self.update_status("❌ Failed to send request", 'red')
                return False
        except Exception as e:
            logger.error(f"Failed to request files from peer: {e}")
            self.update_status(f"❌ Request failed: {e}", 'red')
            return False
    
    def handle_transfer_request(self, data: dict):
        """Handle file transfer request from peer - send our saved timestamp files."""
        try:
            logger.info("Received FILE_TRANSFER_REQUEST from peer")
            
            # Get list of saved files from plot_updater
            if not self.plot_updater:
                logger.error("No plot_updater available")
                self._send_transfer_complete(False, "No plot_updater available")
                return
            
            saved_files = getattr(self.plot_updater, 'acquisition_ids', {})
            if not saved_files:
                logger.warning("No saved files to transfer")
                self._send_transfer_complete(False, "No files available")
                return
            
            # Send each file
            files_sent = 0
            for channel, acq_info in saved_files.items():
                if not isinstance(acq_info, dict):
                    continue
                    
                filepath = acq_info.get('filepath')
                if not filepath or not Path(filepath).exists():
                    logger.warning(f"File not found for channel {channel}: {filepath}")
                    continue
                
                # Read file and send
                logger.info(f"Sending file: {filepath}")
                try:
                    with open(filepath, 'rb') as f:
                        file_data = f.read()
                    
                    # Encode as base64 for JSON transport
                    encoded_data = base64.b64encode(file_data).decode('ascii')
                    
                    self.peer_connection.send_command('FILE_TRANSFER_DATA', {
                        'channel': channel,
                        'filename': Path(filepath).name,
                        'data': encoded_data,
                        'size': len(file_data)
                    })
                    logger.info(f"Sent {len(file_data)} bytes for channel {channel}")
                    files_sent += 1
                except Exception as e:
                    logger.error(f"Error sending file for channel {channel}: {e}")
            
            # Send completion message
            self._send_transfer_complete(files_sent > 0, None, files_sent)
            logger.info(f"File transfer complete - sent {files_sent} files")
            
        except Exception as e:
            logger.error(f"Error handling file transfer request: {e}")
            self._send_transfer_complete(False, str(e))
    
    def handle_transfer_data(self, data: dict):
        """Handle receiving file data from peer."""
        try:
            channel = data.get('channel')
            filename = data.get('filename')
            encoded_data = data.get('data')
            size = data.get('size')
            
            logger.info(f"Receiving file for channel {channel}: {filename} ({size} bytes)")
            
            # Decode file data
            file_data = base64.b64decode(encoded_data)
            
            # Save to remote files directory
            output_path = self.remote_dir / filename
            with open(output_path, 'wb') as f:
                f.write(file_data)
            
            logger.info(f"Saved remote file to: {output_path}")
            
            # Format size nicely
            size_mb = size / (1024 * 1024)
            if size_mb >= 1:
                size_str = f"{size_mb:.1f} MB"
            else:
                size_kb = size / 1024
                size_str = f"{size_kb:.1f} KB"
            
            self.update_status(f"📥 Received Ch{channel} ({size_str})", 'green')
            
        except Exception as e:
            logger.error(f"Error handling file transfer data: {e}")
            self.update_status(f"❌ Error receiving file: {e}", 'red')
    
    def handle_transfer_complete(self, data: dict):
        """Handle file transfer completion notification."""
        try:
            success = data.get('success', False)
            num_files = data.get('num_files', 0)
            error = data.get('error')
            
            if success:
                logger.info(f"File transfer complete: {num_files} files received")
                self.update_status(f"✅ Transfer complete ({num_files} files)", 'green')
            else:
                logger.error(f"File transfer failed: {error}")
                self.update_status(f"❌ Transfer failed: {error}", 'red')
        except Exception as e:
            logger.error(f"Error handling transfer complete: {e}")
    
    def _send_transfer_complete(self, success: bool, error: str = None, num_files: int = 0):
        """Send transfer completion message to peer."""
        if self.peer_connection and self.peer_connection.is_connected():
            try:
                self.peer_connection.send_command('FILE_TRANSFER_COMPLETE', {
                    'success': success,
                    'num_files': num_files,
                    'error': error
                })
            except Exception as e:
                logger.error(f"Error sending transfer complete: {e}")
    
    def get_remote_files(self) -> list:
        """Get list of received remote timestamp files."""
        if not self.remote_dir.exists():
            return []
        
        files = list(self.remote_dir.glob("timestamps_*.bin"))
        return sorted(files)
    
    def clear_remote_files(self):
        """Clear all remote timestamp files."""
        try:
            for file in self.get_remote_files():
                file.unlink()
                logger.info(f"Deleted remote file: {file}")
        except Exception as e:
            logger.error(f"Error clearing remote files: {e}")
