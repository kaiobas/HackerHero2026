"""
Sistema de Proteção Overlay

Responsável por:
  🟡 YELLOW → exibe uma borda de alerta pulsante na tela
  🔴 RED    → tela vermelha com mensagem de bloqueio

Privacidade: nenhuma imagem é salva. O bloqueio é puramente visual.
"""

from __future__ import annotations

import sys
import threading
from datetime import datetime

import tkinter as tk
from loguru import logger

from Agent.config import settings
from Agent.models.schemas import ProtectionAction, ProtectionState, RiskAssessment, RiskLevel

# Espessura da borda amarela (px)
_BORDER_THICKNESS = 16


def _enable_windows_dpi_awareness() -> None:
    """Evita que o Tk use tamanho lógico menor que a resolução real (Windows HiDPI)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        # PER_MONITOR_DPI_AWARE v2 (Windows 10+)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _virtual_screen_bounds() -> tuple[int, int, int, int]:
    """
    Retorna (left, top, width, height) da área virtual de todos os monitores.
    Mesma referência usada pelo mss na captura de tela.
    """
    try:
        import mss

        with mss.mss() as sct:
            mon = sct.monitors[0]
            return mon["left"], mon["top"], mon["width"], mon["height"]
    except Exception as exc:
        logger.debug("Fallback bounds do Tk: {}", exc)
        root = tk._default_root
        if root:
            return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()
        return 0, 0, 1920, 1080


class OverlayProtection:
    """
    Gerencia o overlay de proteção na tela.
    Toda interação com Tkinter ocorre na thread dedicada `_tk_thread`.
    """

    def __init__(self) -> None:
        self._state = ProtectionState()
        self._root: tk.Tk | None = None
        self._tk_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._quarantine_win: tk.Toplevel | None = None

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Inicia a thread Tkinter em background (não bloqueante)."""
        self._tk_thread = threading.Thread(target=self._tk_main, daemon=True)
        self._tk_thread.start()

    def stop(self) -> None:
        if self._root:
            self._root.after(0, self._clear_all)

    # ------------------------------------------------------------------
    # Interface pública (thread-safe)
    # ------------------------------------------------------------------

    def apply(self, assessment: RiskAssessment) -> None:
        """Aplica a proteção visual baseada no nível de risco."""
        action = self._level_to_action(assessment.level)
        with self._lock:
            self._state = ProtectionState(
                active=action != ProtectionAction.NONE,
                action=action,
                triggered_at=datetime.utcnow(),
                reason=assessment.explanation,
            )

        if self._root:
            self._root.after(0, lambda a=action, r=assessment: self._dispatch(a, r))

    def release(self) -> None:
        """Remove qualquer proteção ativa (uso pelos pais)."""
        with self._lock:
            self._state = ProtectionState(action=ProtectionAction.UNBLOCK)
        if self._root:
            self._root.after(0, self._clear_all)

    @property
    def state(self) -> ProtectionState:
        with self._lock:
            return self._state.model_copy()

    def is_quarantine_active(self) -> bool:
        """True somente se a janela de bloqueio RED existir de fato."""
        return self._is_quarantine_visible()

    # ------------------------------------------------------------------
    # Janela fullscreen (multi-monitor + HiDPI)
    # ------------------------------------------------------------------

    def _create_fullscreen_window(self, title: str) -> tk.Toplevel:
        """Cria Toplevel cobrindo todos os monitores com geometria correta."""
        assert self._root is not None
        win = tk.Toplevel(self._root)
        win.title(title)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        self._apply_screen_geometry(win)
        return win

    def _apply_screen_geometry(self, win: tk.Toplevel) -> None:
        left, top, width, height = _virtual_screen_bounds()
        win.geometry(f"{width}x{height}+{left}+{top}")
        win.update_idletasks()

    # ------------------------------------------------------------------
    # Dispatch de ações
    # ------------------------------------------------------------------

    def _dispatch(self, action: ProtectionAction, assessment: RiskAssessment) -> None:
        try:
            if action in (ProtectionAction.BLUR, ProtectionAction.QUARANTINE):
                self._show_block_screen(assessment)
            elif action == ProtectionAction.WARN:
                if self._is_quarantine_visible():
                    return
                self._clear_warnings()
                self._show_warning_border()
        except Exception as exc:
            logger.error("Erro ao aplicar overlay: {}", exc)

    # ------------------------------------------------------------------
    # Elementos visuais
    # ------------------------------------------------------------------

    def _show_warning_border(self) -> None:
        """Borda amarela – nível YELLOW, cobre área virtual completa."""
        if not self._root:
            return

        win = self._create_fullscreen_window("guardian_warn")
        win.configure(bg="#FFD700")

        # Borda amarela responsiva (outer) + conteúdo (inner)
        shell = tk.Frame(win, bg="#FFD700")
        shell.pack(fill="both", expand=True)

        inner = tk.Frame(shell, bg="#2a2200")
        inner.pack(
            fill="both",
            expand=True,
            padx=_BORDER_THICKNESS,
            pady=_BORDER_THICKNESS,
        )

        banner = tk.Frame(inner, bg="#3d3200", bd=2, relief="ridge")
        banner.pack(side="top", pady=24)

        tk.Label(
            banner,
            text="⚠️  Atividade suspeita detectada – monitorando…",
            fg="#FFD700",
            bg="#3d3200",
            font=("Segoe UI", 16, "bold"),
            padx=24,
            pady=12,
        ).pack()

        win.lift()
        win.focus_force()
        win.update()

        left, top, w, h = _virtual_screen_bounds()
        logger.warning("🟡 ALERTA amarelo exibido | {}x{} @ ({}, {})", w, h, left, top)
        self._root.after(8000, lambda: self._destroy_window(win))

    def _show_block_screen(self, assessment: RiskAssessment) -> None:
        """Tela vermelha – nível RED, cobre área virtual completa."""
        if not self._root:
            return

        if self._is_quarantine_visible():
            try:
                for widget in self._quarantine_win.winfo_children():
                    if isinstance(widget, tk.Frame):
                        for child in widget.winfo_children():
                            if isinstance(child, tk.Label) and child.cget("fg") == "#ff9999":
                                child.config(text=f"Motivo: {assessment.explanation}")
                                logger.warning("🔴 BLOQUEIO atualizado – {}", assessment.explanation)
                                return
            except tk.TclError:
                self._quarantine_win = None

        self._clear_warnings()

        win = self._create_fullscreen_window("guardian_quarantine")
        win.configure(bg="#1a0000")

        # Fundo vermelho em tela cheia (responsivo)
        bg = tk.Frame(win, bg="#1a0000")
        bg.pack(fill="both", expand=True)

        frame = tk.Frame(bg, bg="#2d0000", bd=4, relief="ridge")
        frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            frame,
            text="🛑",
            font=("Segoe UI", 72),
            bg="#2d0000",
            fg="white",
        ).pack(pady=(30, 0))

        tk.Label(
            frame,
            text=settings.quarantine_message,
            font=("Segoe UI", 18, "bold"),
            bg="#2d0000",
            fg="white",
            wraplength=600,
            justify="center",
        ).pack(padx=40, pady=20)

        tk.Label(
            frame,
            text=f"Motivo: {assessment.explanation}",
            font=("Segoe UI", 12),
            bg="#2d0000",
            fg="#ff9999",
            wraplength=580,
            justify="center",
        ).pack(padx=40, pady=(0, 30))

        win.grab_set()
        win.lift()
        win.focus_force()
        win.update()

        left, top, w, h = _virtual_screen_bounds()
        self._quarantine_win = win
        logger.warning("🔴 BLOQUEIO ativado | {}x{} @ ({}, {}) – {}", w, h, left, top, assessment.explanation)

    def _is_quarantine_visible(self) -> bool:
        if self._quarantine_win is None:
            return False
        try:
            return bool(self._quarantine_win.winfo_exists())
        except tk.TclError:
            self._quarantine_win = None
            return False

    def _destroy_window(self, win: tk.Toplevel) -> None:
        """Destrói janela liberando grab antes (crítico no Windows)."""
        if not win:
            return
        try:
            if win.winfo_exists():
                try:
                    win.grab_release()
                except tk.TclError:
                    pass
                win.destroy()
        except tk.TclError:
            pass
        if win is self._quarantine_win:
            self._quarantine_win = None

    def _clear_warnings(self) -> None:
        """Remove apenas janelas de aviso amarelo."""
        if not self._root:
            return
        for child in list(self._root.winfo_children()):
            try:
                if child.title() == "guardian_warn":
                    self._destroy_window(child)
            except Exception:
                pass

    def _clear_all(self) -> None:
        """Remove todas as janelas de overlay (release / shutdown)."""
        if not self._root:
            return
        for child in list(self._root.winfo_children()):
            try:
                if "guardian" in child.title():
                    self._destroy_window(child)
            except Exception:
                pass
        self._quarantine_win = None

    # ------------------------------------------------------------------
    # Thread Tkinter
    # ------------------------------------------------------------------

    def _tk_main(self) -> None:
        _enable_windows_dpi_awareness()
        self._root = tk.Tk()
        self._root.withdraw()
        self._root.mainloop()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _level_to_action(level: RiskLevel) -> ProtectionAction:
        return {
            RiskLevel.GREEN: ProtectionAction.NONE,
            RiskLevel.YELLOW: ProtectionAction.WARN,
            RiskLevel.RED: ProtectionAction.QUARANTINE,
        }[level]
