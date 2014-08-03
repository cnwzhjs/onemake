import os
import thread

OUTPUT_LOCK=thread.allocate_lock()
USE_COLOR = os.getenv("TERM") in ("linux", "screen", "xterm")

def echo_color(color, text):
    OUTPUT_LOCK.acquire()
    if USE_COLOR:
        print "\033[{0}m{1}\033[0m".format(color, text)
    else:
        print text
    OUTPUT_LOCK.release()

def echo_info(text):
    echo_color("32;1", text)

def echo_warn(text):
    echo_color("33;1", text)

def echo_error(text):
    echo_color("31;1", text)

def fatal(text):
    echo_error(text)
    exit(1)
