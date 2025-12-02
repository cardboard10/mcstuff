import socket
import threading
import time

class RCON:
    def __init__(self, host: str, port: int, password: str, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self._sock = None
        self._request_id = 0

    def _send_packet(self, packet_type: int, payload: str) -> None:
        self._request_id += 1
        payload_bytes = payload.encode('utf8')
        size = 4 + 4 + len(payload_bytes) + 2
        packet = size.to_bytes(4, 'little')
        packet += self._request_id.to_bytes(4, 'little')
        packet += packet_type.to_bytes(4, 'little')
        packet += payload_bytes + b'\x00\x00'
        self._sock.sendall(packet)

    def _receive_packet(self):
        def read_exact(n):
            data = b''
            while len(data) < n:
                chunk = self._sock.recv(n - len(data))
                if not chunk:
                    raise ConnectionError("RCON connection closed")
                data += chunk
            return data

        size_bytes = read_exact(4)
        size = int.from_bytes(size_bytes, 'little')
        data = read_exact(size)
        request_id = int.from_bytes(data[:4], 'little')
        packet_type = int.from_bytes(data[4:8], 'little')
        payload = data[8:-2].decode('utf8', errors='ignore')
        return request_id, packet_type, payload

    def connect(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(self.timeout)
        self._sock.connect((self.host, self.port))
        # Authenticate
        self._send_packet(3, self.password)  # SERVERDATA_AUTH
        req_id, typ, resp = self._receive_packet()
        if req_id == -1:
            raise ConnectionError("RCON authentication failed")
        return True

    def command(self, cmd: str) -> str:
        if not self._sock:
            raise ConnectionError("Not connected")
        self._send_packet(2, cmd)  # SERVERDATA_EXECCOMMAND
        req_id, typ, resp = self._receive_packet()
        return resp

    def schedule_command(self, cmd: str, delay: float):
        def delayed():
            try:
                if not self._sock:
                    self.connect()
                time.sleep(delay)
                self.command(cmd)
            except Exception as e:
                print(f"Error running scheduled command: {e}")
        threading.Thread(target=delayed).start()

    def wait_command(self, cmd: str) -> str:
        return self.command(cmd)

    def run_commands(self, cmds, delay_between=0, schedule=False):
        """
        Run multiple commands.
        cmds: list of commands
        delay_between: seconds between commands
        schedule: if True, schedules commands instead of running immediately
        """
        for cmd in cmds:
            if schedule:
                self.schedule_command(cmd, delay_between)
            else:
                print(self.wait_command(cmd))
            time.sleep(delay_between)

    def shell(self):
        """
        Interactive RCON shell: type commands and see live output
        """
        print("Minecraft RCON shell. Type 'exit' to quit.")
        while True:
            cmd = input("> ").strip()
            if cmd.lower() in ("exit", "quit"):
                break
            try:
                response = self.wait_command(cmd)
                print(response)
            except Exception as e:
                print(f"Error: {e}")

    def close(self):
        if self._sock:
            self._sock.close()
            self._sock = None

