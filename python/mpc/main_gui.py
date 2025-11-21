import tkinter as tk
from tkinter import ttk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import logging

from gui_components import (
    DEFAULT_TC_ADDRESS, SERVER_TC_ADDRESS, CLIENT_TC_ADDRESS,
    SERVER_FS740_ADDRESS, CLIENT_FS740_ADDRESS,
    DEFAULT_ACQ_DURATION, DEFAULT_BIN_WIDTH,
    DEFAULT_BIN_COUNT, DEFAULT_HISTOGRAMS, BG_COLOR, FG_COLOR,
    HIGHLIGHT_COLOR, PRIMARY_COLOR, ACTION_COLOR, 
    DEFAULT_LOCAL_SERIALS, DEFAULT_REMOTE_SERIALS,
    format_number, PlotUpdater, OptimizerRowExtended
)
from mock_time_controller import MockTimeController, is_mock_controller
from peer_connection import PeerConnection
from connection_dialog import show_connection_dialog

logger = logging.getLogger(__name__)


class App:
    """Main application class for the GUI."""
    
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
                
                # Register command handlers
                self.peer_connection.register_command_handler('OPTIMIZE_START', self._handle_remote_optimize_start)
                self.peer_connection.register_command_handler('OPTIMIZE_STOP', self._handle_remote_optimize_stop)
                self.peer_connection.register_command_handler('STATUS_UPDATE', self._handle_remote_status_update)
                self.peer_connection.register_command_handler('PROGRESS_UPDATE', self._handle_remote_progress_update)
                
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
            # Connection skipped - use default server addresses
            self.peer_connection = None
            self.tc_address = DEFAULT_TC_ADDRESS
            self.fs740_address = SERVER_FS740_ADDRESS
    
    def _connect_time_controller(self):
        """Connect to Time Controller with fallback to mock."""
        from utils.common import connect, adjust_bin_width
        
        # Use configured address based on computer role
        tc_addr = getattr(self, 'tc_address', DEFAULT_TC_ADDRESS)
        
        tc = None
        try:
            tc = connect(tc_addr)
            self.bin_width = adjust_bin_width(tc, DEFAULT_BIN_WIDTH)
            logger.info("Connected to Time Controller at %s", tc_addr)
        except (ConnectionError, Exception) as e:
            logger.warning("Failed to connect to Time Controller: %s", e)
            logger.info("Using MockTimeController")
            tc = MockTimeController()
            self.bin_width = DEFAULT_BIN_WIDTH
        
        return tc

    def _handle_remote_optimize_start(self, data: dict):
        """Handle remote optimization start command."""
        remote_row_idx = data.get('row_index', 0)
        local_row_idx = remote_row_idx - 4  # Map 4-7 to 0-3
        
        if local_row_idx in self.optim_rows:
            row = self.optim_rows[local_row_idx]
            if not row.is_remote:
                row.channel_box.set(data.get('channel', 1))
                if data.get('serial'):
                    row.serial_var.set(data['serial'])
                row._on_start()
    
    def _handle_remote_optimize_stop(self, data: dict):
        """Handle remote optimization stop command."""
        local_row_idx = data.get('row_index', 0) - 4  # Map 4-7 to 0-3
        
        if local_row_idx in self.optim_rows:
            row = self.optim_rows[local_row_idx]
            if not row.is_remote:
                row._on_stop()
    
    def _handle_remote_status_update(self, data: dict):
        """Handle status update from remote peer."""
        remote_row_idx = data.get('row_index', 0) + 4  # Map 0-3 to 4-7
        
        if remote_row_idx in self.optim_rows:
            self.optim_rows[remote_row_idx].handle_remote_status(data)
    
    def _handle_remote_progress_update(self, data: dict):
        """Handle progress update from remote peer."""
        remote_row_idx = data.get('row_index', 0) + 4  # Map 0-3 to 4-7
        
        if remote_row_idx in self.optim_rows:
            self.optim_rows[remote_row_idx].handle_remote_progress(data)
    
    def _setup_layout(self):
        """Configure root window layout."""
        self.root.configure(background=self.primary_color)
        self.root.rowconfigure(0, weight=0)  # Connection status row
        self.root.rowconfigure(1, weight=0)  # Mock status bar row
        self.root.rowconfigure(2, weight=1)  # Main content row
        self.root.columnconfigure(0, weight=1)
        self.root.columnconfigure(1, weight=1)

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
            status_frame = tk.Frame(self.root, background='#ff9800', relief=tk.RAISED, bd=2)
            status_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 5))
            status_label = tk.Label(
                status_frame,
                text="⚠️ MOCK MODE: Using random data (20,000-100,000) - Time Controller not connected",
                font=('Arial', 10, 'bold'),
                background='#ff9800',
                foreground='white',
                pady=8
            )
            status_label.pack(fill=tk.BOTH, expand=True)

    def _build_notebook(self):
        """Create tabbed notebook on the left."""
        self.notebook = ttk.Notebook(self.root)
        self.tab_plot = ttk.Frame(self.notebook)
        self.tab_polarizer = ttk.Frame(self.notebook)
        self.tab_gps_sync = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_plot, text="Plotolás")
        self.notebook.add(self.tab_polarizer, text="Polarizáció kontroller")
        self.notebook.add(self.tab_gps_sync, text="GPS Szinkronizáció")
        self.notebook.grid(row=2, column=0, sticky="news")

    def _build_plot_frame(self):
        """Create plot frame on the right."""
        self.plot_frame = tk.Frame(self.root, background=self.primary_color)
        self.plot_frame.grid(row=2, column=1, sticky="news")


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
        canvas.get_tk_widget().config(background=self.primary_color)

        # Create plot updater
        self.plot_updater = PlotUpdater(
            fig, ax, canvas, self.tc,
            DEFAULT_ACQ_DURATION, self.bin_width,
            DEFAULT_BIN_COUNT, DEFAULT_HISTOGRAMS
        )

        # Build control panel
        self._build_plot_controls()
        
        # Build live counters panel
        self._build_live_counters()

    def _build_plot_controls(self):
        """Build plot control buttons and checkboxes."""
        controls = tk.Frame(self.tab_plot, relief=tk.GROOVE, bd=2, width=600)
        controls.grid(row=0, column=0, sticky="nws", pady=5)

        tk.Label(controls, text="Plot:", width=20, height=2).grid(row=0, column=0, sticky="news")
        
        btn_start = tk.Button(
            controls, text="Start", background=self.action_color, width=15,
            command=self.plot_updater.start
        )
        btn_start.grid(row=0, column=1, sticky="news", padx=2)
        
        btn_stop = tk.Button(
            controls, text="Stop", background=self.action_color, width=15,
            command=self.plot_updater.stop
        )
        btn_stop.grid(row=0, column=2, sticky="news")
        
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

    def _build_live_counters(self):
        """Build live detector counter display."""
        counters = tk.Frame(self.tab_plot, relief=tk.GROOVE, bd=2, width=600)
        counters.grid(row=1, column=0, sticky="nws", pady=5)
        
        tk.Label(counters, text="Detektorok beütésszámai", width=20, height=2).grid(
            row=0, column=0, columnspan=4, sticky="news"
        )

        self.beutes_labels = []
        for i in range(4):
            tk.Label(counters, text=f"{i+1}.").grid(row=1, column=i, sticky="news")
            lbl = tk.Label(counters, text="0", width=10)
            lbl.grid(row=2, column=i, sticky="news")
            self.beutes_labels.append(lbl)

        # Start periodic counter update
        self._update_counters()

    def _update_counters(self):
        """Periodically update counter labels from plot updater."""
        vals = getattr(self.plot_updater, 'beutes_szamok', [0, 0, 0, 0])
        try:
            for i in range(4):
                if self.beutes_labels[i].winfo_exists():
                    self.beutes_labels[i].config(text=format_number(vals[i]))
        except Exception:
            pass
        
        if self.root.winfo_exists():
            self._after_id = self.root.after(300, self._update_counters)


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
                local_frame, r, DEFAULT_TC_ADDRESS, self.action_color,
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
                remote_frame, r, DEFAULT_TC_ADDRESS, self.action_color,
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
        from gps_sync import FS740Connection, get_gps_time, calculate_time_diff, format_time_diff, measure_local_drift
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
        
        # REMOTE GPS TIME section (if peer connected)
        if self.peer_connection and self.peer_connection.is_connected():
            remote_frame = tk.LabelFrame(container, text="Remote GPS Time", 
                                        font=('Arial', 11, 'bold'),
                                        background='#E3F2FD', bd=2, relief=tk.RIDGE, padx=15, pady=10)
            remote_frame.pack(fill=tk.X, pady=(0, 15))
            
            self.gps_remote_time_label = tk.Label(remote_frame, text="--:--:--.------------",
                                                  font=('Courier New', 16, 'bold'),
                                                  background='#E3F2FD', foreground='#1565C0')
            self.gps_remote_time_label.pack()
            
            # TIME OFFSET section
            offset_frame = tk.LabelFrame(container, text="Clock Offset (Local - Remote)", 
                                        font=('Arial', 11, 'bold'),
                                        background='#FFF3E0', bd=2, relief=tk.RIDGE, padx=15, pady=10)
            offset_frame.pack(fill=tk.X, pady=(0, 15))
            
            self.gps_offset_label = tk.Label(offset_frame, text="--- ps",
                                            font=('Courier New', 18, 'bold'),
                                            background='#FFF3E0', foreground='#E65100')
            self.gps_offset_label.pack()
        
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
        
        # Register peer command handler for GPS sync
        if self.peer_connection:
            self.peer_connection.register_command_handler('GPS_TIME_SYNC', self._handle_remote_gps_time)
    
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
            from gps_sync import get_gps_time, calculate_time_diff, format_time_diff
            
            # Get local GPS time from FS740
            local_time = get_gps_time(self.fs740) if hasattr(self, 'fs740') and self.fs740 else None
            if local_time:
                self.gps_local_time_label.config(text=local_time)
                
                # Send to peer if connected
                if self.peer_connection and self.peer_connection.is_connected():
                    self.peer_connection.send_command('GPS_TIME_SYNC', {
                        'gps_time': local_time
                    })
        except Exception as e:
            logger.error(f"GPS sync update error: {e}")
        
        # Schedule next update
        if self.gps_sync_running and self.root.winfo_exists():
            self.root.after(1000, self._update_gps_sync)
    
    def _handle_remote_gps_time(self, data: dict):
        """Handle GPS time received from remote peer."""
        try:
            from gps_sync import get_gps_time, calculate_time_diff, format_time_diff
            
            remote_time = data.get('gps_time')
            if remote_time and hasattr(self, 'gps_remote_time_label'):
                self.gps_remote_time_label.config(text=remote_time)
                
                # Calculate offset using local FS740
                local_time = get_gps_time(self.fs740) if hasattr(self, 'fs740') and self.fs740 else None
                if local_time:
                    offset = calculate_time_diff(local_time, remote_time)
                    if offset is not None:
                        value, unit = format_time_diff(offset)
                        self.gps_offset_label.config(text=f"{value} {unit}")
        except Exception as e:
            logger.error(f"Handle remote GPS time error: {e}")
    
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
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info("Starting MPC320 Peer-to-Peer Control Application")
    
    root = tk.Tk()
    app = App(root)
    root.mainloop()


if __name__ == "__main__":
    main()

