"""A child plus its descendants, contained before any browser can start.

On Windows a suspended runner is assigned to a kill-on-close Job Object before
it is resumed. Parent exit is not proof that Chromium descendants have exited.
"""
from __future__ import annotations
import ctypes
import os
import signal
import subprocess
import sys
import threading
import time
from ctypes import wintypes


class OwnedProcess:
    def __init__(self, command, **kwargs):
        self._job = None
        self._lock = threading.RLock()
        self._process_handles = {}
        if sys.platform != 'win32':
            self.proc = subprocess.Popen(command, start_new_session=True, **kwargs)
            return
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self._kernel = kernel
        kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
        kernel.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        kernel.QueryInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p)
        kernel.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel.WaitForSingleObject.restype = wintypes.DWORD

        class BasicLimits(ctypes.Structure):
            _fields_ = [('ProcessTime', ctypes.c_longlong), ('JobTime', ctypes.c_longlong),
                        ('Flags', wintypes.DWORD), ('MinWS', ctypes.c_size_t), ('MaxWS', ctypes.c_size_t),
                        ('ActiveLimit', wintypes.DWORD), ('Affinity', ctypes.c_size_t),
                        ('Priority', wintypes.DWORD), ('Scheduling', wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in ('ReadOps','WriteOps','OtherOps','ReadBytes','WriteBytes','OtherBytes')]
        class ExtendedLimits(ctypes.Structure):
            _fields_ = [('Basic', BasicLimits), ('IO', IO), ('ProcessMemory', ctypes.c_size_t),
                        ('JobMemory', ctypes.c_size_t), ('PeakProcess', ctypes.c_size_t), ('PeakJob', ctypes.c_size_t)]
        job = kernel.CreateJobObjectW(None, None)
        if not job:
            raise ctypes.WinError(ctypes.get_last_error())
        self._job = job
        limits = ExtendedLimits()
        limits.Basic.Flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        try:
            if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise ctypes.WinError(ctypes.get_last_error())
            # CREATE_SUSPENDED prevents a launch/assignment race. No breakaway.
            self.proc = subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW | 0x4, **kwargs)
            if not kernel.AssignProcessToJobObject(job, wintypes.HANDLE(int(self.proc._handle))):
                raise ctypes.WinError(ctypes.get_last_error())
            resume = ctypes.WinDLL('ntdll').NtResumeProcess
            resume.argtypes, resume.restype = (wintypes.HANDLE,), ctypes.c_long
            if resume(wintypes.HANDLE(int(self.proc._handle))) != 0:
                raise OSError('Cannot resume the contained browser runner')
        except BaseException:
            try:
                if hasattr(self, 'proc'):
                    self.proc.kill()
                    self.proc.wait(timeout=3)
            finally:
                kernel.CloseHandle(job)
                self._job = None
            raise

    @property
    def pid(self):
        return self.proc.pid

    @property
    def returncode(self):
        return self.proc.returncode

    def communicate(self, timeout=None):
        return self.proc.communicate(timeout=timeout)

    def poll(self):
        return self.proc.poll()

    def wait(self, timeout=None):
        return self.proc.wait(timeout=timeout)

    def _remember_job_processes(self):
        # Hold SYNCHRONIZE handles before termination. Job accounting alone
        # can reach zero before an exiting descendant's handle is signaled.
        capacity = 128
        while capacity <= 4096:
            class ProcessIds(ctypes.Structure):
                _fields_ = [('Assigned', wintypes.DWORD), ('Count', wintypes.DWORD),
                            ('Ids', ctypes.c_size_t * capacity)]
            ids = ProcessIds()
            ok = self._kernel.QueryInformationJobObject(
                self._job, 3, ctypes.byref(ids), ctypes.sizeof(ids), None)
            if ok and ids.Count >= ids.Assigned:
                break
            error = ctypes.get_last_error()
            if not ok and error != 234:  # ERROR_MORE_DATA
                raise ctypes.WinError(error)
            capacity = max(capacity * 2, ids.Assigned)
        else:
            raise OSError('Owned job membership exceeded the safe query bound')
        for pid in ids.Ids[:ids.Count]:
            if pid == self.pid or pid in self._process_handles:
                continue
            handle = self._kernel.OpenProcess(0x100000, False, pid)
            if not handle:
                error = ctypes.get_last_error()
                if error == 87:  # Process exited before OpenProcess.
                    continue
                raise ctypes.WinError(error)
            self._process_handles[pid] = handle

    def _descendants_alive(self):
        alive = False
        for pid, handle in list(self._process_handles.items()):
            status = self._kernel.WaitForSingleObject(handle, 0)
            if status == 0:
                if not self._kernel.CloseHandle(handle):
                    raise ctypes.WinError(ctypes.get_last_error())
                del self._process_handles[pid]
            elif status == 258:
                alive = True
            else:
                raise ctypes.WinError(ctypes.get_last_error())
        return alive

    def is_alive(self):
        with self._lock:
            return self._is_alive()

    def _is_alive(self):
        if sys.platform == 'win32':
            if self._job is None:
                return self.proc.poll() is None
            self._remember_job_processes()
            class Accounting(ctypes.Structure):
                _fields_ = [(name, ctypes.c_longlong) for name in ('User','Kernel','PeriodUser','PeriodKernel')] + [
                    ('Faults', wintypes.DWORD), ('Total', wintypes.DWORD),
                    ('Active', wintypes.DWORD), ('Terminated', wintypes.DWORD)]
            accounting = Accounting()
            if not self._kernel.QueryInformationJobObject(self._job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None):
                raise ctypes.WinError(ctypes.get_last_error())
            descendants_alive = self._descendants_alive()
            return bool(accounting.Active) or self.proc.poll() is None or descendants_alive
        try:
            os.killpg(self.pid, 0)
            return True
        except ProcessLookupError:
            return self.proc.poll() is None

    def cleanup(self, timeout=8):
        """Only terminate this owned job/group; return false on unknown exit."""
        with self._lock:
            return self._cleanup(timeout)

    def _cleanup(self, timeout):
        try:
            if self.is_alive():
                if sys.platform == 'win32':
                    if not self._kernel.TerminateJobObject(self._job, 1):
                        return False
                else:
                    os.killpg(self.pid, signal.SIGKILL)
            deadline = time.monotonic() + timeout
            self.proc.wait(timeout=max(0.1, deadline-time.monotonic()))
            while self.is_alive():
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.1)
            if self._job is not None:
                if not self._kernel.CloseHandle(self._job):
                    return False
                self._job = None
            return True
        except (OSError, subprocess.SubprocessError):
            return False
