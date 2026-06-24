import cv2
import numpy as np
import zlib
import struct
import argparse
import sys
import os
import threading
from PIL import Image, ImageSequence

def play_bin(filepath):
    try:
        with open(filepath, 'rb') as f:
            header_data = f.read(20)
            magic, version, w, h, fps, total_frames, f_size, c_size = struct.unpack("<4sBHHBHII", header_data)
            
            if magic != b"R4BT":
                raise Exception("Formato invalido! Magic (R4BT) nao encontrado.")
                
            comp_data = f.read()
            
        print(f"Lendo BIN: {w}x{h} @ {fps}fps | {total_frames} frames")
        raw_data = zlib.decompress(comp_data)
        
        frame_bytes = w * h * 2
        
        for i in range(total_frames):
            start = i * frame_bytes
            end = start + frame_bytes
            frame_raw = raw_data[start:end]
            
            arr16 = np.frombuffer(frame_raw, dtype='>u2')
            r = ((arr16 >> 11) & 0x1F) * 255 // 31
            g = ((arr16 >> 5) & 0x3F) * 255 // 63
            b = (arr16 & 0x1F) * 255 // 31
            
            img = np.stack((b, g, r), axis=-1).astype(np.uint8)
            img = img.reshape((h, w, 3))
            
            img_show = cv2.resize(img, (w*3, h*3), interpolation=cv2.INTER_NEAREST)
            
            cv2.imshow(f"Preview: {os.path.basename(filepath)}", img_show)
            delay = int(1000 / fps) if fps > 0 else 60
            if cv2.waitKey(delay) & 0xFF == 27:
                break
                
        cv2.destroyAllWindows()
    except Exception as e:
        cv2.destroyAllWindows()
        raise e

def process_video(input_path, output_path, width, height, fps_target, start_sec, duration_sec, max_kb, show_frames, swap_bgr, progress_cb=None):
    extracted_frames = []
    
    is_gif = input_path.lower().endswith('.gif')

    if is_gif:
        # Usar PIL para GIFs (OpenCV tem bugs para separar frames e paletas de GIF)
        img = Image.open(input_path)
        orig_fps = 1000.0 / img.info.get('duration', 100)
        if orig_fps <= 0: orig_fps = 10.0
        fps_ratio = orig_fps / fps_target
        
        frame_count = 0
        orig_frame_idx = 0
        
        for frame in ImageSequence.Iterator(img):
            current_sec = orig_frame_idx / orig_fps
            if start_sec > 0 and current_sec < start_sec:
                orig_frame_idx += 1
                continue
                
            if duration_sec > 0 and (current_sec - start_sec) > duration_sec:
                break
                
            if int(orig_frame_idx / fps_ratio) == frame_count:
                # Converter frame PIL para numpy RGB
                frame_rgb = frame.convert('RGB')
                frame_np = np.array(frame_rgb)
                
                resized = cv2.resize(frame_np, (width, height), interpolation=cv2.INTER_AREA)
                
                if show_frames:
                    # cv2.imshow quer BGR
                    cv2.imshow("Gerando Frames (GIF)...", cv2.cvtColor(resized, cv2.COLOR_RGB2BGR))
                    cv2.waitKey(1)
                
                r = resized[:,:,0].astype(np.uint16)
                g = resized[:,:,1].astype(np.uint16)
                b = resized[:,:,2].astype(np.uint16)
                
                if swap_bgr:
                    r, b = b, r
                
                r5 = (r >> 3) & 0x1F
                g6 = (g >> 2) & 0x3F
                b5 = (b >> 3) & 0x1F
                
                rgb565 = (r5 << 11) | (g6 << 5) | b5
                extracted_frames.append(rgb565.astype('>u2').tobytes())
                
                frame_count += 1
                if progress_cb and frame_count % 5 == 0:
                    progress_cb(frame_count, "Extraindo frames GIF...")
                    
            orig_frame_idx += 1
    else:
        # Usar OpenCV para MP4, AVI, etc.
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            raise Exception(f"Nao foi possivel abrir {input_path}")

        orig_fps = cap.get(cv2.CAP_PROP_FPS)
        if orig_fps <= 0: orig_fps = 30.0
        fps_ratio = orig_fps / fps_target
        
        if start_sec > 0:
            cap.set(cv2.CAP_PROP_POS_MSEC, start_sec * 1000.0)
            
        orig_frame_idx = 0
        frame_count = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            current_sec = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            if duration_sec > 0 and (current_sec - start_sec) > duration_sec:
                break
                
            if int(orig_frame_idx / fps_ratio) == frame_count:
                resized = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
                rgb_frame = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                
                if show_frames:
                    cv2.imshow("Gerando Frames...", resized)
                    cv2.waitKey(1)
                
                r = rgb_frame[:,:,0].astype(np.uint16)
                g = rgb_frame[:,:,1].astype(np.uint16)
                b = rgb_frame[:,:,2].astype(np.uint16)
                
                if swap_bgr:
                    r, b = b, r
                
                r5 = (r >> 3) & 0x1F
                g6 = (g >> 2) & 0x3F
                b5 = (b >> 3) & 0x1F
                
                rgb565 = (r5 << 11) | (g6 << 5) | b5
                extracted_frames.append(rgb565.astype('>u2').tobytes())
                
                frame_count += 1
                if progress_cb and frame_count % 5 == 0:
                    progress_cb(frame_count, "Extraindo frames de Video...")
                    
            orig_frame_idx += 1

        cap.release()

    if show_frames:
        cv2.destroyAllWindows()

    if not extracted_frames:
        raise Exception("Nenhum frame processado.")

    current_frames = extracted_frames.copy()
    max_bytes = max_kb * 1024 if max_kb > 0 else float('inf')
    
    drop_iterations = 0
    while True:
        if progress_cb:
            msg = "Comprimindo (ZLIB)..." if drop_iterations == 0 else f"Otimizando... (Removidos {len(extracted_frames) - len(current_frames)} frames)"
            progress_cb(len(current_frames), msg)
            
        full_data = b"".join(current_frames)
        compressed_data = zlib.compress(full_data, level=9)
        total_size = 20 + len(compressed_data)
        
        if total_size <= max_bytes or len(current_frames) < 5:
            break
            
        drop_count = max(1, int(len(current_frames) * 0.1))
        indices_to_drop = set(np.linspace(0, len(current_frames)-1, drop_count, dtype=int))
        current_frames = [f for i, f in enumerate(current_frames) if i not in indices_to_drop]
        drop_iterations += 1

    final_frame_count = len(current_frames)
    comp_size = len(compressed_data)
    frame_size = width * height * 2

    magic = b"R4BT"
    version = 1
    header = struct.pack("<4sBHHBHII", magic, version, width, height, fps_target, final_frame_count, frame_size, comp_size)

    with open(output_path, "wb") as f:
        f.write(header)
        f.write(compressed_data)
        
    return final_frame_count, final_frame_count * frame_size, comp_size

def run_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.title("TFT Video to Bin Framework")
    root.geometry("450x600")
    root.resizable(False, False)

    def select_input():
        fp = filedialog.askopenfilename(title="Selecionar Video", filetypes=[("Videos", "*.mp4 *.avi *.gif *.mkv")])
        if fp:
            ent_input.delete(0, tk.END)
            ent_input.insert(0, fp)
            out = os.path.splitext(fp)[0] + ".bin"
            ent_output.delete(0, tk.END)
            ent_output.insert(0, out)

    def select_output():
        fp = filedialog.asksaveasfilename(title="Salvar", defaultextension=".bin", filetypes=[("BIN", "*.bin")])
        if fp:
            ent_output.delete(0, tk.END)
            ent_output.insert(0, fp)
            
    def preview():
        fp = filedialog.askopenfilename(title="Abrir BIN", filetypes=[("BIN Animation", "*.bin")])
        if fp:
            try:
                play_bin(fp)
            except Exception as e:
                messagebox.showerror("Erro Preview", str(e))

    def do_convert():
        inp = ent_input.get()
        outp = ent_output.get()
        if not inp or not outp:
            messagebox.showerror("Erro", "Arquivos invalidos.")
            return

        try:
            w, h = int(ent_w.get()), int(ent_h.get())
            fps = int(ent_fps.get())
            start, dur = float(ent_start.get()), float(ent_dur.get())
            max_kb = int(ent_max.get())
            show_f = var_show.get()
            swap_bgr = var_bgr.get()
        except ValueError:
            messagebox.showerror("Erro", "Parametros numericos invalidos.")
            return

        btn_convert.config(state=tk.DISABLED)
        lbl_status.config(text="Iniciando...")

        def task():
            try:
                def cb(fc, msg):
                    lbl_status.config(text=f"{msg} ({fc} frames)")
                
                fc, raw, comp = process_video(inp, outp, w, h, fps, start, dur, max_kb, show_f, swap_bgr, cb)
                
                ratio = (comp / raw) * 100 if raw > 0 else 0
                lbl_status.config(text=f"Pronto! {fc} frames. Comp: {comp/1024:.1f}KB ({ratio:.1f}%)")
                messagebox.showinfo("Sucesso", f"Animacao pronta!\nFrames Finais: {fc}\nTamanho: {comp/1024:.1f} KB")
            except Exception as e:
                lbl_status.config(text="Erro!")
                messagebox.showerror("Erro", str(e))
            finally:
                btn_convert.config(state=tk.NORMAL)

        threading.Thread(target=task, daemon=True).start()

    frm = tk.Frame(root, padx=15, pady=15)
    frm.pack(fill=tk.BOTH, expand=True)

    tk.Label(frm, text="Video/GIF de Entrada:").grid(row=0, column=0, sticky="w")
    ent_input = tk.Entry(frm, width=35)
    ent_input.grid(row=0, column=1, padx=5, pady=5)
    tk.Button(frm, text="Procurar...", command=select_input).grid(row=0, column=2)

    tk.Label(frm, text="Arquivo .BIN:").grid(row=1, column=0, sticky="w")
    ent_output = tk.Entry(frm, width=35)
    ent_output.grid(row=1, column=1, padx=5, pady=5)
    tk.Button(frm, text="Procurar...", command=select_output).grid(row=1, column=2)

    frm_opt = tk.LabelFrame(frm, text="TFT & Otimizacao", padx=10, pady=10)
    frm_opt.grid(row=2, column=0, columnspan=3, sticky="ew", pady=15)

    tk.Label(frm_opt, text="Larg:").grid(row=0, column=0, sticky="w")
    ent_w = tk.Entry(frm_opt, width=6); ent_w.insert(0, "128"); ent_w.grid(row=0, column=1, sticky="w")
    tk.Label(frm_opt, text="Alt:").grid(row=0, column=2, sticky="w")
    ent_h = tk.Entry(frm_opt, width=6); ent_h.insert(0, "160"); ent_h.grid(row=0, column=3, sticky="w")
    tk.Label(frm_opt, text="FPS:").grid(row=0, column=4, sticky="w")
    ent_fps = tk.Entry(frm_opt, width=6); ent_fps.insert(0, "16"); ent_fps.grid(row=0, column=5, sticky="w")

    tk.Label(frm_opt, text="Max Size (KB):").grid(row=1, column=0, columnspan=2, sticky="w", pady=5)
    ent_max = tk.Entry(frm_opt, width=6); ent_max.insert(0, "0"); ent_max.grid(row=1, column=2, sticky="w")
    
    var_bgr = tk.BooleanVar(value=True)
    tk.Checkbutton(frm_opt, text="Inverter Cores R/B (Crucial p/ o R4bb1t TFT)", variable=var_bgr).grid(row=2, column=0, columnspan=6, sticky="w")

    var_show = tk.BooleanVar(value=True)
    tk.Checkbutton(frm_opt, text="Mostrar preview dos frames", variable=var_show).grid(row=3, column=0, columnspan=6, sticky="w")

    frm_time = tk.LabelFrame(frm, text="Corte de Tempo", padx=10, pady=10)
    frm_time.grid(row=4, column=0, columnspan=3, sticky="ew")

    tk.Label(frm_time, text="Inicio (s):").grid(row=0, column=0, sticky="w")
    ent_start = tk.Entry(frm_time, width=8); ent_start.insert(0, "0.0"); ent_start.grid(row=0, column=1, sticky="w")
    tk.Label(frm_time, text="Duracao (s):").grid(row=0, column=2, sticky="w")
    ent_dur = tk.Entry(frm_time, width=8); ent_dur.insert(0, "0.0"); ent_dur.grid(row=0, column=3, sticky="w")

    btn_convert = tk.Button(frm, text="CONVERTER PARA .BIN", command=do_convert, bg="green", fg="white", font=("Arial", 10, "bold"))
    btn_convert.grid(row=5, column=0, columnspan=3, pady=15, sticky="we")

    tk.Button(frm, text="Visualizador/Player de .BIN", command=preview, bg="gray", fg="white").grid(row=6, column=0, columnspan=3, pady=5, sticky="we")

    lbl_status = tk.Label(frm, text="Pronto.", fg="blue")
    lbl_status.grid(row=7, column=0, columnspan=3, pady=10)

    root.mainloop()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        parser = argparse.ArgumentParser()
        parser.add_argument("input")
        parser.add_argument("output")
        parser.add_argument("--width", type=int, default=128)
        parser.add_argument("--height", type=int, default=160)
        parser.add_argument("--fps", type=int, default=16)
        parser.add_argument("--max_kb", type=int, default=0)
        parser.add_argument("--play", action="store_true")
        args = parser.parse_args()
        
        if args.play:
            play_bin(args.input)
        else:
            process_video(args.input, args.output, args.width, args.height, args.fps, 0, 0, args.max_kb, True, True, lambda fc, msg: print(f"\r{msg} {fc}", end=""))
            print("\nFeito!")
    else:
        run_gui()
