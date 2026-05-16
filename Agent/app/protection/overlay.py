"""
Sistema de Proteção Overlay

Responsável por:
  🟡 YELLOW → exibe uma borda de alerta pulsante na tela
  🔴 RED    → tela vermelha com mensagem de bloqueio

Privacidade: nenhuma imagem é salva. O bloqueio é puramente visual.
Os pais são notificados apenas sobre o nível de risco — a decisão
de verificar o que aconteceu é tomada presencialmente pelo responsável.
"""

from __future__ import annotations

import threading
from datetime import datetime
import tkinter as tk

from loguru import logger

from Agent.config import settings
from Agent.models.schemas import ProtectionAction, ProtectionState, RiskAssessment, RiskLevel


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

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Inicia a thread Tkinter em background (não bloqueante)."""
        self._tk_thread = threading.Thread(target=self._tk_main, daemon=True)
        self._tk_thread.start()

    def stop(self) -> None:
        if self._root:
            self._root.after(0, self._root.destroy)

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
            self._root.after(0, lambda: self._dispatch(action, assessment))

    def release(self) -> None:
        """Remove qualquer proteção ativa (uso pelos pais)."""
        with self._lock:
            self._state = ProtectionState(action=ProtectionAction.UNBLOCK)
        if self._root:
            self._root.after(0, self._clear_overlay)

    @property
    def state(self) -> ProtectionState:
        with self._lock:
            return self._state.model_copy()

    # ------------------------------------------------------------------
    # Dispatch de ações
    # ------------------------------------------------------------------

    def _dispatch(self, action: ProtectionAction, assessment: RiskAssessment) -> None:
        self._clear_overlay()
        if action == ProtectionAction.WARN:
            self._show_warning_border()
        elif action in (ProtectionAction.BLUR, ProtectionAction.QUARANTINE):
            self._show_block_screen(assessment)

    # ------------------------------------------------------------------
    # Elementos visuais
    # ------------------------------------------------------------------

    def _show_warning_border(self) -> None:
        """Borda amarela pulsante – nível YELLOW."""
        if not self._root:
            return
        w = self._root.winfo_screenwidth()
        h = self._root.winfo_screenheight()
        thickness = 12

        win = tk.Toplevel(self._root)
        win.title("guardian_warn")
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-transparentcolor", "black")
        win.geometry(f"{w}x{h}+0+0")
        win.configure(bg="black")

        canvas = tk.Canvas(win, bg="black", highlightthickness=0, width=w, height=h)
        canvas.pack()
        canvas.create_rectangle(0, 0, w, h, outline="#FFD700", width=thickness)

        label = tk.Label(
            win,
            text="⚠️  Atividade suspeita detectada – monitorando…",
            fg="#FFD700", bg="#1a1a1a",
            font=("Arial", 14, "bold"),
            padx=16, pady=8,
        )
        label.place(relx=0.5, rely=0.02, anchor="n")

        self._root.after(8000, win.destroy)   # desaparece após 8s

    def _show_block_screen(self, assessment: RiskAssessment) -> None:
        """Tela vermelha com mensagem de bloqueio – nível RED."""
        if not self._root:
            return
        w = self._root.winfo_screenwidth()
        h = self._root.winfo_screenheight()

        win = tk.Toplevel(self._root)
        win.title("guardian_quarantine")
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.geometry(f"{w}x{h}+0+0")
        win.configure(bg="#1a0000")
        win.grab_set()   # captura todo input do teclado/mouse

        frame = tk.Frame(win, bg="#2d0000", bd=4, relief="ridge")
        frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            frame, text="🛑",
            font=("Arial", 72), bg="#2d0000", fg="white",
        ).pack(pady=(30, 0))

        tk.Label(
            frame,
            text=settings.quarantine_message,
            font=("Arial", 18, "bold"),
            bg="#2d0000", fg="white",
            wraplength=600, justify="center",
        ).pack(padx=40, pady=20)

        tk.Label(
            frame,
            text=f"Motivo: {assessment.explanation}",
            font=("Arial", 12),
            bg="#2d0000", fg="#ff9999",
            wraplength=580, justify="center",
        ).pack(padx=40, pady=(0, 30))

        logger.warning("🔴 BLOQUEIO ativado – {}", assessment.explanation)

    def _clear_overlay(self) -> None:
        """Fecha todas as janelas de overlay."""
        if not self._root:
            return
        for child in list(self._root.winfo_children()):
            try:
                if "guardian" in child.title():
                    child.destroy()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Thread Tkinter
    # ------------------------------------------------------------------

    def _tk_main(self) -> None:
        self._root = tk.Tk()
        self._root.withdraw()   # janela raiz invisível
        self._root.mainloop()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _level_to_action(level: RiskLevel) -> ProtectionAction:
        return {
            RiskLevel.GREEN:  ProtectionAction.NONE,
            RiskLevel.YELLOW: ProtectionAction.WARN,
            RiskLevel.RED:    ProtectionAction.QUARANTINE,
        }[level]



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

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Inicia a thread Tkinter em background (não bloqueante)."""
        self._tk_thread = threading.Thread(target=self._tk_main, daemon=True)
        self._tk_thread.start()

    def stop(self) -> None:
        if self._root:
            self._root.after(0, self._root.destroy)

    # ------------------------------------------------------------------
    # Interface pública (thread-safe)
    # ------------------------------------------------------------------

    def apply(self, assessment: RiskAssessment) -> None:
        """Aplica a proteção baseada no nível de risco."""
        action = self._level_to_action(assessment.level)
        with self._lock:
            self._state = ProtectionState(
                active=action != ProtectionAction.NONE,
                action=action,
                triggered_at=datetime.utcnow(),
                reason=assessment.explanation,
            )

        if self._root:
            self._root.after(0, lambda: self._dispatch(action, assessment))

    def release(self) -> None:
        """Remove qualquer proteção ativa (uso pelos pais)."""
        with self._lock:
            self._state = ProtectionState(action=ProtectionAction.UNBLOCK)
        if self._root:
            self._root.after(0, self._clear_overlay)

    @property
    def state(self) -> ProtectionState:
        with self._lock:
            return self._state.model_copy()

    # ------------------------------------------------------------------
    # Dispatch de ações
    # ------------------------------------------------------------------

    def _dispatch(self, action: ProtectionAction, assessment: RiskAssessment) -> None:
        self._clear_overlay()
        if action == ProtectionAction.WARN:
            self._show_warning_border()
        elif action in (ProtectionAction.BLUR, ProtectionAction.QUARANTINE):
            self._show_quarantine_screen(assessment)
            if action == ProtectionAction.QUARANTINE:
                self._move_to_quarantine(assessment.screenshot_id)

    # ------------------------------------------------------------------
    # Elementos visuais
    # ------------------------------------------------------------------

    def _show_warning_border(self) -> None:
        """Borda amarela pulsante – nível YELLOW."""
        if not self._root:
            return
        w = self._root.winfo_screenwidth()
        h = self._root.winfo_screenheight()
        thickness = 12

        win = tk.Toplevel(self._root)
        win.title("guardian_warn")
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-transparentcolor", "black")
        win.geometry(f"{w}x{h}+0+0")
        win.configure(bg="black")

        canvas = tk.Canvas(win, bg="black", highlightthickness=0, width=w, height=h)
        canvas.pack()

        # Borda amarela
        canvas.create_rectangle(
            0, 0, w, h,
            outline="#FFD700", width=thickness
        )

        label = tk.Label(
            win,
            text="⚠️  Atividade suspeita detectada – monitorando…",
            fg="#FFD700", bg="#1a1a1a",
            font=("Arial", 14, "bold"),
            padx=16, pady=8,
        )
        label.place(relx=0.5, rely=0.02, anchor="n")

        self._root.after(8000, win.destroy)   # desaparece após 8s

    def _show_quarantine_screen(self, assessment: RiskAssessment) -> None:
        """Tela vermelha com desfoque e mensagem de bloqueio – nível RED."""
        if not self._root:
            return
        w = self._root.winfo_screenwidth()
        h = self._root.winfo_screenheight()

        win = tk.Toplevel(self._root)
        win.title("guardian_quarantine")
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.geometry(f"{w}x{h}+0+0")
        win.configure(bg="#1a0000")
        win.grab_set()   # captura todo input do teclado/mouse

        # Painel central
        frame = tk.Frame(win, bg="#2d0000", bd=4, relief="ridge")
        frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            frame,
            text="🛑",
            font=("Arial", 72),
            bg="#2d0000", fg="white",
        ).pack(pady=(30, 0))

        tk.Label(
            frame,
            text=settings.quarantine_message,
            font=("Arial", 18, "bold"),
            bg="#2d0000", fg="white",
            wraplength=600,
            justify="center",
        ).pack(padx=40, pady=20)

        tk.Label(
            frame,
            text=f"Motivo: {assessment.explanation}",
            font=("Arial", 12),
            bg="#2d0000", fg="#ff9999",
            wraplength=580,
            justify="center",
        ).pack(padx=40, pady=(0, 30))

        logger.warning("🔴 QUARENTENA ativada – {}", assessment.explanation)

    def _clear_overlay(self) -> None:
        """Fecha todas as janelas de overlay."""
        if not self._root:
            return
        for child in self._root.winfo_children():
            title = child.winfo_name() if hasattr(child, "winfo_name") else ""
            try:
                if "guardian" in child.title():
                    child.destroy()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Quarentena de arquivos
    # ------------------------------------------------------------------

    @staticmethod
    def _move_to_quarantine(screenshot_id: str) -> None:
        """Move screenshot para pasta de quarentena."""
        src_dir = settings.screenshot_dir
        for f in src_dir.glob(f"*{screenshot_id[:8]}*.png"):
            dest = QUARANTINE_DIR / f.name
            shutil.move(str(f), str(dest))
            logger.info("Screenshot movido para quarentena: {}", f.name)

    # ------------------------------------------------------------------
    # Thread Tkinter
    # ------------------------------------------------------------------

    def _tk_main(self) -> None:
        self._root = tk.Tk()
        self._root.withdraw()   # janela raiz invisível
        self._root.mainloop()

    # ------------------------------------------------------------------
    # Utilitário estático: blur de imagem
    # ------------------------------------------------------------------

    @staticmethod
    def blur_image(filepath: str, strength: int | None = None) -> str:
        """
        Aplica blur gaussiano em uma imagem e salva uma versão borrada.
        Retorna o caminho da imagem borrada.
        """
        strength = strength or settings.blur_strength
        src = Path(filepath)
        dest = src.with_name(f"{src.stem}_blurred{src.suffix}")
        img = Image.open(src)
        blurred = img.filter(ImageFilter.GaussianBlur(radius=strength))
        blurred.save(str(dest))
        return str(dest)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _level_to_action(level: RiskLevel) -> ProtectionAction:
        return {
            RiskLevel.GREEN:  ProtectionAction.NONE,
            RiskLevel.YELLOW: ProtectionAction.WARN,
            RiskLevel.RED:    ProtectionAction.QUARANTINE,
        }[level]
