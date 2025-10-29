# tcp_client.py
# Cliente TCP robusto para o servidor do ESP32 (porta 5000).
# Lê linha por linha usando select (sem makefile) e faz pretty-print do JSON.

import socket
import sys
import json
import select
import time

DEFAULT_IP = "192.168.0.160"
DEFAULT_PORT = 5000
CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 5.0

ALIASES = {
    "sort": "SORT",
    "safety": "SAFETY"
}

def read_line(sock: socket.socket, timeout: float) -> str | None:
    """Lê uma linha (terminada em '\n') com timeout. Retorna None em timeout/EOF."""
    buf = bytearray()
    end = time.time() + timeout
    sock.setblocking(False)
    while time.time() < end:
        remaining = max(0.0, end - time.time())
        r, _, _ = select.select([sock], [], [], remaining)
        if not r:
            continue
        try:
            chunk = sock.recv(1024)
        except BlockingIOError:
            continue
        if not chunk:
            # conexão fechada pelo servidor
            return None
        buf += chunk
        if b"\n" in buf:
            line, _sep, _rest = buf.partition(b"\n")
            return line.decode(errors="ignore").strip()
    return None  # timeout

def pretty(resp: str):
    print("ESP>", resp)
    try:
        obj = json.loads(resp)
        print("JSON:", json.dumps(obj, indent=2, ensure_ascii=False))
    except json.JSONDecodeError:
        pass

def main():
    ip = DEFAULT_IP
    port = DEFAULT_PORT
    if len(sys.argv) >= 2:
        ip = sys.argv[1]
    if len(sys.argv) >= 3:
        port = int(sys.argv[2])

    addr = (ip, port)
    print(f"Conectando em {addr} ...")
    try:
        with socket.create_connection(addr, timeout=CONNECT_TIMEOUT) as s:
            # Tenta ler banner (até 2 linhas) rapidamente
            for _ in range(2):
                line = read_line(s, timeout=1.5)
                if line is None:
                    break
                print(line)

            print("\nDigite comandos (SORT, SAFETY). Ctrl+C para sair.\n")
            while True:
                try:
                    raw = input("> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nSaindo.")
                    break
                if not raw:
                    continue

                cmd = ALIASES.get(raw.lower(), raw)
                # envia com '\n' (o servidor faz parsing por substring/linha)
                try:
                    s.sendall((cmd + "\n").encode())
                except (BrokenPipeError, ConnectionResetError):
                    print("Conexão fechada pelo ESP32 ao enviar.")
                    break

                resp = read_line(s, timeout=READ_TIMEOUT)
                if resp is None:
                    print("Sem resposta (timeout ou conexão encerrada).")
                    continue
                pretty(resp)

    except (ConnectionRefusedError, TimeoutError):
        print("Não foi possível conectar (recusado/timeout). Confirme IP/porta e se o ESP32 está com o servidor ativo.")
    except OSError as e:
        print(f"Erro de socket: {e}")

if __name__ == "__main__":
    main()
