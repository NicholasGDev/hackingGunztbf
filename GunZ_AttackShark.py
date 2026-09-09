"""Windows. Instale: py -m pip install pynput
Execute: py GunZ_AttackShark.py
X1: TBF; segure X2: Late Dash automatico; F8: pausa; F9: sair.
Espada equipada; Space=pulo; Shift esquerdo=defesa.
Tempos experimentais, ainda nao validados no jogo.
"""

import ctypes
from ctypes import wintypes
import threading
import time

from pynput import keyboard, mouse

JUMP_TO_SLASH = 0.250
SLASH_TO_DASH = 0.100
TBF_GAP = 0.140  # Intervalo entre os cortes do TBF (140 ms).
WEAPON_KEYS = ("q", "e")
next_weapon_index = 0
SWORD_KEY = "1"
RELOAD_KEY = "r"
DASH_KEY = "w"
WEAPON_READY = 0.080
SWORD_READY = 0.030
WEAPON_READY = 0.200
SHOT_HOLD = 0.050
SHOT_TO_RELOAD = 0.060
RELOAD_TO_SWORD = 0.040
SWORD_READY = 0.060
COMBO_JUMP_TO_SLASH = 0.030
combo_mode = False
REPEAT_PAUSE = 0.250  # Pausa entre ciclos; ajuste conforme o pouso no jogo.
combo_mode = True
REPEAT_PAUSE = 0.450  # Pausa apos cada ciclo, antes do proximo pulo.
GAME_EXE = "gunz.exe"  # Altere se o executavel do seu cliente tiver outro nome.

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

keys = keyboard.Controller()
pointer = mouse.Controller()
enabled = threading.Event()
enabled.set()
shutdown = threading.Event()
busy = threading.Lock()
workers = []
held_controls = set()
late_held = threading.Event()
macro_context = threading.local()


def game_active():
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
    handle = kernel32.OpenProcess(0x1000, False, pid.value)
    if not handle:
        return False
    try:
        size = wintypes.DWORD(32768)
        path = ctypes.create_unicode_buffer(size.value)
        ok = kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size))
        return bool(ok) and path.value.rsplit("\\", 1)[-1].lower() == GAME_EXE.lower()
    finally:
        kernel32.CloseHandle(handle)


class Cancelled(Exception):
    pass


def check():
    if shutdown.is_set() or not enabled.is_set() or not game_active():
        raise Cancelled
    if getattr(macro_context, "repeat", False) and not late_held.is_set():
        raise Cancelled


def wait(seconds):
    deadline = time.monotonic() + seconds
    while True:
        check()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        shutdown.wait(min(remaining, 0.005))


def tap(controller, key, duration=0.020):
    check()
    controller.press(key)
    try:
        wait(duration)
    finally:
        controller.release(key)


def late_dash():
    tap(keys, keyboard.Key.space)
    wait(JUMP_TO_SLASH)
    tap(pointer, mouse.Button.left)
    wait(SLASH_TO_DASH)
    dash()


def dash():
    tap(keys, DASH_KEY)
    wait(0.030)
    tap(keys, DASH_KEY, 0.040)


def late_dash_shot():
    global next_weapon_index
    # Sequencia solicitada com tiro; tempos precisam de ajuste no cliente.
    tap(keys, keyboard.Key.space)
    wait(COMBO_JUMP_TO_SLASH)
    tap(pointer, mouse.Button.left)
    tap(keys, WEAPON_KEYS[next_weapon_index])
    wait(WEAPON_READY)
    # Um unico acionamento de tiro por ciclo.
    tap(pointer, mouse.Button.left, SHOT_HOLD)
    wait(SHOT_TO_RELOAD)
    tap(keys, RELOAD_KEY)
    wait(RELOAD_TO_SWORD)
    tap(keys, SWORD_KEY)
    # Alterna a proxima arma somente depois de voltar para a espada.
    next_weapon_index = (next_weapon_index + 1) % len(WEAPON_KEYS)
    wait(SWORD_READY)
    wait(SLASH_TO_DASH)
    dash()


def tbf():
    tap(keys, keyboard.Key.space, 0.010)
    wait(0.010)
    for i in range(3):
        tap(pointer, mouse.Button.left, 0.015)
        wait(0.010)
        tap(keys, keyboard.Key.shift_l)
        if i < 2:
            wait(TBF_GAP)


def run_macro(action, repeat=False):
    macro_context.repeat = repeat
    try:
        while True:
            check()
            if repeat:
                (late_dash_shot if combo_mode else late_dash)()
            else:
                action()
                break
            wait(REPEAT_PAUSE)
    except Cancelled:
        pass
    except Exception as exc:
        print(f"Erro na macro: {exc}", flush=True)
    finally:
        if repeat:
            late_held.clear()
        macro_context.repeat = False
        busy.release()


def on_click(x, y, button, pressed):
    if button == mouse.Button.x2 and not pressed:
        late_held.clear()
        return
    if not pressed or button not in (mouse.Button.x1, mouse.Button.x2):
        return
    if shutdown.is_set() or not enabled.is_set() or not game_active():
        return
    if not busy.acquire(blocking=False):
        return
    repeat = button == mouse.Button.x2
    if repeat:
        late_held.set()
    worker = threading.Thread(target=run_macro, args=(tbf, repeat))
    workers[:] = [w for w in workers if w.is_alive()]
    workers.append(worker)
    worker.start()


def on_press(key):
    global combo_mode, SLASH_TO_DASH
    if key not in (keyboard.Key.f6, keyboard.Key.f7, keyboard.Key.f8, keyboard.Key.f9, keyboard.Key.f10) or key in held_controls:
        return
    held_controls.add(key)
    if key == keyboard.Key.f6:
        combo_mode = not combo_mode
        print("Lateral 2: " + ("Late Dash com tiro" if combo_mode else "Late Dash basico"), flush=True)
        return
    if key in (keyboard.Key.f7, keyboard.Key.f10):
        SLASH_TO_DASH = round(max(0.0, min(0.500, SLASH_TO_DASH + (-0.010 if key == keyboard.Key.f7 else 0.010))), 3)
        print(f"Espera antes do dash: {SLASH_TO_DASH * 1000:.0f} ms", flush=True)
        return
    if key == keyboard.Key.f9:
        late_held.clear()
        shutdown.set()
        return False
    if enabled.is_set():
        late_held.clear()
        enabled.clear()
    else:
        enabled.set()
    print("Macro ativada" if enabled.is_set() else "Macro desativada", flush=True)


def on_release(key):
    held_controls.discard(key)


if __name__ == "__main__":
    print("X1: TBF | Segure X2: Late Dash automatico | Solte X2: parar | F8: pausa | F9: sair")
    print("F6: basico/com tiro | F7: -10 ms | F10: +10 ms antes do dash")
    print("Com tiro: armas alternadas Q/E, espada=1, reload=R. Ajustes de F7/F10 valem nesta execucao.")
    print("Modo inicial: COM TIRO | Pausa entre ciclos: 450 ms | TBF: intervalo de 140 ms")
    print(f"Ativo somente em {GAME_EXE}. Tempos iniciais para ajuste.")
    mouse_listener = mouse.Listener(on_click=on_click)
    key_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    mouse_listener.start()
    key_listener.start()
    try:
        key_listener.join()
    except KeyboardInterrupt:
        pass
    finally:
        shutdown.set()
        mouse_listener.stop()
        key_listener.stop()
        mouse_listener.join()
        for worker in workers:
            worker.join()


