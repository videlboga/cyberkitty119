import sys
import os
# ensure project root is in PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from job_worker import main

if __name__ == "__main__":
    sys.exit(main())
