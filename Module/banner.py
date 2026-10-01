# language: Python 3.10+, file: Module/banner.py
# *pure print() menu -- no dynamic centering logic*

import os, sys, getpass

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from Module.colors import R, Y, G, C, W, DG, RS

VERSION = "4.0"
USER    = getpass.getuser()

def _gc(n): return f"\033[38;5;{n}m"

def cls():
    os.system("cls" if os.name == "nt" else "clear")

def print_banner():
    print()
    print(_gc(52)  + r"                                          ____    ____  ___      ___   ___ " + "\033[0m")
    print(_gc(88)  + r"                                          \   \  /   / /   \     \  \ /  / " + "\033[0m")
    print(_gc(124) + r"                                           \   \/   / /  ^  \     \  V  /  " + "\033[0m")
    print(_gc(160) + r"                                            \      / /  /_\  \     >   <   " + "\033[0m")
    print(_gc(196) + r"                                             \    / /  _____  \   /  .  \  " + "\033[0m")
    print(_gc(203) + r"                                              \__/ /__/     \__\ /__/ \__\ " + "\033[0m")
    print()
    print(f"{DG}                                         github.com/hab noch kein  \u2022  v{VERSION}{RS}")
    print()

def print_menu():
    cls()
    print_banner()

    # ── boxes ──────────────────────────────────────────────────────────
    print(f"                   {R}╔═════════════════════╗{RS}    {R}╔═════════════════════╗{RS}    {R}╔═════════════════════╗{RS}")
    print(f"                   {R}╠══════ {W}Attack{R} ═══════╣{RS}    {R}╠══════ {W}Discord{R} ══════╣{RS}    {R}╠═══════ {W}Soon{R} ════════╣{RS}")
    print(f"                   {R}╠═════════════════════╣{RS}    {R}╠═════════════════════╣{RS}    {R}╠═════════════════════╣{RS}")
    print(f"                   {R}║{RS}                     {R}║{RS}    {R}║{RS}                     {R}║{RS}    {R}║{RS}                     {R}║{RS}")
    print(f"                   {R}║{RS} {R}[{W}1{R}]{RS} {W}ddos{RS}            {R}║{RS}    {R}║{RS} {R}[{W}10{R}]{RS} {W}Name Sniper{RS}    {R}║{RS}    {R}║{RS}                     {R}║{RS}")
    print(f"                   {R}╚═════════════════════╝{RS}    {R}╚═════════════════════╝{RS}    {R}╚═════════════════════╝{RS}")
    print()

def print_prompt():
    cwd = os.path.dirname(os.path.abspath(__import__("__main__").__file__))
    sys.stdout.write(f"\n{G}({R}{USER}{G}@{R}VAX-Tool{G})-[{W}{cwd}{G}]{RS}\n{R}$ {RS}")
    sys.stdout.flush()
