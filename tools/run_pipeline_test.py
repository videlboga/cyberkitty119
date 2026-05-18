#!/usr/bin/env python3
import sys
import asyncio
import json
import traceback
import os
from pathlib import Path
#!/usr/bin/env python3
import sys
import asyncio
import json
import traceback
import os
from pathlib import Path

# Runner for main pipeline DeepInfra flow
# Usage: run_pipeline_test.py /path/to/audio

async def main():
    if len(sys.argv) < 2:
        print("Usage: run_pipeline_test.py <path-to-audio-file>")
        return 2
    file_path = sys.argv[1]
    print("Using file:", file_path)
    try:
        # import here to use PYTHONPATH=/app when run in container
        from transkribator_modules.transcribe.transcriber_v4 import transcribe_whole_audio_with_deepinfra
        res = await transcribe_whole_audio_with_deepinfra(file_path)
        print('RESULT:')
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    except Exception as e:
        print('EXCEPTION:', type(e).__name__, str(e))
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
# Runner for main pipeline DeepInfra flow
# Usage: run_pipeline_test.py /path/to/audio

async def main():
    if len(sys.argv) < 2:
        print("Usage: run_pipeline_test.py <path-to-audio-file>")
        return 2
    file_path = sys.argv[1]
    print("Using file:", file_path)
    try:
        # import here to use PYTHONPATH=/app when run in container
        from transkribator_modules.transcribe.transcriber_v4 import transcribe_whole_audio_with_deepinfra
        res = await transcribe_whole_audio_with_deepinfra(file_path)
        print('RESULT:')
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    except Exception as e:
        print('EXCEPTION:', type(e).__name__, str(e))
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
