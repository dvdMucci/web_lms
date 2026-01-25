#!/usr/bin/env python3
"""
Wrapper para ejecutar publish_scheduled_content con el entorno del contenedor.
Cron corre con un entorno mínimo; este script copia las variables de /proc/1/environ
(proceso principal, p. ej. runserver) antes de llamar al management command.
"""
import os
import subprocess
import sys


def main():
    # Copiar env del proceso 1 (proceso principal del contenedor con variables de Docker)
    try:
        with open("/proc/1/environ", "rb") as f:
            for kv in f.read().split(b"\x00"):
                if b"=" in kv:
                    k, v = kv.split(b"=", 1)
                    os.environ[k.decode("utf-8", errors="replace")] = v.decode(
                        "utf-8", errors="replace"
                    )
    except FileNotFoundError:
        pass  # En algunos entornos /proc/1/environ no existe; seguir con el env actual
    except Exception as e:
        sys.stderr.write(f"run_publish_scheduled: error leyendo /proc/1/environ: {e}\n")

    os.chdir("/app")
    return subprocess.run(
        [sys.executable, "manage.py", "publish_scheduled_content"],
        cwd="/app",
    ).returncode


if __name__ == "__main__":
    sys.exit(main())
