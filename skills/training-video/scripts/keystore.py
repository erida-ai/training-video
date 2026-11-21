"""The Gemini keys of the projects, in the secret store of this computer — never in a file.

macOS: the login Keychain (`security`). Windows: Credential Manager (advapi32 through ctypes, no extra packages).
Elsewhere there is no store: GEMINI_API_KEY in the environment.
One entry per project: service SERVICE, account = the project id (macOS) / target SERVICE/<id> (Windows).
The key goes through argv of a local process (macOS) or memory (Windows) only — never to stdout or a log.
"""
import subprocess
import sys

SERVICE = "training-video-gemini"
LEGACY_ACCOUNT = "gemini"   # the one key for everything, before keys were per project (macOS only)


def available():
    return sys.platform in ("darwin", "win32")


def name():
    return {"darwin": "Keychain", "win32": "Credential Manager"}.get(sys.platform, "няма")


# ---------- macOS ----------

def _mac_get(account):
    r = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-a", account, "-w"],
                       capture_output=True, text=True)
    return (r.stdout.strip() or None) if r.returncode == 0 else None


def _mac_set(account, key):
    # -U updates an existing item
    subprocess.run(["security", "add-generic-password", "-U", "-s", SERVICE, "-a", account, "-w", key],
                   check=True, capture_output=True)


def _mac_delete(account):
    r = subprocess.run(["security", "delete-generic-password", "-s", SERVICE, "-a", account], capture_output=True)
    return r.returncode == 0


# ---------- Windows ----------

def _win():
    import ctypes
    from ctypes import wintypes

    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

    class CREDENTIAL(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                    ("Comment", wintypes.LPWSTR), ("LastWritten", FILETIME),
                    ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                    ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                    ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]

    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    adv.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
    adv.CredReadW.restype = wintypes.BOOL
    adv.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIAL), wintypes.DWORD]
    adv.CredWriteW.restype = wintypes.BOOL
    adv.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    adv.CredDeleteW.restype = wintypes.BOOL
    adv.CredFree.argtypes = [ctypes.c_void_p]
    return ctypes, CREDENTIAL, adv


CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2


def _target(account):
    return f"{SERVICE}/{account}"


def _win_get(account):
    ctypes, CREDENTIAL, adv = _win()
    p = ctypes.POINTER(CREDENTIAL)()
    if not adv.CredReadW(_target(account), CRED_TYPE_GENERIC, 0, ctypes.byref(p)):
        return None
    try:
        c = p.contents
        return bytes(c.CredentialBlob[:c.CredentialBlobSize]).decode("utf-8") or None
    finally:
        adv.CredFree(p)


def _win_set(account, key):
    ctypes, CREDENTIAL, adv = _win()
    blob = key.encode("utf-8")
    buf = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    c = CREDENTIAL(Type=CRED_TYPE_GENERIC, TargetName=_target(account), CredentialBlobSize=len(blob),
                   CredentialBlob=ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)),
                   Persist=CRED_PERSIST_LOCAL_MACHINE, UserName="gemini",
                   Comment="Gemini API key (training-video plugin)")
    if not adv.CredWriteW(ctypes.byref(c), 0):
        raise OSError(ctypes.get_last_error(), "CredWriteW failed")


def _win_delete(account):
    _, _, adv = _win()
    return bool(adv.CredDeleteW(_target(account), CRED_TYPE_GENERIC, 0))


# ---------- the same three calls everywhere ----------

def get(account):
    if sys.platform == "darwin":
        return _mac_get(account)
    if sys.platform == "win32":
        return _win_get(account)
    return None


def put(account, key):
    if sys.platform == "darwin":
        return _mac_set(account, key)
    if sys.platform == "win32":
        return _win_set(account, key)
    raise SystemExit("на този компютър няма хранилище за ключове: задайте GEMINI_API_KEY в средата")


def delete(account):
    if sys.platform == "darwin":
        return _mac_delete(account)
    if sys.platform == "win32":
        return _win_delete(account)
    return False


def legacy():
    """The single key saved before keys were per project (macOS Keychain, account "gemini"), if any."""
    return _mac_get(LEGACY_ACCOUNT) if sys.platform == "darwin" else None
