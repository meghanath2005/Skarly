import os


os.environ["SKARLY_STORAGE_BACKEND"] = "mock"
os.environ["SKARLY_REPOSITORY_BACKEND"] = "memory"
os.environ["SKARLY_ENV"] = "test"
