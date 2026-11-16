"""Start the personal Windows worker without putting credentials on the command line."""
import json
import os
from pathlib import Path
import sys


def main():
    private = Path(os.getenv('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / 'BBLIA'
    config = json.loads((private / 'worker-private.json').read_text(encoding='utf-8'))
    key = config.get('worker_key', '')
    if not isinstance(key, str) or len(key) < 40:
        raise ValueError('Executor ainda sem configuração privada válida.')
    # A user-scoped mutex prevents duplicate model workers after logon/reconnect.
    import msvcrt
    lock = (private / 'worker.lock').open('a+b')
    lock.write(b'0')
    lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        return
    log = (private / 'worker.log').open('a', encoding='utf-8', buffering=1)
    sys.stdout = log
    sys.stderr = log
    os.environ['BBLIA_LOCAL_WORKER_KEY'] = key
    os.environ.setdefault('BBLIA_ANDROID_MODEL', 'qwen2.5-coder:1.5b')
    runtime = Path(config.get('runtime', str(Path(__file__).resolve().parent / 'interface-original-local')))
    from bblia_local_worker import Worker
    worker = Worker(config.get('origin', 'https://bblia-teste.onrender.com'), key, str(runtime))
    try:
        worker.run()
    finally:
        worker.server.shutdown()
        worker.server.server_close()
        lock.close()


if __name__ == '__main__':
    main()
