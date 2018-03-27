#
# tests package setup and teardown
#
import os
import signal
import subprocess


# Package level setUp - run by nose
def setUp():
    pass


# Package level tearDown - run by nose
def tearDown():
    kill_aux_processes()


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
    child_pids = [p for p in output.split() if p != str(this_pid)]
    for pid in child_pids:
        try:
            os.kill(int(pid), signal.SIGTERM if nicely else signal.SIGKILL)
        except Exception as e:
            print("Failed to kill child process %s: %s" % (pid, str(e)))
