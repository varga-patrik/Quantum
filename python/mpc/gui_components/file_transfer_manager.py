"""File transfer manager for exchanging timestamp files between peer sites."""

import logging
import base64
from pathlib import Path
from typing import Optional, Callable
import time

logger = logging.getLogger(__name__)

# File transfer settings
CHUNK_SIZE = 256 * 1024  # 256 KB chunks for reliable transfer
CHUNK_DELAY_MS = 10  # Small delay between chunks to avoid flooding


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
        
        # Track incoming file chunks
        self.incoming_files = {}  # transfer_id -> {'filename', 'channel', 'total_chunks', 'chunks', 'size'}
        
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
            
            # Filter out temporary files (only send files marked for saving)
            files_to_send = {}
            for channel, acq_info in saved_files.items():
                if not isinstance(acq_info, dict):
                    continue
                
                # Skip temporary files
                if acq_info.get('is_temp', False):
                    logger.debug(f"Skipping temp file for channel {channel}")
                    continue
                    
                filepath = acq_info.get('filepath')
                if filepath and Path(filepath).exists():
                    files_to_send[channel] = filepath
            
            if not files_to_send:
                logger.warning("No saved files to transfer (all files are temporary)")
                self._send_transfer_complete(False, "No saved files available")
                return
            
            # Send each file in chunks
            files_sent = 0
            for channel, filepath in files_to_send.items():
                # Add delay between files to allow receiver to process
                if files_sent > 0:
                    logger.info("Waiting 500ms before next file for flow control...")
                    time.sleep(0.5)  # 500ms delay between files
                
                logger.info(f"Sending file: {filepath}")
                try:
                    # Skip empty files
                    file_size = Path(filepath).stat().st_size
                    if file_size == 0:
                        logger.warning(f"Skipping empty file for channel {channel}: {filepath}")
                        continue
                    
                    if self._send_file_chunked(channel, Path(filepath)):
                        files_sent += 1
                    else:
                        logger.error(f"Failed to send file for channel {channel}")
                except Exception as e:
                    logger.error(f"Error sending file for channel {channel}: {e}")
            
            # Send completion message
            self._send_transfer_complete(files_sent > 0, None, files_sent)
            logger.info(f"File transfer complete - sent {files_sent} files")
            
        except Exception as e:
            logger.error(f"Error handling file transfer request: {e}")
            self._send_transfer_complete(False, str(e))
    
    def _send_file_chunked(self, channel: int, filepath: Path) -> bool:
        """Send a file in chunks to avoid timeouts."""
        try:
            file_size = filepath.stat().st_size
            
            # Handle empty files
            if file_size == 0:
                logger.warning(f"File {filepath.name} is empty, skipping transfer")
                return False
            
            num_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE  # Ceiling division
            transfer_id = f"{channel}_{filepath.name}_{int(time.time())}"
            
            logger.info(f"Sending file {filepath.name} ({file_size} bytes) in {num_chunks} chunks")
            
            # Send file start metadata
            if not self.peer_connection.send_command('FILE_TRANSFER_START', {
                'transfer_id': transfer_id,
                'channel': channel,
                'filename': filepath.name,
                'size': file_size,
                'num_chunks': num_chunks
            }):
                logger.error("Failed to send FILE_TRANSFER_START")
                return False
            
            # Send file in chunks
            with open(filepath, 'rb') as f:
                for chunk_index in range(num_chunks):
                    chunk_data = f.read(CHUNK_SIZE)
                    encoded_chunk = base64.b64encode(chunk_data).decode('ascii')
                    
                    success = self.peer_connection.send_command('FILE_TRANSFER_CHUNK', {
                        'transfer_id': transfer_id,
                        'chunk_index': chunk_index,
                        'data': encoded_chunk
                    })
                    
                    if not success:
                        logger.error(f"Failed to send chunk {chunk_index}/{num_chunks}")
                        return False
                    
                    # Small delay to avoid flooding
                    if CHUNK_DELAY_MS > 0:
                        time.sleep(CHUNK_DELAY_MS / 1000.0)
                    
                    # Log progress every 10 chunks or at the end
                    if (chunk_index + 1) % 10 == 0 or chunk_index == num_chunks - 1:
                        logger.info(f"Progress: {chunk_index + 1}/{num_chunks} chunks sent")
            
            # Send file end marker
            if not self.peer_connection.send_command('FILE_TRANSFER_END', {
                'transfer_id': transfer_id
            }):
                logger.error("Failed to send FILE_TRANSFER_END")
                return False
            
            logger.info(f"File {filepath.name} sent successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error in _send_file_chunked: {e}")
            return False
    
    def handle_transfer_start(self, data: dict):
        """Handle start of chunked file transfer."""
        try:
            transfer_id = data.get('transfer_id')
            channel = data.get('channel')
            filename = data.get('filename')
            size = data.get('size')
            num_chunks = data.get('num_chunks')
            
            logger.info(f"Starting file transfer: {filename} ({size} bytes, {num_chunks} chunks)")
            
            # Initialize tracking for this transfer
            self.incoming_files[transfer_id] = {
                'channel': channel,
                'filename': filename,
                'size': size,
                'num_chunks': num_chunks,
                'chunks': {},  # chunk_index -> data
                'start_time': time.time()
            }
            
            # Format size nicely
            size_mb = size / (1024 * 1024)
            if size_mb >= 1:
                size_str = f"{size_mb:.1f} MB"
            else:
                size_kb = size / 1024
                size_str = f"{size_kb:.1f} KB"
            
            self.update_status(f"📥 Receiving Ch{channel}: {size_str}...", 'blue')
            
        except Exception as e:
            logger.error(f"Error handling transfer start: {e}")
    
    def handle_transfer_chunk(self, data: dict):
        """Handle receiving a file chunk."""
        try:
            transfer_id = data.get('transfer_id')
            chunk_index = data.get('chunk_index')
            chunk_data = data.get('data')
            
            if transfer_id not in self.incoming_files:
                logger.error(f"Received chunk for unknown transfer: {transfer_id}")
                return
            
            # Store chunk
            transfer = self.incoming_files[transfer_id]
            transfer['chunks'][chunk_index] = chunk_data
            
            # Log progress
            received = len(transfer['chunks'])
            total = transfer['num_chunks']
            if received % 10 == 0 or received == total:
                logger.info(f"Received {received}/{total} chunks for {transfer['filename']}")
                percent = int(100 * received / total)
                self.update_status(f"📥 Ch{transfer['channel']}: {percent}% ({received}/{total})", 'blue')
            
        except Exception as e:
            logger.error(f"Error handling transfer chunk: {e}")
    
    def handle_transfer_end(self, data: dict):
        """Handle end of chunked file transfer - assemble and save file."""
        try:
            transfer_id = data.get('transfer_id')
            
            if transfer_id not in self.incoming_files:
                logger.error(f"Received end for unknown transfer: {transfer_id}")
                return
            
            transfer = self.incoming_files[transfer_id]
            
            # Check if we have all chunks
            if len(transfer['chunks']) != transfer['num_chunks']:
                logger.error(f"Missing chunks: got {len(transfer['chunks'])}/{transfer['num_chunks']}")
                self.update_status(f"❌ Transfer incomplete", 'red')
                del self.incoming_files[transfer_id]
                return
            
            # Ensure remote directory exists
            self.remote_dir.mkdir(parents=True, exist_ok=True)
            
            # Assemble file from chunks (in background to avoid blocking)
            logger.info(f"Assembling file {transfer['filename']} from {transfer['num_chunks']} chunks")
            file_data = b''
            for i in range(transfer['num_chunks']):
                chunk_encoded = transfer['chunks'][i]
                chunk_decoded = base64.b64decode(chunk_encoded)
                file_data += chunk_decoded
            
            # Verify size
            if len(file_data) != transfer['size']:
                logger.error(f"Size mismatch: expected {transfer['size']}, got {len(file_data)}")
                self.update_status(f"❌ Size mismatch", 'red')
                del self.incoming_files[transfer_id]
                return
            
            # Save to file
            output_path = self.remote_dir / transfer['filename']
            with open(output_path, 'wb') as f:
                f.write(file_data)
            
            elapsed = time.time() - transfer['start_time']
            logger.info(f"Saved remote file to: {output_path} (took {elapsed:.1f}s)")
            
            # Format size nicely
            size_mb = transfer['size'] / (1024 * 1024)
            if size_mb >= 1:
                size_str = f"{size_mb:.1f} MB"
            else:
                size_kb = transfer['size'] / 1024
                size_str = f"{size_kb:.1f} KB"
            
            self.update_status(f"✅ Ch{transfer['channel']}: {size_str} saved", 'green')
            
            # Cleanup
            del self.incoming_files[transfer_id]
            
        except Exception as e:
            logger.error(f"Error handling transfer end: {e}")
            import traceback
            traceback.print_exc()
            self.update_status(f"❌ Error: {e}", 'red')
    
    def handle_transfer_data(self, data: dict):
        """Handle receiving file data (legacy single-chunk method - deprecated)."""
        try:
            channel = data.get('channel')
            filename = data.get('filename')
            encoded_data = data.get('data')
            size = data.get('size')
            
            logger.info(f"Receiving file (legacy mode) for channel {channel}: {filename} ({size} bytes)")
            
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
