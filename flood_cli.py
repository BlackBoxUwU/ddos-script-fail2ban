#!/usr/bin/env python3
"""
Script de Prueba de Carga y DDoS Educativo con soporte de línea de comandos (CLI).
Diseñado para ejecutarse fuera de contenedores Docker (en el Host terminal).
Permite ajustar Host, Puerto, Ruta, Concurrencia, RPS y Duración.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

REQUEST_TIMEOUT_SECONDS = 3
REPORT_INTERVAL_SECONDS = 3


class RateLimiter:
    """Limita el ritmo global de inicio de peticiones entre todos los hilos trabajadores."""

    def __init__(self, requests_per_second: int) -> None:
        self.interval = 1.0 / requests_per_second if requests_per_second > 0 else 0
        self.next_request_at = 0.0
        self.lock = threading.Lock()

    def wait_for_turn(self, stop_event: threading.Event) -> bool:
        if self.interval == 0:
            return not stop_event.is_set()
        with self.lock:
            now = time.monotonic()
            scheduled_at = max(now, self.next_request_at)
            self.next_request_at = scheduled_at + self.interval
        return not stop_event.wait(max(0.0, scheduled_at - now))


def request_status(opener: urllib.request.OpenerDirector, url: str) -> str:
    """Realiza una petición HTTP GET y retorna el código de estado, o 000 en error de red/bloqueo."""
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "DDoS-LoadTest-Bot/1.0", "Accept": "*/*"},
    )
    try:
        with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return str(response.status)
    except urllib.error.HTTPError as error:
        return str(error.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        return "000 (Bloqueado/Timeout)"


def worker(
    url: str,
    deadline: float,
    stop_event: threading.Event,
    rate_limiter: RateLimiter,
    counts: Counter[str],
    counts_lock: threading.Lock,
) -> None:
    """Envía peticiones continuas hasta alcanzar el tiempo límite establecido."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while not stop_event.is_set() and time.monotonic() < deadline:
        if not rate_limiter.wait_for_turn(stop_event):
            break
        if time.monotonic() >= deadline:
            break
        code = request_status(opener, url)
        with counts_lock:
            counts[code] += 1


def snapshot(counts: Counter[str], counts_lock: threading.Lock) -> Counter[str]:
    with counts_lock:
        return counts.copy()


def report(url: str, counts: Counter[str], final: bool = False) -> None:
    total = sum(counts.values())
    ok = counts.get("200", 0)
    failed = total - ok
    label = "RESULTADO FINAL" if final else f"[{datetime.now():%H:%M:%S}] Avance"
    print(f"  {label} -> Total: {total} | Exitosas (200 OK): {ok} | Bloqueadas/Fallidas: {failed}", flush=True)
    if final and total:
        pct = (failed * 100) // total
        print(f"  -> Porcentaje de respuestas no-200 / bloqueadas: {pct}%", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Herramienta CLI de Pruebas de Carga DDoS (Host Terminal)"
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host objetivo o IP (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Puerto objetivo (default: 8080)")
    parser.add_argument("--path", default="/", help="Ruta de la URL (default: /)")
    parser.add_argument("--scheme", default="http", choices=["http", "https"], help="Protocolo (http o https)")
    parser.add_argument("--concurrency", "-c", type=int, default=40, help="Número de hilos trabajadores (concurrencia)")
    parser.add_argument("--rps", "-r", type=int, default=100, help="Límite máximo de Peticiones Por Segundo (RPS)")
    parser.add_argument("--duration", "-d", type=int, default=20, help="Duración del ataque en segundos")

    args = parser.parse_args()
    target_url = f"{args.scheme}://{args.host}:{args.port}{args.path}"

    print(f"\n=======================================================", flush=True)
    print(f"🔥 INICIANDO PRUEBA DE CARGA DDoS (FUERA DE DOCKER)", flush=True)
    print(f"🎯 Objetivo: {target_url}", flush=True)
    print(f"⚙️ Configuración: Hilos={args.concurrency}, RPS Máx={args.rps}, Duración={args.duration}s", flush=True)
    print(f"=======================================================\n", flush=True)

    counts: Counter[str] = Counter()
    counts_lock = threading.Lock()
    stop_event = threading.Event()
    rate_limiter = RateLimiter(args.rps)
    deadline = time.monotonic() + args.duration

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(
                worker,
                target_url,
                deadline,
                stop_event,
                rate_limiter,
                counts,
                counts_lock,
            )
            for _ in range(args.concurrency)
        ]
        try:
            while time.monotonic() < deadline:
                time.sleep(min(REPORT_INTERVAL_SECONDS, max(0.1, deadline - time.monotonic())))
                report(target_url, snapshot(counts, counts_lock))
        except KeyboardInterrupt:
            stop_event.set()
            print("\n⚠️ Deteniendo hilos por interrupción de teclado (Ctrl-C)...", flush=True)
        finally:
            stop_event.set()

        for future in futures:
            future.result()

    report(target_url, snapshot(counts, counts_lock), final=True)


if __name__ == "__main__":
    main()
