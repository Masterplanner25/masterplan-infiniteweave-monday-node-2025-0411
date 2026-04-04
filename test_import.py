try:
        __import__("config")
        print("Import successful!")
except ImportError as e:
        print(f"ImportError: {e}")
