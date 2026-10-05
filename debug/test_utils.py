"""Offline self-check for scheduling and resume logic: python debug/test_utils.py"""
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG, BASE_DIR
from core.utils import schedule_time, target_key, find_resume_index, resolve_path

now = datetime(2026, 10, 5, 23, 0, 30)
assert schedule_time("23:30", now) == datetime(2026, 10, 5, 23, 30)
assert schedule_time("00:30", now) == datetime(2026, 10, 6, 0, 30)  # after midnight
assert schedule_time("23:00", now) == datetime(2026, 10, 5, 23, 0)  # this minute = now, not tomorrow
assert schedule_time("", now) is None
assert schedule_time("25:00", now) is None
assert schedule_time("noon", now) is None

a = {"target": "Alice", "message": "hi", "time": ""}
b = {"target": "Bob", "message": "hi", "time": ""}
c = {"target": "Carol", "message": "hi", "time": ""}
assert find_resume_index([a, b, c], 1, target_key(b)) == 1
assert find_resume_index([c, a, b], 1, target_key(b)) == 2  # CSV reordered
assert find_resume_index([a, c], 1, target_key(b)) is None  # Bob removed
assert find_resume_index([a, b], 2, None) == 2  # old checkpoint format

assert os.path.isabs(CONFIG["user_data_dir"]) and CONFIG["user_data_dir"].startswith(BASE_DIR)
assert os.path.isfile(os.path.join(BASE_DIR, "main.py"))
assert os.path.isfile(resolve_path("debug/dummy_test_img.jpg"))  # relative -> project folder
assert resolve_path(os.path.abspath(__file__)) == os.path.abspath(__file__)  # absolute unchanged

print("all checks passed")
