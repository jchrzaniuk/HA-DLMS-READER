import logging
import os
import signal
import threading

from .configuration import ConfigStore
from .runtime import Runtime
from .web import serve
from .integration_api import AccessToken, serve_api


def main():
    os.umask(0o077)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    store = ConfigStore(os.environ.get("DLMS_DATA", "./tmp/dlms-data"))
    runtime = Runtime(store, os.environ.get("SUPERVISOR_TOKEN"))
    server = serve(runtime, os.environ.get("DLMS_BIND", "127.0.0.1"), int(os.environ.get("DLMS_PORT", "8099")))
    api_server = serve_api(runtime, AccessToken(store.directory), os.environ.get("DLMS_BIND", "127.0.0.1"),
                           int(os.environ.get("DLMS_API_PORT", "8098")))
    threading.Thread(target=api_server.serve_forever, daemon=True).start()

    def shutdown(signum, frame):
        runtime.stop()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    if store.value["autostart"]:
        try:
            runtime.start()
        except Exception:
            logging.error("Nie udało się wznowić odczytu. Sprawdź ustawienia w formularzu.")
    logging.info("Uruchomiono interfejs DLMS/COSEM.")
    try:
        server.serve_forever()
    finally:
        runtime.stop()
        if runtime.thread:
            runtime.thread.join(timeout=store.value["timeout"] + 15)
        server.server_close()
        api_server.shutdown()
        api_server.server_close()


if __name__ == "__main__":
    main()
