from progress_bar import ProgressBar
import time

print("This is a text printed before the progress bar.")
time.sleep(1)

for i in ProgressBar(range(10)):
    print(f"Doing some computation for i={i}... ", end="")
    time.sleep(0.1)
    print("Done!")
    time.sleep(0.1)

print("This is a text printed after the progress bar.")

print("\n\nRunning the progress bar with a context manager.")
with ProgressBar() as progress:
    for i in range(10):
        print(f"Doing some computation for i={i}... ", end="")
        time.sleep(0.1)
        print("Done!")
        time.sleep(0.1)
        progress.set_progress((i + 1) / 10)

print("Done!")
