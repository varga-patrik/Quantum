import tkinter as tk
from tkinter import ttk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import logging
import json
import os
import time
from datetime import datetime
import numpy as np

# Suppress matplotlib debug logging (not part of this app)
logging.getLogger('matplotlib').setLevel(logging.WARNING)
logging.getLogger('PIL').setLevel(logging.WARNING)

from gui_components import (
    DEFAULT_TC_ADDRESS, SERVER_TC_ADDRESS, CLIENT_TC_ADDRESS,
    SERVER_FS740_ADDRESS, CLIENT_FS740_ADDRESS,
    DEFAULT_ACQ_DURATION, DEFAULT_BIN_WIDTH,
    DEFAULT_BIN_COUNT, DEFAULT_HISTOGRAMS, BG_COLOR, FG_COLOR,
    HIGHLIGHT_COLOR, PRIMARY_COLOR, ACTION_COLOR, 
    DEFAULT_LOCAL_SERIALS, DEFAULT_REMOTE_SERIALS,
    format_number, PlotUpdater, OptimizerRowExtended
)
from gui_components.file_transfer_manager import FileTransferManager
from gui_components.peer_command_handlers import PeerCommandHandlers
from gui_components.time_offset_tab import TimeOffsetTab
from gui_components.offline_correlation_tab import OfflineCorrelationTab
from mock_time_controller import MockTimeController, is_mock_controller
from peer_connection import PeerConnection
from connection_dialog import show_connection_dialog

logger = logging.getLogger(__name__)


class App:
    """Main application class for the GUI."""

    # Backward-compat aliases — other tabs read/write time_offset_ps
    @property
    def time_offset_ps(self):
        return self.time_offsets_ps[0] if hasattr(self, 'time_offsets_ps') else None

    @time_offset_ps.setter
    def time_offset_ps(self, value):
        if hasattr(self, 'time_offsets_ps'):
            self.time_offsets_ps[0] = value

    @property
    def time_offset_updated(self):
        return self.time_offsets_updated[0] if hasattr(self, 'time_offsets_updated') else None

    @time_offset_updated.setter
    def time_offset_updated(self, value):
        if hasattr(self, 'time_offsets_updated'):
            self.time_offsets_updated[0] = value

    def __init__(self, root):
        self.root = root
        self.root.title("Eszköz optimalizáló")

        # Apply theme colors
        self.bg_color = BG_COLOR
        self.fg_color = FG_COLOR
        self.highlight_color = HIGHLIGHT_COLOR
        self.primary_color = PRIMARY_COLOR
        self.action_color = ACTION_COLOR

        # Peer-to-peer connection
        self.peer_connection: PeerConnection = None
        self.connection_status_label = None
        self.computer_role = "computer_a"  # Default role
        
        # Correlation pairs: (source_a, ch_a, source_b, ch_b, offset_idx)
        # source is "L" (local buffer) or "R" (remote buffer)
        # offset_idx is 0..3 (which of the four offsets to use)
        # For cross-site: ("L", 1, "R", 1, 0)  →  local ch1 vs remote ch1, offset 1
        # For local loop: ("L", 1, "L", 3, 0)  →  local ch1 vs local ch3, offset 1
        self.correlation_pairs = [
            ("L", 1, "L", 3, 0),  # Local-1 ↔ Local-3, Offset 1
            ("L", 1, "L", 4, 1),  # Local-1 ↔ Local-4, Offset 2
        ]
        
        # Time offset configuration (measured by C++ correlator)
        # Four independent offsets — each correlation pair selects which to use
        self.time_offsets_ps = [None, None, None, None]
        self.time_offsets_updated = [None, None, None, None]
        self._load_time_offset()
        
        # Show connection dialog
        self._setup_peer_connection()
        


        # Initialize Time Controller
        self.tc = self._connect_time_controller()
        
        # Optimizer rows state
        self.optim_rows = {}

        # Setup UI layout
        self._setup_layout()
        self._build_connection_status()
        self._build_status_indicator()
        self._build_notebook()
        self._build_plot_frame()
        self._build_plot_tab()
        self._build_polarizer_tab()
        self._build_gps_sync_tab()
        self._build_time_offset_tab()
        self._build_offline_correlation_tab()

        # Auto-start counter display (for singles rates monitoring)
        # This starts the background loop that reads detector counters
        # The actual streaming/correlation needs to be started manually with "Start" button
        if hasattr(self, 'plot_updater') and self.plot_updater:
            self.plot_updater.start_counter_display()
            logger.info("Auto-started detector counter display")

        # Graceful shutdown handler
        self._after_id = None
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_peer_connection(self):
        """Setup peer-to-peer connection via dialog."""
        config = show_connection_dialog(self.root)
        
        if config and config.get('enabled'):
            role = config.get('role')
            
            # Map network role to device role and set hardware addresses
            # Server (static IP, Wigner) = Computer A devices
            # Client (behind NAT, BME) = Computer B devices
            if role == "server":
                self.computer_role = "computer_a"
                self.tc_address = SERVER_TC_ADDRESS
                self.fs740_address = SERVER_FS740_ADDRESS
            else:
                self.computer_role = "computer_b"
                self.tc_address = CLIENT_TC_ADDRESS
                self.fs740_address = CLIENT_FS740_ADDRESS
            
            try:
                # For server: bind to 0.0.0.0 (all interfaces)
                # For client: connect to the provided server IP
                server_ip = "0.0.0.0" if role == "server" else config['server_ip']
                
                self.peer_connection = PeerConnection(
                    mode=role,
                    server_ip=server_ip,
                    port=config['port']
                )
                
                # Start connection (server listens, client connects)
                if self.peer_connection.start():
                    logger.info("Peer connection started successfully in %s mode", role)
                else:
                    logger.error("Failed to start peer connection")
                    self.peer_connection = None
                    
            except Exception as e:
                logger.error("Failed to setup peer connection: %s", e)
                self.peer_connection = None
        else:
            # Connection skipped - use hardware based on selected role
            self.peer_connection = None
            role = config.get('role', 'server') if config else 'server'
            
            if role == "server":
                self.computer_role = "computer_a"
                self.tc_address = SERVER_TC_ADDRESS
                self.fs740_address = SERVER_FS740_ADDRESS
            else:
                self.computer_role = "computer_b"
                self.tc_address = CLIENT_TC_ADDRESS
                self.fs740_address = CLIENT_FS740_ADDRESS
    
    def _get_config_path(self):
        """Get path to time offset configuration file (relative to main_gui.py)."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(script_dir, 'time_offset_config.json')
    
    def _load_time_offset(self):
        """Load time offsets from configuration file."""
        try:
            config_path = self._get_config_path()
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    data = json.load(f)
                    # Support both old single-offset and new multi-offset format
                    if 'offsets' in data:
                        for i, ofs in enumerate(data['offsets'][:4]):
                            self.time_offsets_ps[i] = ofs.get('offset_ps')
                            self.time_offsets_updated[i] = ofs.get('updated')
                    else:
                        # Old format: {"offset_ps": ..., "updated": ...}
                        self.time_offsets_ps[0] = data.get('offset_ps')
                        self.time_offsets_updated[0] = data.get('updated')
                    logger.info("Loaded time offsets: %s ps", self.time_offsets_ps)
        except Exception as e:
            logger.error("Failed to load time offset configuration: %s", e)
            self.time_offsets_ps = [None, None, None, None]
            self.time_offsets_updated = [None, None, None, None]
    
    def _save_time_offset(self):
        """Save time offsets to configuration file."""
        try:
            config_path = self._get_config_path()
            data = {
                'offsets': [
                    {'offset_ps': self.time_offsets_ps[i], 'updated': self.time_offsets_updated[i]}
                    for i in range(4)
                ],
                # Backward compat: keep top-level fields as offset 1
                'offset_ps': self.time_offsets_ps[0],
                'updated': self.time_offsets_updated[0]
            }
            with open(config_path, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("Saved time offsets: %s ps", self.time_offsets_ps)
        except Exception as e:
            logger.error("Failed to save time offset configuration: %s", e)
    
    def _connect_time_controller(self):
        """Connect to Time Controller and DLT service with fallback to mock."""
        from utils.common import connect, dlt_connect, adjust_bin_width
        from pathlib import Path
        
        # Use configured address based on computer role
        tc_addr = getattr(self, 'tc_address', DEFAULT_TC_ADDRESS)
        
        tc = None
        dlt = None
        try:
            # Connect to Time Controller
            tc = connect(tc_addr)
            self.bin_width = adjust_bin_width(tc, DEFAULT_BIN_WIDTH)
            logger.info("Connected to Time Controller at %s", tc_addr)
            
            # Connect to DataLink Target service for streaming
            output_dir = Path.home() / "Documents" / "AgodSolt" / "data"
            output_dir.mkdir(parents=True, exist_ok=True)
            dlt = dlt_connect(output_dir)
            logger.info("Connected to DLT service at localhost:6060")
            self.dlt = dlt
            
        except (ConnectionError, Exception) as e:
            logger.warning("Failed to connect to Time Controller/DLT: %s", e)
            # Use role-based site name for mock (matches connection dialog role)
            site_role = "SERVER" if self.computer_role == "computer_a" else "CLIENT"
            logger.info("Using MockTimeController with role: %s (address: %s)", site_role, tc_addr)
            tc = MockTimeController(site_name=site_role)
            self.bin_width = DEFAULT_BIN_WIDTH
            self.dlt = None
        
        return tc

    
    def _on_start_streaming(self):
        """Start streaming on both local and remote sites."""
        logger.info("Starting synchronized streaming on both sites")
        
        # Get recording duration (parse from text entry)
        duration_str = self.duration_var.get().strip()
        recording_duration_sec = None
        if duration_str:
            try:
                recording_duration_sec = int(duration_str)
                if recording_duration_sec <= 0:
                    recording_duration_sec = None
                else:
                    logger.info(f"Recording duration set to {recording_duration_sec} seconds")
            except ValueError:
                logger.warning(f"Invalid duration '{duration_str}', using unlimited")
                recording_duration_sec = None
        
        # Get save settings from checkboxes
        local_save_channels = [i+1 for i in range(4) if self.local_save_vars[i].get()]
        remote_save_channels = [i+1 for i in range(4) if self.remote_save_vars[i].get()] if self.remote_save_vars else []
        
        logger.info(f"Saving local channels: {local_save_channels}")
        logger.info(f"Saving remote channels: {remote_save_channels}")
        
        # Start local streaming with save settings and duration
        if hasattr(self, 'plot_updater') and self.plot_updater:
            self.plot_updater.start(local_save_channels=local_save_channels, 
                                   remote_save_channels=remote_save_channels,
                                   recording_duration_sec=recording_duration_sec)
        
        # Start recording timer display
        if recording_duration_sec:
            self.recording_start_time = time.time()
            self.recording_duration = recording_duration_sec
            self._update_recording_timer()
        
        # Send command to peer to start streaming (include duration)
        if self.peer_connection and self.peer_connection.is_connected():
            try:
                self.peer_connection.send_command('STREAMING_START', {
                    'duration_sec': recording_duration_sec
                })
                logger.info("Sent STREAMING_START command to peer")
            except Exception as e:
                logger.error(f"Failed to send STREAMING_START to peer: {e}")
        else:
            logger.warning("No peer connection - streaming locally only")
    
    def _on_stop_streaming(self, send_to_peer=True):
        """Stop streaming on both local and remote sites."""
        logger.info("Stopping synchronized streaming on both sites")
        
        # Clear recording timer
        self.recording_start_time = None
        self.recording_duration = None
        self.recording_timer_label.config(text="")
        
        # Stop local streaming (but keep counter display running)
        if hasattr(self, 'plot_updater') and self.plot_updater:
            self.plot_updater.stop_streaming()
        
        # Send command to peer to stop streaming (only if initiated locally)
        if send_to_peer and self.peer_connection and self.peer_connection.is_connected():
            try:
                self.peer_connection.send_command('STREAMING_STOP', {})
                logger.info("Sent STREAMING_STOP command to peer")
            except Exception as e:
                logger.error(f"Failed to send STREAMING_STOP to peer: {e}")
        
        # Auto-transfer files if checkbox is checked
        if hasattr(self, 'auto_transfer_var') and self.auto_transfer_var and self.auto_transfer_var.get():
            logger.info("Auto-transfer enabled - requesting remote files")
            # Delay slightly to ensure peer has finished writing files
            self.root.after(1000, self._request_remote_files)
    
    def _setup_layout(self):
        """Configure root window layout."""
        self.root.configure(background=self.primary_color)
        self.root.rowconfigure(0, weight=0)  # Connection status row
        self.root.rowconfigure(1, weight=0)  # Mock status bar row
        self.root.rowconfigure(2, weight=1)  # Main content row
        self.root.columnconfigure(0, weight=1)  # Only notebook column

    def _build_connection_status(self):
        """Build connection status indicator."""
        status_frame = tk.Frame(self.root, background='#2196F3', relief=tk.RAISED, bd=2)
        status_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 2))
        
        if self.peer_connection and self.peer_connection.is_connected():
            peer_ip = self.peer_connection.get_peer_ip()
            text = f"🔗 CONNECTED to peer: {peer_ip}"
            bg_color = '#4CAF50'  # Green
        elif self.peer_connection:
            text = "⏳ WAITING for peer connection..."
            bg_color = '#FF9800'  # Orange
        else:
            text = "⚠️ STANDALONE MODE: Peer connection disabled"
            bg_color = '#9E9E9E'  # Gray
        
        self.connection_status_label = tk.Label(
            status_frame,
            text=text,
            font=('Arial', 10, 'bold'),
            background=bg_color,
            foreground='white',
            pady=6
        )
        self.connection_status_label.pack(fill=tk.BOTH, expand=True)
        
        # Start periodic status update
        self._update_connection_status()
    
    def _update_connection_status(self):
        """Periodically update connection status."""
        if self.connection_status_label and self.connection_status_label.winfo_exists():
            if self.peer_connection and self.peer_connection.is_connected():
                peer_ip = self.peer_connection.get_peer_ip()
                text = f"🔗 CONNECTED to peer: {peer_ip}"
                bg_color = '#4CAF50'
            elif self.peer_connection:
                text = "⏳ WAITING for peer connection..."
                bg_color = '#FF9800'
            else:
                text = "⚠️ STANDALONE MODE: Peer connection disabled"
                bg_color = '#9E9E9E'
            
            self.connection_status_label.config(text=text, background=bg_color)
        
        if self.root.winfo_exists():
            self.root.after(1000, self._update_connection_status)
    
    def _build_status_indicator(self):
        """Build status indicator bar for mock mode."""
        if is_mock_controller(self.tc):
            # Get correlation mode from config
            from gui_components.config import MOCK_CORRELATION_MODE
            mode_text = "Cross-Site" if MOCK_CORRELATION_MODE == 'cross_site' else "Local Pairs"
            
            status_frame = tk.Frame(self.root, background='#ff9800', relief=tk.RAISED, bd=2)
            status_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 5))
            status_label = tk.Label(
                status_frame,
                text=f"⚠️ MOCK MODE: {mode_text} Correlations - Time Controller not connected",
                font=('Arial', 10, 'bold'),
                background='#ff9800',
                foreground='white',
                pady=8
            )
            status_label.pack(fill=tk.BOTH, expand=True)

    def _build_notebook(self):
        """Create tabbed notebook."""
        self.notebook = ttk.Notebook(self.root)
        self.tab_plot = ttk.Frame(self.notebook)
        self.tab_polarizer = ttk.Frame(self.notebook)
        self.tab_gps_sync = ttk.Frame(self.notebook)
        self.tab_time_offset = ttk.Frame(self.notebook)
        self.tab_offline_correlation = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_plot, text="Plotolás")
        self.notebook.add(self.tab_polarizer, text="Polarizáció kontroller")
        self.notebook.add(self.tab_gps_sync, text="GPS Szinkronizáció")
        self.notebook.add(self.tab_time_offset, text="Időeltolás Kalkulátor")
        self.notebook.add(self.tab_offline_correlation, text="Offline Korreláció")
        self.notebook.grid(row=2, column=0, sticky="news")

    def _build_plot_frame(self):
        """Create plot frame inside the first tab only."""
        # Create a container for the plot tab with left (controls) and right (plot) sections
        plot_container = tk.Frame(self.tab_plot, background='white')
        plot_container.pack(fill=tk.BOTH, expand=True)
        
        # Left section for controls
        left_frame = tk.Frame(plot_container, background='white')
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False)
        
        # Right section for plot
        self.plot_frame = tk.Frame(plot_container, background='white')
        self.plot_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Store left_frame as tab_plot_left for building controls
        self.tab_plot_left = left_frame


    def _build_plot_tab(self):
        """Build the plot tab with controls and live counters."""
        # Create matplotlib figure
        fig, ax = plt.subplots(figsize=(8, 8))
        ax.set_title('Koincidencia mérés')
        ax.set_xlabel('Adat')
        ax.set_ylabel('Beütések')
        ax.set_xticks(range(0, 20))
        ax.set_ylim([0, 4000])
        ax.set_facecolor(self.bg_color)
        ax.grid(color=self.highlight_color)

        canvas = FigureCanvasTkAgg(fig, master=self.plot_frame)
        canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)
        canvas.get_tk_widget().config(background='white')

        # Create plot updater
        self.plot_updater = PlotUpdater(
            fig, ax, canvas, self.tc,
            DEFAULT_ACQ_DURATION, self.bin_width,
            DEFAULT_BIN_COUNT, DEFAULT_HISTOGRAMS,
            peer_connection=self.peer_connection,
            app_ref=self  # Pass reference to access correlation pairs and remote data
        )
        
        # Initialize peer command handlers (for counter sync, optimization control, etc.)
        if self.peer_connection:
            self.peer_command_handlers = PeerCommandHandlers(self)
            self.peer_command_handlers.register_all(self.peer_connection)
            logger.info("Peer command handlers registered")
        else:
            self.peer_command_handlers = None
        
        # Initialize file transfer manager
        if self.peer_connection:
            self.file_transfer_manager = FileTransferManager(
                peer_connection=self.peer_connection,
                plot_updater=self.plot_updater,
                status_callback=self._update_transfer_status
            )
            
            # Register file transfer command handlers (chunked transfer)
            self.peer_connection.register_command_handler('FILE_TRANSFER_REQUEST', 
                                                         self.file_transfer_manager.handle_transfer_request)
            self.peer_connection.register_command_handler('FILE_TRANSFER_START', 
                                                         self.file_transfer_manager.handle_transfer_start)
            self.peer_connection.register_command_handler('FILE_TRANSFER_CHUNK', 
                                                         self.file_transfer_manager.handle_transfer_chunk)
            self.peer_connection.register_command_handler('FILE_TRANSFER_END', 
                                                         self.file_transfer_manager.handle_transfer_end)
            self.peer_connection.register_command_handler('FILE_TRANSFER_DATA', 
                                                         self.file_transfer_manager.handle_transfer_data)
            self.peer_connection.register_command_handler('FILE_TRANSFER_COMPLETE', 
                                                         self.file_transfer_manager.handle_transfer_complete)
        else:
            self.file_transfer_manager = None

        # Build control panel
        self._build_plot_controls()
        self._build_correlation_pair_selector()
        self._build_time_offset_config()
        
        # Build live counters panel
        self._build_live_counters()

    def _build_plot_controls(self):
        """Build plot control buttons and checkboxes."""
        controls = tk.Frame(self.tab_plot_left, relief=tk.GROOVE, bd=2, width=500)
        controls.grid(row=0, column=0, sticky="nws", pady=5)

        tk.Label(controls, text="Plot:", width=15, height=2).grid(row=0, column=0, sticky="news")
        
        btn_start = tk.Button(
            controls, text="Start", background=self.action_color, width=15,
            command=self._on_start_streaming
        )
        btn_start.grid(row=0, column=1, sticky="news", padx=2)
        
        btn_stop = tk.Button(
            controls, text="Stop", background=self.action_color, width=15,
            command=self._on_stop_streaming
        )
        btn_stop.grid(row=0, column=2, sticky="news")
        
        # Recording duration input (custom seconds)
        tk.Label(controls, text="Duration (sec):").grid(row=0, column=3, sticky="e", padx=(10, 2))
        self.duration_var = tk.StringVar(value="")
        duration_entry = tk.Entry(controls, textvariable=self.duration_var, width=10)
        duration_entry.grid(row=0, column=4, sticky="w", padx=2)
        tk.Label(controls, text="(0 = ∞)", font=('Arial', 8), foreground='gray').grid(
            row=0, column=5, sticky="w", padx=2)
        
        # Recording timer display
        self.recording_timer_label = tk.Label(controls, text="", width=20, 
                                             font=('Arial', 10, 'bold'), foreground='green')
        self.recording_timer_label.grid(row=0, column=6, sticky="w", padx=10)
        
        cb_hist = tk.Checkbutton(
            controls, text='Hisztogram', onvalue=True, offvalue=False,
            command=lambda: setattr(self.plot_updater, 'plot_histogram', 
                                   not self.plot_updater.plot_histogram)
        )
        cb_hist.grid(row=1, column=1, sticky="news", pady=4)
        
        cb_norm = tk.Checkbutton(
            controls, text='Normált', onvalue=True, offvalue=False,
            command=lambda: setattr(self.plot_updater, 'normalize_plot', 
                                   not self.plot_updater.normalize_plot)
        )
        cb_norm.grid(row=1, column=2, sticky="news", pady=4)

    def _build_correlation_pair_selector(self):
        """Build UI for selecting correlation pairs (local-local or local-remote)."""
        selector_frame = tk.Frame(self.tab_plot_left, relief=tk.GROOVE, bd=2, width=500)
        selector_frame.grid(row=2, column=0, sticky="nws", pady=5)
        
        tk.Label(selector_frame, text="Correlation Pairs:", 
                font=('Arial', 10, 'bold'), height=1).grid(
            row=0, column=0, columnspan=4, sticky="w", padx=5, pady=5
        )
        
        # List of active pairs
        self.pair_listbox = tk.Listbox(selector_frame, height=6, width=40)
        self.pair_listbox.grid(row=1, column=0, columnspan=4, sticky="ew", padx=5, pady=5)
        
        # Populate with default pairs
        self._update_pair_listbox()
        
        # Add pair controls — Source A
        tk.Label(selector_frame, text="A:").grid(row=2, column=0, sticky="e", padx=2)
        self.pair_src_a_var = tk.StringVar(value="Local")
        ttk.Combobox(selector_frame, values=["Local", "Remote"], width=8, state="readonly",
                     textvariable=self.pair_src_a_var).grid(row=2, column=1, sticky="w", padx=1)
        self.pair_ch_a_var = tk.StringVar(value="1")
        ttk.Combobox(selector_frame, values=["1", "2", "3", "4"], width=3, state="readonly",
                     textvariable=self.pair_ch_a_var).grid(row=2, column=2, sticky="w", padx=1)
        
        # Source B
        tk.Label(selector_frame, text="B:").grid(row=3, column=0, sticky="e", padx=2)
        self.pair_src_b_var = tk.StringVar(value="Remote")
        ttk.Combobox(selector_frame, values=["Local", "Remote"], width=8, state="readonly",
                     textvariable=self.pair_src_b_var).grid(row=3, column=1, sticky="w", padx=1)
        self.pair_ch_b_var = tk.StringVar(value="3")
        ttk.Combobox(selector_frame, values=["1", "2", "3", "4"], width=3, state="readonly",
                     textvariable=self.pair_ch_b_var).grid(row=3, column=2, sticky="w", padx=1)
        
        # Offset selector
        tk.Label(selector_frame, text="Offset:").grid(row=4, column=0, sticky="e", padx=2)
        self.pair_offset_var = tk.StringVar(value="1")
        ttk.Combobox(selector_frame, values=["1", "2", "3", "4"], width=3, state="readonly",
                     textvariable=self.pair_offset_var).grid(row=4, column=1, sticky="w", padx=1)
        
        # Add/Remove buttons
        tk.Button(selector_frame, text="+ Add Pair", background='#4CAF50', width=12,
                 command=self._add_correlation_pair).grid(row=2, column=3, padx=5)
        
        tk.Button(selector_frame, text="- Remove Selected", background='#FF5722', width=12,
                 command=self._remove_correlation_pair).grid(row=3, column=3, padx=5)
    
    def _update_pair_listbox(self):
        """Update the correlation pair listbox display."""
        self.pair_listbox.delete(0, tk.END)
        src_name = lambda s: "Local" if s == "L" else "Remote"
        for src_a, ch_a, src_b, ch_b, ofs_idx in self.correlation_pairs:
            self.pair_listbox.insert(tk.END,
                f"{src_name(src_a)}-{ch_a} ↔ {src_name(src_b)}-{ch_b}  [Offset {ofs_idx + 1}]")
    
    def _add_correlation_pair(self):
        """Add a new correlation pair."""
        try:
            # Convert UI display names to internal codes
            src_a = "L" if self.pair_src_a_var.get() == "Local" else "R"
            ch_a = int(self.pair_ch_a_var.get())
            src_b = "L" if self.pair_src_b_var.get() == "Local" else "R"
            ch_b = int(self.pair_ch_b_var.get())
            ofs_idx = int(self.pair_offset_var.get()) - 1  # UI shows 1/2/3/4, store as 0/1/2/3
            
            pair = (src_a, ch_a, src_b, ch_b, ofs_idx)
            if pair not in self.correlation_pairs:
                self.correlation_pairs.append(pair)
                self._update_pair_listbox()
                logger.info("Added correlation pair: %s-%d ↔ %s-%d [Offset %d]", 
                           src_a, ch_a, src_b, ch_b, ofs_idx + 1)
        except Exception as e:
            logger.error("Error adding correlation pair: %s", e)
    
    def _remove_correlation_pair(self):
        """Remove selected correlation pair."""
        try:
            selection = self.pair_listbox.curselection()
            if selection:
                idx = selection[0]
                removed_pair = self.correlation_pairs.pop(idx)
                self._update_pair_listbox()
                logger.info("Removed correlation pair: %s", removed_pair)
        except Exception as e:
            logger.error("Error removing correlation pair: %s", e)
    
    def _build_time_offset_config(self):
        """Build time offset configuration section with four offset slots."""
        offset_frame = tk.LabelFrame(self.tab_plot_left, text="Time Offsets (ps)", 
                                     font=('Arial', 10, 'bold'),
                                     relief=tk.GROOVE, bd=2, padx=10, pady=8)
        offset_frame.grid(row=3, column=0, sticky="ew", padx=5, pady=5)
        
        # Info label
        tk.Label(offset_frame, 
                 text="Each correlation pair selects which offset to use:",
                 font=('Arial', 9)).grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 5))
        
        self.offset_entries = []
        self.offset_status_labels = []
        
        for i in range(4):
            row_base = 1 + i * 2  # rows 1,2 / 3,4 / 5,6 / 7,8
            
            # Label + Entry
            tk.Label(offset_frame, text=f"Offset {i+1} (ps):", 
                    font=('Arial', 9, 'bold')).grid(row=row_base, column=0, sticky="e", padx=5)
            entry = tk.Entry(offset_frame, width=20, font=('Courier New', 10))
            entry.grid(row=row_base, column=1, sticky="w", padx=5)
            self.offset_entries.append(entry)
            
            # Pre-fill current value
            if self.time_offsets_ps[i] is not None:
                entry.insert(0, str(self.time_offsets_ps[i]))
            
            # Save button
            idx = i  # capture for lambda
            tk.Button(offset_frame, text=f"💾 Save", 
                     background='#2196F3', foreground='white',
                     font=('Arial', 9, 'bold'), width=8,
                     command=lambda idx=idx: self._save_time_offset_ui(idx)
            ).grid(row=row_base, column=2, padx=3)
            
            # Clear button
            tk.Button(offset_frame, text="🗑️", 
                     background='#FF9800', foreground='white',
                     font=('Arial', 9, 'bold'), width=4,
                     command=lambda idx=idx: self._clear_time_offset_ui(idx)
            ).grid(row=row_base, column=3, padx=3)
            
            # Status label on next row
            status_lbl = tk.Label(offset_frame, text="", font=('Arial', 8),
                                  foreground='#555')
            status_lbl.grid(row=row_base + 1, column=0, columnspan=5, sticky="w", padx=25, pady=(0, 4))
            self.offset_status_labels.append(status_lbl)
        
        # Update all status displays
        self._update_time_offset_status()
    
    def _save_time_offset_ui(self, idx=0):
        """Save time offset from UI input for the given slot (0-3)."""
        try:
            value = self.offset_entries[idx].get().strip()
            if not value:
                logger.warning("No time offset value entered for offset %d", idx + 1)
                return
            
            offset_ps = int(float(value))
            
            self.time_offsets_ps[idx] = offset_ps
            self.time_offsets_updated[idx] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._save_time_offset()
            self._update_time_offset_status()
            
            logger.info("Offset %d saved: %d ps", idx + 1, offset_ps)
            
        except ValueError as e:
            logger.error("Invalid time offset value: %s", e)
    
    def _clear_time_offset_ui(self, idx=0):
        """Clear time offset for the given slot (0-3)."""
        self.time_offsets_ps[idx] = None
        self.time_offsets_updated[idx] = None
        self._save_time_offset()
        self.offset_entries[idx].delete(0, tk.END)
        self._update_time_offset_status()
        logger.info("Offset %d cleared", idx + 1)
    
    def _update_time_offset_status(self):
        """Update the time offset status display for all slots."""
        for i in range(4):
            if not hasattr(self, 'offset_status_labels'):
                return
            if self.time_offsets_ps[i] is not None and self.time_offsets_updated[i]:
                formatted = format_number(self.time_offsets_ps[i])
                text = f"✅ Offset {i+1}: {formatted} ps | Updated: {self.time_offsets_updated[i]}"
                self.offset_status_labels[i].config(text=text, foreground='#2E7D32')
            else:
                self.offset_status_labels[i].config(text=f"⚠️ Offset {i+1} not configured", 
                                                     foreground='#F57C00')

    def _build_live_counters(self):
        """Build live detector counter display for local and remote."""
        # LOCAL COUNTERS
        local_counters = tk.Frame(self.tab_plot_left, relief=tk.GROOVE, bd=2, width=250, background='#E8F5E9')
        local_counters.grid(row=1, column=0, sticky="nws", pady=5, padx=(5, 2))
        
        role_label = "BME" if self.computer_role == "computer_b" else "Wigner"
        tk.Label(local_counters, text=f"🟢 LOCAL Detektorok ({role_label})", 
                font=('Arial', 10, 'bold'), foreground='#2E7D32',
                background='#E8F5E9', width=22, height=2).grid(
            row=0, column=0, columnspan=4, sticky="news"
        )

        self.beutes_labels = []
        self.local_save_vars = []  # Checkbox variables for local channels
        for i in range(4):
            tk.Label(local_counters, text=f"{i+1}.", background='#E8F5E9').grid(row=1, column=i, sticky="news")
            lbl = tk.Label(local_counters, text="0", width=10, background='#E8F5E9')
            lbl.grid(row=2, column=i, sticky="news")
            self.beutes_labels.append(lbl)
            
            # Add save-to-file checkbox (checked by default)
            save_var = tk.BooleanVar(value=True)
            cb = tk.Checkbutton(local_counters, text='Save', variable=save_var, 
                              background='#E8F5E9', font=('Arial', 8),
                              command=lambda: self._on_local_save_changed())
            cb.grid(row=3, column=i, sticky="news")
            self.local_save_vars.append(save_var)

        # REMOTE COUNTERS (if peer connected)
        if self.peer_connection:
            remote_counters = tk.Frame(self.tab_plot_left, relief=tk.GROOVE, bd=2, width=250, background='#E3F2FD')
            remote_counters.grid(row=1, column=1, sticky="nws", pady=5, padx=(2, 5))
            
            remote_role = "Wigner" if self.computer_role == "computer_b" else "BME"
            tk.Label(remote_counters, text=f"🔵 REMOTE Detektorok ({remote_role})", 
                    font=('Arial', 10, 'bold'), foreground='#1565C0',
                    background='#E3F2FD', width=22, height=2).grid(
                row=0, column=0, columnspan=4, sticky="news"
            )

            self.remote_beutes_labels = []
            self.remote_save_vars = []  # Checkbox variables for remote channels
            for i in range(4):
                tk.Label(remote_counters, text=f"{i+1}.", background='#E3F2FD').grid(row=1, column=i, sticky="news")
                lbl = tk.Label(remote_counters, text="---", width=10, background='#E3F2FD')
                lbl.grid(row=2, column=i, sticky="news")
                self.remote_beutes_labels.append(lbl)
                
                # Add save-to-file checkbox (checked by default)
                save_var = tk.BooleanVar(value=True)
                cb = tk.Checkbutton(remote_counters, text='Save', variable=save_var,
                                  background='#E3F2FD', font=('Arial', 8),
                                  command=lambda: self._on_remote_save_changed())
                cb.grid(row=3, column=i, sticky="news")
                self.remote_save_vars.append(save_var)
            
            # File transfer controls
            transfer_frame = tk.Frame(remote_counters, background='#E3F2FD')
            transfer_frame.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(5, 5))
            
            self.auto_transfer_var = tk.BooleanVar(value=False)
            tk.Checkbutton(transfer_frame, text='Auto-transfer files after recording',
                          variable=self.auto_transfer_var, background='#E3F2FD',
                          font=('Arial', 8, 'bold')).pack(side=tk.TOP, pady=2)
            
            tk.Button(transfer_frame, text="📥 Request Remote Files",
                     background='#2196F3', foreground='white',
                     font=('Arial', 9, 'bold'), width=25,
                     command=self._request_remote_files).pack(side=tk.TOP, pady=2)
            
            self.transfer_status_label = tk.Label(transfer_frame, text="",
                                                   background='#E3F2FD',
                                                   font=('Arial', 8), foreground='#555')
            self.transfer_status_label.pack(side=tk.TOP, pady=2)
        else:
            self.remote_beutes_labels = []
            self.remote_save_vars = []
            self.auto_transfer_var = None
            self.transfer_status_label = None

        # Store remote counter values (received from peer)
        self.remote_beutes_szamok = [0, 0, 0, 0]
        
        # Recording timer state
        self.recording_start_time = None
        self.recording_duration = None
        
        # Send initial save settings to peer
        self.root.after(1000, self._send_initial_save_settings)

        # Start periodic counter update
        self._update_counters()

    def _send_initial_save_settings(self):
        """Send initial local save settings to peer after startup."""
        if self.peer_connection and self.peer_connection.is_connected():
            self._on_local_save_changed()
    
    def _on_local_save_changed(self):
        """Called when local save checkboxes change - notify peer of our settings."""
        if not hasattr(self, 'local_save_vars'):
            return
        
        local_save_channels = [i+1 for i in range(4) if self.local_save_vars[i].get()]
        logger.info(f"Local save settings changed: {local_save_channels}")
        
        # Notify peer of our save settings (they display this in their REMOTE checkboxes)
        if self.peer_connection and self.peer_connection.is_connected():
            try:
                self.peer_connection.send_command('SAVE_SETTINGS_UPDATE', {
                    'save_channels': local_save_channels
                })
            except Exception as e:
                logger.error(f"Failed to send save settings to peer: {e}")
    
    def _on_remote_save_changed(self):
        """Called when remote save checkboxes change - tell peer to change their settings."""
        if not hasattr(self, 'remote_save_vars'):
            return
        
        remote_save_channels = [i+1 for i in range(4) if self.remote_save_vars[i].get()]
        logger.info(f"Remote save settings changed (will request peer to save): {remote_save_channels}")
        
        # Send command to peer to update their LOCAL save settings
        if self.peer_connection and self.peer_connection.is_connected():
            try:
                # Send as a request for them to update their local save checkboxes
                self.peer_connection.send_command('SAVE_SETTINGS_REQUEST', {
                    'save_channels': remote_save_channels
                })
                logger.info(f"Requested peer to update save settings: {remote_save_channels}")
            except Exception as e:
                logger.error(f"Failed to send save settings request to peer: {e}")
        else:
            logger.warning("No peer connection - cannot change remote save settings")
    
    def _request_remote_files(self):
        """Request timestamp files from remote peer."""
        if self.file_transfer_manager:
            self.file_transfer_manager.request_remote_files()
        else:
            logger.error("File transfer manager not initialized")
    
    def _update_transfer_status(self, text: str, color: str = 'black'):
        """Update transfer status label (callback for FileTransferManager)."""
        if hasattr(self, 'transfer_status_label') and self.transfer_status_label:
            try:
                self.transfer_status_label.config(text=text, foreground=color)
            except Exception:
                pass
    
    def _update_counters(self):
        """Periodically update counter labels from plot updater."""
        # Update local counters
        vals = getattr(self.plot_updater, 'beutes_szamok', [0, 0, 0, 0])
        try:
            for i in range(4):
                if self.beutes_labels[i].winfo_exists():
                    self.beutes_labels[i].config(text=format_number(vals[i]))
        except Exception:
            pass
        
        # Update remote counters
        if self.remote_beutes_labels:
            try:
                for i in range(4):
                    if self.remote_beutes_labels[i].winfo_exists():
                        if self.peer_connection and self.peer_connection.is_connected():
                            self.remote_beutes_labels[i].config(text=format_number(self.remote_beutes_szamok[i]))
                        else:
                            self.remote_beutes_labels[i].config(text="---")
            except Exception:
                pass
        
        if self.root.winfo_exists():
            self._after_id = self.root.after(300, self._update_counters)
    
    def _update_recording_timer(self):
        """Update recording timer countdown display."""
        if not self.recording_start_time or not self.recording_duration:
            return
        
        elapsed = time.time() - self.recording_start_time
        remaining = max(0, self.recording_duration - elapsed)
        
        if remaining > 0:
            # Update display
            mins = int(remaining // 60)
            secs = int(remaining % 60)
            self.recording_timer_label.config(
                text=f"⏱️ Recording: {mins:02d}:{secs:02d}",
                foreground='red'
            )
            
            # Schedule next update
            if self.root.winfo_exists():
                self.root.after(100, self._update_recording_timer)
        else:
            # Time's up! Auto-stop
            logger.info("Recording duration completed - auto-stopping")
            self.recording_timer_label.config(
                text="✅ Recording Complete",
                foreground='green'
            )
            self._on_stop_streaming()


    def _build_polarizer_tab(self):
        """Build the polarization controller tab with optimizer rows."""
        # Main container with padding
        container = tk.Frame(self.tab_polarizer, background=self.primary_color)
        container.grid(row=0, column=0, sticky="nws", pady=5, padx=5)
        
        # Header
        header = tk.Label(container, text="Polarizáció optimizálás", 
                         width=120, height=2, font=('Arial', 12, 'bold'),
                         background=self.primary_color, foreground=self.fg_color)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        # LOCAL GROUP FRAME
        local_frame = tk.Frame(container, relief=tk.RIDGE, bd=3, background='#E8F5E9')  # Light green
        local_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        
        # Local group header
        tk.Label(local_frame, text="🟢 LOCAL DEVICES (This Computer)", 
                font=('Arial', 11, 'bold'), foreground='#2E7D32', background='#E8F5E9').grid(
            row=0, column=0, columnspan=10, sticky="news", pady=(5, 5), padx=5
        )
        
        # Column headers for local
        headers = [
            "Serial Number", "TC Ch", "Start [deg]", "Start Val",
            "Angles [deg]", "Current Val", "Best [deg]", "Best Val",
            "Status", "Actions"
        ]
        for j, h in enumerate(headers):
            tk.Label(local_frame, text=h, font=('Arial', 9, 'bold'), 
                    background='#E8F5E9').grid(row=1, column=j, padx=3, pady=3)

        # Create 4 LOCAL optimizer rows (rows 0-3)
        # Use appropriate serials based on computer role
        local_serials = DEFAULT_LOCAL_SERIALS if self.computer_role == "computer_a" else DEFAULT_REMOTE_SERIALS
        
        for r in range(4):
            default_serial, default_channel = local_serials[r] if r < len(local_serials) else (None, r + 1)
            row = OptimizerRowExtended(
                local_frame, r, self.tc_address, self.action_color,
                is_remote=False,
                peer_connection=self.peer_connection,
                default_serial=default_serial,
                default_channel=default_channel
            )
            self.optim_rows[r] = row

        # REMOTE GROUP FRAME
        remote_frame = tk.Frame(container, relief=tk.RIDGE, bd=3, background='#E3F2FD')  # Light blue
        remote_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        
        # Remote group header
        tk.Label(remote_frame, text="🔵 REMOTE DEVICES (Peer Computer)", 
                font=('Arial', 11, 'bold'), foreground='#1565C0', background='#E3F2FD').grid(
            row=0, column=0, columnspan=10, sticky="news", pady=(5, 5), padx=5
        )
        
        # Column headers for remote
        for j, h in enumerate(headers):
            tk.Label(remote_frame, text=h, font=('Arial', 9, 'bold'),
                    background='#E3F2FD').grid(row=1, column=j, padx=3, pady=3)

        # Create 4 REMOTE optimizer rows (rows 4-7)
        # Use opposite serials for remote (what the peer computer has)
        remote_serials = DEFAULT_REMOTE_SERIALS if self.computer_role == "computer_a" else DEFAULT_LOCAL_SERIALS
        
        for r in range(4, 8):
            local_idx = r - 4  # Map 4-7 to 0-3 for serial lookup
            default_serial, default_channel = remote_serials[local_idx] if local_idx < len(remote_serials) else ("", r - 3)
            
            row = OptimizerRowExtended(
                remote_frame, r, self.tc_address, self.action_color,
                is_remote=True,
                peer_connection=self.peer_connection,
                default_serial=default_serial,
                default_channel=default_channel
            )
            self.optim_rows[r] = row

        # Build bulk controls
        self._build_bulk_controls()

    def _build_bulk_controls(self):
        """Build bulk control buttons for all optimizer rows."""
        bulk = tk.Frame(self.tab_polarizer, relief=tk.GROOVE, bd=2, width=800)
        bulk.grid(row=1, column=0, sticky="nws", pady=5)
        
        # Local controls
        tk.Label(bulk, text="LOCAL:", font=('Arial', 9, 'bold'), foreground='green').grid(
            row=0, column=0, padx=(10, 5), sticky=tk.W
        )
        tk.Button(
            bulk, text="Optimize all local", background='#4CAF50', width=16,
            command=self._optimize_all_local
        ).grid(row=0, column=1, padx=4)
        
        tk.Button(
            bulk, text="Stop all local", background='#FF5722', width=16,
            command=self._stop_all_local
        ).grid(row=0, column=2, padx=4)
        
        # Remote controls
        tk.Label(bulk, text="REMOTE:", font=('Arial', 9, 'bold'), foreground='blue').grid(
            row=1, column=0, padx=(10, 5), sticky=tk.W
        )
        tk.Button(
            bulk, text="Optimize all remote", background='#2196F3', width=16,
            command=self._optimize_all_remote
        ).grid(row=1, column=1, padx=4)
        
        tk.Button(
            bulk, text="Stop all remote", background='#FF5722', width=16,
            command=self._stop_all_remote
        ).grid(row=1, column=2, padx=4)
        
        # Single row selector
        tk.Label(bulk, text="Row (1-8):").grid(row=0, column=3, padx=(20, 2))
        self.sel_var = tk.StringVar(value="1")
        sel_combo = ttk.Combobox(bulk, values=["1", "2", "3", "4", "5", "6", "7", "8"], 
                                width=4, state="readonly", textvariable=self.sel_var)
        sel_combo.grid(row=0, column=4, padx=2)
        
        # Optimize one button
        tk.Button(
            bulk, text="Optimize one", background=self.action_color, width=14,
            command=self._optimize_one
        ).grid(row=0, column=5, padx=4)

    def _optimize_all_local(self):
        """Start optimization for all local rows (0-3)."""
        for i in range(4):
            row = self.optim_rows.get(i)
            if row and row.has_serial():
                row._on_start()

    def _stop_all_local(self):
        """Stop optimization for all local rows (0-3)."""
        for i in range(4):
            row = self.optim_rows.get(i)
            if row:
                row._on_stop()

    def _optimize_all_remote(self):
        """Start optimization for all remote rows (4-7)."""
        for i in range(4, 8):
            row = self.optim_rows.get(i)
            if row and row.has_serial():
                row._on_start()

    def _stop_all_remote(self):
        """Stop optimization for all remote rows (4-7)."""
        for i in range(4, 8):
            row = self.optim_rows.get(i)
            if row:
                row._on_stop()

    def _optimize_one(self):
        """Start optimization for selected row (1-8)."""
        try:
            idx = max(0, min(7, int(self.sel_var.get()) - 1))
        except Exception:
            idx = 0
        
        row = self.optim_rows.get(idx)
        if row and row.has_serial():
            row._on_start()
        elif row:
            try:
                row.status_lbl.config(text="Hiányzó serial/nincs kapcsolat")
            except Exception:
                pass

    def _build_gps_sync_tab(self):
        """Build the GPS synchronization monitoring tab."""
        from gps_sync import FS740Connection, get_gps_time, format_time_diff, measure_local_drift
        from gui_components.config import DEFAULT_FS740_ADDRESS, DEFAULT_FS740_PORT
        
        # Use configured address based on computer role
        fs740_address = getattr(self, 'fs740_address', DEFAULT_FS740_ADDRESS)
        
        # Main container
        container = tk.Frame(self.tab_gps_sync, background=self.primary_color, padx=20, pady=20)
        container.pack(fill=tk.BOTH, expand=True)
        
        # Header
        header = tk.Label(container, text="GPS Clock Synchronization Monitor (FS740)", 
                         font=('Arial', 14, 'bold'),
                         background=self.primary_color, foreground=self.fg_color)
        header.pack(pady=(0, 20))
        
        # Connect to FS740 GPS clock (matches C++ implementation)
        try:
            self.fs740 = FS740Connection(fs740_address, DEFAULT_FS740_PORT)
            if not self.fs740.connected:
                raise ConnectionError("Failed to connect to FS740")
        except Exception as e:
            warning = tk.Label(container, 
                             text=f"⚠️ GPS sync unavailable\nFailed to connect to FS740 at {fs740_address}:{DEFAULT_FS740_PORT}\n{e}",
                             font=('Arial', 12), foreground='#FF9800',
                             background=self.primary_color)
            warning.pack(pady=50)
            self.fs740 = None
            return
        
        # LOCAL GPS TIME section
        local_frame = tk.LabelFrame(container, text="Local GPS Time", 
                                   font=('Arial', 11, 'bold'),
                                   background='#E8F5E9', bd=2, relief=tk.RIDGE, padx=15, pady=10)
        local_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.gps_local_time_label = tk.Label(local_frame, text="--:--:--.------------",
                                             font=('Courier New', 16, 'bold'),
                                             background='#E8F5E9', foreground='#2E7D32')
        self.gps_local_time_label.pack()
        

        
        # LOCAL DRIFT MONITOR section
        drift_frame = tk.LabelFrame(container, text="Local Computer Clock Drift", 
                                   font=('Arial', 11, 'bold'),
                                   background='#F3E5F5', bd=2, relief=tk.RIDGE, padx=15, pady=10)
        drift_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.gps_drift_label = tk.Label(drift_frame, text="Click 'Measure Drift' to test",
                                       font=('Courier New', 14),
                                       background='#F3E5F5', foreground='#6A1B9A')
        self.gps_drift_label.pack()
        
        tk.Button(drift_frame, text="Measure Local Drift (10 samples, matches C++)", 
                 background=self.action_color, font=('Arial', 10),
                 command=self._measure_gps_drift).pack(pady=(10, 0))
        
        # Control buttons
        btn_frame = tk.Frame(container, background=self.primary_color)
        btn_frame.pack(pady=(20, 0))
        
        self.gps_sync_running = False
        self.gps_sync_button = tk.Button(btn_frame, text="Start Monitoring", 
                                         background='#4CAF50', width=20,
                                         font=('Arial', 10, 'bold'),
                                         command=self._toggle_gps_sync)
        self.gps_sync_button.pack(side=tk.LEFT, padx=5)
    
    def _toggle_gps_sync(self):
        """Toggle GPS synchronization monitoring."""
        self.gps_sync_running = not self.gps_sync_running
        
        if self.gps_sync_running:
            self.gps_sync_button.config(text="Stop Monitoring", background='#FF5722')
            self._update_gps_sync()
        else:
            self.gps_sync_button.config(text="Start Monitoring", background='#4CAF50')
    
    def _update_gps_sync(self):
        """Periodically update GPS synchronization display."""
        if not self.gps_sync_running:
            return
        
        try:
            from gps_sync import get_gps_time
            
            # Get local GPS time from FS740
            local_time = get_gps_time(self.fs740) if hasattr(self, 'fs740') and self.fs740 else None
            if local_time:
                self.gps_local_time_label.config(text=local_time)
        except Exception as e:
            logger.error(f"GPS sync update error: {e}")
        
        # Schedule next update
        if self.gps_sync_running and self.root.winfo_exists():
            self.root.after(1000, self._update_gps_sync)
    

    
    def _measure_gps_drift(self):
        """Measure drift between computer clock and GPS clock (matches C++ measure_timedrift())."""
        try:
            from gps_sync import measure_local_drift, format_time_diff
            
            if not hasattr(self, 'fs740') or not self.fs740:
                self.gps_drift_label.config(text="FS740 not connected")
                return
            
            self.gps_drift_label.config(text="Measuring... (10 seconds)")
            self.root.update()
            
            drifts = measure_local_drift(self.fs740, samples=10)
            
            if drifts:
                avg_drift = sum(drifts) // len(drifts)
                min_drift = min(drifts)
                max_drift = max(drifts)
                
                avg_val, avg_unit = format_time_diff(avg_drift)
                min_val, min_unit = format_time_diff(min_drift)
                max_val, max_unit = format_time_diff(max_drift)
                
                result = f"Avg: {avg_val} {avg_unit} | Min: {min_val} {min_unit} | Max: {max_val} {max_unit}"
                self.gps_drift_label.config(text=result)
            else:
                self.gps_drift_label.config(text="Measurement failed")
        except Exception as e:
            logger.error(f"GPS drift measurement error: {e}")
            self.gps_drift_label.config(text=f"Error: {e}")
    
    def _build_time_offset_tab(self):
        """Build the time offset calculator tab."""
        self.time_offset_tab_component = TimeOffsetTab(
            self.tab_time_offset,
            app_ref=self,
            bg_color=self.bg_color,
            fg_color=self.fg_color,
            action_color=self.action_color
        )

    def _build_offline_correlation_tab(self):
        """Build the offline correlation analysis tab."""
        self.offline_correlation_tab_component = OfflineCorrelationTab(
            self.tab_offline_correlation,
            app_ref=self,
            bg_color=self.bg_color,
            fg_color=self.fg_color,
            action_color=self.action_color
        )

    def _on_close(self):
        """Handle window close event with proper cleanup."""
        logger.info("Closing application...")
        
        # Stop background updater loop
        try:
            if hasattr(self, 'plot_updater'):
                self.plot_updater.stop()
        except Exception:
            pass
        
        # Cancel scheduled UI updates
        try:
            if self._after_id is not None:
                self.root.after_cancel(self._after_id)
                self._after_id = None
        except Exception:
            pass
        
        # Cleanup per-row optimizer resources (all 8 rows)
        try:
            for i in list(getattr(self, 'optim_rows', {}).keys()):
                row = self.optim_rows[i]
                try:
                    row.cleanup()
                except Exception:
                    pass
        except Exception:
            pass
        
        # Close peer connection
        try:
            if hasattr(self, 'peer_connection') and self.peer_connection is not None:
                logger.info("Closing peer connection...")
                self.peer_connection.close()
        except Exception as e:
            logger.exception("Error closing peer connection: %s", e)
        
        # Close FS740 GPS clock connection
        try:
            if hasattr(self, 'fs740') and self.fs740 is not None:
                logger.info("Closing FS740 connection...")
                self.fs740.close()
        except Exception as e:
            logger.exception("Error closing FS740 connection: %s", e)
        
        # Close Time Controller socket
        try:
            if hasattr(self, 'tc') and self.tc is not None:
                try:
                    self.tc.close(0)
                except Exception:
                    try:
                        self.tc.close()
                    except Exception:
                        pass
        except Exception:
            pass
        
        # Close matplotlib figures
        try:
            plt.close('all')
        except Exception:
            pass
        
        # Ensure Tk loop exits then destroy window
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
        
        logger.info("Application closed")


def main():
    """Main entry point for the application."""
    # Always use INFO level logging (DEBUG_MODE only controls explicit if-statements in code)
    from gui_components.config import DEBUG_MODE
    log_level = logging.INFO
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Silence excessive matplotlib font debugging
    logging.getLogger('matplotlib.font_manager').setLevel(logging.WARNING)
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    
    if DEBUG_MODE:
        logger.warning("="*80)
        logger.warning("DEBUG MODE ENABLED - Extensive logging active")
        logger.warning("="*80)
    
    logger.info("Starting MPC320 Peer-to-Peer Control Application")
    
    root = tk.Tk()
    app = App(root)
    root.mainloop()


if __name__ == "__main__":
    main()

