# language: Python 3.10+, file: Module/colors.py
# *all ANSI escape codes live here -- import once, use everywhere*

R  = "\033[91m"       # bright red
DR = "\033[38;5;88m"  # dark red (xterm-256)
Y  = "\033[93m"       # yellow
G  = "\033[92m"       # green
C  = "\033[96m"       # cyan
W  = "\033[97m"       # white
DG = "\033[90m"       # dark grey
M  = "\033[95m"       # magenta/purple
B  = "\033[94m"       # blue
RS = "\033[0m"        # reset

def gc(n: int) -> str:
    """xterm-256 foreground colour code."""
    return f"\033[38;5;{n}m"

def col(label: str) -> str:
    """Wrap a category label in red brackets: [Attack]."""
    return f"{R}[{W}{label}{R}]{RS}"
