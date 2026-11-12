"""Shared low-level process containment helpers for optional worker APIs."""
import ctypes
import os
import select
import signal
import subprocess
import time


DEFAULT_MEMORY_LIMIT_BYTES = 512 * 1024 * 1024


def apply_linux_memory_limit(memory_limit_bytes):
    if not memory_limit_bytes:
        return
    import resource

    limit = resource.RLIMIT_AS
    _, hard = resource.getrlimit(limit)
    if hard != resource.RLIM_INFINITY:
        memory_limit_bytes = min(memory_limit_bytes, hard)
    resource.setrlimit(limit, (memory_limit_bytes, memory_limit_bytes))


def windows_job(process, memory_limit_bytes):
    """Assign a Windows worker to a kill-on-close Job Object."""
    from ctypes import wintypes

    class BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_ulong),
            ("SchedulingClass", ctypes.c_ulong),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimitInformation),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
    process_handle = None
    try:
        information = ExtendedLimitInformation()
        flags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if memory_limit_bytes:
            flags |= 0x00000100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
            information.ProcessMemoryLimit = memory_limit_bytes
        information.BasicLimitInformation.LimitFlags = flags
        if not kernel32.SetInformationJobObject(
            job, 9, ctypes.byref(information), ctypes.sizeof(information)
        ):
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")
        access = 0x0001 | 0x0100 | 0x0400  # terminate, set quota, query
        process_handle = kernel32.OpenProcess(access, False, process.pid)
        if not process_handle:
            raise OSError(ctypes.get_last_error(), "OpenProcess failed")
        if not kernel32.AssignProcessToJobObject(job, process_handle):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")
        return job, kernel32.CloseHandle
    except BaseException:
        kernel32.CloseHandle(job)
        raise
    finally:
        if process_handle:
            kernel32.CloseHandle(process_handle)


def kill_worker(process, windows_job=None):
    if os.name == "nt" and windows_job is not None:
        from ctypes import wintypes

        class BasicAccountingInformation(ctypes.Structure):
            _fields_ = [
                ("TotalUserTime", ctypes.c_longlong),
                ("TotalKernelTime", ctypes.c_longlong),
                ("ThisPeriodTotalUserTime", ctypes.c_longlong),
                ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
                ("TotalPageFaultCount", wintypes.DWORD),
                ("TotalProcesses", wintypes.DWORD),
                ("ActiveProcesses", wintypes.DWORD),
                ("TotalTerminatedProcesses", wintypes.DWORD),
            ]

        handle, close_handle = windows_job
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.TerminateJobObject.restype = wintypes.BOOL
        kernel32.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryInformationJobObject.restype = wintypes.BOOL

        reap_deadline = time.monotonic() + 5.0
        try:
            if not kernel32.TerminateJobObject(handle, 1):
                error = ctypes.get_last_error()
                raise OSError(error, "terminating Windows worker job failed")
            while True:
                accounting = BasicAccountingInformation()
                if not kernel32.QueryInformationJobObject(
                    handle, 1, ctypes.byref(accounting),
                    ctypes.sizeof(accounting), None,
                ):
                    error = ctypes.get_last_error()
                    raise OSError(error, "querying Windows worker job failed")
                if accounting.ActiveProcesses == 0:
                    break
                remaining = reap_deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        "Windows worker job did not exit before the cleanup deadline"
                    )
                time.sleep(min(0.01, remaining))
        finally:
            # Close even if a job API call fails. This also invokes the configured
            # kill-on-close fallback when termination could not be confirmed.
            if not close_handle(handle):
                error = ctypes.get_last_error()
                raise OSError(error, "closing Windows worker job handle failed")

        if process.poll() is None:
            remaining = reap_deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    "Windows worker process did not exit before the cleanup deadline"
                )
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired as error:
                raise TimeoutError(
                    "Windows worker process did not exit before the cleanup deadline"
                ) from error
        return

    if os.name == "nt":
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired as error:
                raise TimeoutError(
                    "Windows worker process did not exit after termination"
                ) from error
        return

    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass
    if process.poll() is None:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired as error:
                raise TimeoutError(
                    "worker process did not exit after termination"
                ) from error



def stop_output_reader(reader, stop_event, timeout=1.0):
    """Request reader shutdown and interrupt a pending synchronous Windows I/O."""
    stop_event.set()
    deadline = time.monotonic() + timeout
    while reader.is_alive():
        if os.name == "nt" and reader.native_id is not None:
            try:
                from ctypes import wintypes

                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                kernel32.OpenThread.restype = wintypes.HANDLE
                kernel32.CancelSynchronousIo.argtypes = [wintypes.HANDLE]
                kernel32.CancelSynchronousIo.restype = wintypes.BOOL
                kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
                kernel32.CloseHandle.restype = wintypes.BOOL
                handle = kernel32.OpenThread(0x0001, False, reader.native_id)
                if handle:
                    try:
                        if not kernel32.CancelSynchronousIo(handle):
                            error = ctypes.get_last_error()
                            if error not in (87, 1168):  # thread exited / no I/O pending
                                raise OSError(error, "CancelSynchronousIo failed")
                    finally:
                        kernel32.CloseHandle(handle)
            except OSError:
                pass
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        reader.join(min(0.05, remaining))
    return not reader.is_alive()


def read_bounded_output(stream, output, overflow, process, max_bytes, stop_event, polling_event=None):
    """Drain a pipe without blocking indefinitely between cleanup checks."""
    descriptor = stream.fileno()
    windows_kernel = None
    pipe_handle = None
    if os.name == "nt":
        import msvcrt
        from ctypes import wintypes

        windows_kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        windows_kernel.PeekNamedPipe.argtypes = [
            wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
            ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
        ]
        windows_kernel.PeekNamedPipe.restype = wintypes.BOOL
        pipe_handle = wintypes.HANDLE(msvcrt.get_osfhandle(descriptor))
    total = 0
    while not stop_event.is_set():
        if os.name == "nt":
            available = wintypes.DWORD()
            if not windows_kernel.PeekNamedPipe(
                pipe_handle, None, 0, None, ctypes.byref(available), None
            ):
                error = ctypes.get_last_error()
                if error == 109:  # ERROR_BROKEN_PIPE
                    return
                raise OSError(error, "PeekNamedPipe failed")
            if available.value == 0:
                if polling_event is not None:
                    polling_event.set()
                stop_event.wait(0.05)
                continue
            chunk_size = min(64 * 1024, available.value)
        else:
            ready, _, _ = select.select([descriptor], [], [], 0.05)
            if not ready:
                if polling_event is not None:
                    polling_event.set()
                continue
            chunk_size = 64 * 1024
        chunk = os.read(descriptor, chunk_size)
        if not chunk:
            return
        total += len(chunk)
        if total > max_bytes:
            overflow.set()
            if process.poll() is None:
                try:
                    process.kill()
                except OSError:
                    pass
        elif not overflow.is_set():
            if hasattr(output, "write"):
                output.write(chunk)
            else:
                output.extend(chunk)
