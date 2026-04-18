import os

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SDK_TESTS_PATH = os.path.join(ROOT_DIR, "sdk", "tests")

if os.path.isdir(SDK_TESTS_PATH) and SDK_TESTS_PATH not in __path__:
    __path__.insert(0, SDK_TESTS_PATH)


def hello():
    print("Hello from DeepSeek ARM test!")
