import sys
import time
import subprocess


def main():
    # argv[1]: ruta del launcher a relanzar
    # argv[2] (opcional): PID del proceso viejo a esperar
    if len(sys.argv) < 2:
        return

    target_path = sys.argv[1]

    if len(sys.argv) > 2:
        try:
            old_pid = int(sys.argv[2])
            _wait_for_pid(old_pid)
        except ValueError:
            pass

    # Margen chico igual, por si el proceso viejo todavía está soltando
    # archivos/handles justo al momento de cerrar.
    time.sleep(0.5)

    subprocess.Popen([target_path])


def _wait_for_pid(pid, timeout=10):
    import ctypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.windll.kernel32

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return  # ya no existe

    try:
        exit_code = ctypes.c_ulong(0)
        waited = 0.0
        while waited < timeout:
            kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            if exit_code.value != STILL_ACTIVE:
                return
            time.sleep(0.2)
            waited += 0.2
    finally:
        kernel32.CloseHandle(handle)


if __name__ == "__main__":
    main()