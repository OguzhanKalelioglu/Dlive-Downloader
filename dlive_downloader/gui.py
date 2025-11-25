"""Tkinter based graphical interface for the DLive downloader."""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from tkinter import END, E, N, S, Tk, VERTICAL, W, Button, Entry, Frame, Label, Listbox, Scrollbar, StringVar, ttk, filedialog, messagebox

from .client import Broadcast, DLiveAPIError, DLiveDownloader, PlaylistError, StreamVariant
from .utils import extract_permlink


@dataclass
class VariantDisplay:
    variant: StreamVariant
    text: str


class DownloaderApp:
    """Encapsulates the Tkinter GUI application."""

    def __init__(self, root: Tk):
        self.root = root
        self.root.title("DLive Downloader")
        self.downloader = DLiveDownloader()

        self.broadcast: Optional[Broadcast] = None
        self.variant_items: list[VariantDisplay] = []

        self.url_var = StringVar()
        self.status_var = StringVar()
        self.output_dir_var = StringVar(value=str(Path.home() / "Downloads"))

        self.progress_queue: "queue.Queue[tuple]" = queue.Queue()
        self.downloading = False

        self._build_layout()
        self.root.after(100, self._process_queue)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        main_frame = Frame(self.root, padx=12, pady=12)
        main_frame.grid(column=0, row=0, sticky=(N, S, E, W))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # URL input
        Label(main_frame, text="DLive VOD URL").grid(column=0, row=0, sticky=W)
        url_entry = Entry(main_frame, textvariable=self.url_var, width=50)
        url_entry.grid(column=0, row=1, columnspan=2, sticky=(E, W), pady=(0, 6))
        url_entry.focus()

        self.fetch_button = Button(main_frame, text="Bilgileri Getir", command=self.fetch_info)
        self.fetch_button.grid(column=2, row=1, padx=(6, 0))

        # Output directory
        Label(main_frame, text="İndirme klasörü").grid(column=0, row=2, sticky=W)
        output_entry = Entry(main_frame, textvariable=self.output_dir_var, width=50)
        output_entry.grid(column=0, row=3, columnspan=2, sticky=(E, W), pady=(0, 6))
        Button(main_frame, text="Seç", command=self.choose_directory).grid(column=2, row=3, padx=(6, 0))

        # Variant list
        Label(main_frame, text="Kalite seçenekleri").grid(column=0, row=4, sticky=W)
        list_frame = Frame(main_frame)
        list_frame.grid(column=0, row=5, columnspan=3, sticky=(E, W))
        list_frame.columnconfigure(0, weight=1)

        self.variant_list = Listbox(list_frame, height=6, exportselection=False)
        self.variant_list.grid(column=0, row=0, sticky=(E, W))
        scrollbar = Scrollbar(list_frame, orient=VERTICAL, command=self.variant_list.yview)
        scrollbar.grid(column=1, row=0, sticky=(N, S))
        self.variant_list.config(yscrollcommand=scrollbar.set)

        # Progress bar and status
        self.progress = ttk.Progressbar(main_frame, maximum=100, mode="determinate")
        self.progress.grid(column=0, row=6, columnspan=3, sticky=(E, W), pady=(12, 0))

        self.status_label = Label(main_frame, textvariable=self.status_var)
        self.status_label.grid(column=0, row=7, columnspan=3, sticky=(W), pady=(6, 0))

        # Action buttons
        self.download_button = Button(main_frame, text="İndir", command=self.start_download, state="disabled")
        self.download_button.grid(column=0, row=8, columnspan=3, pady=(12, 0))

        for child in main_frame.winfo_children():
            child.grid_configure(padx=4, pady=4)

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------
    def fetch_info(self) -> None:
        if self.downloading:
            return
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Uyarı", "Lütfen bir DLive VOD bağlantısı girin.")
            return
        self._set_status("Bilgiler alınıyor...")
        self.fetch_button.config(state="disabled")
        thread = threading.Thread(target=self._fetch_worker, args=(url,), daemon=True)
        thread.start()

    def _fetch_worker(self, url: str) -> None:
        try:
            permlink = extract_permlink(url)
            broadcast = self.downloader.fetch_broadcast(permlink)
            variants = self.downloader.list_variants(broadcast.playback_url)
            self.progress_queue.put(("loaded", broadcast, variants))
        except (ValueError, DLiveAPIError, PlaylistError) as exc:
            self.progress_queue.put(("error", str(exc)))
        except Exception as exc:  # pragma: no cover - defensive fallback
            self.progress_queue.put(("error", f"Beklenmeyen hata: {exc}"))

    def choose_directory(self) -> None:
        if self.downloading:
            return
        current = Path(self.output_dir_var.get()).expanduser()
        directory = filedialog.askdirectory(initialdir=current)
        if directory:
            self.output_dir_var.set(directory)

    def start_download(self) -> None:
        if self.downloading or not self.broadcast:
            return
        try:
            selection = self.variant_list.curselection()
            if not selection:
                messagebox.showinfo("Bilgi", "Lütfen bir kalite seçin.")
                return
            variant = self.variant_items[selection[0]].variant
        except IndexError:
            messagebox.showerror("Hata", "Kalite seçimi geçersiz.")
            return

        output_dir = Path(self.output_dir_var.get()).expanduser()
        if not output_dir.exists():
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                messagebox.showerror("Hata", f"Klasör oluşturulamadı: {exc}")
                return

        self.downloading = True
        self.download_button.config(state="disabled")
        self.fetch_button.config(state="disabled")
        self.progress.config(value=0, maximum=100)
        self._set_status("İndirme başladı...")

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
                if event == "loaded":
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

    def _handle_loaded(self, broadcast: Broadcast, variants: list[StreamVariant]) -> None:
        self.broadcast = broadcast
        self.variant_items = [
            VariantDisplay(v, v.display_name(broadcast.duration_seconds)) for v in variants
        ]
        self.variant_list.delete(0, END)
        for item in self.variant_items:
            self.variant_list.insert(END, item.text)
        if self.variant_items:
            self.variant_list.select_set(0)
        self.download_button.config(state="normal")
        self.fetch_button.config(state="normal")
        self._set_status(f"{broadcast.creator_name} - {broadcast.title}")

    def _handle_progress(self, completed: int, total: int, stage: str) -> None:
        if total <= 0:
            return
        percent = int((completed / total) * 100)
        self.progress.config(maximum=100, value=percent)
        stage_texts = {
            "segments": "Parçalar indiriliyor",
            "merge": "Dosya birleştiriliyor",
            "remux": "MP4 hazırlanıyor",
        }
        stage_text = stage_texts.get(stage, "İşleniyor")
        self._set_status(f"{stage_text}: %{percent}")

    def _handle_done(self, output: str) -> None:
        self._set_status("İndirme tamamlandı")
        self.progress.config(value=100)
        self.download_button.config(state="normal")
        self.fetch_button.config(state="normal")
        self.downloading = False
        messagebox.showinfo("Tamamlandı", f"Dosya kaydedildi:\n{output}")

    def _handle_error(self, message: str) -> None:
        self._set_status("Hata oluştu")
        self.progress.config(value=0)
        self.download_button.config(state="normal" if self.broadcast else "disabled")
        self.fetch_button.config(state="normal")
        self.downloading = False
        messagebox.showerror("Hata", message)

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)


def run() -> None:
    root = Tk()
    style = ttk.Style()
    if "clam" in style.theme_names():
        style.theme_use("clam")
    DownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":  # pragma: no cover
    run()
