import zmq
from threading import Thread
from zmq.utils.monitor import recv_monitor_message


class StreamClient(Thread):
    """Simple timestamps stream client.
    
    The message_callback callback function is called when timestamps are received.
    
    Assing message_callback with a dedicate function to process timestamp on the fly.
    """

    def __init__(self, addr):
        Thread.__init__(self)

        self.running = False

        # initialize data socket
        self.data_socket = zmq.Context().socket(zmq.PAIR)
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
            for socket, *_ in self.poller.poll(timeout=1000):
                if socket == self.data_socket:
                    binary_timestamps = socket.recv()
                    if len(binary_timestamps) == 0:
                        self.running = False

                    self.message_callback(binary_timestamps)

                if socket == self.monitor_socket:
                    evt = recv_monitor_message(socket)
                    if evt["event"] == zmq.EVENT_DISCONNECTED:
                        self.running = False

    def join(self):
        self.running = False
        super().join()
