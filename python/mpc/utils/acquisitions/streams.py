import zmq
from threading import Thread
from zmq.utils.monitor import recv_monitor_message


class StreamClient(Thread):
    """Simple timestamps stream client.
    
    The message_callback callback function is called when timestamps are received.
    
    Assing message_callback with a dedicate function to process timestamp on the fly.
    """

    def __init__(self, addr, socket_type: int = zmq.PAIR, subscribe_prefix: bytes = b""):
        Thread.__init__(self)

        self.running = False

        self.socket_type = socket_type
        self.subscribe_prefix = subscribe_prefix

        # initialize data socket
        self.data_socket = zmq.Context.instance().socket(socket_type)
        self.data_socket.setsockopt(zmq.LINGER, 0)
        if socket_type == zmq.SUB:
            self.data_socket.setsockopt(zmq.SUBSCRIBE, subscribe_prefix)
        self.data_socket.connect(addr)

        # initialize monitor socket to check connection/disconnections
        self.monitor_socket = self.data_socket.get_monitor_socket()

        self.poller = zmq.Poller()
        self.poller.register(self.data_socket, zmq.POLLIN)
        self.poller.register(self.monitor_socket, zmq.POLLIN)

        self.message_callback = lambda _: None

    def is_running(self):
        return self.running

    def run(self):
        self.running = True
        while self.running:
            try:
                events = self.poller.poll(timeout=1000)
            except zmq.ZMQError:
                # Most commonly happens if sockets are closed while polling.
                break

            for socket, *_ in events:
                if socket == self.data_socket:
                    try:
                        parts = socket.recv_multipart()
                    except zmq.ZMQError:
                        self.running = False
                        break

                    binary_timestamps = parts[-1] if len(parts) > 0 else b""
                    if len(binary_timestamps) == 0:
                        self.running = False
                        break

                    try:
                        self.message_callback(binary_timestamps)
                    except Exception:
                        # Callback exceptions should not kill the receiver thread.
                        pass

                if socket == self.monitor_socket:
                    try:
                        evt = recv_monitor_message(socket)
                    except zmq.ZMQError:
                        self.running = False
                        break
                    if evt["event"] == zmq.EVENT_DISCONNECTED:
                        self.running = False
                        break

    def join(self):
        self.running = False
        try:
            if self.data_socket is not None:
                self.data_socket.close(linger=0)
        except Exception:
            pass
        try:
            if self.monitor_socket is not None:
                self.monitor_socket.close(linger=0)
        except Exception:
            pass
        super().join()
