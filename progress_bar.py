import sys
import shutil
import time
from typing import Optional

MOVE_UP = "\033[A"
MOVE_DOWN = "\033[B"
MOVE_LEFT = "\033[D"
MOVE_RIGHT = "\033[C"
MOVE_UP_START_OF_LINE = "\033[F"
MOVE_DOWN_START_OF_LINE = "\033[E"
CLEAR_LINE = "\033[K"
MOVE_START_OF_LINE = "\033[G"
MOVE_END_OF_LINE = "\033[1000C"

MIN_PROGRESS_BAR_LENGTH = 40


def _get_terminal_width():
    return shutil.get_terminal_size(fallback=(30, 24)).columns


class ProgressBar:
    """
    Class that can be used as a context manager to print a progress bar while iterating over an iterable.
    It supports printing additional logs during the computation, similarly to a package manager.
    """

    # Lock for ensuring that a single progress bar exists at a time.
    _lock = False

    def __init__(self, iterable: Optional[iter] = None):
        # The percentage of the progress bar.
        self.percentage = 0

        # The length of the last line printed to the terminal (excluding the progress bar).
        self.last_output_line_length = 0

        # The number of columns in the terminal.
        self.columns = _get_terminal_width()

        # Whether the output is a TTY. If it is not a TTY, then we don't print the progress bar.
        self.is_tty = sys.stdout.isatty()

        # The iterable that we are iterating over.
        self.iterable = iterable

        # Metrics used for the progress bar.
        self.total_items = None
        self.processed_items = None
        self.elapsed_time = None

    def __iter__(self):
        """
        Replaces the stdout with self, so that we can print the progress bar, then yields
        the items from the iterable.
        """
        # Make sure we actually have an iterable.
        assert self.iterable is not None, "An iterable must be provided."

        # Make sure there aren't any other progress bars.
        assert not ProgressBar._lock, "A single progress bar can exist at a time."
        ProgressBar._lock = True

        # Get metrics for the progress bar.
        self.processed_items = 0
        self.total_items = 0
        try:
            self.total_items = len(self.iterable)
        except (TypeError, AttributeError):
            assert "The iterable must have a length."
        start_time = time.time()

        with self:
            for i, item in enumerate(self.iterable):
                yield item

                # Update the progress bar.
                self.processed_items += 1
                self.elapsed_time = time.time() - start_time
                self.set_progress((i + 1) / len(self.iterable))

        # Mark the progress bar as finished.
        ProgressBar._lock = False

    def set_progress(self, percentage: float):
        """
        Sets the progress of the progress bar to the given percentage.
        """
        assert 0 <= percentage <= 1
        self.percentage = percentage

        # Not a TTY. We just print the percentage.
        if not self.is_tty:
            self.stdout_write(self._compute_progress_bar_string() + "\n")
            return

        # If the number of columns changed, we need to re-render the progress bar.
        if self.columns != _get_terminal_width():
            self._handle_columns_resize()

        # We always asume that the cursor is at the end of the progress bar.
        self.stdout_write(MOVE_START_OF_LINE + CLEAR_LINE)
        self.stdout_write(self._compute_progress_bar_string() + MOVE_END_OF_LINE)
        sys.stdout.flush()

    def _compute_progress_bar_string(self):
        # Depending on the width of the terminal, we adjust the length of the progress bar
        # and the amount of information displayed.

        def get_slider(percentage: float, length: int):
            length -= 3
            done = int(length * percentage)
            partial_block = int((length * percentage - done) * 8)
            bar = "█" * done

            if done < length:
                bar += chr(0x258F - partial_block)

            remaining = length - done - 1
            bar += " " * remaining
            return "╟" + bar + "╢ "

        # The percentage of the progress bar (e,g. "42%")
        percentage = f"{int(self.percentage * 100):3}%"

        # The number of processed items out of the total items (e.g. "5/100")
        processed_items = ""
        if self.total_items is not None:
            processed_items = f"{self.processed_items}/{self.total_items}  ".rjust(
                len(str(self.total_items)) * 2 + 3
            )

        # The number of iterations per second or seconds per iteration (e.g. "50 it/s" or "2 it/s")
        speed = None
        speed_as_str = ""
        if self.elapsed_time is not None and self.processed_items > 0:
            speed = self.processed_items / self.elapsed_time
            speed_as_str = (
                f"{speed:.2f} it/s  "
                if speed >= 1
                else f"{1/speed:.2f} s/it  ".rjust(11)
            )

        # The remaining time (e.g. "ETA: 1m 30s")
        eta = ""
        if speed is not None and self.total_items is not None:
            remaining_items = self.total_items - self.processed_items
            remaining_time = remaining_items / speed
            eta = f"{int(remaining_time) // 60}m {int(remaining_time) % 60}s".ljust(8)

        if (
            len(percentage)
            + len(processed_items)
            + len(speed_as_str)
            + len(eta)
            + MIN_PROGRESS_BAR_LENGTH
            <= self.columns
        ):
            slider_length = (
                self.columns
                - len(percentage)
                - len(processed_items)
                - len(speed_as_str)
                - len(eta)
            )
            slider = get_slider(self.percentage, slider_length)
            return percentage + slider + processed_items + speed_as_str + eta
        elif (
            len(percentage) + len(speed_as_str) + len(eta) + MIN_PROGRESS_BAR_LENGTH
            <= self.columns
        ):
            slider_length = (
                self.columns - len(percentage) - len(speed_as_str) - len(eta)
            )
            slider = get_slider(self.percentage, slider_length)
            return percentage + slider + speed_as_str + eta
        elif len(percentage) + len(eta) + MIN_PROGRESS_BAR_LENGTH <= self.columns:
            slider_length = self.columns - len(percentage) - len(eta)
            slider = get_slider(self.percentage, slider_length)
            return percentage + slider + eta
        else:
            slider_length = self.columns - len(percentage)
            slider = get_slider(self.percentage, slider_length)
            return percentage + slider

    def __enter__(self):
        # Replace the stdout with self.
        self.stdout_write = sys.stdout.write
        sys.stdout.write = self.write

        # Print a new line, which represents the user-written text.
        self.stdout_write("\n")

        # Render the progress bar.
        self.set_progress(0)
        sys.stdout.flush()

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # Print a new line to separate the progress bar from the next text.
        self.stdout_write("\n")
        sys.stdout.flush()

        # Restore the stdout.
        sys.stdout.write = self.stdout_write

    def _handle_columns_resize(self):
        """
        Handles the case when the number of columns in the terminal changes.
        We need to re-render the progress bar.
        """
        new_columns = _get_terminal_width()
        progress_bar_length = len(self._compute_progress_bar_string())
        progress_bar_lines = (progress_bar_length + new_columns - 1) // new_columns

        # Need to clear the last `progress_bar_lines` lines.
        # The cursor is not on the first line containing the progress bar, at the start of the line.
        self.stdout_write(
            (CLEAR_LINE + MOVE_UP) * (progress_bar_lines - 1)
            + CLEAR_LINE
            + MOVE_START_OF_LINE
        )

        # We may need to force the next text to be printed on a new line.
        if self.last_output_line_length > new_columns:
            # We need to force a line break. We move the cursor to the end of printed text and add a new line.
            text_on_last_line = self.last_output_line_length % new_columns
            if text_on_last_line == 0:
                text_on_last_line = new_columns

            # Add a line break after `text_on_last_line` characters.
            self.stdout_write(MOVE_UP + MOVE_RIGHT * text_on_last_line + "\n")

            # The new length of the text on the last line is 0.
            self.last_output_line_length = 0

            # Add a new line for the progress bar.
            self.stdout_write("\n")

        # Update the number of colums and print the progress bar.
        self.columns = new_columns
        self.stdout_write(self._compute_progress_bar_string() + MOVE_END_OF_LINE)
        sys.stdout.flush()

    def write(self, text):
        """
        Writes the given text to the terminal, re-rendering the progress bar if needed.
        """
        # Not a TTY, so we can't use ANSI escape codes. We just print the text.
        if not self.is_tty:
            for c in text:
                if c == "\n":
                    self.stdout_write("\n")
                    self.last_output_line_length = 0
                else:
                    self.stdout_write(c)
                    self.last_output_line_length += 1
            return

        # If the number of columns changed, we need to re-render the progress bar.
        if self.columns != _get_terminal_width():
            self._handle_columns_resize()

        # Move the cursor to the last position of the user-written text.
        self.stdout_write(
            MOVE_UP_START_OF_LINE + MOVE_RIGHT * self.last_output_line_length
        )

        # Flags if we overwrote the progress bar, and will need to re-render it.
        overwrote_progress = False

        # Buffer to store the characters of the current line.
        buffer = []

        for c in text:
            # If we reach the end of the line, we need to move to the next one.
            if self.last_output_line_length >= self.columns or c == "\n":
                if buffer:
                    self.stdout_write("".join(buffer))
                    buffer.clear()
                self.stdout_write("\n" + CLEAR_LINE)
                overwrote_progress = True
                self.last_output_line_length = 0

            # Print the character.
            if c != "\n":
                buffer.append(c)
                self.last_output_line_length += 1
        if buffer:
            self.stdout_write("".join(buffer))

        if not overwrote_progress:
            # Progress bar was not overwriten, so we need to move the cursor to the end of the line.
            self.stdout_write(MOVE_DOWN + MOVE_END_OF_LINE)
        else:
            # Progress bar needs to be re-rendered on a new line.
            self.stdout_write("\n")
            self.stdout_write(self._compute_progress_bar_string() + MOVE_END_OF_LINE)

        # Flush the output.
        sys.stdout.flush()
