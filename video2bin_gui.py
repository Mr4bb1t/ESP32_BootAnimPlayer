import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import cv2
import numpy as np
import zlib
import struct
import os
import threading
from PIL import Image, ImageTk

class VideoConverterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("R4BB1T Boot Anim Converter (XOR Delta)")
        self.root.geometry("600x550")
        
        self.video_path = ""
        self.preview_frame = None
        
        # UI Setup
        self.setup_ui()
        
    def setup_ui(self):
        frame = ttk.Frame(self.root, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        
        # File selection
        ttk.Label(frame, text="Video File:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.lbl_file = ttk.Label(frame, text="No file selected", width=50)
        self.lbl_file.grid(row=0, column=1, pady=5)
        ttk.Button(frame, text="Browse", command=self.browse_file).grid(row=0, column=2, padx=5)
        
        # Resolution
        ttk.Label(frame, text="Resolution:").grid(row=1, column=0, sticky=tk.W, pady=5)
        res_frame = ttk.Frame(frame)
        res_frame.grid(row=1, column=1, sticky=tk.W)
        self.res_var = tk.StringVar(value="128x160")
        ttk.Entry(res_frame, textvariable=self.res_var, width=10).pack(side=tk.LEFT)
        ttk.Label(res_frame, text="(Width x Height)").pack(side=tk.LEFT, padx=5)
        
        # FPS
        ttk.Label(frame, text="Target FPS:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.fps_var = tk.IntVar(value=15)
        ttk.Entry(frame, textvariable=self.fps_var, width=10).grid(row=2, column=1, sticky=tk.W)
        
        # Byte Swap Checkbox
        self.swap_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Swap Bytes (Big Endian)", variable=self.swap_var).grid(row=3, column=1, sticky=tk.W, pady=5)
        
        # Preview Canvas
        self.canvas = tk.Canvas(frame, width=128, height=160, bg="black")
        self.canvas.grid(row=4, column=0, columnspan=3, pady=10)
        
        # Progress
        self.progress = ttk.Progressbar(frame, orient="horizontal", length=400, mode="determinate")
        self.progress.grid(row=5, column=0, columnspan=3, pady=10)
        
        self.lbl_status = ttk.Label(frame, text="Ready")
        self.lbl_status.grid(row=6, column=0, columnspan=3)
        
        # Convert Button
        self.btn_convert = ttk.Button(frame, text="Convert to .BIN", command=self.start_conversion)
        self.btn_convert.grid(row=7, column=0, columnspan=3, pady=10)
        
    def browse_file(self):
        self.video_path = filedialog.askopenfilename(filetypes=[("Video files", "*.mp4 *.avi *.gif *.mov")])
        if self.video_path:
            self.lbl_file.config(text=os.path.basename(self.video_path))
            self.show_preview()
            
    def show_preview(self):
        cap = cv2.VideoCapture(self.video_path)
        ret, frame = cap.read()
        cap.release()
        
        if ret:
            res = self.res_var.get().split("x")
            w, h = int(res[0]), int(res[1])
            frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_NEAREST)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame)
            self.preview_frame = ImageTk.PhotoImage(img)
            self.canvas.config(width=w, height=h)
            self.canvas.create_image(0, 0, anchor=tk.NW, image=self.preview_frame)
            
    def rgb_to_rgb565(self, img, swap_bytes):
        # r: 5 bits, g: 6 bits, b: 5 bits
        r = (img[:, :, 0] >> 3).astype(np.uint16)
        g = (img[:, :, 1] >> 2).astype(np.uint16)
        b = (img[:, :, 2] >> 3).astype(np.uint16)
        
        rgb565 = (r << 11) | (g << 5) | b
        
        if swap_bytes:
            # Swap the two bytes of each 16-bit pixel
            rgb565 = ((rgb565 & 0x00FF) << 8) | ((rgb565 & 0xFF00) >> 8)
            
        return rgb565.astype(np.uint16)
        
    def start_conversion(self):
        if not self.video_path:
            messagebox.showerror("Error", "Please select a video file first.")
            return
            
        save_path = filedialog.asksaveasfilename(defaultextension=".bin", filetypes=[("BIN files", "*.bin")])
        if not save_path:
            return
            
        self.btn_convert.config(state=tk.DISABLED)
        thread = threading.Thread(target=self.convert, args=(save_path,))
        thread.start()
        
    def convert(self, save_path):
        try:
            res = self.res_var.get().split("x")
            target_w, target_h = int(res[0]), int(res[1])
            target_fps = self.fps_var.get()
            swap_bytes = self.swap_var.get()
            
            cap = cv2.VideoCapture(self.video_path)
            orig_fps = cap.get(cv2.CAP_PROP_FPS)
            frame_skip = int(round(orig_fps / target_fps)) if orig_fps > target_fps else 1
            if frame_skip < 1: frame_skip = 1
            
            frames_rgb565 = []
            
            self.lbl_status.config(text="Extracting frames...")
            
            if self.video_path.lower().endswith('.gif'):
                # Use PIL for GIFs to avoid OpenCV ghosting/transparency bugs
                from PIL import ImageSequence
                gif = Image.open(self.video_path)
                for i, frame_img in enumerate(ImageSequence.Iterator(gif)):
                    if i % frame_skip == 0:
                        frame_img = frame_img.convert("RGBA")
                        # Handle transparency by pasting on black background
                        bg = Image.new("RGBA", frame_img.size, (0, 0, 0, 255))
                        bg.paste(frame_img, mask=frame_img)
                        frame = np.array(bg.convert("RGB"))
                        frame = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
                        # Clean up near-black noise
                        frame[frame < 8] = 0
                        frames_rgb565.append(self.rgb_to_rgb565(frame, swap_bytes))
            else:
                count = 0
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break
                        
                    if count % frame_skip == 0:
                        frame = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        # Clean up near-black noise
                        frame[frame < 8] = 0
                        frames_rgb565.append(self.rgb_to_rgb565(frame, swap_bytes))
                    count += 1
            cap.release()
            
            total_frames = len(frames_rgb565)
            self.progress["maximum"] = total_frames
            
            self.lbl_status.config(text="Computing XOR deltas and compressing...")
            
            # Compress using Delta XOR
            # Frame n = Frame n XOR Frame n-1 (for n > 0)
            
            compressed_data = bytearray()
            compressor = zlib.compressobj(level=9, wbits=15) # zlib max compression
            
            prev_frame_bytes = np.zeros((target_h, target_w), dtype=np.uint16).tobytes()
            
            for i, f in enumerate(frames_rgb565):
                curr_frame_bytes = f.tobytes()
                
                # XOR delta with previous frame
                delta = np.bitwise_xor(
                    np.frombuffer(curr_frame_bytes, dtype=np.uint8),
                    np.frombuffer(prev_frame_bytes, dtype=np.uint8)
                ).tobytes()
                
                compressed_data.extend(compressor.compress(delta))
                prev_frame_bytes = curr_frame_bytes
                
                self.progress["value"] = i + 1
                self.root.update_idletasks()
                
            compressed_data.extend(compressor.flush())
            
            # Create header
            magic = b'R4BT'
            version = 1
            frame_size = target_w * target_h * 2
            comp_size = len(compressed_data)
            
            header = struct.pack('<4sBHHBHII', 
                magic, version, target_w, target_h, target_fps, 
                total_frames, frame_size, comp_size)
                
            with open(save_path, 'wb') as f:
                f.write(header)
                f.write(compressed_data)
                
            # Compute savings
            raw_size = total_frames * frame_size
            savings = (1.0 - (comp_size / raw_size)) * 100
                
            self.lbl_status.config(text=f"Done! Saved {savings:.1f}% space (Size: {comp_size//1024}KB)")
            messagebox.showinfo("Success", f"Animation saved to:\n{save_path}\n\nSize: {comp_size//1024}KB (Saved {savings:.1f}%)")
            
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.lbl_status.config(text="Error occurred.")
        finally:
            self.btn_convert.config(state=tk.NORMAL)
            self.progress["value"] = 0

if __name__ == "__main__":
    root = tk.Tk()
    app = VideoConverterGUI(root)
    root.mainloop()
