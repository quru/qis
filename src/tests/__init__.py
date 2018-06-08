#
# Testing package utilities
#
import os
import signal
import subprocess

# Utility - kill the aux child processes
def kill_aux_processes(nicely=True):
    this_pid = os.getpid()
    p = subprocess.Popen(
        ['pgrep', '-g', str(this_pid)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    output = p.communicate()
    output = (output[1] or output[0])
    output = output.decode('utf8')
    child_pids = [p for p in output.split() if p != str(this_pid)]
    for pid in child_pids:
        try:
            os.kill(int(pid), signal.SIGTERM if nicely else signal.SIGKILL)
        except Exception as e:
            print("Failed to kill child process %s: %s" % (pid, str(e)))
