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
        self.dialog.geometry("450x450")
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
        
        # Role selection - determines both device serials AND network role
        role_frame = ttk.LabelFrame(main_frame, text="Computer Role", padding="10")
        role_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 15))
        
        self.role_var = tk.StringVar(value="server")
        ttk.Radiobutton(role_frame, text="Wigner - server", 
                       variable=self.role_var, value="server").pack(anchor=tk.W, pady=2)
        ttk.Radiobutton(role_frame, text="BME - client", 
                       variable=self.role_var, value="client").pack(anchor=tk.W, pady=2)
        
        # Add role change callback to update UI
        self.role_var.trace_add('write', self._on_role_change)
        
        # Server IP (shown differently for server vs client)
        self.server_ip_label = ttk.Label(main_frame, text="Server IP:")
        self.server_ip_label.grid(row=2, column=0, sticky=tk.W, pady=5)
        local_ip = self._get_local_ip()
        self.server_ip_var = tk.StringVar(value=local_ip)
        self.server_ip_entry = ttk.Entry(main_frame, textvariable=self.server_ip_var, width=25)
        self.server_ip_entry.grid(row=2, column=1, sticky=tk.W, pady=5)
        
        # Port
        ttk.Label(main_frame, text="Port:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.port_var = tk.StringVar(value="27015")
        port_entry = ttk.Entry(main_frame, textvariable=self.port_var, width=25)
        port_entry.grid(row=3, column=1, sticky=tk.W, pady=5)
        
        # Info label - will update based on role
        self.info_label = ttk.Label(main_frame, text="", font=('Arial', 8), 
                                    foreground='#D84315', justify=tk.LEFT, wraplength=380)
        self.info_label.grid(row=4, column=0, columnspan=2, pady=(15, 10))
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=(10, 0))
        
        self.connect_btn = ttk.Button(btn_frame, text="Connect", command=self._on_connect, width=12)
        self.connect_btn.pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Skip", command=self._on_skip, 
                  width=12).pack(side=tk.LEFT, padx=5)
        
        # Bind Enter key
        self.dialog.bind('<Return>', lambda e: self._on_connect())
        self.dialog.bind('<Escape>', lambda e: self._on_skip())
        
        # Initialize UI state based on default role (after all widgets created)
        self._on_role_change()
    
    def _on_role_change(self, *args):
        """Update UI based on selected role."""
        role = self.role_var.get()
        
        if role == "server":
            # Server mode: show local IP (read-only), listen on port
            self.server_ip_label.config(text="Local IP:")
            local_ip = self._get_local_ip()
            self.server_ip_var.set(local_ip)
            self.server_ip_entry.config(state='readonly')
            self.connect_btn.config(text="Start Server")
            self.info_label.config(text="SERVER mode:\n• Start this first\n")
        else:
            # Client mode: enter server IP (editable), connect to port
            self.server_ip_label.config(text="Server IP:")
            self.server_ip_var.set("148.6.27.16")  # Default to localhost for testing
            self.server_ip_entry.config(state='normal')
            self.server_ip_entry.focus()
            self.connect_btn.config(text="Connect")
            self.info_label.config(text="CLIENT mode:\n• Start this second\n• Enter server IP (127.0.0.1 for localhost test)")
    
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
        server_ip = self.server_ip_var.get().strip()
        port_str = self.port_var.get().strip()
        role = self.role_var.get()
        
        # Validate inputs
        if not server_ip:
            if role == "server":
                messagebox.showerror("Error", "Could not detect local IP address")
            else:
                messagebox.showerror("Error", "Please enter server IP address")
            return
        
        if not self._validate_ip(server_ip):
            messagebox.showerror("Error", "Invalid server IP address format")
            return
        
        if not self._validate_port(port_str):
            messagebox.showerror("Error", "Invalid port number (1-65535)")
            return
        
        port = int(port_str)
        
        self.result = {
            'server_ip': server_ip,
            'port': port,
            'role': role,
            'enabled': True
        }
        
        logger.info("Connection configured: role=%s, server_ip=%s, port=%d", 
                   role, server_ip, port)
        self.dialog.destroy()
    
    def _on_skip(self):
        """Handle Skip button click - save role for local hardware config."""
        role = self.role_var.get()
        self.result = {
            'enabled': False,
            'role': role  # Save role even when skipping for hardware address selection
        }
        logger.info("Peer connection skipped (local mode, role=%s)", role)
        self.dialog.destroy()
    
    def show(self):
        """Show dialog and wait for result."""
        self.dialog.wait_window()
        return self.result


def show_connection_dialog(parent) -> dict:
    """
    Show connection configuration dialog.
    
    Returns:
        dict: Configuration with keys:
              - 'enabled': bool - whether connection is enabled
              - 'server_ip': str - server IP address
              - 'port': int - connection port
              - 'role': str - 'server' or 'client'
              If 'enabled' is False, connection should be skipped.
    """
    dialog = ConnectionDialog(parent)
    return dialog.show()
