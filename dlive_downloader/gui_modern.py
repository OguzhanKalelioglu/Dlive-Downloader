"""Modern CustomTkinter based graphical interface for the DLive downloader."""
from __future__ import annotations

import logging
import platform
import queue
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import customtkinter as ctk
from tkinter import messagebox

from .client import Broadcast, DLiveAPIError, DLiveDownloader, PlaylistError, StreamVariant

# Enable debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


IS_MAC = platform.system() == "Darwin"

# Set appearance and color theme
ctk.set_appearance_mode("dark")  # Dark mode by default
ctk.set_default_color_theme("blue")  # Can be "blue", "green", "dark-blue"

# Slightly scale down widgets on macOS so the layout fits better on Retina displays
if IS_MAC:
    try:
        ctk.set_widget_scaling(0.95)
        ctk.set_window_scaling(1.0)
    except Exception:
        pass


@dataclass
class VariantDisplay:
    variant: StreamVariant
    text: str


class ModernDownloaderApp:
    """Modern GUI application using CustomTkinter."""

    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title("DLive Vault")
        self.root.geometry("900x560")

        # Set minimum window size so the content fits on macOS screens
        self.root.minsize(760, 500)
        
        self.downloader = DLiveDownloader()

        self.broadcast: Optional[Broadcast] = None
        self.variant_items: list[VariantDisplay] = []
        self.broadcast_items: list[Broadcast] = []

        self.status_var = ctk.StringVar()
        self.output_dir_var = ctk.StringVar(value=str(Path.home() / "Downloads"))
        self.channel_name = "uzayzuhal"

        self.progress_queue: "queue.Queue[tuple]" = queue.Queue()
        self.downloading = False
        self.loading_variants = False
        self.loading_broadcasts = False
        self.retry_job: Optional[str] = None

        self._build_layout()
        self.root.after(100, self._process_queue)
        self.root.after(200, self.refresh_broadcasts)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        # Configure grid
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        # Main frame with padding
        main_frame = ctk.CTkFrame(self.root, corner_radius=12)
        main_frame.grid(row=0, column=0, padx=16, pady=16, sticky="nsew")
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(main_frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=6, pady=(8, 10))
        header.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(
            header,
            text="🚀 DLive Vault",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.grid(row=0, column=0, sticky="w")

        subtitle_label = ctk.CTkLabel(
            header,
            text="DLive VOD'larını yüksek kalitede indirin",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        subtitle_label.grid(row=1, column=0, sticky="w", pady=(2, 0))

        # Body split into two columns to avoid an overly tall window
        body_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        body_frame.grid(row=1, column=0, sticky="nsew")
        body_frame.grid_columnconfigure(0, weight=1)
        body_frame.grid_columnconfigure(1, weight=1)
        body_frame.grid_rowconfigure(0, weight=1)

        # Broadcast list section (left column)
        broadcasts_card = ctk.CTkFrame(body_frame, corner_radius=10, fg_color=("gray90", "gray20"))
        broadcasts_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 4))
        broadcasts_card.grid_columnconfigure(0, weight=1)
        broadcasts_card.grid_rowconfigure(1, weight=1)

        broadcasts_label = ctk.CTkLabel(
            broadcasts_card,
            text=f"📺 {self.channel_name} - Geçmiş Yayınlar",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        broadcasts_label.grid(row=0, column=0, sticky="w", padx=14, pady=(12, 4))

        self.broadcast_frame = ctk.CTkScrollableFrame(
            broadcasts_card,
            fg_color="transparent"
        )
        self.broadcast_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.broadcast_frame.grid_columnconfigure(0, weight=1)
        self.selected_broadcast = ctk.IntVar(value=-1)
        self.broadcast_buttons: list[ctk.CTkRadioButton] = []
        self.broadcast_placeholder = ctk.CTkLabel(
            self.broadcast_frame,
            text="Yayınlar otomatik yükleniyor...",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.broadcast_placeholder.grid(row=0, column=0, sticky="w", padx=10, pady=6)

        # Quality selection and controls (right column)
        controls_card = ctk.CTkFrame(body_frame, corner_radius=10, fg_color=("gray90", "gray20"))
        controls_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 4))
        controls_card.grid_columnconfigure(0, weight=1)
        controls_card.grid_rowconfigure(1, weight=1)

        quality_label = ctk.CTkLabel(
            controls_card,
            text="⚙️ Kalite Seçenekleri",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        quality_label.grid(row=0, column=0, sticky="w", padx=14, pady=(12, 4))

        self.variant_frame = ctk.CTkScrollableFrame(
            controls_card,
            fg_color="transparent"
        )
        self.variant_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        self.variant_frame.grid_columnconfigure(0, weight=1)
        
        # Will be populated with radio buttons
        self.selected_variant = ctk.IntVar(value=-1)
        self.variant_buttons = []
        self.variant_placeholder = ctk.CTkLabel(
            self.variant_frame,
            text="Önce bir yayın seçin.",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.variant_placeholder.grid(row=0, column=0, sticky="w", padx=10, pady=6)

        # Output directory selection
        output_frame = ctk.CTkFrame(controls_card, fg_color="transparent")
        output_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 8))
        output_frame.grid_columnconfigure(0, weight=1)

        output_label = ctk.CTkLabel(
            output_frame,
            text="📁 İndirme klasörü",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        output_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))

        output_entry = ctk.CTkEntry(output_frame, textvariable=self.output_dir_var, height=36)
        output_entry.grid(row=1, column=0, sticky="ew")

        choose_button = ctk.CTkButton(
            output_frame,
            text="Seç",
            command=self.choose_directory,
            width=90,
            height=36,
            corner_radius=8
        )
        choose_button.grid(row=1, column=1, padx=(8, 0))

        # Progress Section
        progress_frame = ctk.CTkFrame(controls_card, fg_color="transparent")
        progress_frame.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 6))
        progress_frame.grid_columnconfigure(0, weight=1)

        self.progress = ctk.CTkProgressBar(progress_frame, height=18)
        self.progress.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.progress.set(0)

        self.status_label = ctk.CTkLabel(
            progress_frame,
            textvariable=self.status_var,
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.status_label.grid(row=1, column=0, sticky="w")

        # Download Button
        self.download_button = ctk.CTkButton(
            controls_card,
            text="⬇️ İndir",
            command=self.start_download,
            state="disabled",
            height=46,
            font=ctk.CTkFont(size=16, weight="bold"),
            corner_radius=10,
            fg_color="#FFD700",
            hover_color="#FFA500",
            text_color="#1a1a1a"
        )
        self.download_button.grid(row=4, column=0, sticky="ew", padx=12, pady=(4, 12))

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------
    def refresh_broadcasts(self) -> None:
        if self.downloading or self.loading_broadcasts:
            return
        self._cancel_retry()
        self.loading_broadcasts = True
        self._set_status("🔄 Yayınlar yükleniyor...")
        self._show_broadcast_placeholder("Yayınlar yükleniyor...")
        thread = threading.Thread(target=self._fetch_broadcasts_worker, daemon=True)
        thread.start()

    def _fetch_broadcasts_worker(self) -> None:
        try:
            broadcasts = self.downloader.list_recent_broadcasts(self.channel_name, first=20)
            self.progress_queue.put(("broadcasts_loaded", broadcasts))
        except Exception as exc:
            self.progress_queue.put(("error", f"Yayın listesi alınamadı: {exc}"))
        finally:
            self.loading_broadcasts = False

    def _on_broadcast_selected(self) -> None:
        if self.downloading or self.loading_variants:
            return
        idx = self.selected_broadcast.get()
        if idx < 0 or idx >= len(self.broadcast_items):
            return
        broadcast = self.broadcast_items[idx]
        self.broadcast = None
        self.variant_items = []
        self._clear_variants("Kaliteler alınıyor...")
        self.download_button.configure(state="disabled", text="⬇️ İndir")
        self._set_status("🔄 Kaliteler alınıyor...")
        self.loading_variants = True
        thread = threading.Thread(target=self._fetch_variants_worker, args=(broadcast,), daemon=True)
        thread.start()

    def _fetch_variants_worker(self, broadcast: Broadcast) -> None:
        try:
            variants = self.downloader.list_variants(broadcast.playback_url)
            self.progress_queue.put(("variants_loaded", broadcast, variants))
        except (DLiveAPIError, PlaylistError, ValueError) as exc:
            self.progress_queue.put(("error", str(exc)))
        except Exception as exc:  # pragma: no cover - defensive
            self.progress_queue.put(("error", f"Kalite listesi alınamadı: {exc}"))
        finally:
            self.loading_variants = False

    def choose_directory(self) -> None:
        if self.downloading:
            return
        current = Path(self.output_dir_var.get()).expanduser()
        initialdir = current if current.exists() else Path.home()
        try:
            selection = ctk.filedialog.askdirectory(initialdir=str(initialdir))
        except Exception:
            try:
                from tkinter import filedialog as tk_filedialog  # type: ignore
                selection = tk_filedialog.askdirectory(initialdir=str(initialdir))
            except Exception as exc:
                logger.error("Klasör seçici açılamadı: %s", exc)
                return
        if selection:
            self.output_dir_var.set(selection)

    def start_download(self) -> None:
        if self.downloading or not self.broadcast:
            return
        
        selected_idx = self.selected_variant.get()
        if selected_idx < 0 or selected_idx >= len(self.variant_items):
            messagebox.showinfo("Bilgi", "Lütfen bir kalite seçin.")
            return
        
        variant = self.variant_items[selected_idx].variant

        output_dir = Path(self.output_dir_var.get()).expanduser()
        if not output_dir.exists():
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                messagebox.showerror("Hata", f"Klasör oluşturulamadı: {exc}")
                return

        self.downloading = True
        self.download_button.configure(state="disabled", text="İndiriliyor...")
        self.progress.set(0)
        self._set_status("⬇️ İndirme başladı...")

        thread = threading.Thread(
            target=self._download_worker,
            args=(self.broadcast, variant, output_dir),
            daemon=True,
        )
        thread.start()

    def _download_worker(self, broadcast: Broadcast, variant: StreamVariant, output_dir: Path) -> None:
        try:
            def callback(completed: int, total: int, stage: str) -> None:
                self.progress_queue.put(("progress", completed, total, stage))

            output = self.downloader.download_variant(
                broadcast=broadcast,
                variant=variant,
                output_directory=output_dir,
                progress_callback=callback,
            )
            self.progress_queue.put(("done", str(output)))
        except (DLiveAPIError, PlaylistError, ValueError) as exc:
            self.progress_queue.put(("error", str(exc)))
        except Exception as exc:  # pragma: no cover - fallback
            self.progress_queue.put(("error", f"İndirme hatası: {exc}"))

    # ------------------------------------------------------------------
    # Queue / progress handling
    # ------------------------------------------------------------------
    def _process_queue(self) -> None:
        try:
            while True:
                item = self.progress_queue.get_nowait()
                event = item[0]
                if event == "broadcasts_loaded":
                    self._handle_broadcasts_loaded(item[1])
                elif event == "variants_loaded":
                    self._handle_loaded(item[1], item[2])
                elif event == "progress":
                    self._handle_progress(item[1], item[2], item[3])
                elif event == "done":
                    self._handle_done(item[1])
                elif event == "error":
                    self._handle_error(item[1])
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._process_queue)

    def _handle_broadcasts_loaded(self, broadcasts: list[Broadcast]) -> None:
        self._cancel_retry()
        self.broadcast_items = broadcasts
        self.selected_broadcast.set(-1)
        for btn in self.broadcast_buttons:
            btn.destroy()
        self.broadcast_buttons.clear()
        self.broadcast = None

        if not self.broadcast_items:
            self._show_broadcast_placeholder("Bu kanal için geçmiş yayın bulunamadı.")
            self._clear_variants("Önce bir yayın seçin.")
            self.download_button.configure(state="disabled", text="⬇️ İndir")
            self._set_status("⚠️ Yayın bulunamadı")
            return

        self._hide_broadcast_placeholder()

        for idx, bcast in enumerate(self.broadcast_items):
            created_str = ""
            if bcast.created_at_ms:
                dt = datetime.fromtimestamp(bcast.created_at_ms / 1000)
                created_str = dt.strftime("%d %b %Y %H:%M")
            duration_str = ""
            if bcast.duration_seconds:
                mins, secs = divmod(bcast.duration_seconds, 60)
                hrs, mins = divmod(mins, 60)
                duration_str = f" · {int(hrs):02}:{int(mins):02}:{int(secs):02}"
            label = f"{bcast.title}\n{created_str}{duration_str}"
            btn = ctk.CTkRadioButton(
                self.broadcast_frame,
                text=label,
                variable=self.selected_broadcast,
                value=idx,
                font=ctk.CTkFont(size=12),
                radiobutton_width=20,
                radiobutton_height=20,
                command=self._on_broadcast_selected
            )
            btn.grid(row=idx, column=0, sticky="ew", padx=10, pady=6)
            self.broadcast_buttons.append(btn)

        if self.broadcast_items:
            self.selected_broadcast.set(0)
            self._on_broadcast_selected()
        self._set_status("✅ Yayın listesi yüklendi")

    def _clear_variants(self, placeholder: Optional[str] = None) -> None:
        for btn in self.variant_buttons:
            btn.destroy()
        self.variant_buttons.clear()
        self.selected_variant.set(-1)
        self._show_variant_placeholder(placeholder or "Önce bir yayın seçin.")

    def _handle_loaded(self, broadcast: Broadcast, variants: list[StreamVariant]) -> None:
        self.broadcast = broadcast
        self.variant_items = [
            VariantDisplay(v, v.display_name(broadcast.duration_seconds)) for v in variants
        ]

        self._clear_variants()
        self._hide_variant_placeholder()
        for idx, item in enumerate(self.variant_items):
            btn = ctk.CTkRadioButton(
                self.variant_frame,
                text=item.text,
                variable=self.selected_variant,
                value=idx,
                font=ctk.CTkFont(size=12),
                radiobutton_width=20,
                radiobutton_height=20
            )
            btn.grid(row=idx, column=0, sticky="w", padx=10, pady=5)
            self.variant_buttons.append(btn)

        if not self.variant_items:
            self.download_button.configure(state="disabled", text="⬇️ İndir")
            self._show_variant_placeholder("Bu yayın için kalite bulunamadı.")
            self._set_status("⚠️ Kalite bulunamadı")
            return

        if self.variant_items:
            self.selected_variant.set(0)

        self.download_button.configure(state="normal", text="⬇️ İndir")
        self._set_status(f"✅ {broadcast.creator_name} - {broadcast.title}")

    def _handle_progress(self, completed: int, total: int, stage: str) -> None:
        if total <= 0:
            return
        percent = completed / total
        self.progress.set(percent)
        stage_texts = {
            "segments": "📥 Parçalar indiriliyor",
            "merge": "🔧 Dosya birleştiriliyor",
            "remux": "📦 MP4 hazırlanıyor",
        }
        stage_text = stage_texts.get(stage, "⌛ İşleniyor")
        self._set_status(f"{stage_text}: {int(percent * 100)}%")

    def _handle_done(self, output: str) -> None:
        self._set_status("✅ İndirme tamamlandı!")
        self.progress.set(1.0)
        self.download_button.configure(state="normal", text="⬇️ İndir")
        self.downloading = False
        messagebox.showinfo("Tamamlandı", f"Dosya kaydedildi:\n{output}")

    def _handle_error(self, message: str) -> None:
        self._set_status("❌ Hata oluştu")
        self.progress.set(0)
        self.download_button.configure(
            state="normal" if self.broadcast else "disabled",
            text="⬇️ İndir"
        )
        was_downloading = self.downloading
        self.downloading = False

        if not self.broadcast_items:
            self._show_broadcast_placeholder("Yayınlar alınamadı, tekrar denenecek...")
            self._clear_variants("Yayın listesi bekleniyor.")
            self._schedule_broadcast_retry()

        show_dialog = was_downloading or self.broadcast is not None or bool(self.broadcast_items)
        if show_dialog:
            messagebox.showerror("Hata", message)
        else:
            logger.error("Başlatma hatası: %s", message)

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)

    def _schedule_broadcast_retry(self, delay_ms: int = 3500) -> None:
        if self.loading_broadcasts:
            return
        if self.retry_job:
            self.root.after_cancel(self.retry_job)
        self.retry_job = self.root.after(delay_ms, self.refresh_broadcasts)

    def _cancel_retry(self) -> None:
        if self.retry_job:
            self.root.after_cancel(self.retry_job)
            self.retry_job = None

    def _show_broadcast_placeholder(self, text: str) -> None:
        if self.broadcast_placeholder and self.broadcast_placeholder.winfo_exists():
            self.broadcast_placeholder.configure(text=text)
            self.broadcast_placeholder.grid()
        else:
            self.broadcast_placeholder = ctk.CTkLabel(
                self.broadcast_frame,
                text=text,
                font=ctk.CTkFont(size=12),
                text_color="gray"
            )
            self.broadcast_placeholder.grid(row=0, column=0, sticky="w", padx=10, pady=6)

    def _hide_broadcast_placeholder(self) -> None:
        if self.broadcast_placeholder and self.broadcast_placeholder.winfo_exists():
            self.broadcast_placeholder.grid_remove()

    def _show_variant_placeholder(self, text: str) -> None:
        if self.variant_placeholder and self.variant_placeholder.winfo_exists():
            self.variant_placeholder.configure(text=text)
            self.variant_placeholder.grid()
        else:
            self.variant_placeholder = ctk.CTkLabel(
                self.variant_frame,
                text=text,
                font=ctk.CTkFont(size=12),
                text_color="gray"
            )
            self.variant_placeholder.grid(row=0, column=0, sticky="w", padx=10, pady=6)

    def _hide_variant_placeholder(self) -> None:
        if self.variant_placeholder and self.variant_placeholder.winfo_exists():
            self.variant_placeholder.grid_remove()


def run() -> None:
    """Run the modern GUI application."""
    root = ctk.CTk()
    
    # Set app icon if available
    try:
        icon_path = Path(__file__).parent.parent / "packaging" / "macos" / "icon.icns"
        if icon_path.exists():
            root.iconbitmap(str(icon_path))
    except:
        pass  # Icon not critical
    
    ModernDownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":  # pragma: no cover
    run()
