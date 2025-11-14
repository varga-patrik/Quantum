"""Connection configuration dialog for peer-to-peer setup."""

import tkinter as tk
from tkinter import ttk, messagebox
import socket
import logging

logger = logging.getLogger(__name__)


class ConnectionDialog:
    """Dialog for configuring peer-to-peer connection settings."""
    
    def __init__(self, parent):
        self.parent = parent
        self.result = None
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Peer Connection Setup")
        self.dialog.geometry("450x420")
        self.dialog.resizable(False, False)
        
        # Make dialog modal
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self._build_ui()
        
        # Center dialog on parent
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.dialog.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.dialog.winfo_height() // 2)
        self.dialog.geometry(f"+{x}+{y}")
    
    def _build_ui(self):
        """Build the dialog UI."""
        main_frame = ttk.Frame(self.dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title = ttk.Label(main_frame, text="Configure Peer-to-Peer Connection", 
                         font=('Arial', 12, 'bold'))
        title.grid(row=0, column=0, columnspan=2, pady=(0, 20))
        
        # Role selection
        role_frame = ttk.LabelFrame(main_frame, text="Computer Role", padding="10")
        role_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 15))
        
        self.role_var = tk.StringVar(value="computer_a")
        ttk.Radiobutton(role_frame, text="Computer A (Local serials: 38530254, ...)", 
                       variable=self.role_var, value="computer_a").pack(anchor=tk.W, pady=2)
        ttk.Radiobutton(role_frame, text="Computer B (Local serials: 12340001, ...)", 
                       variable=self.role_var, value="computer_b").pack(anchor=tk.W, pady=2)
        
        # Local IP (auto-detected)
        ttk.Label(main_frame, text="Local IP:").grid(row=2, column=0, sticky=tk.W, pady=5)
        local_ip = self._get_local_ip()
        self.local_ip_var = tk.StringVar(value=local_ip)
        local_entry = ttk.Entry(main_frame, textvariable=self.local_ip_var, width=25)
        local_entry.grid(row=2, column=1, sticky=tk.W, pady=5)
        local_entry.config(state='readonly')
        
        # Peer IP (user input)
        ttk.Label(main_frame, text="Peer IP:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.peer_ip_var = tk.StringVar(value="127.0.0.1")  # localhost for testing
        peer_entry = ttk.Entry(main_frame, textvariable=self.peer_ip_var, width=25)
        peer_entry.grid(row=3, column=1, sticky=tk.W, pady=5)
        peer_entry.focus()
        
        # Server Port
        ttk.Label(main_frame, text="Server Port:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.port_var = tk.StringVar(value="27015")
        port_entry = ttk.Entry(main_frame, textvariable=self.port_var, width=25)
        port_entry.grid(row=4, column=1, sticky=tk.W, pady=5)
        
        # Peer Port (for localhost testing with different ports)
        ttk.Label(main_frame, text="Peer Port:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.peer_port_var = tk.StringVar(value="27015")
        peer_port_entry = ttk.Entry(main_frame, textvariable=self.peer_port_var, width=25)
        peer_port_entry.grid(row=5, column=1, sticky=tk.W, pady=5)
        
        # Info label
        info_text = "⚠️ For localhost testing: Use DIFFERENT ports!\nComputer A: Server=27015, Peer=27016\nComputer B: Server=27016, Peer=27015"
        info_label = ttk.Label(main_frame, text=info_text, font=('Arial', 8), 
                              foreground='#D84315', justify=tk.LEFT)
        info_label.grid(row=6, column=0, columnspan=2, pady=(15, 10))
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=7, column=0, columnspan=2, pady=(10, 0))
        
        ttk.Button(btn_frame, text="Connect", command=self._on_connect, 
                  width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Skip", command=self._on_skip, 
                  width=12).pack(side=tk.LEFT, padx=5)
        
        # Bind Enter key
        self.dialog.bind('<Return>', lambda e: self._on_connect())
        self.dialog.bind('<Escape>', lambda e: self._on_skip())
    
    def _get_local_ip(self) -> str:
        """Auto-detect local IP address."""
        try:
            # Connect to external address to determine local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception:
            return "127.0.0.1"
    
    def _validate_ip(self, ip: str) -> bool:
        """Validate IP address format."""
        try:
            socket.inet_aton(ip)
            return True
        except socket.error:
            return False
    
    def _validate_port(self, port_str: str) -> bool:
        """Validate port number."""
        try:
            port = int(port_str)
            return 1 <= port <= 65535
        except ValueError:
            return False
    
    def _on_connect(self):
        """Handle Connect button click."""
        peer_ip = self.peer_ip_var.get().strip()
        port_str = self.port_var.get().strip()
        peer_port_str = self.peer_port_var.get().strip()
        
        # Validate inputs
        if not peer_ip:
            messagebox.showerror("Error", "Please enter peer IP address")
            return
        
        if not self._validate_ip(peer_ip):
            messagebox.showerror("Error", "Invalid IP address format")
            return
        
        if not self._validate_port(port_str):
            messagebox.showerror("Error", "Invalid server port number (1-65535)")
            return
        
        if not self._validate_port(peer_port_str):
            messagebox.showerror("Error", "Invalid peer port number (1-65535)")
            return
        
        port = int(port_str)
        peer_port = int(peer_port_str)
        local_ip = self.local_ip_var.get()
        role = self.role_var.get()
        
        self.result = {
            'local_ip': local_ip,
            'peer_ip': peer_ip,
            'port': port,
            'peer_port': peer_port,
            'role': role,
            'enabled': True
        }
        
        logger.info("Connection configured: local=%s, peer=%s:%d, server_port=%d, role=%s", 
                   local_ip, peer_ip, peer_port, port, role)
        self.dialog.destroy()
    
    def _on_skip(self):
        """Handle Skip button click."""
        self.result = {
            'enabled': False
        }
        logger.info("Peer connection skipped")
        self.dialog.destroy()
    
    def show(self):
        """Show dialog and wait for result."""
        self.dialog.wait_window()
        return self.result


def show_connection_dialog(parent) -> dict:
    """
    Show connection configuration dialog.
    
    Returns:
        dict: Configuration with keys 'enabled', 'local_ip', 'peer_ip', 'port'
              If 'enabled' is False, connection should be skipped.
    """
    dialog = ConnectionDialog(parent)
    return dialog.show()
