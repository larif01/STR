# udp_listener.py
import socket, json, datetime, time, math, signal, sys
from collections import defaultdict

PORT = 6010
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", PORT))
print(f"📡 Ouvindo UDP na porta {PORT}... (Ctrl+C para relatório final)")

# Quais percentis quer ver como HWM:
HWM_PCTS = [1.00, 0.99, 0.95]   # 100%, 99%, 95%

# ===== Helpers =====
def parse_send_ms(obj: dict) -> int | None:
    """
    Extrai o instante de envio em ms desde epoch (UTC) a partir de:
    - obj['epoch_ms'] (preferido), ou
    - obj['now'] (ISO 8601, ex.: '2025-10-27T17:37:06.388Z').
    """
    if isinstance(obj.get("epoch_ms"), (int, float)):
        return int(obj["epoch_ms"])
    if isinstance(obj.get("now"), str):
        s = obj["now"].strip()
        try:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"  # trata 'Z' como UTC
            dt = datetime.datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return int(dt.timestamp() * 1000)
        except ValueError:
            return None
    return None

def task_key(obj: dict) -> str:
    """
    Determina a 'tarefa' para agregação de métricas.
    Prioriza 'task' (ex.: 'SORT', 'SAFETY'); senão usa 'name'/'tag'; ou 'event' (ex.: 'TIME').
    """
    return (obj.get("task")
            or obj.get("name")
            or obj.get("tag")
            or obj.get("event")
            or "UNKNOWN")

def percentile_hwm(values: list[int], q: float) -> float:
    """
    Retorna o 'High Water Mark' no percentil q (0..1), usando método 'nearest-rank' (ceil).
    Ex.: q=0.99 -> valor tal que ~99% das amostras são <= valor.
    """
    if not values:
        return float("nan")
    vals = sorted(values)  # ascendente
    n = len(vals)
    k = max(1, math.ceil(q * n)) - 1  # índice zero-based
    return float(vals[k])

def format_hwms(values: list[int], pcts: list[float]) -> str:
    parts = []
    for p in pcts:
        v = percentile_hwm(values, p)
        label = f"HWM({int(p*100)}%)"
        parts.append(f"{label}={v:.0f}ms")
    return " | ".join(parts)

# ===== Estado das métricas =====
# Por tarefa: acumulamos todos delays (em ms). Armazene tudo (ou troque por deque se quiser limitar memória).
delays_by_task: dict[str, list[int]] = defaultdict(list)

def print_summary():
    if not delays_by_task:
        print("\nNenhuma amostra recebida.")
        return
    print("\nRelatório final por tarefa (WCRT e HWMs):")
    for t, arr in sorted(delays_by_task.items(), key=lambda kv: kv[0].lower()):
        n = len(arr)
        wcrt = max(arr) if arr else float("nan")
        hwms = format_hwms(arr, HWM_PCTS)
        avg = sum(arr)/n if n else float("nan")
        print(f" - {t}: n={n} | WCRT={wcrt:.0f}ms | avg={avg:.1f}ms | {hwms}")

def handle_sigint(sig, frame):
    print_summary()
    sys.exit(0)

signal.signal(signal.SIGINT, handle_sigint)

# ===== Loop principal =====
while True:
    data, addr = sock.recvfrom(4096)
    recv_ms = time.time_ns() // 1_000_000           # epoch ms (host)
    local_hms = datetime.datetime.now().strftime("%H:%M:%S")
    txt = data.decode("utf-8", "ignore")

    print(f"[{local_hms}] {addr[0]}:{addr[1]} -> {txt}")

    try:
        obj = json.loads(txt)
        send_ms = parse_send_ms(obj)
        if send_ms is None:
            continue

        delay_ms = recv_ms - send_ms  # se negativo: skew de relógio
        tname = task_key(obj)

        # Guarda amostra
        arr = delays_by_task[tname]
        arr.append(int(delay_ms))
        wcrt = max(arr)

        # Pequeno resumo por mensagem
        hwms_short = format_hwms(arr, [1.00, 0.99])  # mostra 100% e 99% a cada linha
        print(f"   {tname}: delay={delay_ms}ms | WCRT={wcrt}ms | {hwms_short} | n={len(arr)}")

    except json.JSONDecodeError:
        # Mensagem não-JSON: ignoramos para métricas
        continue
