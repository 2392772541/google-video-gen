"""One contained Google Vids session. The server never enters Playwright sync."""
import json
import sys
from pathlib import Path
from .models import Task, Profile
from .vids_worker import VidsWorker


def main():
    request_path = Path(sys.argv[1]).resolve()
    spec = json.loads(request_path.read_text(encoding='utf8'))
    worker = VidsWorker(output_dir=spec['output_dir'], timeout_sec=spec['timeout_sec'],
                        headless=spec['headless'], submission_state_path=spec['submission_state_path'])
    result = worker._execute_browser_task(Task(**spec['task']), Profile(**spec['profile']))
    # A response is authoritative only after the owned browser cleanup returned.
    result_path = request_path.parent / 'result.json'
    temporary = result_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False), encoding='utf8')
    temporary.replace(result_path)


if __name__ == '__main__':
    main()
